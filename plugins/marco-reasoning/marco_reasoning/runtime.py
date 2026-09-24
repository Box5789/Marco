"""Deterministic sidecar adapter over the public :mod:`mco` API.

The sidecar deliberately accepts *grounded* premise spans instead of arbitrary
fact strings.  A caller supplies source texts and exact character ranges; this
module extracts the actual premise sentences and refuses invalid ranges before
MARCO sees them.  That keeps LLM interpretation separate from facts that the
reasoner is allowed to trust.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from typing import Any, Mapping, Sequence


VERDICTS = frozenset({
    "verified",
    "contradicted",
    "underdetermined",
    "not_applicable",
    "parse_uncertain",
})

_EXPLICIT_REFUTATION = frozenset({"C", "수치미달", "전제불성립", "무너짐"})
_OUT_OF_SCOPE = frozenset({"B2"})
_PARSE_FAILURE = frozenset({"입력이해실패", "오류"})


def _repo_root() -> Path:
    # .../plugins/marco-reasoning/marco_reasoning/runtime.py -> repository root
    return Path(__file__).resolve().parents[3]


def _plain(value: Any) -> Any:
    """Convert MappingProxyType/tuples/enums in MCO results to JSON data."""
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    if hasattr(value, "value") and isinstance(getattr(value, "value"), str):
        return value.value
    return value


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[`*_~]", "", str(text or "")).strip()).casefold()


def _single_number(text: str) -> str | None:
    values = re.findall(r"(?<![0-9.])-?\d+(?:\.\d+)?(?![0-9.])", str(text or ""))
    return values[0] if len(values) == 1 else None


def _compare_answer(proposed: str, engine: str) -> bool | None:
    """Conservatively compare an LLM answer with MARCO's surface answer.

    Exact normalized text and a single unambiguous numeric value are the only
    equivalences accepted.  Anything richer is returned as ``None`` rather
    than pretending that string similarity proves semantic equivalence.
    """
    if _normal(proposed) == _normal(engine):
        return True
    left, right = _single_number(proposed), _single_number(engine)
    if left is not None and right is not None:
        return float(left) == float(right)
    return None


def _extract_missing(raw: Any, limit: int = 16) -> list[str]:
    """Best-effort compact missing-premise hints from MARCO's unstable raw payload."""
    wanted = {"missing", "slots", "slot_keys", "need", "빈자리", "남은", "남은요건"}
    found: list[str] = []

    def add(value: Any) -> None:
        if len(found) >= limit:
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                if item in (None, "", [], {}):
                    continue
                add(key if isinstance(item, bool) and item else item)
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                add(item)
        elif isinstance(value, (str, int, float)):
            text = str(value).strip()
            if text and text not in found:
                found.append(text)

    def walk(value: Any, depth: int = 0) -> None:
        if depth > 8 or len(found) >= limit:
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key) in wanted:
                    add(item)
                walk(item, depth + 1)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item, depth + 1)

    walk(raw)
    return found[:limit]


def _status(result: Any) -> str:
    value = getattr(result, "status", "unknown")
    return str(getattr(value, "value", value))


def _raw_status(result: Any) -> str | None:
    value = getattr(result, "raw_status", None)
    return str(value) if value is not None else None


def _sidecar_verdict(result: Any) -> tuple[str, str]:
    status, raw = _status(result), _raw_status(result)
    if status in {"answered", "observed"}:
        return "verified", "marco_grounded_result"
    if status == "needs_input":
        return "underdetermined", "marco_needs_more_information"
    if status == "rejected":
        if raw in _OUT_OF_SCOPE:
            return "not_applicable", "marco_out_of_scope"
        if raw in _EXPLICIT_REFUTATION or raw is not None:
            return "contradicted", "marco_rejected_claim"
        return "underdetermined", "marco_rejected_without_refutation_kind"
    if status == "pending_approval":
        return "underdetermined", "marco_requires_approval"
    if raw in _PARSE_FAILURE:
        return "parse_uncertain", "marco_could_not_parse_input"
    return "not_applicable", "marco_has_no_grounded_answer"


