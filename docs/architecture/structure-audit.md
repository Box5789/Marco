# Structure audit — refactor Phase 0

Goal: `docs/ko/2026-09-22-structure-audit-goal.md`. Written 2026-09-22.
Audited commit: **`6195040`** (`main` = `origin/main`). Nothing was moved, renamed or
deleted. New files: this document, `docs/architecture/target-map.json`,
`tools/import_graph.py`. Edited: `README.md` (architecture diagrams, layout by
subsystem, routing rows re-measured at `6195040`).

Every number below is re-measurable:

```bash
python tools/import_graph.py --rev 6195040                  # A2
python tools/import_graph.py --rev 6195040 --uses engine    # A3 callers
python tools/import_graph.py --rev 6195040 --targets docs/architecture/target-map.json   # A1 rows, A6 layers
```

The tool reads blobs straight from git (`git cat-file --batch`), so it measures a
commit, not whatever the shared working tree holds.

## A0. Baseline

- Commit `6195040`, `main`, 2026-09-22 09:57 +0900. 177 `.py` files in the tree,
  **61 at the root, 31,396 lines at the root.**
- Full suite, once:

  ```bash
  git archive 6195040 | tar -x -C <scratch>/a0      # export of the commit
  # + this clone's gitignored files (not __pycache__/.mypy_cache/.pytest_cache), APFS-cloned in
  #   (data/위키 90M corpus, data/models, .nai-tools, NAI.kgpack, .vec_*.npz caches)
  cd <scratch>/a0 && KG_ENCODER=문자 python -m pytest -q -p no:cacheprovider -rfEs
  ```

  Python 3.13.9 (anaconda), macOS 26 (Darwin 25.6.0).

  | passed | failed | skipped | errors | time | exit |
  | --- | --- | --- | --- | --- | --- |
  | **770** | **4** | 0 | 0 | 1206.91 s (20:06) | 1 |

  | Failing test | Cause | Also fails elsewhere? |
  | --- | --- | --- |
  | `tests/test_alma_integrated_reproduction.py:31` | asserts `process_max_rss_supported is False`; macOS reports RSS | passes on the Windows clone (plan §5: 766 passed there) — machine-dependent |
  | `tests/test_experience_concept_reproduction.py:22` | intentionally-wrong run reports `execution_error == 1`, test wants 0 | not investigated (found, not fixed) |
  | `tests/test_response_composer.py:153` (`…compare…`) | verdict `입력이해실패` ≠ `원문정의비교` | known machine-dependent (plan §5) |
  | `tests/test_response_composer.py` (`…summary…`) | same family: `'manager'` ≠ `extractive_grounded_response` | known machine-dependent (plan §5) |

- Two more baselines on the same export, used as Phase 3 gates:

  | Command | Exit | Time | Output |
  | --- | --- | --- | --- |
  | `KG_ENCODER=문자 python engine.py --check` | **1** | 3 s | `AssertionError: graphs/graph_일상추론.kg` at engine.py:4768 (`2등인 사람을 추월했습니다` expected to route to `graph_순위_추월.kg`) |
  | `KG_ENCODER=문자 python routing_benchmark.py --답` | 0 | 185 s | `제자리 2807/6912 (40.6%)  답함 5259 (76.1%)  밖 거절 24/24` — the whole stdout, 92 bytes, sha1 `d1937d7e1eb111e46b04da6f033a75049fb0cf32` |

- Why an export and not the working tree: at audit time the shared tree held another
  session's uncommitted merge of `repair-and-english` (reset at 15:12 by that session,
  files still modified). Neither state is a commit. The export is the commit plus
  this clone's ignored data, so the count is reproducible on this machine.
- Lines per root file (`wc -l`, commit `6195040`):

