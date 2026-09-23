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

## R1–R8 (2026-09-23)

Tests: `tests/language/test_w1_r*.py`, `tests/test_language_seam.py` — 68 passed.
Measurements: `marco/language/measurements/w1-measurements.json` (`python tests/language/w1_measure.py`).
Fixed dialogues for measurement: §12 ×2, the 20 phrasings of `unseen-before.json`,
12 own dev dialogues (`tests/language/w1_dev_dialogues.json`). The frozen set was not opened.

"With W1-1 fields" = the `meaning` block of `docs/requests/W1-1.md`, attached inside
tests by `tests/language/w1_harness.py` (engine files unedited). "Live" = today's seam.

| Item | State | Evidence |
| --- | --- | --- |
| R1 | done | one Meaning Graph → `4개입니다.` / `4 apples.`; trace shows 6 layers + check `parsed` (`test_w1_r1_thin_slice.py`) |
| R2 | composed and verified with W1-1 fields; **live blocked on W1-1** | 3b, 5, 6 composed in ko+en, engine sentence poisoned, bench checks 7/7 each (`test_w1_r2_section12.py`); live seam passes those turns through (`reason: no_plan`) |
| R3 | done | swap → `parse`, number → `numbers`+`parse`, negation → `polarity`; 6/6 caught, 6/6 held, 0 emitted (`test_w1_r3_injected_errors.py`) |
| R4 | done | every proposition deleted one at a time (≥15 per language) takes its clause; deleted transfer leaves no amount; poisoned engine sentence changes nothing (`test_w1_r4_removal.py`) |
| R5 | done (with W1-1 fields) | 34 dialogues: referents elided 37/37; known facts 50: omitted 35, said 15 (all read through ellipsis, repair or a resolved referent); repeated roles elided 18/18; live: referents 37/37 (`test_w1_r5_discourse.py`) |
| R6 | done | §12 ×2 reasoned once (`_turn` calls = turns); 14/14 graphs said in both languages, same numbers, 0 held; names by romanization, items by sense links, unlinked words kept (`test_w1_r6_two_languages.py`) |
| R7 | done in a Realizer with learning on; **live off until W1-1 item 8 (conversation id)** | ko casual: `이제 민재 사과는 2개야.` → learned from `지호는 구슬 열 개가 있어` → `이제 민재는 사과 두 개가 있어.` → removed → before; en: `3 apples` → `three apples`; disable/enable/remove/remove by conversation; a meaning-changing learned candidate is never selected (`test_w1_r7_learning.py`) |
| R8 | done | files: every `.py` under `marco/language/` (8). Hangul words in string constants: 0. Declared surface forms or whitespace in constants: 0 (`test_w1_r8_literals.py`; the test plants literals and sees them) |

### Invariants

- I1 not a list-picker: no finished sentence in any realizer file; `R8` plus the grammar
  tests (`뒹굴 → 뒹굽니다`, particles by coda, English agreement and do-support computed).
  Frames with slots exist only as ordered parts over roles realized by the grammar.
- I2 nothing language-specific in Python: R8 = 0/0. Language behaviour is declared
  (`grammar.strategies`: verbs by endings or agreement, cases by particles or prepositions).
- I3 meaning never changes: every realized clause is checked (`test_the_check_is_not_sampled…`);
  a failing clause is never emitted and the turn is held. Parse-back covers 75/242 clauses
  (count, transfer, location); the other 167 (meta clauses: holds, citations, rules) are
  checked by the independent number, polarity and quotation readers only.

### Counts (with W1-1 fields / live)

| | with W1-1 fields | live |
| --- | --- | --- |
| replies | 109 | 109 |
| realized | 109 | 21 |
| passed through (engine sentence) | 0 | 88 |
| held by the realizer | 0 | 0 |
| clauses / parsed back / overt-only | 242 / 75 / 167 | 22 / 21 / 1 |
| check blocks | 0 | 0 |
| wrong assertions (answer number ≠ fact) | 0 | 0 |
| execution errors | 0 | 0 |
| intents used | INFORM 166, ASK 22, REFUSE 17, WARN 10, CORRECT 8, REASSURE 8 | INFORM 22 |

