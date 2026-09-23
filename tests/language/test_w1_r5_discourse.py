"""R5: established referents are elided, known facts are not repeated — counted on fixed dialogues.

Fixed dialogues: the §12 dialogue in each language, the 20 frozen phrasings
(docs/ko/repair-and-english-2026-09-22/unseen-before.json) and the W1 dev
dialogues (tests/language/w1_dev_dialogues.json). Run with the W1-1 meaning
block attached in the test. ``discourse_counts()`` is also what
``w1_measure.py`` publishes.
"""
import json
from pathlib import Path

from w1_harness import play

from bench.seven_step_dialogue import SCRIPTS

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def fixed_dialogues():
    dialogues = []
    for language, script in SCRIPTS.items():
        dialogues.append({"id": "section12-" + language, "language": language, "turns": script["turns"],
                          "companion": "english" if language == "한국어" else "한국어"})
    ids = [row["id"] for row in json.loads(
        (ROOT / "docs/ko/repair-and-english-2026-09-22/unseen-before.json").read_text("utf-8"))["rows"]]
    cases = {c["id"]: c for c in json.loads((ROOT / "data/benchmarks/unseen_phrasing_v1.json").read_text("utf-8"))["cases"]}
    dialogues += [{"id": i, "language": cases[i]["language"], "turns": cases[i]["turns"]} for i in ids]
    dialogues += json.loads((HERE / "w1_dev_dialogues.json").read_text("utf-8"))["dialogues"]
    return dialogues


def discourse_counts(dialogues=None, fields=True):
    totals = {"dialogues": 0, "turns": 0, "replies": 0, "realized": 0, "held": 0, "passthrough": 0,
              "eligible_referents": 0, "elided_referents": 0, "known_facts": 0, "known_facts_omitted": 0,
              "known_facts_repeated": 0, "repeated_roles": 0, "repeated_roles_elided": 0}
    rows = []
    for dialogue in dialogues or fixed_dialogues():
        turns, _context = play(dialogue["language"], dialogue["turns"], companion=dialogue.get("companion"),
                               fields=fields)
        totals["dialogues"] += 1
        for text, result, report in turns:
            totals["turns"] += 1
            if result is None or report is None:
                continue
            totals["replies"] += 1
            if not report.get("realized"):
                totals["passthrough"] += 1
                continue
            totals["held" if report.get("held") else "realized"] += 1
            for key, value in (report.get("discourse") or {}).items():
                totals[key] += value
            rows.append({"dialogue": dialogue["id"], "input": text, "answer": result.get("answer")})
    return totals, rows


def test_discourse_rules_hold_on_the_fixed_dialogues():
    totals, _rows = discourse_counts()
    assert totals["dialogues"] == 2 + 20 + 12
    # every referent the question established is left out of its answer
    assert totals["eligible_referents"] > 0 and totals["elided_referents"] == totals["eligible_referents"]
    # a fact the user stated this turn is said back only when its reading added something
    assert totals["known_facts"] > 0
    assert totals["known_facts_omitted"] + totals["known_facts_repeated"] == totals["known_facts"]
    assert totals["known_facts_omitted"] > totals["known_facts_repeated"]
    # a role repeated in the next clause of the same frame is not said again
    assert totals["repeated_roles"] > 0 and totals["repeated_roles_elided"] == totals["repeated_roles"]
    assert totals["held"] == 0


def test_a_repeated_fact_is_one_whose_reading_added_something():
    from marco.language.realizer import Realizer
    realizer = Realizer()
    turns, _context = play("english", ["Minsu has five apples, and Jiyeon has two."], realizer=realizer)
    _text, result, report = turns[0]
    # "Jiyeon has two" inherits "apples" by ellipsis: that reading is said; Minsu's plain statement is not.
    assert report["discourse"]["known_facts"] == 2 and report["discourse"]["known_facts_repeated"] == 1
    assert result["answer"] == "Recorded. Jiyeon has 2 apples."
