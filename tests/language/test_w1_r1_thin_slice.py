"""R1: one INFORM answer through all six layers and the semantic check, Korean and English, one Meaning Graph."""
import copy

import pytest

from marco.language.realizer import Realizer, meaning as mg


def answered(subject, predicate, value):
    return {"status": "answered", "operator": "relational_graph",
            "answer": "this sentence is never read",
            "transitions": [{"fact": [subject, predicate, value], "evidence": {"turn": 1, "source": "x"}}]}


def test_one_meaning_graph_two_languages_all_layers():
    realizer = Realizer()
    graph = realizer.build_graph(answered("지연 사과", "count", "4"), "styles/한국어.json")
    assert graph is not None
    # the Meaning Graph carries no sentence and no language words beyond the conversation's own
    assert [p["frame"] for p in graph["props"]] == ["count"]
    prop = graph["props"][0]
    assert prop["roles"]["owner"]["text"] == "지연" and prop["roles"]["item"]["text"] == "사과"
    assert prop["roles"]["value"] == {"number": "4"} and prop["focus"] == "value"
    ko_text, ko = realizer.realize_graph(copy.deepcopy(graph), "한국어")
    en_text, en = realizer.realize_graph(copy.deepcopy(graph), "english")
    assert ko_text == "4개입니다."
    assert en_text == "4 apples."
    for report in (ko, en):
        trace = report["trace"]
        assert trace["meaning"] == [{"id": "p0.0", "frame": "count", "polarity": True}]
        assert trace["intent"] == ["INFORM"]
        assert trace["discourse"][0]["elided"] == [["item", "owner"]]
        assert trace["expression"][0]
        assert trace["grammar"][0]
        assert trace["check"] == ["read"]          # the full clause was parsed back by the pack parser
        assert report["held"] is False


@pytest.mark.parametrize("language,expected", [("한국어", "4개입니다."), ("english", "4 apples.")])
def test_the_live_seam_realizes_an_answered_turn(language, expected):
    subject = "지연 사과" if language == "한국어" else "Jiyeon apples"
    realizer = Realizer()
    text, report = realizer.realize_with_report(answered(subject, "count", "4"), "answered",
                                                "styles/%s.json" % language)
    assert (text, report["realized"], report["held"]) == (expected, True, False)


def test_location_answer_both_languages():
    realizer = Realizer()
    ko = realizer.realize(answered("연필", "location", "서랍"), "answered", "styles/한국어.json")
    en = realizer.realize(answered("pencil", "location", "drawer"), "answered", "styles/english.json")
    assert (ko, en) == ("서랍에 있습니다.", "In the drawer.")


def test_the_realized_stem_is_computed_not_listed():
    # A verb stem no declaration contains still gets its ending by the pack's
    # inflection rules: the grammar layer computes, it does not look sentences up.
    from marco.language.realizer.grammar import Grammar
    from marco.language.realizer.packs import language
    grammar = Grammar(language("한국어"))
    assert grammar.inflect("뒹굴", "present", "background", "regular") == "뒹구는데"
    assert grammar.inflect("뒹굴", "present", "formal_declarative", "regular") == "뒹굽니다"
    assert grammar.particle("서울", "goal") == "로" and grammar.particle("책", "goal") == "으로"
    assert grammar.particle("사과", "topic") == "는" and grammar.particle("연필", "topic") == "은"


def test_unplanned_turns_keep_the_engine_sentence_unchanged():
    realizer = Realizer()
    held = {"status": "unresolved", "answer": "engine sentence", "transitions": []}
    text, report = realizer.realize_with_report(held, "unresolved", "styles/english.json")
    assert text == "engine sentence" and report["realized"] is False and report["reason"] == "no_plan"


def test_meaning_graph_splits_the_engine_compound_subject_without_language():
    source = "english"
    prop = mg.fact_prop(["Jiyeon apples", "count", "4"], source)
    assert prop["roles"]["owner"]["text"] == "Jiyeon" and prop["roles"]["item"]["text"] == "apples"
    single = mg.fact_prop(["apples", "count", "4"], source)          # a word the pack links to a concept
    assert "item" in single["roles"] and "owner" not in single["roles"]
    person = mg.fact_prop(["Jiyeon", "count", "4"], source)
    assert "owner" in person["roles"] and "item" not in person["roles"]
