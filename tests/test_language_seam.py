"""The language seam: ``marco.language.realize`` and its one call in the dialogue.

The 20 phrasings listed in docs/ko/repair-and-english-2026-09-22/unseen-before.json
are played twice: once through the seam, once with ``realize`` replaced by the
pre-seam identity (the sentence the dialogue built). A turn the realizer does
not plan must come out byte for byte the same. A turn it realizes (goal W1)
says the same meaning in a composed sentence: REALIZED pins those sentences,
and each keeps the answer value of the pre-seam sentence. ``None`` marks a
turn with no reply.
"""
import inspect
import json
from pathlib import Path

import pytest

import marco.language
import reasoning_context
from pack_model import development_model
from reasoning_context import ReasoningContext

ROOT = Path(__file__).resolve().parents[1]
IDS = [row["id"] for row in json.loads(
    (ROOT / "docs/ko/repair-and-english-2026-09-22/unseen-before.json").read_text("utf-8"))["rows"]]
CASES = {case["id"]: case for case in json.loads(
    (ROOT / "data/benchmarks/unseen_phrasing_v1.json").read_text("utf-8"))["cases"]}

REALIZED = {
    'ko-06': {2: "5개입니다."},
    'ko-07': {1: "[수선] \"지금 연필은 어디 있어\"를 \"지금 연필은 어디에 있어\"로 읽습니다 "
                 "(규칙 \"지금 연필은 어디에 있어\", '어디' 뒤에 조사 '에' 붙이기, 비용 1/2). 서랍에 있습니다."},
    'en-01': {1: "3 pencils."},
    'en-03': {1: "6 apples."},
    'en-06': {1: "In the drawer."},
    'en-07': {2: "4 cards."},
    'en-09': {2: "4 balls."},
    'en-10': {1: "2 books."},
}


def _answers(case):
    context = ReasoningContext(model=development_model(case["language"]))
    return [None if result is None else result.get("answer")
            for result in (context.turn(text) for text in case["turns"])]


def _before_the_seam(case, monkeypatch):
    """The same dialogue with ``realize`` returning the sentence the dialogue built."""
    with monkeypatch.context() as patch:
        patch.setattr(reasoning_context, "realize", lambda meaning, intent, language: meaning["answer"])
        return _answers(case)


def _numbers(text):
    import re
    return re.findall(r"\d+", re.sub(r"\([^)]*\)|\"[^\"]*\"|'[^']*'", " ", text or ""))


def test_realize_is_exported_with_the_declared_signature():
    assert marco.language.__all__ == ["realize"]
    assert list(inspect.signature(marco.language.realize).parameters) == ["meaning", "intent", "language"]
    assert inspect.signature(marco.language.realize).return_annotation in (str, "str")


def test_the_twenty_phrasings_cover_every_recorded_case():
    assert len(IDS) == 20 and set(IDS) == set(CASES) and set(REALIZED) <= set(IDS)


@pytest.mark.parametrize("case_id", IDS)
def test_unrealized_turns_are_byte_identical_and_realized_turns_keep_the_value(case_id, monkeypatch):
    before = _before_the_seam(CASES[case_id], monkeypatch)
    answers = _answers(CASES[case_id])
    realized = REALIZED.get(case_id, {})
    expected = [realized.get(index, answer) for index, answer in enumerate(before)]
    assert answers == expected
    assert [a.encode("utf-8") for a in answers if a is not None] == \
        [a.encode("utf-8") for a in expected if a is not None]
    for index, sentence in realized.items():
        assert _numbers(sentence)[-1:] == _numbers(before[index])[-1:], (before[index], sentence)
        assert before[index].rstrip(".").split()[-1] in sentence, (before[index], sentence)


def test_every_answered_turn_passes_through_realize_once(monkeypatch):
    calls = []

    def recording(meaning, intent, language):
        calls.append((intent, language))
        return marco.language.realize(meaning, intent, language)

    monkeypatch.setattr(reasoning_context, "realize", recording)
    replies = 0
    for case_id in IDS:
        replies += sum(answer is not None for answer in _answers(CASES[case_id]))
    assert replies and len(calls) == replies
    assert {language for _intent, language in calls} == {"styles/한국어.json", "styles/english.json"}
