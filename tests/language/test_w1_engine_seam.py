"""W1-2: answers the engine composes from graph routing pass through the language seam.

The realizer has no plan for a graph's own line yet, so the line comes back
unchanged; what changes is that it now goes through ``realize`` once, with a
language-free meaning (the graph, the verdict, the line as a quoted source).
"""
import pytest

import engine
import marco.language


@pytest.fixture
def calls(monkeypatch):
    seen = []
    original = marco.language.realize

    def recording(meaning, intent, language):
        seen.append({"meaning": meaning["meaning"], "intent": intent})
        return original(meaning, intent, language)
    monkeypatch.setattr(marco.language, "realize", recording)
    return seen


@pytest.mark.language("한국어")
def test_engine_answer_goes_through_realize_once_and_keeps_its_line(calls, monkeypatch):
    before = engine._answer("고혈압이 뭐야")
    after = engine.answer("고혈압이 뭐야")
    assert after == before
    assert len(calls) == 1
    meaning = calls[0]["meaning"]
    assert meaning["act"] in ("hold", "inform") and meaning["source"]["text"] == before[2]
    assert calls[0]["intent"] == before[1]


@pytest.mark.language("한국어")
def test_dialogue_say_goes_through_realize_once(calls):
    dialogue = engine.Dialogue()
    graph, verdict, line = dialogue.say("고혈압이 뭐야")
    assert len(calls) == 1 and calls[0]["meaning"]["source"]["text"] == line
