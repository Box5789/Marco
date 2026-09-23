"""The language seam: ``marco.language.realize`` and its one call in the dialogue.

The 20 phrasings listed in docs/ko/repair-and-english-2026-09-22/unseen-before.json
are played twice: once through the seam, once with ``realize`` replaced by the
pre-seam identity (the sentence the dialogue built). A turn the realizer does
not plan must come out byte for byte the same. A turn it realizes (goal W1)
says the same meaning in a composed sentence: REALIZED pins those sentences by
the first 20 hex digits of their SHA-256 (the text quotes user words that must
not appear verbatim in a test file, see test_f1_3 in test_dialogue_gate.py),
and each answered one keeps the answer value of the pre-seam sentence. ``None`` marks a
turn with no reply.
"""
import hashlib
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
    'ko-01': {0: 'e7132b4f29f6e96d460c', 1: '1ad97b6bdaf86fb66fea'},
    'ko-03': {0: 'ecbbccfb685b3bbb0738', 1: '8e9069ab022a2c6c3220'},
    'ko-04': {0: 'b3e325da6c9e35542e00'},
    'ko-05': {0: '4efad3ad2c6142a9f541', 1: 'ecbbccfb685b3bbb0738', 2: '736c1f47d36366063ddb'},
    'ko-06': {0: 'de529bf8452f578c92f9', 1: '1377ce2af0b31d1bdbe4', 2: '738d55eca11ee4c34a33'},
    'ko-07': {0: 'de529bf8452f578c92f9', 1: '9791612d97c0b370f6d6'},
    'ko-08': {0: '4cbbb1c87b85fbe51ba2', 1: '8e39fd66a17f4cf05cab'},
    'ko-09': {0: 'ba335e7f4501e7447cc2', 1: 'ecbbccfb685b3bbb0738', 2: '0f5e0d83a645e2e2f228', 3: '6555b110b8aa79627cbe'},
    'ko-10': {0: '631e12d76b89b1d025d2'},
    'en-01': {0: '6f77cb3948368060dffa', 1: '3243f803374fb149f6f7'},
    'en-02': {0: 'b4b4d16864402acedf8c', 1: 'b49ae171f78ec4168507'},
    'en-03': {0: 'a6a4f6e7838539c9efa0', 1: 'aed953c11fa88f7dfffb'},
    'en-04': {0: '6f77cb3948368060dffa', 1: 'b4b4d16864402acedf8c', 2: 'c504dd645e5f1c46eda5'},
    'en-05': {0: '6f77cb3948368060dffa', 1: 'b4b4d16864402acedf8c', 2: 'd4b36e9283e2e71118ef'},
    'en-06': {0: '6f77cb3948368060dffa', 1: '8abc9867e26c2abcda46'},
    'en-07': {0: '6f77cb3948368060dffa', 1: '0a84a1b02d1b29fb1a23', 2: '1f6b8a2417214e30c9a9'},
    'en-08': {0: '6f77cb3948368060dffa', 1: 'b4b4d16864402acedf8c', 2: 'db4500aaf9115e1cebb2', 3: '06251b92116fc2eacad7'},
    'en-09': {0: '6f77cb3948368060dffa', 1: '8049f41bd48c88c1f18a', 2: '5b9a2c87e08393537b5e'},
    'en-10': {0: '6f77cb3948368060dffa', 1: '2aa53e47ed2f89eac8e3'},
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
    assert len(answers) == len(before)
    for index, answer in enumerate(answers):
        if index in realized:
            assert hashlib.sha256(answer.encode("utf-8")).hexdigest()[:20] == realized[index], answer
        else:
            assert answer == before[index]
    for index in realized:
        sentence = answers[index]
        if index in answered:
            assert _numbers(sentence)[-1:] == _numbers(before[index])[-1:], (before[index], sentence)
            assert before[index].rstrip(".").split()[-1] in sentence, (before[index], sentence)


# Sums and comparisons (G2.0(c)): the answer is no single fact; the proof lists each
# member's count last, and the realized sentence once said the last member's count.
# Values here are the test's own arithmetic over the stated amounts, not engine output.
SUMS = {
    "english": {"turns": ["Nell has 5 jars and Oto has 4.", "Nell gave Oto 2 jars.",
                          "How many jars do Nell and Oto have together?",
                          "Who has more jars now, Nell or Oto?"],
                "total": (2, 5 + 4), "more": (3, "Oto", "Nell")},
    "한국어": {"turns": ["보라는 사탕이 다섯 개 있어.", "현수는 사탕이 네 개 있어.",
                        "보라가 현수에게 사탕 두 개를 줬어.", "두 사람 합치면 사탕 몇 개야?"],
              "total": (3, 5 + 4), "more": None},
}


@pytest.mark.parametrize("language", sorted(SUMS))
def test_a_total_and_a_comparison_keep_the_value_the_reasoning_produced(language, monkeypatch):
    spec = SUMS[language]
    case = {"language": language, "turns": spec["turns"]}
    before = _before_the_seam(case, monkeypatch)
    statuses = []
    after = _answers(case, statuses)
    turn, total = spec["total"]
    assert statuses[turn] == "answered"
    assert _numbers(after[turn]) == _numbers(before[turn]) == [str(total)]
    if spec["more"] is not None:
        turn, winner, other = spec["more"]
        assert statuses[turn] == "answered"
        for answer in (before[turn], after[turn]):
            assert winner in answer and other not in answer


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
    # The dialogue passes the model it speaks for (request W1-3); its language is the pack it carries.
    from marco.language.realizer.packs import stem_of
    assert all(hasattr(language, "parser") for _intent, language in calls)
    assert {stem_of(language) for _intent, language in calls} == {"한국어", "english"}
