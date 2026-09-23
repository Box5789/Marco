"""R7: an expression observed in user input becomes a selectable candidate in the same context.

It is kept only after it says its own source meaning and passes the semantic
check; it is listed with the sentence and conversation it came from; it can be
disabled and removed; removing it restores the before output. A learned
candidate that would change the meaning is never selected.
"""
import copy

from w1_harness import play

from marco.language.realizer import Realizer

KOREAN = ["지호는 구슬 열 개가 있어.", "민재 사과는 3개 있다.", "민재가 사과 한 개를 꺼냈다."]
ENGLISH = ["Minsu has five apples.", "Jiyeon has 2 apples.", "Minsu gave Jiyeon 2 apples.",
           "How many apples does Jiyeon have?"]


def _learn(language, turns, context):
    realizer = Realizer(learning=True, context=context)
    rows, _context = play(language, turns, realizer=realizer)
    return realizer, rows


def _said(realizer, result, language):
    return realizer.realize_with_report(copy.deepcopy(result), result["status"], "styles/%s.json" % language)


def test_korean_casual_expression_learned_selected_listed_disabled_removed():
    realizer, rows = _learn("한국어", KOREAN, {"register": "casual"})
    learned = realizer.learning.list()
    source = [item for item in learned if item["learned"]["source"] == "지호는 구슬 열 개가 있어"]
    assert len(source) == 1 and source[0]["register"] == ["casual"] and source[0]["enabled"]
    candidate_id = source[0]["id"]
    turn = rows[2][1]                                     # 민재가 사과 한 개를 꺼냈다. -> derived count

    before = Realizer(context={"register": "casual"})
    before_text, _ = _said(before, turn, "한국어")
    after_text, after = _said(realizer, turn, "한국어")
    assert before_text == "반영했어. 이제 민재 사과는 2개야."
    assert after_text == "반영했어. 이제 민재는 사과 두 개가 있어."     # the user's way: topic on the owner, a numeral word
    chosen = [c for c in after["clauses"] if c["frame"] == "count"][0]
    assert chosen["candidate"] == candidate_id and chosen["learned"] and chosen["parse"] == "parsed"

    realizer.learning.disable(candidate_id)
    assert _said(realizer, turn, "한국어")[0] == before_text
    realizer.learning.enable(candidate_id)
    assert _said(realizer, turn, "한국어")[0] == after_text
    realizer.learning.remove(candidate_id)
    assert _said(realizer, turn, "한국어")[0] == before_text
    assert candidate_id not in [item["id"] for item in realizer.learning.list()]


def test_a_learned_expression_stays_in_its_own_context():
    realizer, rows = _learn("한국어", KOREAN, {"register": "casual"})
    realizer.context = {"register": "formal"}
    text, report = _said(realizer, rows[2][1], "한국어")
    assert text == "반영했습니다. 이제 민재 사과는 2개입니다."
    assert not any(c.get("learned") for c in report["clauses"])


def test_english_number_words_learned_and_answers_keep_their_fragment():
    realizer, rows = _learn("english", ENGLISH, {})
    assert [item["learned"]["source"] for item in realizer.learning.list()] == ["Minsu has five apples"]
    assert rows[2][1]["answer"] == "Recorded. Now Minsu has three apples and Jiyeon has four."
    assert rows[3][1]["answer"] == "4 apples."            # an answer fragment keeps the declared expression
    plain = Realizer()
    assert _said(plain, rows[2][1], "english")[0] == "Recorded. Now Minsu has 3 apples and Jiyeon has 4."


def test_learned_expressions_are_removed_with_their_conversation():
    realizer, rows = _learn("english", ENGLISH[:1], {})
    first = copy.deepcopy(rows[0][1])
    realizer.learning.items.clear()
    first["meaning"]["conversation"] = "conversation-a"
    learned = realizer.learning.observe(first, "english")
    assert learned and realizer.learning.list()[0]["learned"]["conversation"] == "conversation-a"
    realizer.learning.remove_conversation("conversation-a")
    assert realizer.learning.list() == []


def test_a_learned_candidate_that_changes_the_meaning_is_never_selected():
    realizer, rows = _learn("한국어", KOREAN, {"register": "casual"})
    good = [item for item in realizer.learning.items if item["register"] == ["casual"]][0]
    bad = copy.deepcopy(good)
    bad["id"] = "learned-bad"
    # owner and item trade places: "사과는 민재 두 개가 있어"
    for part in bad["parts"]:
        if part.get("np") == ["owner"]:
            part["np"] = ["item"]
        elif part.get("np") == ["item"]:
            part["np"] = ["owner"]
    realizer.learning.items.insert(0, bad)
    text, report = _said(realizer, rows[2][1], "한국어")
    count = [c for c in report["clauses"] if c["frame"] == "count"][0]
    assert count["candidate"] == good["id"]
    tried = count["attempts"][0]
    assert tried["candidate"] == "learned-bad" and not tried["check"]["ok"]
    assert "사과는 민재" not in text
