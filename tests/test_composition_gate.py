"""The composition gate (F2.5, F2.6): composed, passed through or held, per reply.

These tests check the gate, not the realizer's coverage: the number itself
comes from ``python bench/composition_gate.py``.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench"))
import composition_gate as cg  # noqa: E402


def realized(text, **extra):
    return dict({"realized": True, "held": False, "reason": None, "text": text}, **extra)


def test_classification_rules():
    assert cg.classify("4 apples.", realized("4 apples.")) == ("composed", "composed")
    assert cg.classify(" 4  apples. ", realized("4 apples.")) == ("composed", "composed")
    assert cg.classify("4 apples.", None) == ("passed_through", "no_realizer_report")
    assert cg.classify("Recorded in this conversation: Omar stamps 9.",
                       {"realized": False, "reason": "no_plan"}) == ("passed_through", "realizer:no_plan")
    assert cg.classify("I cannot say that.", realized("I cannot say that.", held=True)) == ("held", "realizer_hold")
    # a graph node's own text counts only inside a composed sentence
    assert cg.classify('The graph says "water boils at 100".', realized('The graph says "water boils at 100".')) == \
        ("composed", "composed")
    assert cg.classify('"water boils at 100"', realized('"water boils at 100"')) == ("passed_through", "quotation_only")
    assert cg.classify('4 apples. "water boils at 100"', realized("4 apples.")) == \
        ("passed_through", "text_outside_composed_sentence")
    assert cg.classify("four", realized("4 apples.")) == ("passed_through", "spoken_differs_from_composed")


def test_acts_come_from_the_engine_meaning_then_its_status():
    assert cg.act_of({"act": "revise"}, "observed", "observed") == "correct"
    assert cg.act_of({"act": "refuse"}, "unresolved", "held") == "hold"
    assert cg.act_of({"act": "inform"}, "answered", "answered") == "answer"
    assert cg.act_of({"act": None}, "observed", "observed") == "record"
    assert cg.act_of({"act": None}, None, "answered") == "answer"
    assert set(cg.MEANING_ACTS.values()) <= set(cg.ACTS)


def test_fixed_dialogue_sets_in_the_gate_shape():
    seven = cg.seven_step_dialogues()
    assert [d["language"] for d in seven] == ["ko", "en"]
    assert all(len(d["turns"]) == 10 and d["turns"][8].get("restart_before") for d in seven)
    phrasings = cg.phrasing_dialogues()
    assert len(phrasings) == 20 and {d["language"] for d in phrasings} == {"ko", "en"}


def test_the_score_states_its_denominator():
    dialogues = [{"id": "d", "language": "en", "turns": [{"n": 1, "say": "a"}, {"n": 2, "say": "b"},
                                                       {"n": 3, "say": "c"}]}]
    answers = {"d": [
        {"phase": "answer", "verdict": "상태기억", "answer": "Recorded.",
         "composition": {"realized": True, "held": False, "text": "Recorded.", "engine_act": "record"}},
        {"phase": "answer", "verdict": "조건부족", "known": False, "answer": "Not enough.",
         "composition": {"realized": False, "reason": "no_plan", "engine_act": "hold"}},
        {"error": "RuntimeError: boom"}]}
    report = cg.score(dialogues, answers)
    assert (report["total"]["composed"], report["total"]["spoken"], len(report["execution_errors"])) == (1, 2, 1)
    assert report["by_act"]["record"]["composed"] == 1 and report["by_act"]["hold"]["passed_through"] == 1
    assert "every reply the UI returned" in report["total"]["denominator"]
    assert cg.format_report(report).startswith("composed 1 / 2 spoken replies")


def test_f2_6_a_realizer_that_passes_everything_through_scores_zero_composed(monkeypatch):
    from marco.language.realizer import Realizer

    def passthrough(self, result, report, source, model):
        return self._passthrough(result, dict(report, reason="injected_passthrough"))
    monkeypatch.setattr(Realizer, "_realize", passthrough)
    dialogues = cg.seven_step_dialogues() + cg.phrasing_dialogues()[:4]
    report = cg.score(dialogues, cg.run(dialogues))
    total = report["total"]
    assert total["spoken"] == sum(len(d["turns"]) for d in dialogues)
    assert total["composed"] == 0 and total["passed_through"] == total["spoken"]
    assert report["reasons"].get("realizer:injected_passthrough", 0) > 0
    assert set(report["reasons"]) <= {"realizer:injected_passthrough", "realizer:no_declarations",
                                      "no_realizer_report"}


def test_the_live_realizer_is_seen_composing_the_seven_step_dialogue():
    dialogues = cg.seven_step_dialogues()
    report = cg.score(dialogues, cg.run(dialogues))
    assert report["total"]["spoken"] == 20 and not report["execution_errors"]
    assert all(report["by_language"][code]["composed"] > 0 for code in ("ko", "en"))
    for row in report["rows"]:
        if row["bucket"] == "composed":
            assert row["reports"] >= 1 and row["spoken"].split() == row["composed_text"].split()
