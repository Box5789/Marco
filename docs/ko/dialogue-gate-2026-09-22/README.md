# MARCO 1 usability gate — frozen dialogue set v1

Goal F1 (`docs/ko/2026-09-22-frozen-dialogue-set-goal.md`). Written 2026-09-22,
before the language realizer. The dialogues are the exam: they are never used to
tune the engine, and nothing in this folder fixes what they find.

## Contents

| Path | What |
| --- | --- |
| `data/benchmarks/dialogues_v1/*.json` | 52 dialogues (26 ko, 26 en), 4–10 turns, 340 turns |
| `data/benchmarks/dialogues_v1/FROZEN.sha256` | directory hash; `tests/test_dialogue_gate.py` fails if it changes |
| `bench/dialogue_gate.py` | validator, category table, overlap check, runner, scorer, baseline |
| `tests/test_dialogue_gate.py` | F1.1–F1.5, F1.7 checks and one UI-path smoke run |
| `baseline.json` (this folder) | F1.6 before number — **not yet recorded**, see below |

Adding or editing a dialogue means `dialogues_v2/`. v1 does not change.

## Turn schema

Each turn has `say`, `label`, `tags`, and `expect`, a semantic structure with
`act`, `entity`, `quantity`, `relation`, and `evidence.turns`. It never holds a
surface string. Optional fields: `restart_before` (a new app over the saved
conversation) and `lang` (the question is in the other language).

| label | act | right response |
| --- | --- | --- |
| answerable | answer (`count`, `total`, `more`) | state the value, with evidence, without retracted evidence |
| hold | record | record the statement, give no answer |
| hold | hold | no answer, and name the entity whose premise is missing |
| ambiguous | clarify | no answer, and name every candidate |
| unsupported | decline | no confident answer, no state change |
| correction | revise | revise the same event, add no new event, reach the declared state |
| why | explain | cite every turn in `evidence.turns`, or the correction turn for a corrected turn |

Statement turns are labelled `hold` because the label set is fixed and the right
response is to give no answer. The scorer reports them apart as `record`.

Answers after a correction also carry `retracted_quantity`, the value if the
correction were ignored, and `reexecuted_quantity`, the value if it ran as a new
event. Each expected value differs from every other holder's value of the same
item, so a right number cannot come from the wrong entity.

## Scoring (`python bench/dialogue_gate.py run`)

Each dialogue runs through `views.kgpack_ui.AppState.turn`, which the UI calls
for `POST /api/turn`, in its own conversation. Web research is stubbed and its
calls are counted. The encoder is `KG_ENCODER=문자` unless it is set otherwise.

* Status comes from the trace verdict and the `known` flag. `phase` other than
  `answer` means held.
* The value is read from the answer text after quoted, bracketed and
  parenthesised spans are removed. Digits and English and Korean numeral words
  count.
* Evidence comes from the answered `fact` rows and the verification checks. Fact
  evidence quoting the original wording of a corrected turn is retracted
  evidence.

**Gate number: every turn labelled `answerable` (108 turns), needing 98 correct
(90%).** Hold, wrong, execution error, and unverifiable all count against it and
are printed apart. Unverifiable means the answer states several values, none,
or gives no evidence.

The report also lists confident answers without evidence and uses of retracted
evidence (gate item 3), every failure, and results per language and per category.

## Commands

```bash
python bench/dialogue_gate.py validate      # F1.1
python bench/dialogue_gate.py categories    # F1.2
python bench/dialogue_gate.py overlap       # F1.3, at HEAD; --rev / --disk-root for others
python bench/dialogue_gate.py run --report-out report.json            # F1.4, this checkout
python bench/dialogue_gate.py run --code-rev <commit> --report-out r.json  # against another commit
python bench/dialogue_gate.py hash          # F1.7
python bench/dialogue_gate.py baseline      # F1.6
python -m pytest tests/test_dialogue_gate.py
```

## Baseline (F1.6)

`baseline` finds the first commit on `main`'s first-parent history that contains
`f985857`. It exports that commit with `git archive`, runs the exam against it,
and writes `baseline.json` with the commit hash and the full failure list. It
refuses to overwrite an existing baseline. On 2026-09-22 `main` is `542e8d9`
and does not contain `f985857`, so the baseline waits for P0.
