# MARCO 1 reasoning gate and composition gate

Goal F2 (`docs/ko/2026-09-24-reasoning-and-composition-gate-goal.md`), written
2026-09-24 on branch `reasoning-gate` from `main` at `70ba9f8`. It builds the
measurements behind gate conditions 5 and 6 of
`docs/ko/2026-09-22-freeze-decision.md`. No engine, realizer or pack file was
changed. The frozen dialogues (`data/benchmarks/dialogues_v1/`) were never opened
and no scorer was run against them; the overlap script read them internally and
printed no sentence.

## Contents

| Path | What |
| --- | --- |
| `data/benchmarks/reasoning_v1/*.json` | 114 problems (63 ko, 51 en), 349 setup statements, 156 questions |
| `data/benchmarks/reasoning_v1/FROZEN.sha256` | directory SHA-256 `e0f3458c…`; `tests/test_reasoning_gate.py` fails if it changes |
| `bench/reasoning_gate.py` | validator, overlap check, runner, scorer, baseline (gate condition 6) |
| `bench/composition_gate.py` | composed / passed through / held per reply (gate condition 5) |
| `tests/test_reasoning_gate.py` | F2.1, F2.3, F2.4 checks, one UI-path run, one undeclared-phrasing run |
| `tests/test_composition_gate.py` | classification rules, F2.6 pass-through proof, one live 7-step run |
| `baseline.json` (this folder) | F2.4 baseline at `70ba9f8` |
| `docs/requests/F2-1.md` | "more" and "total" answers composed from one holder's count (all 24 baseline wrongs) |
| `docs/requests/F2-2.md` | kinds no pack can express; declared forms not recorded |

Adding or editing a problem means `reasoning_v2/`. v1 does not change.

## F2.1 What the set covers

One JSON per problem: `setup` (numbered statements, each with its `events`
declared as structure), `questions` (each after setup statement `after`,
optionally `restart_before`), and per question `expect`, a semantic structure,
and `derivation` (`facts`: the setup statements the answer needs; `rules`: from a
fixed list of 19; `steps`: the arithmetic for counts). No expectation holds a
surface string. `validate` replays every expectation from the declared events,
independently of the file that wrote them.

| kind | ko problems / questions | en problems / questions |
| --- | --- | --- |
| count_arithmetic | 7 / 8 | 7 / 9 |
| transfer_chain (3–4 transfers each) | 7 / 13 | 7 / 13 |
| comparison (more; taller, transitive) | 5 / 7 | 5 / 7 |
| total over 2–3 holders | 6 / 7 | 6 / 7 |
| negation | 9 / 10 | 0 / 0 (not expressible, see below) |
| temporal_order | 6 / 8 | 5 / 8 |
| missing_premise | 6 / 7 | 6 / 7 |
| correction then re-derivation | 5 / 9 | 5 / 9 |
| restart (snapshot, restore, ask) | 6 / 7 | 5 / 6 |
| class_inference (own choice; `tests/test_relational_transfer.py`) | 6 / 6 | 5 / 8 |
| **total** | **63 / 82** | **51 / 74** |

Expectation types: count 66, location 23, total 12, more 12, hold 12, taller 11,
yes 10, unknown 10.

- `count`, `total`: the value; after a correction also `retracted_value`, the
  value if the correction were ignored.
- `more`, `taller`: the candidates and the one expected.
- `location`: the place, and every other place of the problem (naming one is wrong).
- `yes`: a membership or action that follows (`[subject, isa|action, object]`).
- `unknown`: nothing may be concluded (negated or contradicted comparisons,
  converse class questions, unrelated chains).
- `hold`: a missing premise; the hold must name it (`names`) — as the goal
  requires, "the right answer is a hold that names what is missing".

**Phrasing rule.** Every setup statement and question uses a form a pack
declares: the `관계해석.examples` of `styles/english.json` and
`styles/한국어.json` and their declared variants (`조사바꿈` 한테/한테서,
`역할바꿈` 받았다/가져갔다, `같은틀` 드렸다/빌려줬다/넘겨줬다, `어순바꿈`,
`수량연쇄` 뒤/후 chains, `수량단위` counters 개/장/권/자루, `수량물음`
합치면/합하면/합쳐서 with 두 사람/둘 다/다들, `비교물음` `A야 B야`, `대조정정`,
`context_correction` `correct:`/`정정:`). Checked with the engine only for the
setup statements: 344 of 349 are recorded, none through a repair (`[수선]`), none
with another value than declared (`reasoning_gate.misread`, 0). No name or item is
a declared numeral word (see F2-2: `공` is the digit 0). The five statements not
recorded are declared forms the engine does not read or refuses; they stay in
the set and land in unparsed.