def _validate_sources(sources: Sequence[Mapping[str, Any]], spans: Sequence[Mapping[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    indexed: dict[str, str] = {}
    for row in sources:
        source_id, text = row.get("id"), row.get("text")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("every source needs a non-empty string id")
        if source_id in indexed:
            raise ValueError("duplicate source id: %s" % source_id)
        if not isinstance(text, str) or not text:
            raise ValueError("source %s has no text" % source_id)
        indexed[source_id] = text

    facts, grounds = [], []
    for index, row in enumerate(spans):
        source_id, start, end = row.get("source_id"), row.get("start"), row.get("end")
        if source_id not in indexed:
            raise ValueError("fact span %d references unknown source %r" % (index, source_id))
        if type(start) is not int or type(end) is not int:
            raise ValueError("fact span %d start/end must be integers" % index)
        source = indexed[source_id]
        if start < 0 or end <= start or end > len(source):
            raise ValueError("fact span %d is outside source bounds" % index)
        text = source[start:end]
        if not text.strip():
            raise ValueError("fact span %d is blank" % index)
        facts.append(text.strip())
        grounds.append({"source_id": source_id, "start": start, "end": end, "text": text})
    return facts, grounds


class MarcoReasoningService:
    """Thread-safe, read-only adapter that keeps a bounded proof cache."""

    def __init__(self, *, model: Any = None, model_path: str | os.PathLike[str] | None = None,
                 repo_root: str | os.PathLike[str] | None = None, proof_limit: int = 128) -> None:
        self._provided_model = model
        self._model = model
        self._model_path = Path(model_path).expanduser() if model_path else None
        self._root = Path(repo_root).expanduser().resolve() if repo_root else _repo_root()
        self._proof_limit = max(8, int(proof_limit))
        self._proofs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.RLock()

    def _resolve_model_path(self, mco: Any) -> Path:
        if self._model_path is not None:
            return self._model_path.resolve()
        env = os.environ.get("MARCO_MODEL_PATH")
        if env:
            return Path(env).expanduser().resolve()
        preview = self._root / "MARCO-1-preview.mco"
        if preview.is_file():
            return preview
        cache = Path(os.environ.get(
            "MARCO_MODEL_CACHE",
            str(Path.home() / ".cache" / "marco-reasoning" / "MARCO-sidecar.mco"),
        )).expanduser()
        if not cache.is_file():
            cache.parent.mkdir(parents=True, exist_ok=True)
            mco.compile(self._root, cache, name="MARCO-sidecar")
        return cache.resolve()

    def _ensure_model(self) -> Any:
        with self._lock:
            if self._model is not None:
                return self._model
            import mco  # lazy: unit tests can inject a fake model without MARCO installed
            path = self._resolve_model_path(mco)
            self._model = mco.load(path, marco_root=str(self._root), allow_network=False)
            return self._model

    def close(self) -> None:
        with self._lock:
            if self._model is not None and self._model is not self._provided_model:
                close = getattr(self._model, "close", None)
                if callable(close):
                    close()
            self._model = self._provided_model
            self._proofs.clear()

    def _record(self, *, facts: list[str], grounds: list[dict[str, Any]], question: str,
                result: Any, verdict: str, reason: str) -> dict[str, Any]:
        if hasattr(result, "to_dict"):
            public = result.to_dict(include_raw=True)
        else:
            public = {
                "answer": getattr(result, "answer", ""), "status": _status(result),
                "raw_status": _raw_status(result),
                "evidence": _plain(getattr(result, "evidence", [])),
                "trace": _plain(getattr(result, "trace", [])),
                "raw": _plain(getattr(result, "raw", None)),
            }
        public = _plain(public)
        payload = {"facts": facts, "grounds": grounds, "question": question,
                   "result": public, "verdict": verdict, "reason": reason}
        proof_id = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                             default=str).encode("utf-8")).hexdigest()[:24]
        self._proofs[proof_id] = deepcopy(payload)
        self._proofs.move_to_end(proof_id)
        while len(self._proofs) > self._proof_limit:
            self._proofs.popitem(last=False)
        evidence = public.get("evidence") if isinstance(public, Mapping) else []
        trace = public.get("trace") if isinstance(public, Mapping) else []
        missing = _extract_missing(public.get("raw") if isinstance(public, Mapping) else None)
        return {
            "verdict": verdict,
            "engine_status": _status(result),
            "raw_status": _raw_status(result),
            "answer": str(getattr(result, "answer", "") or ""),
            "missing": missing,
            "proof_id": proof_id,
            "evidence_count": len(evidence or []),
            "trace_stages": [str(row.get("stage")) for row in (trace or [])
                             if isinstance(row, Mapping) and row.get("stage")],
            "reason": reason,
        }

    def reason(self, *, sources: Sequence[Mapping[str, Any]], fact_spans: Sequence[Mapping[str, Any]],
               question: str) -> dict[str, Any]:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be a non-empty string")
        facts, grounds = _validate_sources(sources, fact_spans)
        if not facts:
            raise ValueError("at least one grounded fact span is required")
        model = self._ensure_model()
        result = model.reason({"facts": facts, "question": question.strip()})
        verdict, reason = _sidecar_verdict(result)
        with self._lock:
            return self._record(facts=facts, grounds=grounds, question=question.strip(),
                                result=result, verdict=verdict, reason=reason)

    def verify(self, *, sources: Sequence[Mapping[str, Any]], fact_spans: Sequence[Mapping[str, Any]],
               question: str, proposed_answer: str) -> dict[str, Any]:
        if not isinstance(proposed_answer, str) or not proposed_answer.strip():
            raise ValueError("proposed_answer must be a non-empty string")
        facts, grounds = _validate_sources(sources, fact_spans)
        if not facts:
            raise ValueError("at least one grounded fact span is required")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be a non-empty string")
        model = self._ensure_model()
        result = model.reason({"facts": facts, "question": question.strip()})
        base, base_reason = _sidecar_verdict(result)
        comparison = "not_compared"
        if base == "verified":
            same = _compare_answer(proposed_answer, str(getattr(result, "answer", "") or ""))
            if same is True:
                verdict, reason, comparison = "verified", "proposed_answer_matches_marco", "equivalent"
            elif same is False:
                verdict, reason, comparison = "contradicted", "proposed_answer_conflicts_with_marco", "different_scalar"
            else:
                verdict, reason, comparison = "parse_uncertain", "answer_equivalence_not_proven", "unverifiable_equivalence"
        else:
            verdict, reason = base, base_reason
        with self._lock:
            out = self._record(facts=facts, grounds=grounds, question=question.strip(),
                               result=result, verdict=verdict, reason=reason)
        out.update({"proposed_answer": proposed_answer.strip(), "comparison": comparison})
        return out

    def explain(self, proof_id: str, *, include_raw: bool = False) -> dict[str, Any]:
        if not isinstance(proof_id, str) or not proof_id.strip():
            raise ValueError("proof_id must be a non-empty string")
        with self._lock:
            record = deepcopy(self._proofs.get(proof_id))
            if record is not None:
                self._proofs.move_to_end(proof_id)
        if record is None:
            return {"found": False, "proof_id": proof_id, "reason": "proof_not_in_this_server_process"}
        result = record["result"]
        out = {
            "found": True,
            "proof_id": proof_id,
            "verdict": record["verdict"],
            "reason": record["reason"],
            "question": record["question"],
            "facts": record["facts"],
            "grounds": record["grounds"],
            "answer": result.get("answer", ""),
            "engine_status": result.get("status"),
            "raw_status": result.get("raw_status"),
            "evidence": result.get("evidence") or [],
            "trace": result.get("trace") or [],
        }
        if include_raw:
            out["raw"] = result.get("raw")
        return out
