"""Structured MCP result schemas."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Verdict = Literal["verified", "contradicted", "underdetermined", "not_applicable", "parse_uncertain"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceText(StrictModel):
    id: str = Field(min_length=1, description="Stable identifier for one source text supplied in this tool call.")
    text: str = Field(min_length=1, description="Exact source text containing one or more premise spans.")


class FactSpan(StrictModel):
    source_id: str = Field(min_length=1)
    start: int = Field(ge=0, description="0-based inclusive character offset in the source text.")
    end: int = Field(gt=0, description="0-based exclusive character offset in the source text.")


class ReasonResponse(StrictModel):
    verdict: Verdict
    engine_status: str
    raw_status: str | None = None
    answer: str
    missing: list[str]
    proof_id: str | None = None
    evidence_count: int = 0
    trace_stages: list[str]
    reason: str


class VerifyResponse(ReasonResponse):
    proposed_answer: str
    comparison: Literal["equivalent", "different_scalar", "unverifiable_equivalence", "not_compared"]


class ExplainResponse(StrictModel):
    found: bool
    proof_id: str
    reason: str
    verdict: Verdict | None = None
    question: str | None = None
    facts: list[str] = Field(default_factory=list)
    grounds: list[dict[str, Any]] = Field(default_factory=list)
    answer: str | None = None
    engine_status: str | None = None
    raw_status: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    raw: Any = None