```text
engine                 6072  act                     343  alma_cli                123
reasoning_context      2971  graph_inference         336  universal_agent         119
explain                2311  kgpack                  308  proof_chunking          104
alma_runtime           2071  semantic_parser         294  expression_graph        103
vision                 1725  purpose_graph           288  passage_classifier       97
web_learn              1344  kgbin                   262  expression_learning      93
relational_semantics   1170  graph_dialogue          259  rule_learning            91
codegen                 982  response_composer       257  verbal_expression        87
build                   971  pack_model              221  conversation_store       85
document_visual         643  goal_runtime            210  document_vlm             81
frame_induction         607  alias_diag              188  affect_state             65
hangul                  586  routing_benchmark       180  semantic_feedback        58
self_authoring          579  local_definitions       179  document_pose            58
encoder                 567  alma_environment        177  document_objects         44
document_kg             506  nai                     168  passage_components       38
language_components     502  state_engine            164  numeral_semantics        35
action_runtime          453  intelligence_check      151  output_contracts         20
experience_concepts     401  progress                144  conftest                 14
self_learning           360  autocoder               144  situation_reasoner       13
yardstick               353  input_understanding     140
dict_extract            344  cache_tool              137
```

---

## A2. Import graph

Tool: `tools/import_graph.py` (new, stdlib only). AST walk of every `.py`; imports
resolved the way the repo runs (root on `sys.path` via `conftest.py`; a script's
own directory first; relative imports inside packages; a bare name that matches
exactly one module in a plain directory counts as a `sys.path.insert` import).
Edge kinds: `top` (runs at import), `lazy` (inside a function), `main` (under
`if __name__ == "__main__":`), `typing`, `dynamic` (`import_module("literal")`).
A unit is one root file, or one top-level directory.

