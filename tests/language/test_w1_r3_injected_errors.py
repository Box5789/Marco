"""R3: the semantic check blocks injected realizer faults; none is emitted.

Three faults, each a change to one realizer declaration, in each language:

* swap — the transfer expression gives the giver's place to the receiver;
* number — the number rule says another number than the one meant;
* negation — the negation of a negative clause is dropped.

For each, the clean realizer says the turn; the faulty one's clause fails the
check with the reader that should see it, the faulty clause never appears in
the output, and the turn is held (or said by a plainer expression that passes).
"""
import copy
import json

import pytest

from w1_harness import play

from marco.language.realizer import Realizer
from marco.language.realizer.grammar import ClauseRealizer, Grammar
from marco.language.realizer.packs import HERE, Language

TURNS = {
    "한국어": ["민수는 사과 다섯 개, 지연은 두 개가 있어.", "민수가 지연에게 두 개 줬어.", "지연은 지금 몇 개야?",
             "그 사람은 어디 있어?", "아까 준 건 두 개가 아니라 한 개야."],
    "english": ["Minsu has five apples, and Jiyeon has two.", "Minsu gave Jiyeon two.", "How many does Jiyeon have now?",
                "Where is that person?", "Actually, the one given was one, not two."],
}


def declarations(language):
    return json.loads((HERE / (language + ".json")).read_text(encoding="utf-8"))


def swap_transfer_roles(decl):
    for candidate in decl["expressions"]["transfer"]:
        for part in candidate["parts"]:
            if part.get("np") == ["giver"]:
                part["np"] = ["receiver"]
            elif part.get("np") == ["receiver"]:
                part["np"] = ["giver"]


def change_numbers(decl):
    words = decl["numbers"]["words"]
    decl["numbers"]["style"] = "words"
    decl["numbers"]["words"] = {value: words[str(int(value) + 1)] for value in words if str(int(value) + 1) in words}


def drop_negation(decl):
    for candidates in decl["expressions"].values():
        for candidate in candidates:
            kept = []
            for part in candidate["parts"]:
                part.pop("negation", None)
                if part.get("lex") in ("never", "no"):
                    continue
                if part.get("verb") == "not_exist":
                    part["verb"] = "exist"
                kept.append(part)
            candidate["parts"] = kept


FAULTS = {"swap": (swap_transfer_roles, 1, "transfer", "parse"),
          "number": (change_numbers, 2, "count", "numbers"),
          "negation": (drop_negation, 4, "new_event", "polarity")}


@pytest.fixture(scope="module")
def results():
    out = {}
    for language, turns in TURNS.items():
        rows, _context = play(language, turns)
        out[language] = [result for _text, result, _report in rows]
    return out


def _faulty_surface(language, decl, prop):
    """What the faulty declaration would say for this proposition, without the check."""
    grammar = Grammar(Language(language, decl))
    candidate = decl["expressions"][prop["frame"]][0]
    clause = ClauseRealizer(grammar).realize(prop, candidate, sentence="declarative",
                                             register=decl["register"]["default"])
    return clause.text(grammar.ortho["word_separator"])


@pytest.mark.parametrize("language", ["한국어", "english"])
@pytest.mark.parametrize("fault", sorted(FAULTS))
def test_an_injected_fault_is_caught_and_never_emitted(results, language, fault):
    mutate, index, frame, reader = FAULTS[fault]
    result = copy.deepcopy(results[language][index])
    path = "styles/%s.json" % language

    clean_text, clean = Realizer().realize_with_report(copy.deepcopy(result), result["status"], path)
    assert clean["realized"] and not clean["held"], clean
    clean_frames = [c["frame"] for c in clean["clauses"]]
    assert frame in clean_frames

    decl = declarations(language)
    mutate(decl)
    faulty = Realizer(overrides={language: decl})
    text, report = faulty.realize_with_report(copy.deepcopy(result), result["status"], path)
    graph = faulty.build_graph(copy.deepcopy(result), path)
    prop = next(p for p in graph["props"] if p["frame"] == frame)
    bad = _faulty_surface(language, decl, prop)

    blocked = [c for c in report["clauses"] if c["frame"] == frame]
    assert blocked and blocked[0].get("blocked"), report["clauses"]
    readers = {failure["reader"] for attempt in blocked[0]["attempts"]
               for failure in attempt.get("check", {}).get("failures", [])}
    assert reader in readers, blocked[0]["attempts"]
    assert report["held"] is True and text and text != clean_text
    if fault == "number":
        wrong = decl["numbers"]["words"][prop["roles"]["value"]["number"]]
        assert wrong in bad and wrong not in text
    else:
        assert bad not in text


def test_the_check_is_not_sampled_every_realized_clause_is_checked(results):
    realizer = Realizer()
    checked = 0
    for language, rows in results.items():
        for result in rows:
            _text, report = realizer.realize_with_report(copy.deepcopy(result), result["status"],
                                                         "styles/%s.json" % language)
            for clause in report.get("clauses", []):
                assert clause["attempts"] and all("check" in a or "error" in a for a in clause["attempts"])
                checked += 1
    assert checked >= 20
