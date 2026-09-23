# Model comparison on the frozen exams (goal C1)

Goal: `docs/ko/2026-09-24-model-comparison-goal.md`. Written 2026-09-24 on branch
`model-comparison`. Evaluation only: no MARCO product file was changed.

The same two frozen exams, the 52 dialogues (`data/benchmarks/dialogues_v1/`,
SHA-256 `a2294c68…`, matches `FROZEN.sha256`) and the 114 reasoning problems
(`data/benchmarks/reasoning_v1/`, `e0f3458c…`, matches), played turn by turn
through four answerers and scored from the reply text by one extractor
(`bench/compare_models.py`). Every answerer ran once, both sets, both
languages, at commit `ce7d73b` (MARCO's product code there is identical to
`main` `e35587f`); the saved replies were scored by the extractor at `99a15d9`.
No exam sentence is in this folder: the reports hold aggregates and per-turn
buckets by id, never a reply, and this file quotes only short generic reply
phrasings.

## The table

| model | params | dialogues answerable correct | wrong | invented answers on unsupported turns | reasoning correct | reasoning wrong | median latency | resident memory |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MARCO (`views.kgpack_ui.AppState.turn`) | none learned (rules, language packs, graphs) | 21/108 | 1 | 0/26 (reasoning 0/12) | 148/156 questions, 106/114 problems | 0 | 27 ms | 505 MB |
| always_hold | 0 | 0/108 | 0 | 0/26 (reasoning 0/12) | 10/156 questions, 7/114 problems | 0 | 0 ms | 17 MB |
| GPT-2 `openai-community/gpt2`, fp32, CPU | 124M | 1/108 | 51 | 9/26 (reasoning 2/12) | 10/156 questions, 6/114 problems | 82 | 468 ms | 398 MB |
| Qwen2.5-7B-Instruct, 4-bit MLX, Apple GPU | 7.61B | 75/108 | 25 | 5/26 (reasoning 1/12) | 88/156 questions, 57/114 problems | 22 | 749 ms | 5,219 MB |

How to read the columns:

- **dialogues answerable**: the dialogue gate's denominator, the 108 turns
  labelled answerable. Correct means the value (or, for the two "who has more"
  turns, the holder) the reply states is the expected one. Hold, wrong and
  unverifiable all count against. Holds: MARCO 86, always_hold 108, GPT-2 4,
  Qwen 7. Unverifiable (no value, or several values the reply does not
  resolve): GPT-2 52, Qwen 1, MARCO 0.
- **invented answers on unsupported turns**: value-bearing replies on the 20
  missing-premise turns plus the 6 unsupported requests of the dialogue set
  (gate condition 3); in brackets the same count on the 12 missing-premise
  questions of the reasoning set.
- **reasoning**: the reasoning gate's buckets over every question (156) and
  every problem (114, correct when all its questions are). A text reply cannot
  show whether a setup statement was recorded, so the text scorer has no
  "unparsed" bucket and every model is scored over all problems.
- **reasoning wrong**: wrong questions, the gate's unit for wrong.
- **median latency**: one `answer` call, over all 845 turns (setup statements
  included). p90: MARCO 950 ms, GPT-2 593 ms, Qwen 1,212 ms.
- **resident memory**: the answerer process's peak physical footprint (macOS
  `phys_footprint`, GPU buffers included), read after every turn. Median over
  turns: MARCO 253 MB, GPT-2 353 MB, Qwen 4,650 MB (MLX's own peak 4,656 MB).
  All under the 6 GB limit. MARCO's figure includes building both language
  packs in the process; the preview-1 note's 137 MB is another measure.

By language, answerable dialogue turns correct / wrong: MARCO ko 10/1, en 11/0;
GPT-2 ko 0/7, en 1/44; Qwen ko 28/19, en 47/6. Reasoning questions correct /
wrong: MARCO ko 76/0, en 72/0; GPT-2 ko 4/22, en 6/60; Qwen ko 31/13, en 57/9.

## MARCO: the text score next to its gate reports

MARCO was scored by the same extractor as every other model. The same run was
also scored by the gates' own structural scorers (from the payload each turn
returned), and both are compared with the recorded round-2 gate reports.

