from response_composer import compare, compose
from unittest.mock import patch

from tests.test_reasoning_persistence import create_app


def test_composer_selects_only_grounded_sentences_and_respects_the_limit():
    evidence = [
        {"text": "첫 근거입니다.", "source": "a"},
        {"text": "둘째 근거입니다.", "source": "b"},
        {"text": "출처 없는 말", "source": ""},
    ]
    result = compose("request.summary", evidence, limit=2)
    assert result["answer"] == "- 첫 근거입니다.\n- 둘째 근거입니다."
    assert result["selected"] == evidence[:2]
    assert "출처 없는" not in result["answer"]


def test_composer_does_not_invent_a_comparison_claim():
    result = compare([
        {"label": "A", "text": "A의 정의", "source": "one"},
        {"label": "B", "text": "B의 정의", "source": "two"},
    ])
    assert result["answer"] == "**A** — A의 정의\n\n**B** — B의 정의"
    assert result["selected"][0]["source"] == "one"


def test_plan_keeps_only_source_backed_action_candidates():
    result = compose("request.plan", [
        {"text": "문제의 원인을 확인한다.", "source": "a", "actionable": False},
        {"text": "배출을 줄여야 한다.", "source": "b", "actionable": True},
    ])
    assert result["answer"] == "1. 배출을 줄여야 한다."
    assert result["selected"] == [{"text": "배출을 줄여야 한다.", "source": "b"}]


def test_ui_summary_uses_a_local_definition_as_its_only_material(tmp_path):
    app = create_app(tmp_path)
    with patch.object(app.goals, "research", side_effect=AssertionError("local source must not search")):
        result = app.turn("광합성 요약해줘", "summary_local")
    answer = result["answer"]
    assert result["phase"] == "answer"
    assert answer["trace"]["mode"] == "extractive_grounded_response"
    assert answer["composition"]["selected"] == answer["trace"]["sources"]
    assert "빛에너지를 화학 에너지로 전환" in answer["answer"]


def test_ui_compare_request_reuses_the_same_two_verified_definitions(tmp_path):
    app = create_app(tmp_path)
    with patch.object(app.goals, "research", side_effect=AssertionError("local source must not search")):
        result = app.turn("수학과 알고리즘 비교해줘", "compare_local")
    answer = result["answer"]
    assert result["phase"] == "answer"
    assert answer["trace"]["verdict"] == "원문정의비교"
    assert [row["label"] for row in answer["composition"]["selected"]] == ["수학", "알고리즘"]
    assert all(row["source"] == "data/위키/정의문.jsonl" for row in answer["composition"]["selected"])