**Unseen.** Zero full-sentence overlap, 510 sentences, checked by the dialogue
gate's own overlap functions (`bench/reasoning_gate.py overlap`):

| directory | read from | files | overlaps |
| --- | --- | --- | --- |
| `data/benchmarks/dialogues_v1` | disk (overlap script only) | 53 | 0 |
| `data/benchmarks/dialogues_dev` | disk | 50 | 0 |
| `data/benchmarks/dialogues_dev2` | git `understanding-r2` at `3237873` (not on main yet) | 74 | 0 |

Re-run after G2 merges: `python bench/reasoning_gate.py overlap` (on disk).

## F2.2 Scorer

`python bench/reasoning_gate.py run` plays each problem as one conversation
through `views.kgpack_ui.AppState.turn` with the dialogue gate's own runner
(`bench/dialogue_gate.py run()`: same packs, research stubbed and counted,
`restart_before` = a new `AppState` over the saved conversation store). Each
question lands in one bucket:

| bucket | when |
| --- | --- |
| correct | the reply (quoted spans removed) states the expected value, winner, place or proven fact; a hold names what is missing; an `unknown` is not concluded |
| wrong | another value, another or no candidate named, another place, a retracted value or retracted evidence, a count fact of another holder, or a confident answer where a hold was due |
| hold | no conclusion: held, the question not understood (`입력이해실패`), no value stated, a hold that does not name what is missing |
| execution_error | the turn raised |
| unparsed | a setup statement before the question was not recorded (status not `observed`): reasoning never started. Leaves the denominator; listed with the statement and its reply |

Totals per kind and language state their denominator (parsed questions).
Gate condition 6 counts problems: unparsed if any question is, wrong if any
parsed question is, correct if every question is. Pass: ≥95% of parsed problems
correct, 0 wrong questions, ≤10% of problems unparsed. `--dataset DIR` reads
another problem directory; `score ANSWERS --expected FILE` scores saved
observations against other expectations.

## F2.3 Error injection (`tests/test_reasoning_gate.py`)

| check | result |
| --- | --- |
| a deliberately wrong expected-answers file against perfect answers (CLI `score --expected`) | 0 of 156 correct |
| deliberately wrong answers against the frozen expectations | 0 correct |
| two expected counts swapped between two problems, 20+ pairs | exactly those two questions and those two problems change, gate −2 |
| setup statement 1 replaced by an undeclared phrasing, through `AppState.turn` (en and ko) | both questions unparsed, 0 wrong, the statement listed |
| a failed setup statement under deliberately wrong answers | all questions unparsed, 0 wrong |

## F2.4 Baseline at `70ba9f8` (`baseline.json`)

`python bench/reasoning_gate.py baseline`: `git archive 70ba9f8` exported, the
set played against it in a subprocess (21.7 s), `KG_ENCODER=문자`, Python 3.13.9.
Dataset SHA-256 `e0f3458cc75ec9ea8279c644e6964df67550a129f08e29b5f49905791b6fcf5a`,
then frozen (`FROZEN.sha256`, same value).

**Gate condition 6: FAIL.** Problems parsed 109 of 114; correct 80 = 73.4%
(needs 104 = 95%); wrong questions 24 (needs 0); unparsed 5 = 4.4% (at most 10%).
Problems: correct 80, wrong 20, hold 9, execution error 0, unparsed 5.

Questions (denominator: parsed questions, whose setup statements were all recorded):