| | gate report | structural, this run | text extractor, this run |
| --- | --- | --- | --- |
| dialogues answerable: correct / wrong / hold / unverifiable | 21 / 1 / 86 / 0 (`docs/ko/dialogue-gate-2026-09-22/round2.json`, code `494f599`) | 21 / 1 / 86 / 0 | 21 / 1 / 86 / 0 |
| dialogues missing premise / ambiguous / unsupported correct | 3/20, 7/12, 6/6 | 3/20, 7/12, 6/6 | 3/20, 7/12, 6/6 |
| reasoning questions: correct / wrong / hold / unparsed | 146 / 0 / 3 / 7 (`docs/ko/reasoning-gate-2026-09-24/round2.json`, code `a7c20b2`) | 146 / 0 / 3 / 7 | 148 / 0 / 8 / – |
| reasoning problems correct | 106 of 109 parsed | 106 of 109 parsed | 106 of 114 |

The product code at both report commits equals the code run here, and this
run's structural score matches both reports turn for turn. The text score
matches the structural score on every dialogue turn. On reasoning it is two
questions higher, both explained:

| question | structural | text | why |
| --- | --- | --- | --- |
| en-missing-05 q2 | unparsed (setup statement 2 not recorded) | correct, a hold that names the missing holder | the gate removes a question from its denominator when a setup statement before it was not recorded; the text scorer has no such bucket and reads the reply, which is the right hold |
| ko-missing-05 q2 | unparsed (setup statement 2 not recorded) | correct, a hold that names the missing holder | same |

The other five unparsed questions are holds under the text scorer. The text
scorer cannot see evidence rows, so it would also count a right value without
evidence as correct; on these runs that never happened (the one dialogue turn
where the gate records a confident answer without evidence, en-18 turn 4, is an
ambiguous-referent turn and is wrong under both).

## What the models did

- **always_hold** is the floor: it never answers, so it is never wrong and
  never invents; declining is the right answer on the 6 unsupported requests
  and on the 10 reasoning questions whose answer is "cannot be concluded".
- **GPT-2** copies the pattern of its worked example: "<name> has <number>
  <things>" to nearly every English question (41 wrong values, 7 values given
  to another holder), a bare acknowledgement to most Korean turns (49
  answerable turns with no value). 1 of 108 correct is a chance hit.
