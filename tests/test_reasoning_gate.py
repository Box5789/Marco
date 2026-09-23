"""The frozen reasoning set (F2) and its scorer.

These tests check the set and the scorer, not the engine: the gate number
itself comes from ``python bench/reasoning_gate.py run``.
"""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench"))
import reasoning_gate as rg  # noqa: E402


@pytest.fixture(scope="module")
def problems():
    return rg.load()


def by_id(problems, pid):
    return next(p for p in problems if p["id"] == pid)


def test_f2_1_counts_schema_and_replay(problems):
    assert rg.validate(problems) == []
    table = rg.tables(problems)
    assert table["problems"] >= 100
    assert all(n >= 40 for n in table["by_language"].values())
    for kind in rg.KINDS:
        assert sum(row["problems"] for row in table["kinds"][kind].values()) >= 8, kind
    for p in problems:
        assert (rg.DATASET / (p["id"] + ".json")).is_file()
        for q in p["questions"]:
            assert q["expect"]["type"] in rg.EXPECT_TYPES
            assert q["derivation"]["rules"] and isinstance(q["derivation"]["facts"], list)


def test_f2_1_expectations_are_structures_not_sentences(problems):
    for p in problems:
        sentences = {s["say"] for s in p["setup"]} | {q["say"] for q in p["questions"]}
        for q in p["questions"]:
            flat = json.dumps(q["expect"], ensure_ascii=False)
            assert not any(sentence in flat for sentence in sentences), (p["id"], q["q"])
            assert not {"answer", "text", "reply", "say"} & set(q["expect"])


def test_f2_1_validation_catches_an_expectation_that_does_not_replay(problems):
    broken = copy.deepcopy(by_id(problems, "en-transfer-01"))
    broken["questions"][0]["expect"]["value"] += 1
    assert any("does not replay" in item for item in rg.validate([broken]))
    broken = copy.deepcopy(by_id(problems, "ko-negation-01"))
    broken["setup"][0]["events"][0]["polarity"] = True       # now the statements conclude it
    assert any("concluded" in item for item in rg.validate([broken]))


def test_f2_1_no_full_sentence_shared_with_the_dialogue_sets(problems):
    """Checked on disk; the frozen dialogues are read by the overlap script only and never printed."""
    result = rg.overlap(problems)
    assert {"data/benchmarks/dialogues_v1", "data/benchmarks/dialogues_dev"} <= set(result["checked"])
    assert result["sentences"] > 400
    assert result["overlaps"] == []
    assert all(set(row) == {"problem", "turn", "file"} for row in result["overlaps"])


def test_perfect_answers_score_everything_correct(problems):
    report = rg.score(problems, rg.synthesize(problems, "perfect"))
    assert report["failures"] == []
    assert report["questions"]["correct"] == report["questions"]["n"] == sum(len(p["questions"]) for p in problems)
    assert report["gate"]["passed"] and report["gate"]["unparsed"] == 0


def test_f2_3_a_wrong_expected_answers_file_scores_zero(problems, tmp_path):
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"answers": rg.synthesize(problems, "perfect")}, ensure_ascii=False), "utf-8")
    expected = tmp_path / "expected.json"
    expected.write_text(json.dumps(rg.wrong_expectations(problems), ensure_ascii=False), "utf-8")
    out = tmp_path / "report.json"
    assert rg.main(["score", str(answers), "--expected", str(expected), "--report-out", str(out)]) == 0
    report = json.loads(out.read_text("utf-8"))
    assert report["questions"]["n"] > 0 and report["questions"]["correct"] == 0
    assert report["gate"]["correct"] == 0 and not report["gate"]["passed"]
    # the other direction: wrong answers against the frozen expectations
    wrong = rg.score(problems, rg.synthesize(problems, "wrong"))
    assert wrong["questions"]["correct"] == 0 and wrong["questions"]["wrong"] > 0


def _count_questions(problems):
    return [(p["id"], q["q"], q["expect"]["value"]) for p in problems for q in p["questions"]
            if q["expect"]["type"] == "count"]


