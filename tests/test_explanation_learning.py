# -*- coding: utf-8 -*-
"""설명을 듣고 이전에 못 풀던 새 질문을 푸는가.

언어팩은 **뜻풀이와 사건이 어떻게 생겼는지**만 선언한다. 어떤 낱말인지는
사용자가 그 자리에서 정하고, 코드도 예문도 그 낱말을 모른다.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relational_semantics import RelationalParser
from reasoning_context import ReasoningContext

KG = "graphs/graph_일상추론.kg"
기준 = ["민수 구슬은 8개 있다.", "지연 구슬은 3개 있다."]


def 대화(turns):
    context = ReasoningContext()
    result = None
    for text in turns:
        result = context.turn(text, KG)
    return result, context


class FrameTest(unittest.TestCase):
    """틀은 선언돼 있고, 낱말은 선언돼 있지 않다."""

    def setUp(self):
        self.parser = RelationalParser()

    def test_a_word_nobody_declared_still_reads_as_a_definition(self):
        for word in ("훔치", "건네", "베풀", "퍼주"):
            got = self.parser.parse("%s다는 상대에게 구슬 2개를 주는 것이다" % word, partial=True)
            self.assertEqual(got["정의"][0]["verb"], word)

    def test_the_definition_carries_operations_the_engine_already_has(self):
        """새 연산을 발명하지 않는다. 있는 것을 엮을 뿐이다."""
        rule = self.parser.parse("베풀다는 상대에게 구슬 2개를 주는 것이다",
                                 partial=True)["정의"][0]
        self.assertEqual([t[1] for t in rule["triples"]], ["count_remove", "count_add"])

    def test_an_event_frame_never_swallows_any_sentence(self):
        """꼬리가 슬롯인 틀은 `...에게 X다` 를 다 삼킨다. 그런 틀을 두지 않는다."""
        for text in ("민수가 지연에게 훔쳤다", "민수가 지연에게 베풀었습니다",
                     "민수가 지연에게 사과를 준다"):
            self.assertIsNone(self.parser.parse(text, partial=True), text)


class ExplanationTest(unittest.TestCase):
    뜻 = "베풀다는 상대에게 구슬 2개를 주는 것이다."

    def test_before_the_explanation_it_asks_instead_of_guessing(self):
        got, context = 대화(기준 + ["민수가 지연에게 베풀었다."])
        self.assertEqual(got["status"], "unresolved")
        self.assertIn("베풀", got["answer"])
        # 쓸 수 없던 사건도 버리지 않는다. 다음 물음이 옛 값을 확정하면 안 된다.
        self.assertEqual([x["text"] for x in context.unread], ["민수가 지연에게 베풀었다."])

    def test_a_stale_value_is_not_confirmed_while_the_word_is_unknown(self):
        got, _ = 대화(기준 + ["민수가 지연에게 베풀었다.", "지금 민수 구슬은 몇 개야?"])
        self.assertEqual(got["status"], "unresolved")
        self.assertNotIn("8개입니다", got["answer"])

    def test_after_the_explanation_both_sides_move(self):
        turns = [self.뜻] + 기준 + ["민수가 지연에게 베풀었다."]
        self.assertEqual(대화(turns + ["지금 민수 구슬은 몇 개야?"])[0]["answer"], "6개입니다.")
        self.assertEqual(대화(turns + ["지금 지연 구슬은 몇 개야?"])[0]["answer"], "5개입니다.")

    def test_the_same_explanation_applies_to_people_and_numbers_never_seen(self):
        """같은 문장을 다시 맞히는 것은 학습 성과가 아니다."""
        got, _ = 대화([self.뜻, "서우 구슬은 10개 있다.", "도아 구슬은 1개 있다.",
                     "서우가 도아에게 베풀었다.", "지금 서우 구슬은 몇 개야?"])
        self.assertEqual(got["answer"], "8개입니다.")

    def test_what_did_not_happen_changes_nothing(self):
        got, _ = 대화([self.뜻] + 기준 + ["민수는 지연에게 베풀지 않았다.",
                                     "지금 민수 구슬은 몇 개야?"])
        self.assertEqual(got["answer"], "8개입니다.")

    def test_changing_the_definition_changes_the_behaviour(self):
        """낱말을 보고 정해 둔 동작을 하면 여기서 걸린다."""
        got, _ = 대화(["베풀다는 상대에게 구슬 3개를 주는 것이다."] + 기준
                    + ["민수가 지연에게 베풀었다.", "지금 민수 구슬은 몇 개야?"])
        self.assertEqual(got["answer"], "5개입니다.")

    def test_a_later_explanation_of_the_same_word_wins(self):
        got, _ = 대화([self.뜻] + 기준 + ["베풀다는 상대에게 구슬 4개를 주는 것이다.",
                                      "민수가 지연에게 베풀었다.", "지금 민수 구슬은 몇 개야?"])
        self.assertEqual(got["answer"], "4개입니다.")

    def test_the_definition_stays_inside_this_conversation(self):
        """한 대화에서 정한 뜻을 온 세상 지식으로 올리지 않는다."""
        대화([self.뜻] + 기준 + ["민수가 지연에게 베풀었다."])
        got, _ = 대화(기준 + ["민수가 지연에게 베풀었다.", "지금 민수 구슬은 몇 개야?"])
        self.assertEqual(got["status"], "unresolved")


if __name__ == "__main__":
    unittest.main()