```text
source: 6195040 (6195040)
python files: 177  root .py: 61  units: 67 (dirs: bench, collectors, docs, tests, tools, views)
module edges: 364 {'lazy': 132, 'main': 2, 'top': 230}  unit edges: 194  root->root: runtime 111, top 44

cycles                  SCCs  sizes                      elementary
  all_modules_runtime      2  6,2                        5
  all_modules_top          0  -                          0
  root_modules_runtime     2  6,2                        5
  root_modules_top         0  -                          0
  units_runtime            2  6,2                        5
  units_top                0  -                          0

unit                              kind     files     out_u      in_u     out_m      in_m   in_root  in_tests   top_out  lazy_out
engine                            root         1         9        16         9        40        13        22         2         7
relational_semantics              root         1         7        10         7        29         8        19         0         7
kgpack                            root         1         1         5         1        22         2        13         0         1
reasoning_context                 root         1         9         5         9        21         2        17         2         7
graph_inference                   root         1         0         9         0        17         6         7         0         0
hangul                            root         1         0        13         0        15        11         3         0         0
state_engine                      root         1         2         6         2        13         3         7         0         2
encoder                           root         1         2        10         2        12         7         3         0         2
language_components               root         1         0         8         0        12         6         5         0         0
alma_runtime                      root         1         6         4         6        11         1         4         3         3
pack_model                        root         1         5         8         5        11         5         3         2         3
semantic_parser                   root         1         2         4         2        10         1         6         0         2
conversation_store                root         1         0         3         0         7         0         2         0         0
numeral_semantics                 root         1         0         6         0         6         5         1         0         0
progress                          root         1         0         6         0         6         6         0         0         0
build                             root         1         2         5         2         5         5         0         1         1
document_visual                   root         1         0         3         0         5         1         1         0         0
input_understanding               root         1         1         3         1         5         0         3         1         0
alma_environment                  root         1         0         3         0         4         1         1         0         0
experience_concepts               root         1         0         3         0         4         1         1         0         0
explain                           root         1         3         4         3         4         3         0         2         1
expression_graph                  root         1         1         4         1         4         3         1         0         1
goal_runtime                      root         1         1         2         1         4         0         3         1         0
local_definitions                 root         1         0         3         0         4         1         2         0         0
action_runtime                    root         1         2         2         2         3         1         2         0         2
document_kg                       root         1         2         2         2         3         0         2         1         1
expression_learning               root         1         1         2         1         3         1         2         0         1
frame_induction                   root         1         3         3         3         3         2         1         2         1
output_contracts                  root         1         1         3         1         3         2         1         0         1
proof_chunking                    root         1         1         3         1         3         1         1         1         0
rule_learning                     root         1         1         3         1         3         2         1         1         0
self_authoring                    root         1         6         3         6         3         2         0         4         2
web_learn                         root         1         3         3         3         3         1         1         2         1
yardstick                         root         1         4         2         4         3         1         0         2         2
act                               root         1         1         2         1         2         2         0         1         0
affect_state                      root         1         1         2         1         2         0         1         1         0
dict_extract                      root         1         2         2         2         2         1         0         0         2
kgbin                             root         1         2         2         2         2         1         1         0         0
passage_components                root         1         0         2         0         2         1         1         0         0
purpose_graph                     root         1         3         2         3         2         1         0         1         2
response_composer                 root         1         0         2         0         2         0         1         0         0
routing_benchmark                 root         1         2         2         2         2         2         0         2         0
graph_dialogue                    root         1         3         1         3         1         0         1         1         2
nai                               root         1         3         1         3         1         0         1         0         3
passage_classifier                root         1         1         1         1         1         0         1         0         1
verbal_expression                 root         1         2         1         2         1         1         0         1         1
alias_diag                        root         1         3         0         3         0         0         0         2         1
alma_cli                          root         1         4         0         4         0         0         0         2         2
autocoder                         root         1         1         0         1         0         0         0         1         0
cache_tool                        root         1         1         0         1         0         0         0         0         1
codegen                           root         1         1         0         1         0         0         0         0         1
conftest                          root         1         0         0         0         0         0         0         0         0
document_objects                  root         1         0         0         0         0         0         0         0         0
document_pose                     root         1         0         0         0         0         0         0         0         0
document_vlm                      root         1         0         0         0         0         0         0         0         0
intelligence_check                root         1         2         0         2         0         0         0         2         0
self_learning                     root         1         2         0         2         0         0         0         0         2
semantic_feedback                 root         1         2         0         2         0         0         0         1         1
situation_reasoner                root         1         1         0         1         0         0         0         1         0
universal_agent                   root         1         1         0         1         0         0         0         1         0
vision                            root         1         0         0         0         0         0         0         0         0
bench                              dir        26        18         2        18        15         0        14        27        20
views                              dir         1        16         2        16        15         0        11        14         2
tests                              dir        75        38         1        50         1         0         0       131        36
collectors                         dir         3         0         0         0         0         0         0         0         0
docs                               dir         4         5         0         5         0         0         0         5         0
tools                              dir         7         4         0         4         0         0         0         2         2

root_modules_runtime SCC (6): expression_graph frame_induction output_contracts pack_model relational_semantics verbal_expression
root_modules_runtime SCC (2): self_authoring yardstick

pack-declared: styles/한국어.json -> graph_dialogue:backend
resolved via sys.path insert: tests/test_answer_quality_scoring.py: answer_quality -> bench.answer_quality
unresolved dynamic: self_learning.py:139: import_module('위키')
third-party (bench): pandas
third-party (build): kiwipiepy
third-party (document_objects): ultralytics
third-party (document_pose): ultralytics
third-party (document_visual): PIL numpy
third-party (document_vlm): PIL qwen_vl_utils torch transformers
third-party (encoder): numpy sentence_transformers
third-party (engine): numpy
third-party (explain): numpy
third-party (kgbin): numpy
third-party (routing_benchmark): numpy
third-party (tests): PIL numpy pytest
third-party (vision): PIL numpy scipy skimage
third-party (web_learn): kiwipiepy
```

Cycles, with the lines that make them (all `lazy`; none can fail at import time):

