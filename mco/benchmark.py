"""``mco.benchmark``: run fixed cases against a model and time them.

A case file is JSON or JSONL. JSON may be a list of cases or an object with a
``"cases"`` list. Each case is::

    {"id": "split-1",
     "input": "3명이야"                  # one utterance, or
     "turns": ["12만원 나왔어", "3명이야"],  # a conversation (last turn is scored)
     "facts": [...], "question": "..."   # or structured input for Model.reason
     "answers": ["..."],                 # optional: accepted answer strings
     "status": "answered",               # optional: expected Status
     "unknown": true}                    # optional: expect unknown/needs_input/rejected

Every case runs in its own fresh session. A case with no expectation is timed
but counted as neither passed nor failed.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import statistics
import time
from typing import Any, Iterable, Mapping, Optional, Sequence, Union

from .errors import InvalidInputError, MCOError
from .model import Model, load
from .result import Result, Status

__all__ = ["BenchmarkCase", "CaseResult", "BenchmarkReport", "benchmark", "load_cases"]

_DECLINED = {Status.UNKNOWN, Status.NEEDS_INPUT, Status.REJECTED}


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    turns: tuple[str, ...] = ()
    facts: tuple[Any, ...] = ()
    question: Optional[str] = None
    answers: tuple[str, ...] = ()
    status: Optional[Status] = None
    unknown: bool = False

    @property
    def structured(self) -> bool:
        return bool(self.facts)

    @property
    def has_expectation(self) -> bool:
        return bool(self.answers) or self.status is not None or self.unknown

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], index: int) -> "BenchmarkCase":
        if not isinstance(data, Mapping):
            raise InvalidInputError(f"case #{index} is not an object")
        case_id = str(data.get("id") or f"case-{index + 1}")
        turns: Sequence[str] = ()
        if "turns" in data:
            turns = data["turns"]
            if isinstance(turns, str) or not isinstance(turns, Sequence) or not turns:
                raise InvalidInputError(f"case {case_id}: 'turns' must be a non-empty list")
        elif "input" in data:
            turns = [data["input"]]
        facts = tuple(data.get("facts") or ())
        question = data.get("question")
        if not turns and not facts and not question:
            raise InvalidInputError(f"case {case_id}: needs 'input', 'turns' or 'facts'/'question'")
        if turns and (facts or question):
            raise InvalidInputError(f"case {case_id}: use either turns/input or facts/question, not both")
        if any(not isinstance(t, str) or not t.strip() for t in turns):
            raise InvalidInputError(f"case {case_id}: every turn must be a non-empty string")
        answers = data.get("answers") or ()
        if isinstance(answers, str):
            answers = (answers,)
        status = data.get("status")
        try:
            status = Status(status) if status is not None else None
        except ValueError as exc:
            raise InvalidInputError(f"case {case_id}: unknown status {status!r}") from exc
        return cls(case_id, tuple(turns), facts, question, tuple(str(a) for a in answers),
                   status, bool(data.get("unknown")))


@dataclass(frozen=True)
class CaseResult:
    id: str
    passed: Optional[bool]
    status: Optional[str]
    answer: str
    elapsed_ms: float
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "passed": self.passed, "status": self.status,
                "answer": self.answer, "elapsed_ms": self.elapsed_ms, "error": self.error}


@dataclass(frozen=True)
class BenchmarkReport:
    model: str
    backend: str
    load_ms: Optional[float]
    cases: tuple[CaseResult, ...] = field(default_factory=tuple)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def scored(self) -> int:
        """Cases that carried an expectation (the denominator of ``accuracy``)."""
        return sum(c.passed is not None for c in self.cases)

    @property
    def passed(self) -> int:
        return sum(c.passed is True for c in self.cases)

    @property
    def errors(self) -> int:
        return sum(c.error is not None for c in self.cases)

    @property
    def accuracy(self) -> Optional[float]:
        return self.passed / self.scored if self.scored else None

    def latency_ms(self) -> dict[str, Optional[float]]:
        times = sorted(c.elapsed_ms for c in self.cases if c.error is None)
        if not times:
            return {"median": None, "p90": None, "max": None, "total": None}
        p90 = times[min(len(times) - 1, int(round(0.9 * (len(times) - 1))))]
        return {"median": round(statistics.median(times), 3), "p90": round(p90, 3),
                "max": round(times[-1], 3), "total": round(sum(times), 3)}

    def to_dict(self) -> dict[str, Any]:
        return {"model": self.model, "backend": self.backend, "load_ms": self.load_ms,
                "total": self.total, "scored": self.scored, "passed": self.passed,
                "errors": self.errors, "accuracy": self.accuracy,
                "statuses": dict(Counter(c.status for c in self.cases if c.status)),
                "latency_ms": self.latency_ms(), "cases": [c.to_dict() for c in self.cases]}

    def summary(self) -> str:
        lat = self.latency_ms()
        score = (f"{self.passed}/{self.scored} passed ({self.accuracy:.1%})" if self.scored
                 else "no scored cases")
        load = f", load {self.load_ms:.1f} ms" if self.load_ms is not None else ""
        return (f"{self.model} [{self.backend}]: {score}, {self.total} case(s), "
                f"{self.errors} error(s), median {lat['median']} ms{load}")


def load_cases(source: Union[str, "os.PathLike[str]", Iterable[Mapping[str, Any]]]) -> list[BenchmarkCase]:
    """Read cases from a JSON/JSONL file or an iterable of mappings."""
    if isinstance(source, (str, os.PathLike)):
        path = Path(source)
        if not path.is_file():
            raise InvalidInputError(f"case file not found: {path}")
        text = path.read_text(encoding="utf-8")
        try:
            if path.suffix == ".jsonl":
                raw: Any = [json.loads(line) for line in text.splitlines() if line.strip()]
            else:
                raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InvalidInputError(f"{path}: invalid JSON ({exc})") from exc
        if isinstance(raw, Mapping):
            raw = raw.get("cases")
        if not isinstance(raw, list):
            raise InvalidInputError(f"{path}: expected a list of cases or an object with 'cases'")
    else:
        raw = list(source)
    cases = [BenchmarkCase.from_mapping(item, i) for i, item in enumerate(raw)]
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise InvalidInputError("case ids must be unique")
    return cases


def _judge(case: BenchmarkCase, result: Result) -> Optional[bool]:
    if not case.has_expectation:
        return None
    checks = []
    if case.answers:
        checks.append(result.answer.strip() in {a.strip() for a in case.answers})
    if case.status is not None:
        checks.append(result.status == case.status)
    if case.unknown:
        checks.append(result.status in _DECLINED)
    return all(checks)


def _run_case(model: Model, case: BenchmarkCase) -> CaseResult:
    start = time.perf_counter()
    try:
        if case.structured or case.question:
            result = model.reason({"facts": list(case.facts), "question": case.question})
        else:
            with model.session() as session:
                for turn in case.turns:
                    result = session.run(turn)
    except MCOError as exc:
        return CaseResult(case.id, False if case.has_expectation else None, None, "",
                          round((time.perf_counter() - start) * 1000, 3), f"{type(exc).__name__}: {exc}")
    elapsed = round((time.perf_counter() - start) * 1000, 3)
    return CaseResult(case.id, _judge(case, result), result.status.value, result.answer, elapsed)


def benchmark(model: Union[Model, str, "os.PathLike[str]"],
              cases: Union[str, "os.PathLike[str]", Iterable[Mapping[str, Any]], Sequence[BenchmarkCase]],
              **load_options: Any) -> BenchmarkReport:
    """Run ``cases`` against ``model`` (a :class:`Model` or a path to load)."""
    if cases and isinstance(cases, Sequence) and not isinstance(cases, (str, bytes)) \
            and all(isinstance(c, BenchmarkCase) for c in cases):
        case_list = list(cases)  # type: ignore[arg-type]
    else:
        case_list = load_cases(cases)  # type: ignore[arg-type]
    owned = not isinstance(model, Model)
    load_ms = None
    if owned:
        start = time.perf_counter()
        model = load(model, **load_options)  # type: ignore[arg-type]
        load_ms = round((time.perf_counter() - start) * 1000, 3)
    elif load_options:
        raise InvalidInputError("load options only apply when benchmark() loads the model")
    assert isinstance(model, Model)
    try:
        results = tuple(_run_case(model, case) for case in case_list)
        return BenchmarkReport(model.info.name or model.info.path, model.backend, load_ms, results)
    finally:
        if owned:
            model.close()
