# MARCO sidecar status contract

The sidecar exposes five verdicts. They are intentionally asymmetric: uncertainty is never collapsed into falsity.

| Verdict | Meaning | Model behavior |
| --- | --- | --- |
| `verified` | MARCO produced a grounded result and, for `marco_verify`, the conservative comparator proved equivalence. | May assert the deterministic conclusion. |
| `contradicted` | MARCO explicitly rejected the claim or returned a different unambiguous scalar. | Do not assert the proposed claim. |
| `underdetermined` | MARCO needs another premise, role, value, or approval. | Name/obtain the missing information; do not guess. |
| `not_applicable` | The loaded knowledge/model has no grounded answer for this question. | Continue normal LLM reasoning without claiming MARCO support. |
| `parse_uncertain` | MARCO could not reliably parse the input or the adapter could not prove that two natural-language answers are equivalent. | Do not use the verdict as proof either way. |

## Gating

Use **hard gating** only where a workflow explicitly declares MARCO as authoritative for that ruleset (for example a deployment checklist or machine-enforced policy pack). In that mode, only `verified` allows the deterministic step to proceed.

Use **advisory gating** for ordinary ChatGPT/Codex reasoning. `contradicted` and `underdetermined` must change the answer; `not_applicable` and `parse_uncertain` return control to the LLM.

## Grounding rule

Premises are accepted only through exact spans of source text supplied to the tool. A model-generated interpretation is not itself a premise unless that interpretation appears in a trusted source text.
