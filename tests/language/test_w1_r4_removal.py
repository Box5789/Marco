"""R4: delete an event from the Meaning Graph; its clause becomes unproducible.

If a deleted proposition's clause still appears, the realizer reads it from
somewhere it must not. Checked three ways, in both languages, on the §12
dialogue:

* every proposition of every turn's graph, deleted one at a time;
* the transfer event deleted from the turn's recorded changes (the graph's source);
* the engine's own sentence replaced: realized output does not change.
"""
import copy
import re

import pytest

from w1_harness import play

from bench.seven_step_dialogue import SCRIPTS
from marco.language.realizer import Realizer


@pytest.fixture(scope="module", params=["english", "한국어"])
def dialogue(request):
    language = request.param
    other = "english" if language == "한국어" else "한국어"
    script = SCRIPTS[language]
    rows, _context = play(language, script["turns"], companion=other)
    return language, [result for _text, result, _report in rows]


def _without(graph, prop_id):
    graph = copy.deepcopy(graph)
    for act in graph["acts"]:
        act["props"] = [p for p in act["props"] if p["id"] != prop_id]
    graph["acts"] = [act for act in graph["acts"] if act["props"]]
    graph["props"] = [p for p in graph["props"] if p["id"] != prop_id]
    return graph


def test_each_deleted_proposition_takes_its_clause_with_it(dialogue):
    language, results = dialogue
    realizer = Realizer()
    path = "styles/%s.json" % language
    removals = 0
    for result in results:
        graph = realizer.build_graph(copy.deepcopy(result), path)
        if graph is None:
            continue
        full_text, full = realizer.realize_graph(copy.deepcopy(graph), graph["answer_language"])
        assert not full["held"]
        clause_text = {c["prop"]: c["text"] for c in full["clauses"]}
        for prop in graph["props"]:
            if prop["id"] not in clause_text:
                continue            # the discourse planner already left it unsaid (a known fact)
            text, report = realizer.realize_graph(_without(graph, prop["id"]), graph["answer_language"])
            assert not report["held"]
            gone = clause_text[prop["id"]]
            others = [t for p, t in clause_text.items() if p != prop["id"]]
            if any(gone in other for other in others):
                continue            # the same words are another proposition's own clause
            assert gone not in text, (prop["frame"], gone, text)
            removals += 1
    assert removals >= 15


def test_a_transfer_deleted_from_the_recorded_changes_is_unproducible(dialogue):
    language, results = dialogue
    transfer_turn = copy.deepcopy(results[1])
    path = "styles/%s.json" % language
    realizer = Realizer()
    said, report = realizer.realize_with_report(copy.deepcopy(transfer_turn), "observed", path)
    assert "transfer" in [c["frame"] for c in report["clauses"]]
    event = (transfer_turn["meaning"]["changes"][0].get("evidence") or {}).get("source")
    transfer_turn["meaning"]["changes"] = [row for row in transfer_turn["meaning"]["changes"]
                                           if (row.get("evidence") or {}).get("source") != event]
    cut, cut_report = realizer.realize_with_report(transfer_turn, "observed", path)
    assert "transfer" not in [c["frame"] for c in cut_report["clauses"]]
    # no amount and no resulting count survives; a repair note cites its own cost
    assert [c["text"] for c in cut_report["clauses"]
            if c["frame"] != "repair_note" and re.search(r"\d", c["text"])] == []
    assert len(cut) < len(said)


def test_the_engine_sentence_is_never_read_for_a_realized_turn(dialogue):
    language, results = dialogue
    path = "styles/%s.json" % language
    for result in results:
        first, report = Realizer().realize_with_report(copy.deepcopy(result), result["status"], path)
        if not report["realized"]:
            continue
        poisoned = {**copy.deepcopy(result), "answer": "0 0 0 poisoned"}
        second = Realizer().realize(poisoned, result["status"], path)
        assert first == second and "poisoned" not in second
