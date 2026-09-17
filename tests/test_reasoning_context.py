from pathlib import Path
from unittest.mock import patch

import engine
import kgpack
from reasoning_context import ReasoningContext
from views.kgpack_ui import AppState

KG = "graphs/graph_일상추론.kg"


def test_dialogue_replays_events_once_and_does_not_share_memory():
    first, second = engine.Dialogue(), engine.Dialogue()
    assert first.say("돌은 23개 있다.")[1] == "상태기억"
    assert first.say("돌 8개를 꺼냈다.")[1] == "상태기억"
    for _ in range(2):
        assert first.say("지금 돌은 몇 개야?")[2] == "15개입니다."
    assert second.say("지금 돌은 몇 개야?")[1] == "미지"


def test_context_combines_facts_across_turns_with_source_turn_ids():
    context = ReasoningContext()
    context.turn("서우는 도아보다 키가 크다.", KG)
    context.turn("도아는 라온보다 키가 크다.", KG)
    result = context.turn("서우와 라온 중 누가 더 커?", KG)
    assert result["answer"] == "서우입니다."
    assert {step["evidence"]["turn"] for step in result["transitions"] if "evidence" in step} == {0, 1}


def test_invalid_event_is_not_committed_and_unknown_text_is_not_a_fact():
    """앞말과 어긋나는 사건은 **안 일어난 일이 아니다.**

    3개에서 8개를 꺼낼 수는 없다. 그렇다고 사용자가 일어났다고 말한 일을 우리가
    없던 일로 바꿀 수는 없다 — 처음 수량이 틀렸을 수도, 중간 사건이 빠졌을 수도
    있다. 사실로 쓰지는 않되 두 말을 다 남기고, 지금 값은 확정하지 않는다.
    """
    context = ReasoningContext()
    context.turn("돌은 3개 있다.", KG)
    말 = context.turn("돌 8개를 꺼냈다.", KG)
    assert 말["status"] == "unresolved"
    assert "셈이 맞지 않습니다" in 말["answer"]
    assert context.turn("만약 돌을 전부 없애면 어떻게 될까?", KG) is None
    assert len(context.observations) == 1          # 사실로는 안 쓴다
    assert [x["text"] for x in context.unread] == ["돌 8개를 꺼냈다."]   # 버리지도 않는다
    이제 = context.turn("지금 돌은 몇 개야?", KG)["answer"]
    assert "3개입니다." not in 이제
    assert "돌 8개를 꺼냈다" in 이제


def test_whole_question_fact_is_not_replayed_twice():
    context = ReasoningContext()
    text = "돌은 23개 있다. 돌 8개를 꺼냈다. 지금 돌은 몇 개야?"
    assert context.turn(text, KG)["answer"] == "15개입니다."
    assert context.turn("지금 돌은 몇 개야?", KG)["answer"] == "15개입니다."


def test_hypothetical_quantity_question_projects_only_the_assumed_events():
    """조건 사건은 실제 기록과 분리해 물음에만 임시 적용한다.

    세 최소 재현은 받는 쪽 증가·꺼내기·넣기이고, 두 반례는 가정이 실제 값을
    바꾸지 않는 것과 실제 사건은 계속 값을 바꾸는 것이다.
    """
    cases = (
        ("민수 구슬은 8개 있다. 지연 구슬은 3개 있다. "
         "만약 민수가 지연에게 구슬 2개를 줬으면 지금 지연 구슬은 몇 개야?", "5개입니다."),
        ("사과는 8개 있다. 만약 사과 3개를 꺼냈으면 지금 사과는 몇 개야?", "5개입니다."),
        ("사과는 4개 있다. 만약 사과 3개를 넣었으면 지금 사과는 몇 개야?", "7개입니다."),
    )
    for text, expected in cases:
        context = ReasoningContext()
        result = context.turn(text, KG)
        assert result["answer"] == expected
        assert any(step["operation"] == "hypothetical_assumption" for step in result["transitions"])

    context = ReasoningContext()
    context.turn(cases[0][0], KG)
    assert context.turn("지금 지연 구슬은 몇 개야?", KG)["answer"] == "3개입니다."

    actual = ReasoningContext()
    assert actual.turn("민수 구슬은 8개 있다. 지연 구슬은 3개 있다. "
                       "민수가 지연에게 구슬 2개를 줬다. 지금 지연 구슬은 몇 개야?", KG)["answer"] == "5개입니다."


def test_ui_remembers_observation_and_separates_sessions(tmp_path):
    pack = tmp_path / "context.kgpack"
    kgpack.write_pack(pack, [Path(KG)] + kgpack.model_files(Path(".")), root=Path("."))
    app = AppState(pack, overlay_root=tmp_path / "overlay")
    with patch.object(app.goals, "research") as research:
        first = app.turn("공책은 서랍에 있었다.", "session_context1")
        moved = app.turn("서우가 공책을 창고로 옮겼다.", "session_context1")
        answer = app.turn("지금 공책은 어디에 있어?", "session_context1")
        other = app.turn("지금 공책은 어디에 있어?", "session_context2")
    research.assert_not_called()
    assert first["answer"]["trace"]["verdict"] == moved["answer"]["trace"]["verdict"] == "상태기억"
    assert answer["answer"]["answer"] == "창고에 있습니다."
    assert other["answer"]["trace"]["verdict"] == "조건부족"