- **Qwen2.5-7B-Instruct** answers most English count questions (47 of 54) and
  just over half of the Korean ones (28 of 54). 10 of its 25 dialogue wrongs
  follow a correction badly: 9 give the value the correction retracted, 1
  applies the correction as a further event instead of a replacement. It
  invents on 5 of 26 turns: four missing starting counts answered as "one",
  and one short song written on request. On reasoning it declines 22 derivable
  questions, often comparisons and chains ("the information given does not
  specify…"), concludes 3 comparisons that cannot be concluded, and gets 14
  counts or totals wrong. In Korean conversations it replied mostly in Chinese
  on 11 dialogue turns and 17 reasoning questions; the extractor reads Korean
  and English and holds those as `other_language` (listed in `qwen.json`).
  Read by hand, the dialogue ones hold 3 right and 2 wrong answerable values,
  4 declines, 1 guess at an ambiguous referent and 1 poem written on request;
  the reasoning ones 6 right and 2 wrong answers and 9 declines or unfinished
  replies.
- **MARCO** holds on 86 answerable turns (phrasings it cannot read yet) and is
  wrong on 1 (a retracted value, the gate's known violation); on reasoning it
  is never wrong. MARCO is right on 21 of the 22 answerable turns it answers,
  Qwen on 75 of the 101 it answers. Of the 148 reasoning questions MARCO gets
  right, Qwen gets 83 right, 22 wrong and holds 43.

## The extractor and its checks

One function reads every reply, MARCO's included (`bench/compare_models.py`,
docstring for the rules): quoted, bracketed and parenthesised spans removed as
the gates remove them; values from digits, English number words, Korean native
numerals with or without a counter and Sino-Korean or mixed numerals before a
counter; each value attributed to the holder its clause names ("than X" and
"X보다" mark the other side of a comparison, "from X" and "X에서" where
something was); a hold when a clause declines or says the information is
missing and no value remains, or when the reply concludes with a decline.
Naming checks for holds use the raw reply, as the gates do. One deliberate
difference from the reasoning gate: on a "cannot be concluded" question, a
reply that says nothing about the question (an acknowledgement, another fact)
is a hold, where the gate counts an engine answer without a conclusion as
correct; MARCO's score is the same under both readings.

`tests/test_compare_models.py` (14 tests): 47 hand-written English and 51
Korean replies against conversations written for the test (digits, number
words, counters, holder names, comparisons, declines, hedges, acknowledgements,
repeated sentences, other scripts); 17 English and 19 Korean reasoning replies
across the question types; replies built from the frozen expectations (all correct;
all wrong; one injected wrong reply is the only wrong; declines are holds; an
invented value on every missing-premise and unsupported turn counts 26
invented); the floor answerer end to end; no frozen sentence in any file this
goal owns; no reply or exam text in these reports; MARCO's text score within 2
of its structural score or explained turn by turn.

**Changes after replies were seen, in order, each applied to every model:**

1. After MARCO's first scoring, before any language model ran (`ce7d73b`): two
   decline phrasings the lexicon missed ("nothing … has told me", "did not
   answer"; 나온 적이 없다, 들은 것이 없다, 반영하지 않았다), and hold names read
   on the raw reply as the gates read them. MARCO's text score then matched its
   structural score.
2. After auditing GPT-2's and then Qwen's replies (`99a15d9`): LaTeX math
   `\( 3 + 2 = 5 \)` was being removed as a parenthetical; Korean numerals that
   mix Sino and native parts; nouns ending in 서 or 고 split from their value;
   the value after 뺀, `=` and after a "-아서" or "때문에" clause; a comparison's
   than-side taken as the claim; a decline that closes the reply; bare
   acknowledgements and repeated user sentences counted as invented; a question
   parroted back counted as a named hold; replies mostly in another script.
   Rescored from the saved replies; no model was rerun.

**Audit of the final extractor.** Every Qwen decision was read by hand (108
answerable, 38 other scored dialogue turns, 156 reasoning questions) and 60
GPT-2 decisions drawn at random. Disagreements: Qwen 4 of 302, GPT-2 0 of 60.
The four: ko-06 turn 4 (text hold; read as wrong, the reply states a value then
declines later changes), en-05 turn 5 (text unverifiable; read as wrong, a
garbled Korean count), ko-transfer-03 q1 (text hold; read as wrong, the reply
computes a negative count), ko-10 turn 5 (text wrong on a missing premise;
read as a hold written half in Chinese). With the reader's calls and the
other-language replies read, Qwen would be 78/108 correct with 29 wrong on the
dialogues, 94/156 correct with 25 wrong on reasoning, and 6/26 invented.

**Suite (C1.6).** Full parallel suite (`python -m pytest -q`), same machine,
same hour: `main` `e35587f` 1057 passed, 1 failed, 8 skipped; this branch 1071
passed, 1 failed, 8 skipped (the 14 new tests). The failure is the known macOS
RSS assertion in `tests/test_alma_integrated_reproduction.py`; the two
machine-dependent `test_response_composer` failures did not occur in either run.

## Fairness notes

**What every model was given.** The same turns in the same order: each frozen
dialogue, and each reasoning problem's setup statements with its questions
after the statement they follow (the gates' play order), one conversation per
dialogue or problem, starting empty. On every turn the answerer received the
whole conversation so far: Qwen as chat messages, GPT-2 as `User:` /
`Assistant:` lines, MARCO through its own conversation store, which already
holds every earlier turn. A `restart_before` turn rebuilds MARCO's process over
the saved conversation, as the gates do; a language model handed the history
loses nothing at a restart.

**Prompts.** Qwen: one fixed system message (answer briefly, in the user's
language, only from what the user said; acknowledge facts in a few words; say
that the information was not given when it was not; do not guess), no
examples, the model's own chat template. GPT-2 is a base model, so it got a
one-line header with the same instruction and one four-turn worked example in
the conversation's language, written for this goal with names and items that
appear in neither exam; at most 1024 tokens, the oldest turns dropped first
(this happened on 1 of 845 turns). Both prompts are in the report JSONs and
were written before the first full run and not changed after.

**What no model was given.** No tools, no retrieval, no web (MARCO's web
research is stubbed and was never called), no retries, no sampling
(temperature 0, greedy), no chain-of-thought instruction, no examples from the
exams, no second run. Qwen could write up to 160 tokens per reply, GPT-2 48.

**Why a prompt-based hold counts as a hold.** Every language model was told to
say when the information is missing, which is what MARCO is built to do. The
gates' rule is applied to every reply alike: a hold on an answerable turn
counts against the score (not correct, not wrong), a hold that names what is
missing is the right answer on a missing-premise turn, and a value stated
where none can be known is an invented answer. A hedge ("probably 5") states a
value and is scored by it.

**One extractor, text only.** The gates also read MARCO's structured payload
(answer facts, evidence rows, recorded state). A reply text cannot show those,
so the text scorer is more lenient than the structural gate for everyone: it
does not ask for evidence behind a right value, and it does not score
statement, correction or "why" turns (340 − 108 − 38 = 194 dialogue turns; the
gate checks them against recorded state and cited evidence). On MARCO the two
scorers agree except for the two reasoning questions above.

**Cost.** MARCO and GPT-2 ran on the CPU, Qwen on the Apple GPU through MLX;
one model at a time on an M4 Pro with 24 GB. Other sessions were running test
suites on the same machine (load average 2 to 7 during these runs), so the
latencies are indicative. Memory is the whole answerer process, Python and
harness included.

**What this comparison cannot say.** Nothing about general knowledge,
open-ended chat, writing quality or fluency, instruction following outside
these exams, other languages, long contexts, or other phrasings. Both exams
are MARCO's own domain (counts held and passed between people, places,
comparisons, class membership, corrections, restarts) and were written for its
gate; the reasoning set is phrased in forms MARCO's language packs declare,
which favours MARCO there, while the dialogue set is unseen by every model. One
greedy run per model gives no variance. Qwen ran 4-bit quantized; the bfloat16
model may score somewhat differently. A larger or API model was not run: the
owner decides whether the exams may leave the machine.

## Models

| answerer | model | weights and revision | runtime | quantization |
| --- | --- | --- | --- | --- |
| `marco` | MARCO at `ce7d73b` | packs built as `bench/dialogue_gate.py run` builds them | Python 3.13.9, CPU | none |
| `always_hold` | fixed reply "I do not know." / "모르겠습니다." | – | – | – |
| `gpt2` | `openai-community/gpt2` | `607a30d783dfa663caf39e06633721c8d4cfcd7e` | transformers 5.0.0, torch 2.9.1, CPU, float32 | none |
| `qwen` | `Qwen/Qwen2.5-7B-Instruct` | `mlx-community/Qwen2.5-7B-Instruct-4bit` @ `c26a38f6a37d0a51b4e9a1eb3026530fa35d9fed` | mlx-lm 0.31.3, mlx 0.32.2, Apple GPU | 4-bit affine, group size 64 |

The fallback (`Qwen/Qwen2.5-3B-Instruct`, bfloat16 on MPS) was not needed.

## Files and how to rerun

| file | what |
| --- | --- |
| `marco.json`, `always_hold.json`, `gpt2.json`, `qwen.json` | one report per answerer: run and scorer commits, dataset hashes, model info and prompt, SHA-256 of the answers file, aggregates, per-turn buckets by id, cost; MARCO's also carries the structural cross-check |
| `README.md` | this file |

```sh
python bench/compare_models.py run marco          # or always_hold, gpt2, qwen
python bench/compare_models.py score ~/.cache/nai-model-comparison-2026-09-24/qwen.json
python bench/compare_models.py table
```

`run` saves the replies to `~/.cache/nai-model-comparison-2026-09-24/`
(`NAI_COMPARE_ANSWERS` overrides), outside the repository, because models
repeat exam sentences; each report records the SHA-256 of the file it scored.
The weights come from the local Hugging Face cache and are not in the
repository.
