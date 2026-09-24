"""Streamable-HTTP MCP server exposing MARCO as a read-only reasoning sidecar."""
from __future__ import annotations

import os
from pathlib import Path
import sys

# Run directly from a Marco checkout without modifying the core package layout.
PLUGIN_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PLUGIN_ROOT.parents[1]
for path in (str(PLUGIN_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from starlette.responses import PlainTextResponse

from marco_reasoning.contracts import ExplainResponse, FactSpan, ReasonResponse, SourceText, VerifyResponse
from marco_reasoning.runtime import MarcoReasoningService


mcp = MCPServer(
    "marco-reasoning",
    instructions=(
        "Use MARCO as a deterministic checker for claims that depend on explicit facts, state, rules, or constraints. "
        "Premises must come from exact source spans. Treat underdetermined as unknown, never as false. "
        "If MARCO is not applicable or cannot parse the input, continue with ordinary model reasoning without claiming MARCO verified it."
    ),
)
service = MarcoReasoningService()
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


@mcp.custom_route("/health", methods=["GET"])
async def health(_request):
    """Deployment healthcheck; does not load the model or expose reasoning state."""
    return PlainTextResponse("ok")


@mcp.tool(
    name="marco_reason",
    title="Reason with grounded facts",
    description=(
        "Run deterministic MARCO reasoning on premise sentences extracted from exact character spans of supplied source texts. "
        "Use for rule/state/constraint questions; do not use for creative or subjective tasks."
    ),
    annotations=READ_ONLY,
    structured_output=True,
)
def marco_reason(sources: list[SourceText], fact_spans: list[FactSpan], question: str) -> ReasonResponse:
    out = service.reason(
        sources=[row.model_dump() for row in sources],
        fact_spans=[row.model_dump() for row in fact_spans],
        question=question,
    )
    return ReasonResponse.model_validate(out)


@mcp.tool(
    name="marco_verify",
    title="Verify a proposed deterministic answer",
    description=(
        "Check an LLM's proposed answer against MARCO using grounded premise spans. Exact normalized answers or one unambiguous scalar "
        "can be verified/contradicted; richer surface equivalence returns parse_uncertain rather than guessing."
    ),
    annotations=READ_ONLY,
    structured_output=True,
)
def marco_verify(sources: list[SourceText], fact_spans: list[FactSpan], question: str,
                 proposed_answer: str) -> VerifyResponse:
    out = service.verify(
        sources=[row.model_dump() for row in sources],
        fact_spans=[row.model_dump() for row in fact_spans],
        question=question,
        proposed_answer=proposed_answer,
    )
    return VerifyResponse.model_validate(out)


@mcp.tool(
    name="marco_explain",
    title="Inspect a MARCO proof",
    description="Return evidence and reasoning trace for a proof_id produced by marco_reason or marco_verify in this server process.",
    annotations=READ_ONLY,
    structured_output=True,
)
def marco_explain(proof_id: str, include_raw: bool = False) -> ExplainResponse:
    return ExplainResponse.model_validate(service.explain(proof_id, include_raw=include_raw))


def main() -> None:
    transport = os.environ.get("MARCO_MCP_TRANSPORT", "streamable-http")
    if transport == "stdio":
        mcp.run(transport="stdio")
        return
    mcp.run(
        transport="streamable-http",
        host=os.environ.get("MARCO_MCP_HOST", "127.0.0.1"),
        port=int(os.environ.get("MARCO_MCP_PORT", os.environ.get("PORT", "8765"))),
        streamable_http_path=os.environ.get("MARCO_MCP_PATH", "/mcp"),
    )


if __name__ == "__main__":
    main()