| SCC | Edges |
| --- | --- |
| 6 modules | `pack_model.py:186` → relational_semantics, `:190` → expression_graph, `:195` → output_contracts; `relational_semantics.py:51`, `output_contracts.py:10`, `verbal_expression.py:14` → `pack_model.development_model`; `relational_semantics.py:805,860,891` → frame_induction; `frame_induction.py:23` → relational_semantics (top); `expression_graph.py:12` → verbal_expression |
| 2 modules | `self_authoring.py:261` → yardstick; `yardstick.py:55` → self_authoring |
| not a cycle | `engine.py:2740,3071` → kgbin (lazy); `kgbin.py:239` → engine only under `__main__` |

Importing modules, tests included: `engine` 40 (22 tests), `relational_semantics` 29,
`kgpack` 22, `reasoning_context` 21, `graph_inference` 17, `hangul` 15. `views/kgpack_ui` imports 16.
Entry points with 0 importers: `alias_diag`, `alma_cli`, `autocoder`, `cache_tool`, `codegen`,
`intelligence_check`, `self_learning`, `semantic_feedback`, `situation_reasoner`, `universal_agent`,
`vision`, and 3 subprocess scripts (`document_objects`, `document_pose`, `document_vlm`).

---

## A1. Every root file classified

Read from the code (module docstring, every top-level definition and its
docstring, and the import sites above), not from the name. Target paths use the
A6 layout. "+ split" rows name the primary target; the line ranges are in
`target-map.json` `splits` and in the reason column.