Structured input (graphs given directly): R1, R3, R4, R6 tests. Natural-language input:
the dialogue runs above.

### Existing benchmarks, be25630 export vs this branch (same machine, same conditions)

Identical results: seven_step_dialogue 7/7+7/7, seven_step_ui 10/10+10/10, removal_test 11/11,
error_injection 6/6, repair_checks 7/7, unseen_phrasing 10/20, answer_quality 21/34 wrong 0 (after the fix below),
dialogue_evaluation (outcomes identical; resource timings only), event_runtime_reproduction
solved 12 / hold 1 / wrong 6 / error 0 both, experience_concept_reproduction 31/14/0/0 both,
question_endings, relational_learning, semantic_contrasts unchanged. `yardstick.py` routing
is not on the realizer path (R0 figures stand).

answer_quality: first run showed 21→20 (case 경계-01 held by the realizer: the Korean parser
reads `작은 공책은 큰 서랍에 있다` ambiguously). Fixed in 4461976 (accept the parser's own role
candidates); rerun identical to base: 21/34, wrong 0.

### Cost

- import 0.008 s; first realization with pack load 0.059 s (ko), 0.005 s (en).
- per realize: live median 0.16 ms, p95 0.42 ms; with W1-1 fields median 0.35 ms, p95 1.06 ms, max 49 ms.
- peak memory one realization 145 KB; process max RSS after two languages 22.8 MB.
- declarations: meaning.json 11.2 KB, 한국어.json 16.5 KB, english.json 18.5 KB; Python 86 KB.
- suite: see Full suite.

### Fluency

Not claimed. Sample of 25 replies for the owner to judge: `marco/language/measurements/fluency-sample.md`.

### Requests written

- `docs/requests/W1-1.md` — turn results carry `meaning` (unblocks R2 live, records, holds, R7 live).
- `docs/requests/W1-2.md` — second seam for `engine.answer` (graph-routed answers).
- `docs/requests/W1-3.md` — pass the model to `realize`; carry `부정표지` in the component.

### Known limits

- Live seam realizes answered count/location turns only; everything else waits for W1-1.
- Korean counter is the declared default `개` for `count` (W1-1 item 5 asks for the unit).
- A realizer hold on an answered turn keeps engine status `answered` (W1-1 "optional").
- Packed runtime without `styles/` on disk passes through (W1-3).
- English engine holds seen in dev dialogues are parsing (G1), not realization:
  `Chloe has 1 apple.` then a transfer; `there are 20 books` then `Hugo got 6 books.`

### Full suite (`python -m pytest tests -q -n 12 --dist loadfile`, KG_ENCODER=문자)

- First run: 111 failed / 783 passed. Cause was mine: with `language=None` the realizer used the
  declared default (english) while the engine selects `NAI_LANGUAGE` first, so Korean-marked tests
  got English answers. Fixed in 0ffb41c; test added.
- Final run at 0ffb41c: **893 passed, 2 failed, 8 skipped, 217 s.** Both failures pre-exist:
  - `test_alma_integrated_reproduction.py::test_fixed_alma_life_reproduction_has_no_wrong_checks`
    (one of main's 4 known: RSS on macOS);
  - `test_dialogue_gate.py::test_f1_3_no_full_sentence_shared_with_head`: one frozen sentence occurs
    in `tests/test_language_seam.py:65`, inside the pre-seam record S2-min committed. The same single
    overlap is present at be25630 and at main 78bd062 (`gate.overlaps(rev=...)`), so it predates W1.
    Not fixed: editing the byte-identity record is the owner's call.
- `test_response_composer` (machine-dependent, 2 fail on one clone) passed on this machine.
- The main folder's `pytest.ini` (S3, `-n auto`) applies to this worktree because the worktree has none.
