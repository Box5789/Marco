# -*- coding: utf-8 -*-
"""답 품질 채점이 무엇을 세고 무엇을 안 세는지 못 박는다."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bench"))

import answer_quality as aq


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
