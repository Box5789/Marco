from unittest.mock import patch

import pytest

from tests.test_reasoning_persistence import create_app


@pytest.mark.parametrize("question", ["12 나누기 0은 얼마야?", "2x+1=2x+8이면?"])
def test_recognized_unsolved_question_has_no_research_or_learning_plan(tmp_path, question):
    app = create_app(tmp_path)
    with patch.object(app.goals, "research") as research, patch.object(app.goals, "plan_learning") as learn:
        result = app.turn(question, "session_unsolved1")
    research.assert_not_called()
    learn.assert_not_called()
    assert result["phase"] == "answer"
    assert not result["answer"]["known"]
    assert result["answer"]["trace"]["verdict"] == "조건부족"
    assert result["answer"]["semantic_parse"]["accepted"]
    assert any(not check["ok"] for check in result["answer"]["verification"]["checks"])


@pytest.mark.parametrize("question", [
    "5x + 4만 알아. x는 얼마야?",
])
def test_unreadable_problem_is_not_misclassified_as_an_external_fact_request(tmp_path, question):
    app = create_app(tmp_path)
    with patch.object(app.goals, "research") as research, patch.object(app.goals, "plan_learning") as learn:
        result = app.turn(question, "session_input_failure")
    research.assert_not_called()
    learn.assert_not_called()
    assert result["phase"] == "answer"
    assert not result["answer"]["known"]
    assert result["answer"]["trace"]["verdict"] == "입력이해실패"
    assert result["answer"]["trace"]["retrieval"] == {
        "diagnosis": "input_understanding_failed",
        "need": {"kind": "clarification", "topic": None, "resolved": False},
    }
