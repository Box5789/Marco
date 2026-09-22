"""Backend-neutral result and input types.

These classes are the stable contract between user code and any backend. A
backend translates its own verdicts and traces into them; user code must never
need to know which backend produced a :class:`Result`.

Stability rules (see ``docs/mco/api.md``):

* Fields are only ever *added*. Existing fields keep their names and types.
* :class:`Status` values are stable strings. New values may be added; code
  should treat an unrecognised status like :attr:`Status.UNKNOWN`.
* ``Result.raw_status``, ``Evidence.detail``, ``TraceStep.detail`` and
  ``Result.raw`` carry backend-specific data and are explicitly *not* stable.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
import json
from types import MappingProxyType
from typing import Any, Optional, Union, overload

from .errors import InvalidInputError

__all__ = [
    "Status",
    "Evidence",
    "EvidenceList",
    "TraceStep",
    "Trace",
    "Result",
    "Fact",
    "ReasoningInput",
]


class Status(str, Enum):
    """What kind of outcome a turn produced.

    ``Status`` is a ``str`` subclass, so ``result.status == "answered"`` works.
    """

    #: The model reached a grounded answer.
    ANSWERED = "answered"
    #: The input was recorded as state (a fact was learned); nothing was asked.
    OBSERVED = "observed"
    #: The model progressed but needs more information to reach its goal.
    NEEDS_INPUT = "needs_input"
    #: No grounded answer exists. The model declines rather than guesses.
    UNKNOWN = "unknown"
    #: The model has positive evidence that the input is out of scope or refuted.
    REJECTED = "rejected"
    #: The model proposed a plan that must be approved before anything runs.
    PENDING_APPROVAL = "pending_approval"

    def __str__(self) -> str:  # print(result.status) -> "answered"
        return self.value

    @property
    def grounded(self) -> bool:
        """True when the answer rests on evidence held by the model."""
        return self in (Status.ANSWERED, Status.OBSERVED)


def _freeze(value: Any) -> Any:
    """Return a read-only deep copy of JSON-like data."""
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return value


def _thaw(value: Any) -> Any:
    """Inverse of :func:`_freeze`, producing plain JSON-serialisable data."""
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    return value


@dataclass(frozen=True)
class Evidence:
    """One piece of support for an answer.

    ``kind`` is a short stable category such as ``"graph_path"``,
    ``"graph_node"``, ``"state_transition"``, ``"definition"``, ``"fact"`` or
    ``"external_source"``. ``text`` is human-readable; ``source`` names where it
    lives inside the model (a graph, an asset, a URL).
    """

    kind: str
    text: str
    source: Optional[str] = None
    score: Optional[float] = None
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "detail", _freeze(self.detail))

    def __str__(self) -> str:
        where = f" @ {self.source}" if self.source else ""
        score = f" ({self.score:g})" if self.score is not None else ""
        return f"[{self.kind}] {self.text}{where}{score}"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "text": self.text, "source": self.source,
                "score": self.score, "detail": _thaw(self.detail)}


@dataclass(frozen=True)
class TraceStep:
    """One stage of the reasoning process (``understand``, ``route``, ...)."""

    stage: str
    summary: str
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "detail", _freeze(self.detail))

    def __str__(self) -> str:
        return f"{self.stage}: {self.summary}"

    def to_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "summary": self.summary, "detail": _thaw(self.detail)}


class _FrozenList(Sequence):
    """Immutable sequence that prints one item per line."""

    __slots__ = ("_items",)
    _item_type: type = object

    def __init__(self, items: Iterable[Any] = ()) -> None:
        items = tuple(items)
        for item in items:
            if not isinstance(item, self._item_type):
                raise TypeError(f"{type(self).__name__} holds {self._item_type.__name__}, "
                                f"got {type(item).__name__}")
        self._items = items

    @overload
    def __getitem__(self, index: int) -> Any: ...
    @overload
    def __getitem__(self, index: slice) -> tuple: ...
    def __getitem__(self, index):  # type: ignore[no-untyped-def]
        return self._items[index]

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._items)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _FrozenList):
            return self._items == other._items
        if isinstance(other, (list, tuple)):
            return self._items == tuple(other)
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._items)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({list(self._items)!r})"

    def __str__(self) -> str:
        if not self._items:
            return "(none)"
        return "\n".join(f"{i}. {item}" for i, item in enumerate(self._items, 1))

    def to_list(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self._items]


class EvidenceList(_FrozenList):
    """The evidence behind a result. Prints one item per line."""

    _item_type = Evidence

    def of_kind(self, kind: str) -> "EvidenceList":
        return EvidenceList(e for e in self if e.kind == kind)


class Trace(_FrozenList):
    """The ordered reasoning steps of a result. Prints one step per line."""

    _item_type = TraceStep

    def stage(self, name: str) -> Optional[TraceStep]:
        """The first step with this stage name, or ``None``."""
        return next((s for s in self if s.stage == name), None)


@dataclass(frozen=True)
class Result:
    """The outcome of one :meth:`Model.run` or :meth:`Model.reason` call."""

    answer: str
    status: Status
    evidence: EvidenceList = field(default_factory=EvidenceList)
    trace: Trace = field(default_factory=Trace)
    input: str = ""
    #: The backend's own verdict label. Not stable across backends/versions.
    raw_status: Optional[str] = None
    #: Name of the backend that produced this result.
    backend: str = ""
    #: The backend's full native payload. Not stable; for debugging only.
    raw: Optional[Mapping[str, Any]] = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.status, Status):
            object.__setattr__(self, "status", Status(self.status))
        if not isinstance(self.evidence, EvidenceList):
            object.__setattr__(self, "evidence", EvidenceList(self.evidence))
        if not isinstance(self.trace, Trace):
            object.__setattr__(self, "trace", Trace(self.trace))
        if self.raw is not None:
            object.__setattr__(self, "raw", _freeze(self.raw))

    @property
    def ok(self) -> bool:
        """True when the answer is grounded (answered or observed)."""
        return self.status.grounded

    def __str__(self) -> str:
        return self.answer

    def to_dict(self, *, include_raw: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "input": self.input, "answer": self.answer, "status": self.status.value,
            "raw_status": self.raw_status, "backend": self.backend,
            "evidence": self.evidence.to_list(), "trace": self.trace.to_list(),
        }
        if include_raw:
            data["raw"] = _thaw(self.raw) if self.raw is not None else None
        return data

    def to_json(self, *, include_raw: bool = False, indent: Optional[int] = 2) -> str:
        return json.dumps(self.to_dict(include_raw=include_raw), ensure_ascii=False,
                          indent=indent, default=str)


@dataclass(frozen=True)
class Fact:
    """A premise given to :meth:`Model.reason`.

    A fact is either a sentence in the model's language (``text``) or a
    structured triple (``subject``/``predicate``/``value``). Which forms a
    backend accepts is listed in ``ModelInfo.capabilities`` as ``"text_facts"``
    and ``"structured_facts"``.
    """

    text: Optional[str] = None
    subject: Optional[str] = None
    predicate: Optional[str] = None
    value: Any = None
    unit: Optional[str] = None
    id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.text is not None:
            if not isinstance(self.text, str) or not self.text.strip():
                raise InvalidInputError("Fact.text must be a non-empty string")
        elif not (self.subject and self.predicate):
            raise InvalidInputError("a Fact needs either text, or subject and predicate")

    @property
    def structured(self) -> bool:
        return self.text is None

    @classmethod
    def coerce(cls, value: Union["Fact", str, Mapping[str, Any]]) -> "Fact":
        if isinstance(value, Fact):
            return value
        if isinstance(value, str):
            return cls(text=value)
        if isinstance(value, Mapping):
            known = {"text", "subject", "predicate", "value", "unit", "id"}
            extra = set(value) - known
            if extra:
                raise InvalidInputError(f"unknown Fact field(s): {sorted(extra)}")
            return cls(**dict(value))
        raise InvalidInputError(f"a fact must be a str, mapping or Fact, got {type(value).__name__}")

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in (("text", self.text), ("subject", self.subject),
                                  ("predicate", self.predicate), ("value", self.value),
                                  ("unit", self.unit), ("id", self.id)) if v is not None}


@dataclass(frozen=True)
class ReasoningInput:
    """Structured input for :meth:`Model.reason`: premises plus an optional question.

    The facts and question are evaluated in a fresh, isolated context; nothing
    leaks into or out of the model's ongoing conversation.
    """

    facts: tuple[Fact, ...] = ()
    question: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "facts", tuple(Fact.coerce(f) for f in self.facts))
        if self.question is not None and (not isinstance(self.question, str) or not self.question.strip()):
            raise InvalidInputError("question must be a non-empty string when given")
        if not self.facts and self.question is None:
            raise InvalidInputError("reasoning input needs at least one fact or a question")

    @classmethod
    def coerce(cls, data: Union["ReasoningInput", Mapping[str, Any], Sequence[Any]]) -> "ReasoningInput":
        """Accept a :class:`ReasoningInput`, a ``{"facts": [...], "question": ...}``
        mapping, or a plain list of facts."""
        if isinstance(data, ReasoningInput):
            return data
        if isinstance(data, Mapping):
            extra = set(data) - {"facts", "question"}
            if extra:
                raise InvalidInputError(f"unknown reasoning input field(s): {sorted(extra)}")
            facts = data.get("facts", ())
            if isinstance(facts, (str, bytes)) or not isinstance(facts, Iterable):
                raise InvalidInputError("'facts' must be a list")
            return cls(facts=tuple(facts), question=data.get("question"))
        if isinstance(data, (str, bytes)):
            raise InvalidInputError("reason() takes structured data; use run() for a single utterance")
        if isinstance(data, Iterable):
            return cls(facts=tuple(data))
        raise InvalidInputError(f"unsupported reasoning input: {type(data).__name__}")

    def to_dict(self) -> dict[str, Any]:
        return {"facts": [f.to_dict() for f in self.facts], "question": self.question}
