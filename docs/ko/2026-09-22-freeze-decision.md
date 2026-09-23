# Freeze decision — useful MARCO 1 first

Decided 2026-09-22 by the repository owner after an independent audit. **Every
session working on this repository reads this file before its goal file.** A
goal that touches a frozen area stops and reports; it does not "just add a bit".

## Frozen until MARCO 1 ships

| Area | What is frozen | What remains allowed |
| --- | --- | --- |
| POLO | All of it. `polo/`, host permission boundary (P1), workflows (G4, G5) | Nothing |
| MCO binary | The real `.mco` format, overlay, snapshot, consolidation (M1–M4) | `mco/` API shell stays as is: committed to branch `mco-package`, parked, not merged, not extended |
| Autonomous planning | Re-planning, tool making, self-modification (G6–G9), general planner | Existing `goal_runtime` registered tools stay as they are |
| ALMA advancement | Persona/social features (A1, A2), new ALMA modules, any ALMA goal after goal 1 | Goal 1 on the Windows machine finishes and merges. Existing ALMA tests keep passing |

Also frozen: the full five-phase repository refactor (plan file §4). Only the
read-only audit (S1) and the minimal skeleton the realizer needs (S2-min) run.

## What "useful MARCO 1" means (roadmap §12, stage 1)

A dialogue in a supported life or work domain where MARCO records state,
handles follow-ups, ellipsis, referents, corrections, and "why", in Korean and
English, and creates its sentences instead of picking them.

**Gate, fixed before implementation, not after:**

1. The fixed 7-step dialogue passes in both languages with the verbatim phrasings.
2. 50 or more unseen multi-turn dialogues, written before the realizer work and
   never used during development, score **90% or better** on answerable
   questions. A hold is not a correct answer. Unsupported, ambiguous, and
   correction cases are reported separately.
3. No confident answer without evidence, no use of retracted evidence, in any
   of the 50.
4. Sample count, composition, and the full failure list are published with the number.

No storage format, test count, or refactor progress counts toward this gate.

## The queue (replaces plan file §2 items 3–5) — updated 2026-09-23

| # | Goal | File | State |
| --- | --- | --- | --- |
| S1 | Structure audit | `docs/architecture/structure-audit.md` | done, on `main` |
| F1 | Frozen dialogue set: 52 dialogues, scorer, baseline **3/108 (2.8%)** | `main` 986e753 | done |
| P0 | Integrate goal 2, park `mco/` | `main` 4adc504 | done |
| S2-min | Skeleton + `marco/language/` seam | `main` 78bd062 | done |
| S3 | Test hygiene and speed: parallel default, 211 s vs 1744 s, same 3 failures, corpus skips | `main` 344078c | done |
| D1 | Docs that tell the truth: README from scripts, 5 package docs, `tools/doc_facts.py` | `main` 366c630 | done |
| G1 | Understanding round 1: 50 dev dialogues, dev set **65/96 answerable, 0 wrong**, 29 commits of declared rules | `main` a8388e9 | done 2026-09-23. **Frozen round 1: 19/108 (17.6%)**, KO 9/54, EN 10/54, 87 holds, 1 wrong, 1 unverifiable (`docs/ko/dialogue-gate-2026-09-22/round1.json`). Dev 67.7% vs frozen 17.6%: the rules fit the dev set, not the language |
| W1 | Language realizer: R0–R8 done, seam composes 109/109 fixed replies, suite 898 passed / 1 known / 8 skipped, report `marco/language/W1-report.md` | `main`, merged 2026-09-23 | done. Open: W1-3 part 2 (negation marker as a pack component field) after G1 merges |
| G2.. | Understanding rounds until the frozen gate reaches 90% | written per round | after each frozen run |

Known failures on `main` at 366c630: two `test_response_composer` tests (machine-dependent)
and the macOS RSS assertion in the ALMA reproduction tests. Found by D1, not fixed:
`tests/test_dialogue_gate.py::test_f1_3` fails because `tests/test_language_seam.py`
shares a sentence with a frozen dialogue (W1 owns the fix); `target-map.json` gives
`marco` no layer; `tests/test_dialogue_etiquette.py` collects nothing.

**Ownership carve-out (2026-09-23):** W1 implements its own requests W1-1 and W1-2:
the result-building sites in `reasoning_context.py` (a language-free `meaning` key on
every result with `answer`, plus a stable conversation id) and the return points of
`engine.answer` routed through `realize()`. G1 keeps the parsing, repair, and matching
code in both files and writes a request instead of touching those sites.

**Exam rule:** the frozen 52 are scored once per round by the owner. No development
chat opens them or runs them. Development uses its own dev set (G1.1).

Parallel at most: four chats (raised from three by the owner on 2026-09-23). Each in its own hidden checkout under
`.claude/worktrees/`, never a sibling folder. The owner merges between goals.

## Unfreezing

Only the owner unfreezes, by editing this file and the plan file. A session
that finds a frozen area blocking its goal writes `docs/requests/<goal>-<n>.md`
and continues on what does not depend on it.
