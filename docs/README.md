# Documentation

Where each kind of document lives. The project overview, the measured numbers
and the release status are in the root [README](../README.md).

## Architecture (`docs/architecture/`)

One document per package. Each begins with the five template headings: Purpose,
Owns, Does not own, Depends on, Public interface.
`python tools/doc_facts.py packages` prints how many packages lack one.

| Document | Package |
| --- | --- |
| [marco.md](architecture/marco.md) | `marco` |
| [marco.language.md](architecture/marco.language.md) | `marco.language` |
| [marco.language.realizer.md](architecture/marco.language.realizer.md) | `marco.language.realizer` |
| [mco.md](architecture/mco.md) | `mco` |
| [mco.backends.md](architecture/mco.backends.md) | `mco.backends` |

| Document | What |
| --- | --- |
| [structure-audit.md](architecture/structure-audit.md) | Structure audit of commit `6195040`: root files by subsystem, import graph, `engine.py` parts, target layout, phase plan |
| [target-map.json](architecture/target-map.json) | Target package for every root module, read by `tools/import_graph.py` |

## `mco` (`docs/mco/`)

| Document | What |
| --- | --- |
| [README.md](mco/README.md) | User guide: install, Python API, CLI, the `.mco` file in this release |
| [api.md](mco/api.md) | Stability contract and how to write a backend |

## English (`docs/en/`)

Index: [docs/en/README.md](en/README.md). Development guide, graph authoring
guide, design record, project direction, explanation-engine guide, legal-theory
guide.

## Korean design records (`docs/ko/`)

The source records. Dated files are plans, goals and decisions; dated folders
hold the measurements that a goal recorded.

| Document | What |
| --- | --- |
| [2026-09-22-freeze-decision.md](ko/2026-09-22-freeze-decision.md) | What is frozen until MARCO 1 ships, the gate, the goal queue |
| [2026-09-22-plans-organized.md](ko/2026-09-22-plans-organized.md) | The organized plan; §4.12 is the architecture document template |
| [dialogue-gate-2026-09-22/](ko/dialogue-gate-2026-09-22/README.md) | The frozen 52-dialogue gate set, its scorer, the baseline |
| [README-full.md](ko/README-full.md) | The long Korean README |
| [README.md](ko/README.md) | Korean documentation index |
| [그래프-저작-프롬프트.md](ko/그래프-저작-프롬프트.md) | Graph authoring guide |
| [alma-0.1.md](ko/alma-0.1.md) | ALMA 0.1 research loop |

Goal files are the dated `*-goal.md` files. The owner edits the goal and plan
files; other sessions read them.