| kind | lang | N | parsed | correct | wrong | hold | error | unparsed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| count_arithmetic | ko | 8 | 8 | 8 | 0 | 0 | 0 | 0 |
| count_arithmetic | en | 9 | 9 | 9 | 0 | 0 | 0 | 0 |
| transfer_chain | ko | 13 | 13 | 13 | 0 | 0 | 0 | 0 |
| transfer_chain | en | 13 | 13 | 13 | 0 | 0 | 0 | 0 |
| comparison | ko | 7 | 7 | 3 | 4 | 0 | 0 | 0 |
| comparison | en | 7 | 7 | 3 | 4 | 0 | 0 | 0 |
| total | ko | 7 | 7 | 1 | 6 | 0 | 0 | 0 |
| total | en | 7 | 7 | 1 | 6 | 0 | 0 | 0 |
| negation | ko | 10 | 8 | 8 | 0 | 0 | 0 | 2 |
| temporal_order | ko | 8 | 7 | 7 | 0 | 0 | 0 | 1 |
| temporal_order | en | 8 | 8 | 8 | 0 | 0 | 0 | 0 |
| missing_premise | ko | 7 | 5 | 1 | 0 | 4 | 0 | 2 |
| missing_premise | en | 7 | 5 | 1 | 0 | 4 | 0 | 2 |
| correction | ko | 9 | 9 | 7 | 2 | 0 | 0 | 0 |
| correction | en | 9 | 9 | 7 | 2 | 0 | 0 | 0 |
| restart | ko | 7 | 7 | 6 | 0 | 1 | 0 | 0 |
| restart | en | 6 | 6 | 6 | 0 | 0 | 0 | 0 |
| class_inference | ko | 6 | 6 | 6 | 0 | 0 | 0 | 0 |
| class_inference | en | 8 | 8 | 8 | 0 | 0 | 0 | 0 |
| **all** | ko | 82 | 77 | 60 (77.9%) | 12 | 5 | 0 | 5 |
| **all** | en | 74 | 72 | 56 (77.8%) | 12 | 4 | 0 | 2 |
| **all** | | 156 | 149 | 116 (77.9%) | 24 | 9 | 0 | 7 |

What fails:

- **Wrong 24, one cause** (`docs/requests/F2-1.md`): every "more" question
  (comparison 8, correction 4) and every "total" question (12). The engine's own
  sentence is right (`Omar.`, `13 stamps.`); the realizer composes the last
  `fact` row, one holder's count (`4 stamps.`, `9 stamps.`). Taller comparisons
  are right (their answer passes through uncomposed).
- **Hold 9**: 8 missing-premise questions held without naming what is missing
  (`What this conversation has established is not enough to decide the answer.`);
  the holds that name it (`Where is Lior?` → `…never stated the location of Lior`)
  are correct. 1 restart: `이것만으로 태린이 텔루라고 할 수 있는가?` is not
  understood after the restore (the same form is answered without a restart).
- **Unparsed 5 statements, 7 questions** — declared forms not recorded:

| problem | statement | reply |
| --- | --- | --- |
| en-missing-05#2 | `Uma gave Vito 4 badges.` | `The new statement does not fit what was already recorded. Please check it.` (Vito's count never stated) |
| ko-missing-05#2 | `새봄이 은결에게 딸기 4개를 줬다.` | `새 말이 이미 반영한 상태와 맞지 않습니다. 확인해 주세요.` (same) |
| ko-negation-06#2 | `슬기가 나침반을 책상으로 옮기지 않았다.` | `이 문장에서 조사할 사실의 주제를 확인하지 못했습니다. …` |
| ko-negation-07#3 | `지안이 우산을 베란다로 옮기지 않았다.` | same |
| ko-order-05#2 | `하랑이 있는 곳으로 목도리를 옮긴다.` | same |

## F2.5 / F2.6 Composition gate

