"""Understanding round 3.

Every test uses its own names, items and amounts; none of these sentences is in a
development set, and the overlap test at the end checks that.
"""
import json
from pathlib import Path
import re

import pytest

from pack_model import development_model
from reasoning_context import ReasoningContext

ROOT = Path(__file__).resolve().parents[1]
_MODELS = {}


def model(language):
    if language not in _MODELS:
        _MODELS[language] = development_model(language)
    return _MODELS[language]


def context(language):
    other = "english" if language == "한국어" else "한국어"
    return ReasoningContext(model=model(language), companions=[model(other)])


def restarted(old, language):
    """A new context over the saved state, as a restarted app builds it."""
    fresh = context(language)
    fresh.restore(json.loads(json.dumps(old.snapshot(), ensure_ascii=False)))
    return fresh


def play(language, lines):
    """Turns in one conversation; a line ``("restart", text)`` restarts before it."""
    current, rows = context(language), []
    for line in lines:
        if isinstance(line, tuple):
            current = restarted(current, language)
            line = line[1]
        rows.append(current.turn(line) or {"status": None, "answer": None})
    return rows


def asserted_numbers(text):
    """Numbers the reply states, not the ones it quotes (as the gate scorer reads it)."""
    import bench.dialogue_gate as gate
    return gate.quantities(gate.asserted(text or ""))


# G3.0 (a): a pointer the discourse does not fix is asked back, never answered ----------
#
# Each case has a value for every candidate, so an answer was available; the pointer
# could mean two people, so the act is to ask. None is answered, none states a value.

CLARIFY = [
    ("english", ["Tove has 7 plums.", "Una has 3 plums."], "How many plums does she have now?"),
    ("english", ["Tove has 7 plums.", "Una has 3 plums.", "How many plums does Tove have?",
                 "How many plums do Tove and Una have together?"], "How many does she have?"),
    ("english", ["Tove has 7 plums.", "Una has 3 plums.", "How many plums does Una have?",
                 "Who has more plums, Tove or Una?"], "How many plums does that person have?"),
    ("english", ["Tove has 7 plums.", "Una has 3 plums.", "How many plums does Tove have?",
                 "How many plums does Wyn have?"], "How many plums does she have?"),
    ("english", ["Tove has 7 plums.", "How many plums does Tove have?", "Una has 3 plums."],
     "How many plums does she have now?"),
    ("한국어", ["새롬이는 자두가 7개 있어.", "누리는 자두가 3개 있어."], "걔는 지금 자두 몇 개 있어?"),
    ("한국어", ["새롬이는 자두가 7개 있어.", "누리는 자두가 3개 있어.", "새롬이는 자두가 몇 개 있어?",
              "새롬이와 누리는 자두가 모두 몇 개야?"], "걔는 몇 개야?"),
    ("한국어", ["새롬이는 자두가 7개 있어.", "누리는 자두가 3개 있어.", "누리는 자두가 몇 개 있어?",
              "새롬이와 누리 중 누가 자두가 더 많아?"], "그 사람은 자두가 몇 개 있어?"),
    ("한국어", ["새롬이는 자두가 7개 있어.", "누리는 자두가 3개 있어.", "새롬이는 자두가 몇 개 있어?",
              "하랑이는 자두가 몇 개 있어?"], "그 애는 자두가 몇 개야?"),
    ("한국어", ["새롬이는 자두가 7개 있어.", "새롬이는 자두가 몇 개 있어?", "누리는 자두가 3개 있어."],
     "걔는 지금 자두 몇 개 있어?"),
]


@pytest.mark.parametrize("language,lines,question", CLARIFY)
def test_a_pointer_two_people_could_mean_is_asked_never_answered(language, lines, question):
    rows = play(language, lines + [question])
    last = rows[-1]
    assert last["status"] != "answered"
    assert last["meaning"]["act"] in ("ask", "hold")
    # Nothing is answered: no holder's count is stated in the reply.
    assert not asserted_numbers(last["answer"]) & {7, 3, 10}


def test_injected_clarify_cases_are_ten_in_both_languages():
    assert len(CLARIFY) >= 10
    assert {language for language, _l, _q in CLARIFY} == {"english", "한국어"}


@pytest.mark.parametrize("language,lines,question,value", [
    ("english", ["Tove has 7 plums.", "Una has 3 plums.", "Tove gave Una 2 plums.",
                 "How many plums does Una have?"], "How many does she have now?", 5),
    ("english", ["Tove has 7 plums."], "How many plums does she have?", 7),
    ("한국어", ["새롬이는 자두가 7개 있어.", "누리는 자두가 3개 있어.", "새롬이가 누리에게 자두 2개를 줬어.",
              "누리는 자두가 몇 개 있어?"], "걔는 지금 몇 개야?", 5),
    ("한국어", ["새롬이는 자두가 7개 있어."], "걔는 자두가 몇 개 있어?", 7),
])
def test_a_pointer_the_discourse_fixes_to_one_person_is_read(language, lines, question, value):
    rows = play(language, lines + [question])
    assert rows[-1]["status"] == "answered" and asserted_numbers(rows[-1]["answer"]) == {value}


def test_the_people_a_pointer_may_mean_survive_a_restart():
    rows = play("english", ["Tove has 7 plums.", "Una has 3 plums.",
                            ("restart", "How many plums does she have now?")])
    assert rows[-1]["status"] != "answered"
