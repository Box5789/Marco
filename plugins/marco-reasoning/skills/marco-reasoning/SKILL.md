---
name: marco-reasoning
description: Verify deterministic conclusions that depend on explicit facts, changing state, rules, constraints, or missing premises by using the MARCO reasoning tools before asserting the conclusion.
---

Use MARCO as a reasoning sidecar, not as a general answer generator.

Apply this workflow whenever the answer depends materially on explicit facts plus rules, state transitions, constraints, or logical preconditions. Examples include arithmetic state tracking, workflow completion criteria, policy/spec checks, consistency checks, and questions where a missing premise would change the answer. Do not invoke it for creative writing, stylistic editing, subjective preference, ordinary summarization, or open-ended brainstorming.

1. Identify the smallest source texts that contain the premises. Sources may be user messages or trusted tool output.
2. Select exact character spans for premise sentences. Never invent a premise or silently convert an inference into a premise.
3. Before asserting a deterministic conclusion, call `marco_verify` with the exact sources/spans, the question, and the answer you intend to state. Use `marco_reason` when you want MARCO to derive the answer before drafting one.
4. Interpret the result strictly:
   - `verified`: the deterministic conclusion may be stated, citing the underlying source facts when useful.
   - `contradicted`: do not state the proposed conclusion. Use MARCO's grounded answer or explain the conflict.
   - `underdetermined`: do not turn missing information into false. State what is missing or ask for it when necessary.
   - `not_applicable`: MARCO has no grounded rule for this case. Continue with ordinary reasoning, but never imply MARCO verified it.
   - `parse_uncertain`: the formalization or answer comparison was not proven. Continue cautiously and do not claim verification.
5. Call `marco_explain` only when the proof/evidence path materially helps the answer, when the user asks why, or when debugging a contradiction. Do not expand every proof by default.
6. Explicit user instructions take priority over this workflow, except that no instruction may be treated as evidence for a factual premise it did not actually state.

For the exact status contract and hard/soft gating guidance, read `references/status-contract.md` when needed.