def test_f2_3_swapping_two_expected_values_changes_exactly_those_problems(problems):
    answers = rg.synthesize(problems, "perfect")
    before = rg.score(problems, answers)
    counts = _count_questions(problems)
    tried = 0
    for (pa, qa, va), (pb, qb, vb) in zip(counts, counts[1:]):
        if pa == pb or va == vb:
            continue
        tried += 1
        expected = {p["id"]: [copy.deepcopy(q["expect"]) for q in p["questions"]] for p in problems}
        expected[pa][qa - 1]["value"], expected[pb][qb - 1]["value"] = vb, va
        after = rg.score(problems, answers, expected=expected)
        changed = {(r["problem"], r["q"]) for r, s in zip(before["rows"], after["rows"]) if r["bucket"] != s["bucket"]}
        assert changed == {(pa, qa), (pb, qb)}
        assert {r["problem"] for r in after["problem_rows"] if r["bucket"] != "correct"} == {pa, pb}
        assert after["gate"]["correct"] == before["gate"]["correct"] - 2
    assert tried >= 20


def test_f2_3_a_failed_setup_statement_is_unparsed_not_wrong(problems):
    p = by_id(problems, "en-correct-01")
    answers = rg.synthesize([p], "wrong")               # every question would be wrong ...
    answers[p["id"]][0] = dict(answers[p["id"]][0], verdict="입력이해실패", answer="not read")  # ... but setup 1 failed
    report = rg.score([p], answers)
    assert {r["bucket"] for r in report["rows"]} == {"unparsed"}
    assert report["questions"]["wrong"] == 0 and report["questions"]["parsed"] == 0
    assert report["unparsed"][0]["n"] == 1 and report["unparsed"][0]["say"] == p["setup"][0]["say"]
    assert report["gate"]["unparsed"] == 1 and report["gate"]["parsed"] == 0


def test_f2_3_an_undeclared_setup_phrasing_lands_in_unparsed_not_wrong(problems):
    """Through the real UI entry: a setup statement in a phrasing no pack declares is not recorded."""
    chosen = [copy.deepcopy(by_id(problems, "en-count-01")), copy.deepcopy(by_id(problems, "ko-count-01"))]
    chosen[0]["setup"][0]["say"] = "Nadia keeps a dozen or so shells in a tin by the window."
    chosen[1]["setup"][0]["say"] = "보람은 창가 깡통에 단추를 한 줌쯤 모아 둔다."
    report = rg.score(chosen, rg.run(chosen))
    assert [r["bucket"] for r in report["rows"]] == ["unparsed", "unparsed"]
    assert report["questions"]["wrong"] == 0
    assert {("en-count-01", 1), ("ko-count-01", 1)} <= {(u["problem"], u["n"]) for u in report["unparsed"]}
    for row, p in zip(report["rows"], chosen):
        assert row["failed_statements"][0] == {"n": 1, "say": p["setup"][0]["say"],
                                               "reply": row["failed_statements"][0]["reply"]}
    assert report["gate"]["unparsed"] == 2


def test_buckets_are_kept_apart(problems):
    p = by_id(problems, "en-correct-01")
    answers = rg.synthesize([p], "perfect")
    rows = answers[p["id"]]
    turns = rg.script(p)
    index = {t["ref"]: i for i, t in enumerate(turns) if t["role"] == "question"}
    rows[index[1]] = dict(rows[index[1]], verdict="조건부족", known=False)      # hold
    rows[index[2]] = {"error": "RuntimeError: boom"}                            # execution error
    rows[index[3]] = dict(rows[index[3]], answer="6.", facts=[])                # the retracted value
    report = rg.score([p], answers)
    assert [(r["bucket"], r["reason"].split(":")[0]) for r in report["rows"]] == [
        ("hold", "held"), ("execution_error", "RuntimeError"), ("wrong", "retracted_value")]
    assert "parsed questions" in report["questions"]["denominator"]
    assert report["problem_rows"][0]["bucket"] == "wrong"