`python bench/composition_gate.py` plays a dialogue directory in the dialogue-gate
format with the dialogue gate's runner and watches each `AppState.turn`: the
realizer reports made during the turn (`marco.language.realizer.last_report()`,
identity-checked so a stale report is never read) and the engine result's
`meaning.act`. A reply is **composed** when the realizer composed it
(`realized`, not `held`) and the reply the UI returned is exactly that sentence;
a quoted graph node or user sentence counts only inside it (a composed text that
is only quotation, or a reply with text outside the composed sentence, is not
composed). **Held**: the realizer's declared hold. Everything else is **passed
through**, with its reason (`realizer:no_plan`, `no_realizer_report`, …). Per act
(answer, hold, record, explain, ask, correct) and per language (the reply's).
There is no default source, so no development run reaches the frozen set by
accident.

Numbers at `70ba9f8` (engine unchanged on this branch):

| set | composed / spoken | passed through | held |
| --- | --- | --- | --- |
| fixed 7-step, ko + en, as `bench/seven_step_ui.py` plays it (10 turns each, restart at 9) | **20 / 20** | 0 | 0 |
| 20 phrasings (`unseen_phrasing_v1.json`, the cases of `unseen-before.json`), 51 turns | **51 / 51** | 0 | 0 |
| both fixed sets, realizer monkeypatched to pass every turn through | **0 / 71** | 71 (`realizer:injected_passthrough`) | 0 |
| dev set `dialogues_dev` (50 dialogues, extra check) | 232 / 269 | 37 (30 `no_realizer_report`, 7 `realizer:no_plan`) | 0 |
| reasoning set, one dialogue per problem (extra check, `--reasoning`) | 394 / 505 | 111 (107 `realizer:no_plan`, 4 `no_realizer_report`) | 0 |

Fixed sets by act: answer 20/20, hold 20/20, record 25/25, explain 2/2, ask 2/2,
correct 2/2; by language: ko 35/35, en 36/36. On the reasoning set the passed-
through replies are records of class and taller statements (`Recorded in this
conversation.`), `correct:`/`정정:` corrections, class and taller answers, and
unresolved holds — no plan is declared for them. `tests/test_composition_gate.py`
proves the pass-through realizer scores 0 composed through the real entry.

## How the owner runs both gates on the frozen dialogues

From the repository root, on the commit to measure:

```sh
# condition 5: composed, never picked (frozen 52)
KG_ENCODER=문자 python bench/composition_gate.py --dataset data/benchmarks/dialogues_v1 \
    --report-out docs/ko/dialogue-gate-2026-09-22/composition-roundN.json
# condition 6: reasons (frozen reasoning set)
KG_ENCODER=문자 python bench/reasoning_gate.py run \
    --report-out docs/ko/reasoning-gate-2026-09-24/roundN.json
# the set is still the frozen one
python bench/reasoning_gate.py digest          # prints "<sha> frozen"
# conditions 1-4 as before
KG_ENCODER=문자 python bench/dialogue_gate.py run --report-out docs/ko/dialogue-gate-2026-09-22/roundN.json
```

Condition 5 passes when the first line reads `composed M / M spoken replies`.
Condition 6 passes when the `GATE 6` line reads `PASS`. Another revision:
`python bench/reasoning_gate.py run --code-rev <sha>` (exports it like the
baseline); for the composition gate unpack `git archive <sha>` into a folder and
pass `--code-root <folder>`.

## Kinds the engine could not express (not in the set)

Listed, not dropped; the declarations are requested in `docs/requests/F2-2.md`.

| kind | why |
| --- | --- |
| negation, English | no negated statement is declared in `styles/english.json`; all 9 negation problems are Korean |
| comparison: fewer | no "who has fewer" question in either pack |
| comparison: equal | no question or answer frame for equal amounts in either pack |
| order in time: before/after questions | no "where was X before …" / "how many after …" question in either pack; order is asked through latest state after ordered events, planned moves (`…옮길 예정이다`) and a lookup move |
| planned, negated and lookup moves, English | declared in Korean only |
| action classes, English | `every X sings` is Korean only; English class inference is membership only |

Declared but not recorded at `70ba9f8` (in the set, unparsed): Korean negated
moves, the Korean lookup move, and a transfer to a holder whose count was never
stated (both languages).

## F2.7 Suite

Full parallel suite (`KG_ENCODER=문자 python -m pytest -q`, pytest.ini: `-n auto
--dist loadfile`) in this worktree, which has no gitignored corpus (so
`test_response_composer` skips; see the clean-export note in the S3 records):

| run | passed | failed | skipped | time |
| --- | --- | --- | --- | --- |
| start, `70ba9f8` | 909 | 5 | 8 | 224 s |
| end, this branch | 932 (= 909 + 23 new) | 5 | 8 | 219 s |

Same 5 failures at both ends, none new; the 23 new tests are the 17 of
`tests/test_reasoning_gate.py` and the 6 of `tests/test_composition_gate.py`.
`tests/test_dialogue_gate.py::test_f1_3` (no frozen sentence anywhere in the
corpus, now including this set and these tests) passes. The 5 failures are the known ones (3 × `test_language_seam` ko-01/02/08,
`test_understanding_r1::test_a_total_and_a_comparison_read_current_counts`, the macOS
RSS assertion in `test_alma_integrated_reproduction`). The suite includes
`tests/test_dialogue_gate.py`, which plays one frozen dialogue internally; only its
pass/fail was read.
