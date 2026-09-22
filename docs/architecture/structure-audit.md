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