def test_retracted_evidence_is_wrong(problems):
    p = by_id(problems, "en-correct-01")
    answers = rg.synthesize([p], "perfect")
    last = len(rg.script(p)) - 1
    fact = dict(answers[p["id"]][last]["facts"][0], evidence=["Xan gave Yara 3 cookies."])
    answers[p["id"]][last] = dict(answers[p["id"]][last], facts=[fact])
    report = rg.score([p], answers)
    assert report["rows"][-1]["bucket"] == "wrong" and report["rows"][-1]["reason"] == "retracted_evidence"


def test_a_hold_is_correct_only_when_it_names_what_is_missing(problems):
    p = by_id(problems, "en-missing-01")
    q = p["questions"][0]
    held = {"phase": "answer", "verdict": "조건부족", "known": False, "facts": []}
    assert rg.score_question(p, q, dict(held, answer="The location of Lior was never stated."))[0] == "correct"
    assert rg.score_question(p, q, dict(held, answer="Not enough to decide."))[0] == "hold"
    assert rg.score_question(p, q, dict(held, verdict="입력이해실패", answer="Lior?"))[0] == "hold"
    assert rg.score_question(p, q, dict(held, answer='I could not read "Lior is where?".'))[0] == "hold"
    assert rg.score_question(p, q, dict(held, verdict="계산완료", known=True, answer="In the kitchen, Lior."))[0] == \
        "wrong"


def test_cannot_be_concluded_is_correct_only_without_a_conclusion(problems):
    p = by_id(problems, "ko-negation-01")
    q = p["questions"][0]
    base = {"phase": "answer", "facts": []}
    assert rg.score_question(p, q, dict(base, verdict="조건부족", known=False, answer="결정할 수 없습니다."))[0] == \
        "correct"
    assert rg.score_question(p, q, dict(base, verdict="계산완료", known=True, answer="윤슬입니다."))[0] == "wrong"
    assert rg.score_question(p, q, dict(base, verdict="입력이해실패", known=False, answer="?"))[0] == "hold"
    proven = by_id(problems, "en-class-03")
    assert rg.score_question(proven, proven["questions"][0], dict(
        base, verdict="계산완료", known=True, answer="Yes.",
        facts=[{"subject": "Cleo", "predicate": "isa", "value": "veskar", "evidence": []}]))[0] == "wrong"


def test_a_comparison_names_exactly_the_winner(problems):
    p = by_id(problems, "en-compare-01")
    q = p["questions"][0]
    said = {"phase": "answer", "verdict": "계산완료", "known": True, "facts": []}
    assert rg.score_question(p, q, dict(said, answer="Anouk."))[0] == "correct"
    assert rg.score_question(p, q, dict(said, answer="5 shells."))[1] == "no_candidate_named"
    assert rg.score_question(p, q, dict(said, answer="Bram."))[0] == "wrong"


def test_f2_4_directory_hash_is_frozen():
    assert rg.FROZEN.is_file()
    assert rg.tree_hash() == rg.frozen_hash()


def test_f2_4_baseline_is_recorded_at_the_start_commit():
    baseline = json.loads((rg.REPORT_DIR / "baseline.json").read_text("utf-8"))
    assert baseline["meta"]["code_commit"].startswith(rg.BASELINE_COMMIT)
    assert baseline["meta"]["dataset_sha256"] == rg.frozen_hash()
    assert set(baseline["by_kind"]) == set(rg.KINDS)
    assert baseline["questions"]["n"] == sum(len(p["questions"]) for p in rg.load())
    assert isinstance(baseline["unparsed"], list)
    assert baseline["gate"]["problems"] == len(rg.load())


def test_ui_turn_handler_path_runs_one_problem(problems):
    """The real entry (AppState.turn) plays one problem; every turn gets an observation."""
    p = by_id(problems, "en-transfer-01")
    answers = rg.run([p])
    assert len(answers[p["id"]]) == len(rg.script(p))
    assert all(("error" in row) or ("phase" in row) for row in answers[p["id"]])
    report = rg.score([p], answers)
    assert report["questions"]["n"] == len(p["questions"])
    assert report["setup"]["statements"] == len(p["setup"])
