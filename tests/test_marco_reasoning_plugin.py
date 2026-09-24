"""Unit tests for the Marco reasoning plugin adapter.

These tests inject a fake MCO model, so they exercise the sidecar contract
without requiring the optional ``mcp`` package or a compiled model.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "marco-reasoning"
if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from marco_reasoning.runtime import MarcoReasoningService


@dataclass
class FakeResult:
    answer: str
    status: str
    raw_status: str | None = None
    evidence: tuple = ()
    trace: tuple = ()
    raw: dict | None = None

    def to_dict(self, *, include_raw=False):
        out = {"answer": self.answer, "status": self.status, "raw_status": self.raw_status,
               "evidence": list(self.evidence), "trace": list(self.trace)}
        if include_raw:
            out["raw"] = self.raw
        return out


class FakeModel:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def reason(self, request):
        self.calls.append(request)
        return self.results.pop(0)


def grounded(text="민수는 사과가 5개 있다."):
    return ([{"id": "user", "text": text}],
            [{"source_id": "user", "start": 0, "end": len(text)}])


def test_reason_extracts_exact_source_span_and_records_proof():
    model = FakeModel(FakeResult("5개입니다.", "answered", "계산완료",
                                 evidence=({"kind": "fact", "text": "count=5"},),
                                 trace=({"stage": "answer", "summary": "5"},)))
    service = MarcoReasoningService(model=model)
    sources, spans = grounded()
    result = service.reason(sources=sources, fact_spans=spans, question="민수의 사과는 몇 개야?")
    assert result["verdict"] == "verified" and result["proof_id"]
    assert model.calls[0]["facts"] == [sources[0]["text"]]
    proof = service.explain(result["proof_id"])
    assert proof["found"] and proof["grounds"][0]["source_id"] == "user"
    assert proof["evidence"][0]["kind"] == "fact"


def test_invalid_grounding_is_rejected_before_model_call():
    model = FakeModel(FakeResult("x", "answered"))
    service = MarcoReasoningService(model=model)
    with pytest.raises(ValueError, match="outside source bounds"):
        service.reason(sources=[{"id": "u", "text": "abc"}],
                       fact_spans=[{"source_id": "u", "start": 0, "end": 9}], question="q?")
    assert model.calls == []


@pytest.mark.parametrize("status,raw,expected", [
    ("needs_input", "조건부족", "underdetermined"),
    ("rejected", "B2", "not_applicable"),
    ("rejected", "전제불성립", "contradicted"),
    ("unknown", "입력이해실패", "parse_uncertain"),
    ("unknown", "미지", "not_applicable"),
])
def test_status_mapping(status, raw, expected):
    model = FakeModel(FakeResult("", status, raw, raw={"meaning": {"slots": ["인원"]}}))
    service = MarcoReasoningService(model=model)
    sources, spans = grounded()
    result = service.reason(sources=sources, fact_spans=spans, question="q?")
    assert result["verdict"] == expected
    if status == "needs_input":
        assert "인원" in result["missing"]


def test_verify_accepts_only_conservative_equivalence():
    sources, spans = grounded()
    model = FakeModel(
        FakeResult("5개입니다.", "answered", "계산완료"),
        FakeResult("4개입니다.", "answered", "계산완료"),
        FakeResult("민수가 더 많습니다.", "answered", "계산완료"),
    )
    service = MarcoReasoningService(model=model)
    ok = service.verify(sources=sources, fact_spans=spans, question="몇 개?", proposed_answer="사과는 5개입니다")
    wrong = service.verify(sources=sources, fact_spans=spans, question="몇 개?", proposed_answer="5개입니다")
    ambiguous = service.verify(sources=sources, fact_spans=spans, question="누가 더 많아?", proposed_answer="민수가 더 많아")
    assert (ok["verdict"], ok["comparison"]) == ("verified", "equivalent")
    assert (wrong["verdict"], wrong["comparison"]) == ("contradicted", "different_scalar")
    assert (ambiguous["verdict"], ambiguous["comparison"]) == ("parse_uncertain", "unverifiable_equivalence")


def test_unknown_proof_id_is_explicit():
    service = MarcoReasoningService(model=FakeModel())
    result = service.explain("missing")
    assert result == {"found": False, "proof_id": "missing", "reason": "proof_not_in_this_server_process"}
