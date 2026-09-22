"""The language seam: ``marco.language.realize`` and its one call in the dialogue.

The stub must return exactly what the dialogue returned before the seam.
EXPECTED holds every turn's answer for the 20 phrasings listed in
docs/ko/repair-and-english-2026-09-22/unseen-before.json, recorded on 4adc504
before ``realize`` was wired in. ``None`` marks a turn with no reply.
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

EXPECTED = {
    'ko-01': [
        "[수선] 원문 \"하준은 연필 세 개가 있어\" → 가장 가까운 규칙 \"구슬은 18개 있다\", 수선: '하준은'에서 조사 '은' 빼기, '개가'의 조사 '가'를 '연필' 뒤로 옮기기 (비용 2/2). 읽은 뜻: \"하준 연필이 세 개 있어\". 이 대화에 반영했습니다: 하준 연필 3개.",
        "[보류] 원문 \"하준은 지금 연필 몇 개야\": 가장 가까운 규칙 \"구슬은 지금 몇 개야\"에 놓으려면 다음 수선이 필요합니다 — '연필' 건너뛰기. 비용 3이 한도 2를 넘어 반영하지 않았습니다.",
    ],
    'ko-02': [
        None,
        None,
    ],
    'ko-03': [
        "이전 상태와 새 조건을 함께 적용할 수 없습니다. 조건을 확인해 주세요.",
        "이 대화에서 아직 이해하지 못한 말이 있어 지금 값을 확정할 수 없습니다: \"도윤 사과는 4개 있다. 도윤이 유나에게 사과 1개를 줬다.\". 그 말을 풀어 주시면 이어서 계산합니다.",
    ],
    'ko-04': [
        "[수선] 원문 \"유나는 공 여섯 개\" → 가장 가까운 규칙 \"구슬은 18개\", 수선: '유나는'의 조사 '는'를 '공' 뒤로 옮기기 (비용 1/2). 읽은 뜻: \"유나 공은 여섯 개\". [수선] 원문 \"시우는 세 개가 있어\" → 가장 가까운 규칙 \"구슬은 18개 있다\", 수선: '개가'에서 조사 '가' 빼기 (비용 1/2). 읽은 뜻: \"시우는 세 개 있어\". 이 대화에 반영했습니다: 유나 공 6개, 시우 공 3개.",
        None,
    ],
    'ko-05': [
        "[수선] 원문 \"지호는 구슬 열 개가 있어\" → 가장 가까운 규칙 \"구슬은 18개 있다\", 수선: '지호는'에서 조사 '는' 빼기, '개가'의 조사 '가'를 '구슬' 뒤로 옮기기 (비용 2/2). 읽은 뜻: \"지호 구슬이 열 개 있어\". 이 대화에 반영했습니다: 지호 구슬 10개.",
        "이전 상태와 새 조건을 함께 적용할 수 없습니다. 조건을 확인해 주세요.",
        "이 대화에서 아직 이해하지 못한 말이 있어 지금 값을 확정할 수 없습니다: \"지호가 은서에게 구슬 네 개를 줬어.\". 그 말을 풀어 주시면 이어서 계산합니다.",
    ],
    'ko-06': [
        "이 대화에 반영했습니다: 민재 사과 8개.",
        "이 대화에 반영했습니다: 민재 사과 8개 → 5개.",
        "5개입니다.",
    ],
    'ko-07': [
        "이 대화에 반영했습니다: 연필 → 서랍.",
        "[수선] 원문 \"지금 연필은 어디 있어\" → 가장 가까운 규칙 \"지금 연필은 어디에 있어\", 수선: '어디' 뒤에 조사 '에' 붙이기 (비용 1/2). 읽은 뜻: \"지금 연필은 어디에 있어\". 서랍에 있습니다.",
    ],
    'ko-08': [
        "[수선] 원문 \"소희는 딸기 다섯 개가 있다\" → 가장 가까운 규칙 \"구슬은 18개 있다\", 수선: '소희는'에서 조사 '는' 빼기, '개가'의 조사 '가'를 '딸기' 뒤로 옮기기 (비용 2/2). 읽은 뜻: \"소희 딸기가 다섯 개 있다\". 이 대화에 반영했습니다: 소희 딸기 5개.",
        "[수선] 원문 \"소희가 준우에게 두 개 줬다\" → 가장 가까운 규칙 \"하루가 모래에게 2개를 줬다\", 수선: '개' 뒤에 조사 '를' 붙이기 (비용 1/2). 읽은 뜻: \"소희가 준우에게 두 개를 줬다\". 이전 상태와 새 조건을 함께 적용할 수 없습니다. 조건을 확인해 주세요.",
        None,
    ],
    'ko-09': [
        "[수선] 원문 \"태오는 사탕 아홉 개가 있어\" → 가장 가까운 규칙 \"구슬은 18개 있다\", 수선: '태오는'에서 조사 '는' 빼기, '개가'의 조사 '가'를 '사탕' 뒤로 옮기기 (비용 2/2). 읽은 뜻: \"태오 사탕이 아홉 개 있어\". 이 대화에 반영했습니다: 태오 사탕 9개.",
        "이전 상태와 새 조건을 함께 적용할 수 없습니다. 조건을 확인해 주세요.",
        "\"아까 준 건 세 개가 아니라 두 개야\"이 가리키는 앞선 사건을 이 대화에서 찾지 못해 고치지 않았습니다.",
        "이 대화에서 아직 이해하지 못한 말이 있어 지금 값을 확정할 수 없습니다: \"태오가 하나에게 사탕 세 개를 줬어.\". 그 말을 풀어 주시면 이어서 계산합니다.",
    ],
    'ko-10': [
        "[수선] 원문 \"은우는 쿠키 두 개가 있어\" → 가장 가까운 규칙 \"구슬은 18개 있다\", 수선: '은우는'에서 조사 '는' 빼기, '개가'의 조사 '가'를 '쿠키' 뒤로 옮기기 (비용 2/2). 읽은 뜻: \"은우 쿠키가 두 개 있어\". 이 대화에 반영했습니다: 은우 쿠키 2개.",
        None,
    ],
    'en-01': [
        "Recorded in this conversation: Noah pencils 3.",
        "3 pencils.",
    ],
    'en-02': [
        "The earlier state and the new condition cannot both apply. Please check the condition.",
        "Something earlier in this conversation is still not understood, so I cannot fix the current value: \"Emma has seven oranges. Emma gave Liam two oranges.\". If you rephrase it I will continue.",
    ],
    'en-03': [
        "Recorded in this conversation: Ava apples 4, Mia apples 6.",
        "6.",
    ],
    'en-04': [
        "Recorded in this conversation: Leo marbles 10.",
        "The earlier state and the new condition cannot both apply. Please check the condition.",
        "Something earlier in this conversation is still not understood, so I cannot fix the current value: \"Leo gave Zoe four marbles.\". If you rephrase it I will continue.",
    ],
    'en-05': [
        "Recorded in this conversation: Ella cookies 8.",
        "The earlier state and the new condition cannot both apply. Please check the condition.",
        "Something earlier in this conversation is still not understood, so I cannot fix the current value: \"Ella gave Sam three.\". If you rephrase it I will continue.",
    ],
    'en-06': [
        "Recorded in this conversation: pencil → drawer.",
        "The pencil is in the drawer.",
    ],
    'en-07': [
        "Recorded in this conversation: Owen cards 5, Ruby cards 2.",
        "Recorded in this conversation: Owen cards 5 → 3, Ruby cards 2 → 4.",
        "4 cards.",
    ],
    'en-08': [
        "Recorded in this conversation: Lily candies 9.",
        "The earlier state and the new condition cannot both apply. Please check the condition.",
        "I found no earlier event in this conversation that \"the one given was two, not three\" refers to, so nothing was corrected.",
        "Something earlier in this conversation is still not understood, so I cannot fix the current value: \"Lily gave Max three candies.\". If you rephrase it I will continue.",
    ],
    'en-09': [
        "Recorded in this conversation: Jack balls 6.",
        "Recorded in this conversation: Jack balls 6 → 4.",
        "4 balls.",
    ],
    'en-10': [
        "Recorded in this conversation: Grace books 2.",
        "2 books.",
    ],
}


def _answers(case):
    context = ReasoningContext(model=development_model(case["language"]))
    return [None if result is None else result.get("answer")
            for result in (context.turn(text) for text in case["turns"])]


def test_realize_is_exported_with_the_declared_signature():
    assert marco.language.__all__ == ["realize"]
    assert list(inspect.signature(marco.language.realize).parameters) == ["meaning", "intent", "language"]
    assert inspect.signature(marco.language.realize).return_annotation in (str, "str")


def test_the_twenty_phrasings_cover_every_recorded_case():
    assert len(IDS) == 20 and set(IDS) == set(EXPECTED) == set(CASES)


@pytest.mark.parametrize("case_id", IDS)
def test_output_is_byte_identical_to_the_dialogue_before_the_seam(case_id):
    answers = _answers(CASES[case_id])
    assert answers == EXPECTED[case_id]
    assert [a.encode("utf-8") for a in answers if a is not None] == \
        [a.encode("utf-8") for a in EXPECTED[case_id] if a is not None]


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
