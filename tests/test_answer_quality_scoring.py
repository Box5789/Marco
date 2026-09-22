# -*- coding: utf-8 -*-
"""답 품질 채점이 무엇을 세고 무엇을 안 세는지 못 박는다."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bench"))

import answer_quality as aq
import pytest

pytestmark = pytest.mark.language("한국어")  # Korean input: select the Korean pack, do not rely on the default


def case(**kw):
    base = {"id": "x", "family": "f", "split": "개발", "turns": ["q"],
            "답가능": True, "필수결론": {}, "금지결론": [], "필요근거": []}
    base.update(kw)
    return base


class AnswerScoringTest(unittest.TestCase):
    def test_routing_being_right_is_not_the_answer_being_right(self):
        """정답 그래프를 골랐어도 결론이 틀리면 실패다."""
        c = case(필수결론={"포함": ["15"]})
        trace = {"verdict": "계산완료", "winner": "graphs/graph_일상추론.kg",
                 "path": ["맞는노드"], "reasoning": {}}
        asserted, ok, _g = aq._judge(c, "21개입니다.", True, trace)
        self.assertTrue(asserted)
        self.assertFalse(ok)

    def test_a_forbidden_conclusion_fails_even_if_the_required_one_appears(self):
        c = case(필수결론={"포함": ["15"]}, 금지결론=["18"])
        _a, ok, _g = aq._judge(c, "15개입니다. 원래는 18개였습니다.", True, {"verdict": "계산완료"})
        self.assertFalse(ok)

    def test_any_of_the_candidates_is_enough(self):
        c = case(필수결론={"포함후보": ["반가", "안녕"]})
        _a, ok, _g = aq._judge(c, "안녕하세요, 반가워요", True, {"verdict": "대화"})
        self.assertTrue(ok)

    def test_an_item_with_no_stated_expectation_never_passes(self):
        """기대를 안 적은 문항을 조용히 통과시키지 않는다."""
        _a, ok, _g = aq._judge(case(), "아무 말", True, {"verdict": "계산완료"})
        self.assertFalse(ok)


class HoldingTest(unittest.TestCase):
    def test_holding_is_success_when_the_item_is_unanswerable(self):
        c = case(답가능=False, 금지결론=["개입니다"])
        asserted, ok, _g = aq._judge(c, "근거를 찾지 못했습니다", False, {"verdict": "미지"})
        self.assertFalse(asserted)
        self.assertTrue(ok)

    def test_asserting_on_an_unanswerable_item_fails(self):
        c = case(답가능=False, 금지결론=["개입니다"])
        _a, ok, _g = aq._judge(c, "15개입니다.", True, {"verdict": "계산완료"})
        self.assertFalse(ok)

    def test_a_held_verdict_is_not_an_assertion_even_when_known_is_true(self):
        """known 만 보고 단정으로 세면 보류가 성공으로 둔갑한다."""
        for verdict in ("미지", "B2", "조건부족", "근거없음", "A"):
            asserted, _ok, _g = aq._judge(case(답가능=False), "무언가", True, {"verdict": verdict})
            self.assertFalse(asserted, verdict)


class SubstringTest(unittest.TestCase):
    """숫자가 숫자 안에 들어 있는 것을 정답으로 세지 않는다."""

    def test_a_number_inside_a_bigger_number_is_not_a_match(self):
        c = case(필수결론={"포함": ["15"]}, 판정기준={"단위": "개"})
        _a, ok, _g = aq._judge(c, "115개입니다.", True, {"verdict": "계산완료"})
        self.assertFalse(ok)

    def test_the_same_number_standing_on_its_own_still_matches(self):
        c = case(필수결론={"포함": ["15"]}, 판정기준={"단위": "개"})
        _a, ok, _g = aq._judge(c, "15개입니다.", True, {"verdict": "계산완료"})
        self.assertTrue(ok)

    def test_a_forbidden_number_does_not_fire_from_a_bigger_number(self):
        c = case(필수결론={"포함": ["115"]}, 금지결론=["15"], 판정기준={"단위": "개"})
        _a, ok, _g = aq._judge(c, "115개입니다.", True, {"verdict": "계산완료"})
        self.assertTrue(ok)

    def test_an_answer_carrying_a_unit_the_item_never_declared_is_not_auto_judged(self):
        """문항이 단위를 안 적었으면 채점기는 단위가 맞는지 확인할 길이 없다."""
        c = case(필수결론={"포함": ["15"]})
        self.assertIsNone(aq._judge(c, "15개입니다.", True, {"verdict": "계산완료"})[1])

    def test_words_still_match_inside_inflected_forms(self):
        """글자는 부분 일치를 유지한다 — 조사가 붙어도 찾아야 한다."""
        c = case(필수결론={"포함": ["구슬"]})
        _a, ok, _g = aq._judge(c, "구슬이 남았습니다.", True, {"verdict": "계산완료"})
        self.assertTrue(ok)


class CrashTest(unittest.TestCase):
    """터진 실행을 올바른 보류로 세지 않는다."""

    def test_a_crash_on_an_unanswerable_item_is_not_a_correct_hold(self):
        c = case(답가능=False, 금지결론=["개입니다"])
        asserted, ok, _g = aq._judge(c, "KeyError: 'x'", False, {}, error=True)
        self.assertFalse(asserted)
        self.assertFalse(ok)

    def test_a_crash_on_an_answerable_item_is_a_failure_too(self):
        c = case(필수결론={"포함": ["15"]})
        _a, ok, _g = aq._judge(c, "KeyError: 'x'", True, {"verdict": "계산완료"}, error=True)
        self.assertFalse(ok)


class EvidenceTest(unittest.TestCase):
    def test_evidence_comes_from_the_trace_not_from_the_answer_text(self):
        c = case(필수결론={"포함": ["15"]}, 필요근거=["구슬이 18개 있다"])
        trace = {"verdict": "계산완료",
                 "reasoning": {"transitions": [{"evidence": {"text": "상자에 구슬이 18개 있다"}}]}}
        _a, _ok, grounded = aq._judge(c, "15개입니다.", True, trace)
        self.assertTrue(grounded)

    def test_an_answer_that_merely_repeats_the_evidence_is_not_grounded(self):
        c = case(필수결론={"포함": ["15"]}, 필요근거=["구슬이 18개 있다"])
        _a, _ok, grounded = aq._judge(c, "구슬이 18개 있다니까 15개입니다.", True, {"verdict": "계산완료"})
        self.assertFalse(grounded)

    def test_evidence_is_not_scored_when_none_was_required(self):
        _a, _ok, grounded = aq._judge(case(필수결론={"포함": ["2"]}), "2입니다.", True,
                                      {"verdict": "계산완료"})
        self.assertIsNone(grounded)


if __name__ == "__main__":
    unittest.main()


class NumberTest(unittest.TestCase):
    """수는 글자 겹침이 아니라 값으로 견준다."""

    def judge(self, text, expected="15", unit="개", forbidden=()):
        c = case(필수결론={"포함": [expected]}, 금지결론=list(forbidden), 판정기준={"단위": unit})
        return aq._judge(c, text, True, {"verdict": "계산완료"})[1]

    def test_sign_and_decimal_are_not_the_same_number(self):
        for text in ("115개입니다.", "15.5개입니다.", "-15개입니다.", "0.15개입니다."):
            self.assertFalse(self.judge(text), text)

    def test_a_wrong_unit_is_not_the_answer(self):
        self.assertFalse(self.judge("15kg입니다."))

    def test_two_values_are_never_auto_judged(self):
        """끝에 있는 수가 결론이라는 규칙은 둘 중 하나를 반드시 틀린다.

            15개입니다. 원래는 18개였어요.   <- 맞는 답
            18개입니다. 15개가 아닙니다.     <- 틀린 답

        같은 두 수를 담는다. 기계가 못 가르는 것을 정답도 오답도로 몰지 않는다.
        """
        for text in ("15개입니다. 원래는 18개였어요.",
                     "18개입니다. 15개가 아닙니다.",
                     "구슬은 18개, 단추는 15개입니다.",
                     "18개에서 3개를 빼 15개입니다."):
            self.assertIsNone(self.judge(text), text)

    def test_one_clear_value_is_still_judged(self):
        self.assertTrue(self.judge("15개입니다."))
        self.assertFalse(self.judge("18개입니다."))

    def test_a_forbidden_number_is_matched_by_value_too(self):
        self.assertFalse(self.judge("15개입니다.", forbidden=["15"]))


class ReportTest(unittest.TestCase):
    def test_a_crashed_hold_is_not_counted_as_holding_well(self):
        rows = [{"답가능": False, "단정함": False, "성공": False, "오류": "KeyError: 'x'",
                 "근거충족": None, "웹호출": 0, "family": "보류", "split": "개발",
                 "id": "e1", "답": "", "판정": None, "판정기준": {}}]
        text = aq.report({"dataset_sha256": "-", "rows": rows})
        self.assertIn("보류해야 할 때 보류   0/1", text)
        self.assertIn("실행 오류          1/1", text)


class TwoAxesTest(unittest.TestCase):
    """안전과 해결은 서로를 대신하지 못한다.

    보류는 안전에서는 개선이고 해결에서는 미해결이다. 한 숫자로 합치면
    "못 풀어도 안전하게 보류했다" 가 "풀었다" 로 집계된다.
    """

    def item(self):
        # 사람은 21이라 답한다. 우리가 못 푸는 것이지 답 없는 문항이 아니다.
        return case(필수결론={"포함": ["21"]}, 금지결론=["18"], 판정기준={"단위": "개"})

    def test_a_hold_is_never_task_success_on_an_answerable_item(self):
        for text in ("확정할 수 없습니다.",
                     "마지막으로 확인한 수량은 18개입니다. 이후 사건을 이해하지 못해 현재 수량은 미확정입니다."):
            asserted, ok, _g = aq._judge(self.item(), text, False, {"verdict": "미지"})
            self.assertFalse(asserted, text)
            self.assertFalse(ok, text)

    def test_a_structured_hold_counts_as_safe_not_as_solved(self):
        rows = [{"답가능": True, "단정함": False, "성공": False, "오류": "",
                 "금지결론": ["18"], "근거충족": None, "웹호출": 0, "family": "미해석",
                 "split": "개발", "id": "h1",
                 "답": "마지막으로 확인한 수량은 18개입니다. 현재 수량은 미확정입니다.",
                 "판정": "미지", "판정기준": {}}]
        text = aq.report({"dataset_sha256": "-", "rows": rows})
        self.assertIn("보류로 피함    1", text)       # 안전에서는 개선
        self.assertIn("틀린 값 단정    0", text)      # 안전 실패는 아니다
        self.assertIn("과제 성공          0/1", text)  # 해결은 아니다

    def test_the_right_answer_is_success_and_the_wrong_one_is_not(self):
        self.assertTrue(aq._judge(self.item(), "21개입니다.", True, {"verdict": "계산완료"})[1])
        self.assertFalse(aq._judge(self.item(), "18개입니다.", True, {"verdict": "계산완료"})[1])


class DatasetShapeTest(unittest.TestCase):
    """문항 자료가 스스로 모순되지 않는지 본다. 망가진 한 줄이 점수를 끈다."""

    def setUp(self):
        import json
        self.items = json.loads((ROOT / "data/benchmarks/answer_quality.json")
                                .read_text(encoding="utf-8"))["문항"]

    def test_every_id_is_unique(self):
        seen = [c["id"] for c in self.items]
        self.assertEqual(len(seen), len(set(seen)))

    def test_an_answerable_item_always_states_what_it_expects(self):
        """기대를 안 적으면 영영 실패로 깔린다 — 코드 탓처럼 보이는 자료 탓이다."""
        for c in self.items:
            if c["답가능"]:
                self.assertTrue(c["필수결론"].get("포함") or c["필수결론"].get("포함후보"), c["id"])

    def test_a_hold_item_never_states_a_required_conclusion(self):
        for c in self.items:
            if not c["답가능"]:
                self.assertFalse(c["필수결론"], c["id"])

    def test_every_item_actually_has_turns(self):
        for c in self.items:
            self.assertTrue(c["turns"], c["id"])
