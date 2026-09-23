# W1 — language realizer: record

Goal file: `docs/ko/2026-09-22-realization-next-goal.md` (2026-09-23 note governs).
Scope set by the owner: R0–R8, invariants I1–I3. R9 not in this run.

## R0 — state before any code change (HEAD be25630, 2026-09-23)

Previous goal (repair-and-english, f985857, merged 33b9f79, repairs 4adc504).
Its report is the f985857 message plus the HANDOFF stop-point notes. Re-run here:

| Check | Result |
| --- | --- |
| `bench/seven_step_dialogue.py` | english 7/7, 한국어 7/7 |
| `bench/seven_step_ui.py` | english 10/10, 한국어 10/10 |
| `bench/removal_test.py` | 11/11 |
| `bench/error_injection.py` | caught 6/6 |
| `bench/repair_checks.py` | 7/7 |
| `bench/unseen_phrasing.py` | solved 10/20 (answered 8, correct hold 2, held 10, wrong 0, error 0) |
| `yardstick.py`, English default | 대조 375/400, 안 물음 151/400, 근거까지 201/400, 밖 거절 24/24 |
| `yardstick.py`, `NAI_LANGUAGE=한국어` | same, except 근거까지 199/400 |

Left blocked or open by the previous goal:

- §12 steps 3b, 5, 6 pass, but their sentences are pack templates with slots
  (`context_replies`: 51 keys per pack). Nothing composes them.
- Every dialogue answer is a template: answers from the question example's
  `render` (`["$n", "개입니다."]`), holds and records from `context_replies`.
- `realize()` is a stub (returns `meaning["answer"]`). One call site:
  `reasoning_context.py:2731`. Answers composed by `engine.py` from graph
  routing do not pass through it.
- The turn result carries no act and no meaning for holds, explanations,
  corrections or records: `_missing_premise` returns a string,
  `_answer_other_than` returns `transitions: []`, the explanation result has no
  correction utterance and no rule ids. Answered turns carry the answer fact as
  the last transition (`{"fact": [s, p, v]}`).
- "No Korean in Python" is enforced for 9 dialogue modules only
  (`tests/test_repair_and_english.py:test_no_korean_text_left_on_the_dialogue_path`).
- English event reading (`read_event`) is particle-based; English runs only on
  declared example rules.
- Unseen phrasings 10/20: repairs cover particle placement only.

Test files and language (79 `tests/test_*.py`): 64 carry the
`pytest.mark.language` marker, 3 pass a language explicitly
(`test_language_seam.py`, 2 others), 12 neither (9 ALMA reproductions,
`test_dialogue_gate.py`, `test_goal_approval_once.py`, `test_indexed_inference.py`).
At 6195040 it was 52 of 75 without a selection.

English default on existing graphs: routing is the same (yardstick above).
`engine.answer("고혈압이 뭐야")` holds in both packs here (definitions corpus
absent in this checkout); the hold sentence follows the selected pack.
English questions to Korean graph nodes are R9, not measured.

Machine-dependent tests: `tests/test_response_composer.py`, 2 tests fail on one
clone and pass on another (HANDOFF 2026-09-22). Not run here until the end
(owner rule: only `tests/language`, `tests/test_language_seam.py` until S3 reports).

Realization-path files for R8, fixed now: every `.py` under `marco/language/`.
Today: `marco/language/__init__.py`, `marco/language/realizer/__init__.py`.
Language literals in them today: 0 (Hangul string constants outside docstrings: 0).
