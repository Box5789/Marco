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

## The queue (replaces plan file §2 items 3–5)

| # | Goal | File | State |
| --- | --- | --- | --- |
| S1 | Structure audit, read-only | `docs/ko/2026-09-22-structure-audit-goal.md` | running |
| F1 | Frozen dialogue set: 50 unseen dialogues + scorer | `docs/ko/2026-09-22-frozen-dialogue-set-goal.md` | may start now |
| P0 | Integrate: commit `mco/` and the plan docs, merge `repair-and-english`, fix the 5 tests it breaks | `docs/ko/2026-09-22-p0-integration-goal.md` | card posted; owner merges the result to `main` |
| P0b | Merge the Windows ALMA branch when it arrives | owner, by hand | waiting on Windows |
| S2-min | Package skeleton + `marco/language/` seam only | `docs/ko/2026-09-22-s2-minimal-goal.md` | after S1, P0 |
| S3 | Test hygiene and speed | `docs/ko/2026-09-22-test-speed-goal.md` | after P0 |
| W1 | Language realizer, both languages | `docs/ko/2026-09-22-realization-next-goal.md` | after S2-min, F1 |
| G | Gate loop: run the 50, fix, repeat to 90% | written when W1 reports | after W1 |
| D1 | Docs: README truth + per-package docs | `docs/ko/2026-09-22-docs-goal.md` | alongside W1 |

Parallel at most: three chats. Each in its own hidden checkout under
`.claude/worktrees/`, never a sibling folder. The owner merges between goals.

## Unfreezing

Only the owner unfreezes, by editing this file and the plan file. A session
that finds a frozen area blocking its goal writes `docs/requests/<goal>-<n>.md`
and continues on what does not depend on it.
