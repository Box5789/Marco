"""The frozen MARCO 1 dialogue set (F1) and its scorer.

These tests check the exam and the scorer, not the engine: the gate number
itself comes from ``python bench/dialogue_gate.py run``.
"""
import copy
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench"))
import dialogue_gate as gate  # noqa: E402


@pytest.fixture(scope="module")
def dialogues():
    return gate.load()


def test_f1_1_counts_schema_and_replay(dialogues):
    assert gate.validate(dialogues) == []
    assert len(dialogues) >= 50
    assert sum(d["language"] == "ko" for d in dialogues) >= 20
    assert sum(d["language"] == "en" for d in dialogues) >= 20
    for d in dialogues:
        assert 4 <= len(d["turns"]) <= 10
        assert (gate.DATASET / (d["id"] + ".json")).is_file()
        for t in d["turns"]:
            assert t["label"] in gate.LABELS
            assert {"act", "entity", "quantity", "relation", "evidence"} <= set(t["expect"])


def test_f1_2_every_category_in_five_dialogues_and_variation(dialogues):
    table = gate.category_table(dialogues)
    for name in gate.CATEGORIES:
        assert table["categories"][name]["dialogues"] >= 5, name
    for key in gate.VARIATION_KEYS:
        assert len(table["variation"][key]) >= 2, key
    assert len(table["initial_values_used"]) >= 5


@pytest.mark.skipif(shutil.which("git") is None or not (ROOT / ".git").exists(), reason="needs git")
def test_f1_3_no_full_sentence_shared_with_head(dialogues):
    result = gate.overlaps(dialogues, rev="HEAD")
    assert result["files"] > 100 and result["sentences"] > 300
    assert result["overlaps"] == []


def test_full_sentence_boundary():
    assert gate._full_sentence_at('x = "how many now?"', "how many now")
    assert not gate._full_sentence_at("so how many now and later", "how many now")


def test_perfect_answers_score_everything_correct(dialogues):
    report = gate.score(dialogues, gate.synthesize(dialogues, "perfect"))
    assert report["failures"] == []
    assert report["gate"]["correct"] == report["gate"]["n"] and report["gate"]["passed"]
    assert report["dialogues_fully_passed"] == len(dialogues)


def test_f1_5_wrong_answers_file_scores_zero(dialogues, tmp_path):
    path = tmp_path / "wrong.json"
    import json
    path.write_text(json.dumps({"answers": gate.synthesize(dialogues, "wrong")}, ensure_ascii=False), "utf-8")
    report = gate.score(dialogues, json.loads(path.read_text("utf-8"))["answers"])
    assert report["gate"]["n"] > 0 and report["gate"]["correct"] == 0
    assert all(row["bucket"] != "correct" for row in report["rows"])
    assert report["violations"]["confident_without_evidence"]["count"] > 0


def _swappable(d):
    rows = [t for t in d["turns"] if t["label"] == "answerable" and t["expect"]["relation"] in ("count", "total")]
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if a["expect"]["quantity"] != b["expect"]["quantity"]:
                return a["n"], b["n"]
    return None


def test_f1_5_swapping_two_quantities_changes_exactly_that_dialogue(dialogues):
    answers = gate.synthesize(dialogues, "perfect")
    before = gate.score(dialogues, answers)
    tried = 0
    for index, d in enumerate(dialogues):
        pair = _swappable(d)
        if not pair:
            continue
        tried += 1
        changed = copy.deepcopy(dialogues)
        x, y = (changed[index]["turns"][n - 1]["expect"] for n in pair)
        x["quantity"], y["quantity"] = y["quantity"], x["quantity"]
        after = gate.score(changed, answers)
        assert after["gate"]["correct"] == before["gate"]["correct"] - 2
        assert after["dialogues_fully_passed"] == before["dialogues_fully_passed"] - 1
        diff = {(r["dialogue"], r["n"]) for r, s in zip(before["rows"], after["rows"]) if r["bucket"] != s["bucket"]}
        assert diff == {(d["id"], n) for n in pair}
    assert tried >= 40


def test_buckets_are_kept_apart(dialogues):
    d = next(d for d in dialogues if d["id"] == "en-01")
    answers = gate.synthesize([d], "perfect")
    rows = answers["en-01"]
    rows[2] = dict(rows[2], verdict="조건부족", known=False)                  # hold
    rows[3] = {"error": "RuntimeError: boom"}                                 # execution error
    rows[4] = dict(rows[4], answer="Either 11 or 12.", facts=[])              # unverifiable
    report = gate.score([d], answers)
    g = report["gate"]
    assert (g["n"], g["correct"], g["hold"], g["execution_error"], g["unverifiable"]) == (3, 0, 1, 1, 1)
    assert "every turn labelled answerable" in g["denominator"]


def test_retracted_value_and_evidence_are_caught(dialogues):
    d = next(d for d in dialogues if d["id"] == "en-03")
    answers = gate.synthesize([d], "perfect")
    rows = answers["en-03"]
    retracted = d["turns"][3]["expect"]["retracted_quantity"]
    rows[3] = dict(rows[3], answer="%d." % retracted)
    rows[4] = dict(rows[4], facts=[dict(rows[4]["facts"][0], evidence=["To Dev, Marta passed three cookies"])])
    report = gate.score([d], answers)
    assert report["violations"]["retracted_evidence_used"]["count"] == 2


def test_numerals_read_in_both_languages():
    assert gate.quantities(gate.asserted('[수선] 원문 "구슬은 18개" (비용 1/2). 5개입니다.')) == {5}
    assert gate.quantities("스물두 개") == {22} and gate.quantities("한결이는 세아랑") == set()
    assert gate.quantities("twenty-two crates") == {22} and gate.quantities("the other one") == set()


def test_f1_7_directory_hash_is_frozen():
    assert gate.FROZEN.is_file()
    assert gate.tree_hash() == gate.frozen_hash()


def test_ui_turn_handler_path_runs_one_dialogue(dialogues):
    """The real entry (AppState.turn) plays one dialogue and every turn gets an observation."""
    d = next(d for d in dialogues if d["id"] == "ko-01")
    answers = gate.run([d])
    assert len(answers["ko-01"]) == len(d["turns"])
    assert all(("error" in row) or ("phase" in row) for row in answers["ko-01"])
    report = gate.score([d], answers)
    assert report["gate"]["n"] == 3
