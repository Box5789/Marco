# MARCO 1 · Preview 1

A knowledge-graph reasoning engine that answers only from evidence, refuses what
it does not know, and creates its sentences from meaning instead of picking them
from a list. No language model anywhere in the runtime. This is a preview: the
reasoning is exact, the language coverage is not there yet, and every number
below is from the repository's own frozen benchmarks.

## What is in the file

`MARCO-1-preview.mco`, 27.2 MB, build `ff8db40`.

- 905 knowledge graphs
- Two language packs, English (default) and Korean
- The reasoning axioms and the six-layer language realizer
- Format `mco-compat v0`: a deterministic container around a MARCO pack, read
  by the `mco` Python package. The native MCO binary format is not in this
  release.

## Run it

```sh
pip install -e .
python -m mco inspect MARCO-1-preview.mco
printf 'Minsu has five apples, and Jiyeon has two.\nMinsu gave Jiyeon two.\nHow many does Jiyeon have now?\n' \
  | python -m mco run MARCO-1-preview.mco
```

```
Recorded. Jiyeon has 2 apples.
Recorded. Minsu gave Jiyeon 2 apples. Now Minsu has 3 apples and Jiyeon has 4.
4 apples.
```

## Measured, frozen benchmarks, never used for development

| What | Result |
| --- | --- |
| Reasoning: 114 frozen problems, chains, totals, comparisons, negation, time order, corrections, restarts | 146 of 149 parsed questions correct, 98%, **0 wrong** |
| Refuses questions outside its knowledge | 24 of 24 |
| Fixed 7-step state dialogue, Korean and English | 7 of 7 each |
| Unseen dialogues: 52 frozen, 108 answerable turns | **21 correct, 19%**. 86 holds, 1 wrong |
| Replies composed from meaning on the frozen dialogues | 207 of 340; the rest are hold messages not yet routed through the realizer |
| Median turn, peak memory | 32 ms, 137 MB, one dependency |

Read the two dialogue numbers together: when MARCO understands a sentence it
almost never gets the reasoning wrong, and on phrasings it has not been taught it
holds rather than guesses. Teaching it the rest of the grammar is the work in
progress; the gate for MARCO 1 proper is 90% on that unseen set.

## Not in this release

POLO automation, the native MCO binary format with overlay and snapshot,
autonomous planning and self-modification, and ALMA persona features. All are
frozen until MARCO 1 passes its gate.

## Reports

`docs/ko/dialogue-gate-2026-09-22/` (round 2), `docs/ko/reasoning-gate-2026-09-24/`
(round 2), `README.md` for the architecture and the language pipeline.
