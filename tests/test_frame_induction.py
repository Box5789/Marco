# -*- coding: utf-8 -*-
"""틀을 손으로 적지 않고 사례에서 꺼내는가.

낱말이 공짜인 것은 이미 봤다. 여기서 보는 것은 **짜임**이다. 뜻풀이의 몸통은
보통 문장이므로, 앞자리를 지운 사례에 맞춰 읽고 빈자리는 사건이 같은 조사로
채운다. 그래서 새 짜임마다 틀을 더하지 않는다.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from frame_induction import induce, read_event, split_particle
from relational_semantics import RelationalParser
from reasoning_context import ReasoningContext

KG = "graphs/graph_일상추론.kg"


def 대화(turns):
    context = ReasoningContext()
    result = None
    for text in turns:
        result = context.turn(text, KG)
    return result


def 답(turns):
    return (대화(turns) or {}).get("answer") or ""


class BodyTest(unittest.TestCase):
    """몸통은 보통 문장이다. 아는 문장꼴이면 뜻이 따라온다."""

    def setUp(self):
        self.parser = RelationalParser()

    def test_a_body_written_as_a_sentence_we_know_carries_its_meaning(self):
        got = induce(self.parser, "물건을 상자로 옮기는")
        self.assertEqual(got["뜻"]["triple"], ["$item", "location", "$place"])
        self.assertEqual(got["값"], {"item": "물건", "place": "상자"})

    def test_the_slot_the_body_leaves_out_becomes_the_place_the_event_fills(self):
        """빠진 자리가 곧 역할이다. 역할 이름을 따로 선언하지 않는다."""
        self.assertEqual(list(induce(self.parser, "물건을 상자로 옮기는")["빈자리"]), ["actor"])

    def test_a_quantity_body_is_induced_the_same_way(self):
        """자리 옮김만 되는 것이 아니다. 수량도 같은 길로 나온다."""
        for body, predicate in (("구슬 3개를 넣는", "count_add"),
                                ("구슬 두 개를 꺼내는", "count_remove")):
            got = induce(self.parser, body)
            self.assertEqual(got["뜻"]["triple"][1], predicate, body)

    def test_a_two_sided_body_yields_two_facts(self):
        """주고받기는 한 문장이 둘을 말한다. 주는 쪽이 줄고 받는 쪽이 는다."""
        got = induce(self.parser, "상대에게 구슬 2개를 주는")
        self.assertEqual([row[1] for row in got["뜻"]["triples"]],
                         ["count_remove", "count_add"])

    def test_a_body_whose_verb_has_no_sentence_example_is_refused(self):
        """못 읽는 까닭은 틀이 없어서가 아니라 **그 움직임을 모르기 때문**이다.

        `가져오다` 는 어느 사례에도 없다. 틀 탓으로 돌리면 고칠 자리를 놓친다.
        """
        self.assertIsNone(induce(self.parser, "상대에게서 구슬 2개를 가져오는"))

    def test_a_cut_that_swallows_a_marked_word_into_a_name_is_refused(self):
        """`하루가 연필` 을 한 이름으로 삼키면 자름이 틀린 것이다."""
        got = induce(self.parser, "하루가 연필을 상자로 옮기는")
        self.assertEqual(got["값"]["item"], "연필")


class ManyFactsTest(unittest.TestCase):
    """한 문장이 사실 하나라는 법은 없다."""

    def test_one_sentence_moves_both_sides(self):
        기준 = ["민수 구슬은 8개 있다.", "지연 구슬은 3개 있다.",
              "민수가 지연에게 구슬 2개를 줬다."]
        self.assertIn("6개", 답(기준 + ["지금 민수 구슬은 몇 개야?"]))
        self.assertIn("5개", 답(기준 + ["지금 지연 구슬은 몇 개야?"]))

    def test_a_name_written_in_pieces_becomes_one_name(self):
        facts = RelationalParser().parse("하루가 모래에게 구슬 3개를 줬다", partial=True)["facts"]
        self.assertEqual([f["triple"] for f in facts],
                         [["하루 구슬", "count_remove", "3"],
                          ["모래 구슬", "count_add", "3"]])

    def test_a_correction_may_still_state_only_one_fact(self):
        """고쳐 주는 말은 사실 하나다. 사용자가 두 값을 한꺼번에 흔들지 않는다."""
        parser = RelationalParser()
        with self.assertRaises(ValueError):
            parser.learn({"text": "하루가 모래에게 구슬 4개를 건넸다",
                          "slots": {"giver": "하루", "taker": "모래",
                                    "item": "구슬", "n": "4"},
                          "meaning": {"triples": [[["$giver", "$item"], "count_remove", "$n"]]}})


class MovementTest(unittest.TestCase):
    """막는 것은 틀이 아니라 **움직임**이다. 움직임 하나가 짜임 여럿을 연다."""

    def test_learning_one_ordinary_sentence_opens_compositions_that_use_it(self):
        parser = RelationalParser()
        self.assertIsNone(induce(parser, "구슬 4개를 더는"))
        parser.learn({"text": "구슬 4개를 덜었다", "slots": {"item": "구슬", "n": "4"},
                      "inflection": {"stem": "덜", "kind": "regular",
                                     "tense": "past", "ending": "plain"},
                      "meaning": {"triple": ["$item", "count_remove", "$n"]}})
        # 뜻풀이 틀을 더한 것이 아니다. 보통 문장 하나를 더했을 뿐이다.
        got = induce(parser, "구슬 두 개를 더는")
        self.assertEqual(got["뜻"]["triple"][1], "count_remove")
        self.assertEqual(got["값"]["n"], "2")

    def test_a_new_example_never_leaves_a_stale_induced_frame_behind(self):
        parser = RelationalParser()
        ReasoningContext._rule(parser, {"verb": "치우", "몸통": "물건을 상자로 옮기는"})
        self.assertTrue(parser.induced_frames)
        parser.learn({"text": "구슬 4개를 덜었다", "slots": {"item": "구슬", "n": "4"},
                      "inflection": {"stem": "덜", "kind": "regular",
                                     "tense": "past", "ending": "plain"},
                      "meaning": {"triple": ["$item", "count_remove", "$n"]}})
        self.assertFalse(parser.induced_frames)


class EventTest(unittest.TestCase):
    """사건은 조사로 자리를 짚는다. 모르는 낱말은 넘겨짚지 않는다."""

    def setUp(self):
        self.parser = RelationalParser()
        self.parts, self.groups = self.parser.case_particles, self.parser.slot_particles
        self.negation = self.parser.negation

    def test_a_longer_particle_is_read_before_a_shorter_one_it_contains(self):
        self.assertEqual(split_particle("지연에게서", self.parts, self.groups), ("지연", "에게서"))
        self.assertEqual(split_particle("지연에게", self.parts, self.groups), ("지연", "에게"))

    def test_particles_that_share_a_slot_share_one_name(self):
        """`로` 와 `으로` 는 한 자리다. 몸통이 `상자로` 라도 사건의 `학교로` 와 만난다."""
        self.assertEqual(split_particle("상자로", self.parts, self.groups)[1],
                         split_particle("책상으로", self.parts, self.groups)[1])

    def test_the_shape_is_read_without_knowing_the_word(self):
        """뜻을 몰라도 꼴은 안다. 그래야 **무엇을** 모르는지 짚어 줄 수 있다."""
        got = read_event("민수가 지연에게 베풀었다", self.parts, self.groups, self.negation)
        self.assertEqual(got["verb"], "베풀었다")
        self.assertEqual(got["자리"], {"은": "민수", "에게": "지연"})

    def test_what_did_not_happen_is_read_the_same_way(self):
        """부정도 낱말마다 틀을 안 적는다. 잇는 말과 보조 어간 한 줄이면 된다."""
        for tail in ("않았다", "않았어요", "않는다"):
            got = read_event("민수는 지연에게 베풀지 %s" % tail,
                             self.parts, self.groups, self.negation)
            self.assertEqual((got["verb"], got["polarity"]), ("베풀", False), tail)

    def test_a_word_without_a_particle_stops_the_reading(self):
        """`단추 4개를` 는 자리를 못 짚는다. 못 짚으면 짐작하지 않고 멈춘다."""
        self.assertIsNone(read_event("하루가 단추 4개를 담았다",
                                     self.parts, self.groups, self.negation))
        self.assertIsNotNone(read_event("하루가 담았다", self.parts, self.groups, self.negation))

    def test_the_same_slot_twice_is_not_read(self):
        self.assertIsNone(read_event("하루가 민수가 치웠다",
                                     self.parts, self.groups, self.negation))


class QuestionTest(unittest.TestCase):
    """묻는 것은 하는 것이 아니다."""

    뜻 = "베풀다는 상대에게 구슬 2개를 주는 것이다."
    기준 = ["민수 구슬은 8개 있다.", "지연 구슬은 3개 있다."]

    def test_asking_whether_it_happened_does_not_make_it_happen(self):
        for asked in ("민수가 지연에게 베풉니까?", "민수가 지연에게 베풉니까",
                      "민수가 지연에게 베풀었습니까", "민수가 지연에게 베풀었나요?"):
            answer = 답([self.뜻] + self.기준 + [asked, "지금 민수 구슬은 몇 개야?"])
            self.assertIn("8개", answer, asked)

    def test_a_statement_style_that_shares_an_ending_is_still_an_event(self):
        """`베풀었어요` 는 묻기도 하고 말하기도 한다. 묻기 전용 꼬리라야 물음이다."""
        for said in ("민수가 지연에게 베풀었어요.", "민수가 지연에게 베풀었다."):
            self.assertIn("6개", 답([self.뜻] + self.기준 + [said, "지금 민수 구슬은 몇 개야?"]), said)

    def test_a_question_is_not_kept_as_something_we_failed_to_read(self):
        """묻는 말은 못 읽은 사건이 아니다. 뒤 물음을 막으면 안 된다."""
        answer = 답([self.뜻] + self.기준 + ["민수가 지연에게 베풉니까", "지금 지연 구슬은 몇 개야?"])
        self.assertIn("3개", answer)


class UnfilledRoleTest(unittest.TestCase):
    """채우지 못한 자리와 아무 일도 없었던 것은 다르다."""

    뜻 = "베풀다는 상대에게 구슬 2개를 주는 것이다."
    기준 = ["민수 구슬은 8개 있다.", "지연 구슬은 3개 있다."]

    def test_a_missing_role_is_said_out_loud_not_swallowed(self):
        answer = 답([self.뜻] + self.기준 + ["지연에게 베풀었다."])
        self.assertIn("지연에게 베풀었다", answer)
        self.assertIn("은/는/이/가", answer)

    def test_a_missing_role_never_lets_the_old_value_stand(self):
        """이것을 안 하면 해석 실패가 "변화 없음" 으로 둔갑한다."""
        for asked in ("지금 민수 구슬은 몇 개야?", "지금 지연 구슬은 몇 개야?"):
            answer = 답([self.뜻] + self.기준 + ["지연에게 베풀었다.", asked])
            self.assertNotIn("개입니다", answer, asked)

    def test_filling_the_slot_afterwards_carries_on(self):
        self.assertIn("6개", 답([self.뜻] + self.기준 + ["지연에게 베풀었다.",
                                                   "민수가 지연에게 베풀었다.",
                                                   "지금 민수 구슬은 몇 개야?"]))

    def test_a_different_event_does_not_count_as_filling_it_in(self):
        """채운 자리끼리 어긋나면 고쳐 말한 것이 아니라 딴 일이다."""
        answer = 답([self.뜻] + self.기준 + ["가람에게 베풀었다.",
                                        "민수가 지연에게 베풀었다.",
                                        "지금 민수 구슬은 몇 개야?"])
        self.assertNotIn("개입니다", answer)

    def test_a_value_the_event_could_not_touch_is_still_answered(self):
        answer = 답([self.뜻] + self.기준 + ["단추는 5개 있다.", "지연에게 베풀었다.",
                                        "지금 단추는 몇 개야?"])
        self.assertIn("5개", answer)


class ConversationTest(unittest.TestCase):
    """실제 대화에서 한 바퀴 도는가."""

    def test_a_composition_nobody_declared_is_answered(self):
        self.assertIn("상자", 답(["치우다는 물건을 상자로 옮기는 것이다.",
                                "연필은 책상에 있었다.",
                                "하루가 연필을 치웠어요.",
                                "지금 연필은 어디에 있어?"]))

    def test_the_same_path_works_for_a_different_composition(self):
        """한 문항에 맞춘 것이 아니다. 낱말도 자리도 바꿔 본다."""
        self.assertIn("서랍", 답(["숨기다는 물건을 서랍으로 옮기는 것이다.",
                                "구슬은 책상에 있었다.",
                                "민수가 구슬을 숨겼다.",
                                "지금 구슬은 어디에 있어?"]))

    def test_a_quantity_composition_runs_the_same_way(self):
        self.assertIn("8개", 답(["담다는 구슬 3개를 넣는 것이다.", "구슬은 5개 있다.",
                               "하루가 담았다.", "지금 구슬은 몇 개야?"]))

    def test_the_event_fills_the_slot_the_body_left_open(self):
        """비어 있던 자리를 사건이 채운다. 여기까지가 정해진 것이다.

        몸통이 **이미 채운** 자리를 사건이 다시 짚으면 어떻게 되는지는 아직
        안 정했다(`치우다는 물건을 상자로` + `학교로 치웠다`). 몸통의 값이
        고정값인지 바꿀 수 있는 기본값인지를 가릴 근거가 아직 없다. 지금
        동작을 정답으로 못 박지 않는다 — 못 박으면 그 자리가 안 보인다.
        """
        self.assertIn("상자", 답(["치우다는 물건을 상자로 옮기는 것이다.",
                                "연필은 책상에 있었다.",
                                "하루가 연필을 치웠다.",
                                "지금 연필은 어디에 있어?"]))

    def test_without_the_explanation_the_same_event_is_not_assumed(self):
        answer = 답(["연필은 책상에 있었다.", "하루가 연필을 치웠다.",
                    "지금 연필은 어디에 있어?"])
        self.assertNotIn("상자", answer)
        self.assertIn("치웠다", answer)          # 무엇을 못 읽었는지 짚어 준다

    def test_a_sentence_shaped_like_an_event_never_becomes_a_value(self):
        """꼴을 읽는 것은 뜻을 안다는 말이 아니다. 잡담은 값을 안 흔든다."""
        answer = 답(["날씨가 좋다.", "민수 구슬은 8개 있다.", "지금 민수 구슬은 몇 개야?"])
        self.assertIn("8개", answer)

    def test_a_word_used_as_an_event_is_named_even_before_it_is_explained(self):
        answer = 답(["민수 구슬은 8개 있다.", "민수가 지연에게 베풀었다."])
        self.assertIn("베풀었다", answer)

    def test_what_did_not_happen_changes_nothing_for_an_induced_word_too(self):
        """부정은 선언된 틀에만 있던 것이었다. 이제 유도된 말에도 선다."""
        self.assertIn("책상", 답(["치우다는 물건을 상자로 옮기는 것이다.",
                                "연필은 책상에 있었다.",
                                "하루가 연필을 치우지 않았다.",
                                "지금 연필은 어디에 있어?"]))

    def test_an_explanation_we_could_not_read_says_so_instead_of_blaming_the_word(self):
        """방금 설명한 사람에게 "그 말을 모른다" 고 하면 틀린 말이다."""
        answer = 답(["빼앗다는 상대에게서 구슬 2개를 가져오는 것이다."])
        self.assertIn("상대에게서 구슬 2개를 가져오는", answer)

    def test_no_definition_frame_is_declared_anywhere(self):
        """뜻풀이 틀은 이제 한 칸도 안 적혀 있다. 겉틀 하나가 전부다."""
        frames = [e for e in RelationalParser().data["examples"] if "define" in e["meaning"]]
        self.assertEqual(len(frames), 1)
        self.assertEqual(set(frames[0]["meaning"]["define"]), {"verb", "몸통"})

    def test_both_sides_of_a_giving_move_without_a_frame_for_it(self):
        turns = ["베풀다는 상대에게 구슬 2개를 주는 것이다.",
                 "민수 구슬은 8개 있다.", "지연 구슬은 3개 있다.",
                 "민수가 지연에게 베풀었다."]
        self.assertIn("6개", 답(turns + ["지금 민수 구슬은 몇 개야?"]))
        self.assertIn("5개", 답(turns + ["지금 지연 구슬은 몇 개야?"]))


if __name__ == "__main__":
    unittest.main()
