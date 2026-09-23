"""The language seam: ``marco.language.realize`` and its one call in the dialogue.

The 20 phrasings listed in docs/ko/repair-and-english-2026-09-22/unseen-before.json
are played twice: once through the seam, once with ``realize`` replaced by the
pre-seam identity (the sentence the dialogue built). A turn the realizer does
not plan must come out byte for byte the same. A turn it realizes (goal W1)
says the same meaning in a composed sentence: REALIZED pins those sentences,
and each answered one keeps the answer value of the pre-seam sentence. ``None`` marks a
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
    'ko-01': {
        0: "[수선] \"하준은 연필 세 개가 있어\"를 \"하준 연필이 세 개 있어\"로 읽습니다 (규칙 \"구슬은 18개 있다\", '하준은'에서 조사 '은' 빼기, '개가'의 조사 '가'를 '연필' 뒤로 옮기기, 비용 2/2). 반영했습니다. 하준 연필은 3개입니다.",
        1: "[보류] \"하준은 지금 연필 몇 개야\"를 읽지 않았습니다 (규칙 \"구슬은 지금 몇 개야\", '연필' 건너뛰기, 비용 3, 한도 2).",
    },
    'ko-03': {
        0: "새 말이 이미 반영한 상태와 맞지 않습니다. 확인해 주세요.",
        1: "\"도윤 사과는 4개 있다. 도윤이 유나에게 사과 1개를 줬다.\"를 아직 읽지 못했습니다. 그래서 지금 값을 정하지 않았습니다. 다른 말로 다시 말해 주세요.",
    },
    'ko-04': {
        0: "[수선] \"유나는 공 여섯 개\"를 \"유나 공은 여섯 개\"로 읽습니다 (규칙 \"구슬은 18개\", '유나는'의 조사 '는'을 '공' 뒤로 옮기기, 비용 1/2). [수선] \"시우는 세 개가 있어\"를 \"시우는 세 개 있어\"로 읽습니다 (규칙 \"구슬은 18개 있다\", '개가'에서 조사 '가' 빼기, 비용 1/2). 반영했습니다. 유나 공은 6개, 시우는 3개입니다.",
    },
    'ko-05': {
        0: "[수선] \"지호는 구슬 열 개가 있어\"를 \"지호 구슬이 열 개 있어\"로 읽습니다 (규칙 \"구슬은 18개 있다\", '지호는'에서 조사 '는' 빼기, '개가'의 조사 '가'를 '구슬' 뒤로 옮기기, 비용 2/2). 반영했습니다. 지호 구슬은 10개입니다.",
        1: "새 말이 이미 반영한 상태와 맞지 않습니다. 확인해 주세요.",
        2: "\"지호가 은서에게 구슬 네 개를 줬어.\"를 아직 읽지 못했습니다. 그래서 지금 값을 정하지 않았습니다. 다른 말로 다시 말해 주세요.",
    },
    'ko-06': {
        0: "반영했습니다.",
        1: "반영했습니다. 이제 민재 사과는 5개입니다.",
        2: "5개입니다.",
    },
    'ko-07': {
        0: "반영했습니다.",
        1: "[수선] \"지금 연필은 어디 있어\"를 \"지금 연필은 어디에 있어\"로 읽습니다 (규칙 \"지금 연필은 어디에 있어\", '어디' 뒤에 조사 '에' 붙이기, 비용 1/2). 서랍에 있습니다.",
    },
    'ko-08': {
        0: "[수선] \"소희는 딸기 다섯 개가 있다\"를 \"소희 딸기가 다섯 개 있다\"로 읽습니다 (규칙 \"구슬은 18개 있다\", '소희는'에서 조사 '는' 빼기, '개가'의 조사 '가'를 '딸기' 뒤로 옮기기, 비용 2/2). 반영했습니다. 소희 딸기는 5개입니다.",
        1: "[수선] \"소희가 준우에게 두 개 줬다\"를 \"소희가 준우에게 두 개를 줬다\"로 읽습니다 (규칙 \"하루가 모래에게 2개를 줬다\", '개' 뒤에 조사 '를' 붙이기, 비용 1/2). 새 말이 이미 반영한 상태와 맞지 않습니다. 확인해 주세요.",
    },
    'ko-09': {
        0: "[수선] \"태오는 사탕 아홉 개가 있어\"를 \"태오 사탕이 아홉 개 있어\"로 읽습니다 (규칙 \"구슬은 18개 있다\", '태오는'에서 조사 '는' 빼기, '개가'의 조사 '가'를 '사탕' 뒤로 옮기기, 비용 2/2). 반영했습니다. 태오 사탕은 9개입니다.",
        1: "새 말이 이미 반영한 상태와 맞지 않습니다. 확인해 주세요.",
        2: "\"아까 준 건 세 개가 아니라 두 개야\"가 가리키는 앞선 사건을 찾지 못했습니다. 그래서 고치지 않았습니다.",
        3: "\"태오가 하나에게 사탕 세 개를 줬어.\"를 아직 읽지 못했습니다. 그래서 지금 값을 정하지 않았습니다. 다른 말로 다시 말해 주세요.",
    },
    'ko-10': {
        0: "[수선] \"은우는 쿠키 두 개가 있어\"를 \"은우 쿠키가 두 개 있어\"로 읽습니다 (규칙 \"구슬은 18개 있다\", '은우는'에서 조사 '는' 빼기, '개가'의 조사 '가'를 '쿠키' 뒤로 옮기기, 비용 2/2). 반영했습니다. 은우 쿠키는 2개입니다.",
    },
    'en-01': {
        0: "Recorded.",
        1: "3 pencils.",
    },
    'en-02': {
        0: "The new statement does not fit what was already recorded. Please check it.",
        1: "I could not read \"Emma has seven oranges. Emma gave Liam two oranges.\" yet. So I did not fix the current value. Please say it another way.",
    },
    'en-03': {
        0: "Recorded. Mia has 6 apples.",
        1: "6 apples.",
    },
    'en-04': {
        0: "Recorded.",
        1: "The new statement does not fit what was already recorded. Please check it.",
        2: "I could not read \"Leo gave Zoe four marbles.\" yet. So I did not fix the current value. Please say it another way.",
    },
    'en-05': {
        0: "Recorded.",
        1: "The new statement does not fit what was already recorded. Please check it.",
        2: "I could not read \"Ella gave Sam three.\" yet. So I did not fix the current value. Please say it another way.",
    },
    'en-06': {
        0: "Recorded.",
        1: "In the drawer.",
    },
    'en-07': {
        0: "Recorded.",
        1: "Recorded. Now Owen has 3 cards and Ruby has 4.",
        2: "4 cards.",
    },
    'en-08': {
        0: "Recorded.",
        1: "The new statement does not fit what was already recorded. Please check it.",
        2: "I could not find an earlier event that \"the one given was two, not three\" refers to. So I did not correct anything.",
        3: "I could not read \"Lily gave Max three candies.\" yet. So I did not fix the current value. Please say it another way.",
    },
    'en-09': {
        0: "Recorded.",
        1: "Recorded. Now Jack has 4 balls.",
        2: "4 balls.",
    },
    'en-10': {
        0: "Recorded.",
        1: "2 books.",
    },
}


def _answers(case, statuses=None):
    context = ReasoningContext(model=development_model(case["language"]))
    results = [context.turn(text) for text in case["turns"]]
    if statuses is not None:
        statuses.extend(None if result is None else result.get("status") for result in results)
    return [None if result is None else result.get("answer") for result in results]


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
    statuses = []
    answers = _answers(CASES[case_id], statuses)
    answered = {index for index, status in enumerate(statuses) if status == "answered"}
    realized = REALIZED.get(case_id, {})
    expected = [realized.get(index, answer) for index, answer in enumerate(before)]
    assert answers == expected
    assert [a.encode("utf-8") for a in answers if a is not None] == \
        [a.encode("utf-8") for a in expected if a is not None]
    for index, sentence in realized.items():
        if index in answered:
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