| File | Lines | What it does | Target | Conf | Reason / split |
| --- | --- | --- | --- | --- | --- |
| `act.py` | 343 | Runs graph-chosen actions: matches an observation/error to an evidence node, walks -증명->/-충족-> to a registered tool, observe–recover–advance loop, trace sidecar | `marco/host/act.py` | sure | Executes host actions, so it sits with the permission boundary |
| `action_runtime.py` | 453 | JSON action-program contract: compile an induced definition, bind roles, execute emit/lookup/select/compute/when/call into one event's effects | `marco/reasoning/actions.py` | sure |  |
| `affect_state.py` | 65 | Session-only affect expression mode from the user's own affect words (pack-declared); `decorate` prefixes a verified answer; never changes facts | `marco/language/realizer/affect.py` | unsure | Expression-only today (Expression Selector input). Moves to `cognition/` if affect ever feeds decisions |
| `alias_diag.py` | 188 | Diagnostic CLI: nodes that absorb other nodes' phrasings, nodes short of aliases | `tools/alias_diag.py` | sure |  |
| `alma_cli.py` | 123 | ALMA command line over `AlmaRuntime` (turns, memory, recall, mental, cycles, environment, backup) | `alma/cli.py` | sure |  |
| `alma_environment.py` | 177 | Bounded local observation environment for ALMA: read adapters, persisted run advanced by a step budget | `alma/environment.py` | sure |  |
| `alma_runtime.py` | 2071 | `AlmaRuntime`: personal state (logs, episodic/semantic/procedural memory, mental states, goals, affect, preferences, capabilities, cycles, rule/asset/shortcut proposals) over `ReasoningContext` | `alma/runtime.py` | sure | Target is certain; §4.5 split (identity/emotion/preference/memory) is Phase 3+ |
| `autocoder.py` | 144 | Demo tool set for `act.py`: assembles code from templates (two deliberately buggy), runs it, applies graph-chosen fixes | `experiments/autocoder.py` | sure |  |
| `build.py` | 971 | Text folder → concept graph JSON: passage/article splitting, compound-noun concepts (kiwipiepy), definitions, genus/target, concept net, excerpts | `marco/knowledge/ingest/text.py` | sure |  |
| `cache_tool.py` | 137 | Reports vector caches and deletes dead ones (keys are content hashes) | `tools/cache_tool.py` | sure |  |
| `codegen.py` | 982 | Language-neutral algorithm blueprints → source in code dialects (`styles/코드`), prose ↔ blueprint parsing, mental evaluation, mutate/fix search, regressions. 0 importers | `experiments/codegen.py` | sure |  |
| `conftest.py` | 14 | Puts the repo root on `sys.path` for pytest | root (stays) | sure | Stays at root |
| `conversation_store.py` | 85 | JSON store of projects and chats at `.nai/conversations.json` | `marco/storage/conversations.py` | sure |  |
| `dict_extract.py` | 344 | National dictionary XML → genus/action/target chains, schema/concurrency seeds, sense picking | `marco/knowledge/ingest/dictionary.py` | sure |  |
| `document_kg.py` | 506 | PDF/PPTX → conservative claim graph with page positions; pack-declared sentence rules; visual observations as review items | `marco/knowledge/ingest/documents.py` | sure |  |
| `document_objects.py` | 44 | Subprocess script: YOLO boxes → JSON | `marco/perception/objects.py` | sure |  |
| `document_pose.py` | 58 | Subprocess script: YOLO pose keypoints → JSON | `marco/perception/pose.py` | sure |  |
| `document_visual.py` | 643 | Image → verifiable observations: OCR merge (Vision binary + Tesseract), chart/table structure, objects, pose, contacts, spatial relations, optional VLM hypothesis | `marco/perception/visual.py` | sure |  |
| `document_vlm.py` | 81 | Local VLM adapter; output kept as hypothesis only | `marco/perception/vlm.py` | sure |  |
| `encoder.py` | 567 | `EncoderRuntime` (pack-selected), character n-gram/jamo vectors, neural model loader, embed helpers; surface ops: `view_lang`, `strip_english_shell`, `strip_fillers`, `split_fragments` | `marco/language/encoder.py` + split | sure |  |
| `engine.py` | 6072 | Argument engine: graph format, matching, judgement, sessions, router, answer entry, realization, authoring suggestions, diagnostics, selfcheck, CLI — 20 parts, see A3 | `marco/runtime/engine.py` + 19 more (A3) | sure | Split per A3 |
| `experience_concepts.py` | 401 | `ExperienceConceptStore`: bounded concept candidates abstracted from saved action events, applied only as derived classification with supporting events | `marco/learning/concepts.py` | sure |  |
| `explain.py` | 2311 | Second answer pipeline for build.py concept graphs: question intent, node/typo matching, path explanation, excerpts, procedures, code weaving, `DialogueMemory`, grading, Mermaid. Answers are guidance, not verdicts | `marco/runtime/explain.py` | unsure | Not proof explanation as §4.19 assumed. Phase 3 split: matching → knowledge/matching, `_link_form`/`fit_particle` → realization/grammar, `DialogueMemory` → cognition, `_selfcheck` (337 lines) → runtime/selfcheck |
| `expression_graph.py` | 103 | Parses a complete math expression (Python AST as syntax only) into an affine operation graph; `solve` for one variable | `marco/language/arithmetic.py` | unsure | `solve` (40 lines) is reasoning; kept with its parser while it has one caller path |
| `expression_learning.py` | 93 | Supervised paraphrase-template proposals gated by separate validation cases | `marco/learning/expressions.py` | sure |  |
| `frame_induction.py` | 607 | Reads definition bodies by aligning to known examples; particle-marked chunks; induce/apply meaning frames; `read_event`; question detection | `marco/language/frames.py` | sure |  |
| `goal_runtime.py` | 210 | `GoalRuntime`: goal text → approvable plan (work, learning, read-only web research), approval hashing, execution only through registered tools (no shell) | `marco/cognition/goals.py` + split | unsure | Planning is cognition; 147–210 (`_approve_once`, `_run`) is the host permission boundary → `marco/host/permissions.py` (W4 seam). Split in Phase 3 |
| `graph_dialogue.py` | 259 | `GraphDialogueBackend`: the pack-declared dialogue backend (`styles/한국어.json:2993` `graph_dialogue:backend`); asks the KG for dialogue words, computes request endings by inflection | `marco/runtime/graph_dialogue.py` | sure | Imports `engine`, so it sits in runtime. Pack string or a shim must follow the move |
| `graph_inference.py` | 336 | Finite positive Horn-rule closure, `current_facts` projection, replayable proof bundles | `marco/reasoning/inference.py` | sure |  |
| `hangul.py` | 586 | Hangul syllable arithmetic, jamo, particle pick/attach/strip/fix, pack-declared `inflect`, clause spans, word spans, yes/no word lists | `marco/language/hangul.py` | sure | §4.19 said `language/grammar.py`; that name is reserved for the Grammar Realizer |
| `input_understanding.py` | 140 | Structures a user utterance: segments, command/URL safety, session context, goals, via pack + `DialogueBackend` | `marco/language/understanding.py` | sure |  |
| `intelligence_check.py` | 151 | Per-ability test: out-of-domain refusal, traps, paraphrase vs control, sense, multi-turn | `bench/intelligence_check.py` | sure |  |
| `kgbin.py` | 262 | Routing index → one flat mmap-able `.kgbin` (bit packing); `unpack` | `marco/storage/kgbin.py` | sure |  |
| `kgpack.py` | 308 | `.kgpack` ZIP with manifest, SHA-256 per file, default inputs, manager graph; write/read/unpack/selfcheck | `marco/storage/kgpack.py` | sure |  |
| `language_components.py` | 502 | Language pack: path choice (`NAI_LANGUAGE`), validation of every declared section, `decode_language_pack`; `DialogueBackend`, `TemplateBackend`, `resolve_backend` | `marco/language/pack.py` + split | sure | Split: 24–403 → `pack.py`, rest → `backends.py` |
| `local_definitions.py` | 179 | Read-only sqlite index over local wiki definitions for exact "X가 뭐야" questions | `marco/knowledge/definitions.py` | sure |  |
| `nai.py` | 168 | `Conversation`/`Reply`: one chat contract over `.kg` (engine) and `.json` (explain) graphs; `--build` CLI | `marco/runtime/conversation.py` | sure | See A4 |
| `numeral_semantics.py` | 35 | Composes numbers from the pack's numeral vocabulary | `marco/language/numerals.py` | sure |  |
| `output_contracts.py` | 20 | Applies declared output constraints to a verified numeric answer | `marco/language/realizer/contracts.py` | sure |  |
| `pack_model.py` | 221 | `PackModel`: selected model's assets (language, axioms, relational model, encoder), component loader, parser/expression/format factories; `development_model()` | `marco/storage/model.py` + split | sure | Split: 202–221 `development_model` → `runtime/model.py`; its 3 callers are the 6-module cycle |
| `passage_classifier.py` | 97 | Passage-kind classifier learned from human labels (char n-grams, CV threshold) | `marco/language/passages.py` | sure |  |
| `passage_components.py` | 38 | `PassageBackend` protocol, `StatementFallback`, pack-chosen `resolve_backend` | `marco/language/passages.py` | sure |  |
| `progress.py` | 144 | Dependency-free progress bar | `marco/progress.py` | sure | Layer 0; imported by 6 root files |
| `proof_chunking.py` | 104 | Proposes/evaluates/invalidates shortcut rules for repeated Horn paths, keeping source proofs | `marco/learning/chunking.py` | sure |  |
| `purpose_graph.py` | 288 | Definition sentence → purpose-constrains-means `.kg` text; concurrent-role skeleton | `marco/knowledge/ingest/purpose.py` + split | sure | Split: 223–288 (selfcheck + CLI, uses `engine`) → `tools/purpose_graph.py` |
| `reasoning_context.py` | 2971 | `ReasoningContext`: per-conversation evidence ledger replayed per turn; definitions/programs; asks and completions; pointer resolution; incremental/correction replay; concept-relation reasoning; snapshot/restore; `turn()` | `marco/reasoning/context.py` | sure | Target certain; later split: ledger/snapshot → memory, asks/pointers → cognition |
| `relational_semantics.py` | 1170 | `RelationalParser`: compile pack examples into slot templates, `parse` sentences into facts/events, `learn`/`save` templates, `answer` by closure, `diagnose` | `marco/language/parser.py` + split | sure | Split: 1–42 → `language/facts.py`, 405–478 → `learning/templates.py`, 479–532 + 1077–1170 → `reasoning/semantics.py`, rest → `language/parser.py` |
| `response_composer.py` | 257 | Selects verified evidence sentences; summary/explanation/plan along declared preconditions, goal steps, causal chain; comparison only on certified shared attributes | `marco/language/realizer/discourse.py` | sure | Seed of the Discourse Planner |
| `routing_benchmark.py` | 180 | Held-out routing benchmark (last alias removed from the index) | `bench/routing_benchmark.py` | sure |  |
| `rule_learning.py` | 91 | Supervised Horn-rule induction from aligned, corrected proof examples | `marco/learning/rules.py` | sure | §4.19 said `learning/structural.py`; content is rule induction |
| `self_authoring.py` | 579 | Dictionary → candidate graphs → lint → gate against stolen questions → admit/revert/re-audit; round records read by the UI | `marco/learning/authoring.py` | unsure | UI calls `one_round`, so it is library; imports `engine` + 2 benchmarks at top level — 4 upward edges (A6) |
| `self_learning.py` | 360 | Wrong answers → unknown words → wiki fetch → rebuild → re-grade; `import_module("위키")` never resolves | `tools/self_learning.py` | sure | 0 importers; CLI loop |
| `semantic_feedback.py` | 58 | CLI: diagnose a question; apply supervised rule corrections to a model file | `marco/learning/feedback.py` | sure |  |
| `semantic_parser.py` | 294 | Candidate meaning JSON → validated state JSON (spans, types, relations); token-free `StructuralBackend` | `marco/language/representation.py` | sure |  |
| `situation_reasoner.py` | 13 | 13-line compatibility name forwarding to `semantic_parser`/`state_engine`. 0 importers | `marco/reasoning/state.py` | sure | Delete in Phase 5 |
| `state_engine.py` | 164 | Pure state transition/calculation over validated state JSON using KG axioms | `marco/reasoning/state.py` | sure |  |
| `universal_agent.py` | 119 | Demo tool set for `act.py`: data pipeline raising real errors | `experiments/universal_agent.py` | sure |  |
| `verbal_expression.py` | 87 | Declared phrase grammar → bounded arithmetic graph; full match only | `marco/language/arithmetic.py` | sure |  |
| `vision.py` | 1725 | Image-vocabulary experiments: gradient descriptors, LSH words, Heaps' law, SLIC region graphs, COIL-100 angle/clutter tests. 0 importers | `experiments/vision.py` | sure |  |
| `web_learn.py` | 1344 | Open-web search, page reading, topic extraction, relation evidence coverage, verified save to `.수집.jsonl`, stacking onto a graph, `ask` | `marco/knowledge/ingest/web.py` | unsure | Network fetch should become a runtime capability; overlay part stays in knowledge |
| `yardstick.py` | 353 | Frozen question set from human-authored graphs; measures with those aliases removed | `bench/yardstick.py` | sure |  |

Totals: 61 rows, 31,396 lines. Where the reading disagrees with the plan's
first-pass guess (§4.19): `relational_semantics` is mostly a parser (language), not
reasoning; `explain` is a second answer pipeline, not proof explanation; `hangul`
keeps its name because `grammar.py` is the Grammar Realizer; `rule_learning` is rule
induction, not structural learning.

---

