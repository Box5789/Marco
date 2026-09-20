"""Concept-backed relationship judgement and explanation across two domains."""
import json
from pathlib import Path
import subprocess
import sys

from reasoning_context import ReasoningContext


KG = "graphs/graph_일상추론.kg"


def _quantity_context():
    context = ReasoningContext()
    for text in (
        "베풀다는 상대에게 구슬 2개를 주는 것이다.",
        "민수 구슬은 8개 있다. 지연 구슬은 3개 있다. 가람 구슬은 8개 있다. 하루 구슬은 3개 있다. 서준 구슬은 8개 있다. 유나 구슬은 3개 있다. 도윤 구슬은 8개 있다. 소라 구슬은 3개 있다.",
        "민수가 지연에게 베풀었다.", "가람이 하루에게 베풀었다.",
        "서준이 유나에게 베풀었다.", "도윤이 소라에게 베풀었다.",
    ):
        assert context.turn(text, KG)["status"] == "observed"
    return context


def _location_context():
    context = ReasoningContext()
    for text in (
        "옮기다는 내가 물건을 서랍으로 옮기는 것이다.",
        "공책은 책상에 있었다.", "하루가 공책을 옮겼다.",
        "가람이 연필을 옮겼다.", "서준이 공을 옮겼다.", "도윤이 지우개를 옮겼다.",
    ):
        assert context.turn(text, KG)["status"] == "observed"
    return context


def test_quantity_relation_uses_learned_effect_and_independent_permission_with_reason():
    context = _quantity_context()
    assert context.turn("소라는 전달 허가 상태다", KG)["status"] == "observed"
    judged = context.turn("도윤이 소라에게 베푼 일은 전달 가능한가", KG)
    assert judged["answer"] == "전달 가능합니다."
    assert any(row.get("rule") == "learned-transfer-permission-relation"
               for row in judged["transitions"])
    reason = context.turn("왜 그렇게 판단했어", KG)
    assert "도윤이 소라에게 베풀었다" in reason["answer"]
    assert "count_add" in reason["answer"]
    assert "소라 transfer_permission approved" in reason["answer"]
    assert "learned-transfer-permission-relation" in reason["answer"]
    assert "v0" in reason["answer"] and "v1" in reason["answer"]


def test_location_relation_reuses_the_same_event_concept_rule_and_reason_path():
    context = _location_context()
    assert context.turn("지우개는 배치 허가 상태다", KG)["status"] == "observed"
    judged = context.turn("도윤이 지우개를 옮긴 일은 배치 가능한가", KG)
    assert judged["answer"] == "배치 가능합니다."
    assert any(row.get("rule") == "learned-placement-permission-relation"
               for row in judged["transitions"])
    reason = context.turn("왜 그렇게 판단했어", KG)
    assert "도윤이 지우개를 옮겼다" in reason["answer"]
    assert "location" in reason["answer"]
    assert "지우개 placement_permission approved" in reason["answer"]
    assert "learned-placement-permission-relation" in reason["answer"]


def test_permission_change_and_concept_switch_withdraw_only_concept_relation():
    context = _quantity_context()
    context.turn("소라는 전달 허가 상태다", KG)
    assert context.turn("도윤이 소라에게 베푼 일은 전달 가능한가", KG)["status"] == "answered"
    application = context.snapshot()["experience_concepts"]["applications"][0]
    context.concepts.disabled_ids.add(application["candidate_id"])
    assert context.turn("도윤이 소라에게 베푼 일은 전달 가능한가", KG)["status"] == "unresolved"
    unavailable = context.turn("왜 그렇게 판단했어", KG)
    assert "별도 전제는 확인했지만" in unavailable["answer"]
    assert context.turn("지금 소라 구슬은 몇 개야?", KG)["answer"] == "5개입니다."
    context.concepts.disabled_ids.clear()
    assert context.turn("도윤이 소라에게 베푼 일은 전달 가능한가", KG)["status"] == "answered"

    context.turn("정정: 소라는 전달 허가 상태다 => 소라는 전달 허가 상태가 아니다", KG)
    assert context.snapshot()["experience_concepts"]["applications"]  # learning survived the premise edit
    assert context.turn("도윤이 소라에게 베푼 일은 전달 가능한가", KG)["status"] == "unresolved"
    missing = context.turn("왜 그렇게 판단했어", KG)
    assert "전달 허가 상태" in missing["answer"]
    assert "현재 확인되지 않았습니다" in missing["answer"]


def test_same_action_with_a_different_effect_is_not_reused_as_the_active_concept():
    context = _quantity_context()
    context.turn("소라는 전달 허가 상태다", KG)
    assert context.turn("도윤이 소라에게 베푼 일은 전달 가능한가", KG)["status"] == "answered"
    # Same surface action, but a changed declared effect is a structural
    # counterexample; it must not gain the transfer concept by its name.
    context.turn("베풀다는 상대에게 구슬 3개를 주는 것이다.", KG)
    context.turn("라온 구슬은 8개 있다. 마루 구슬은 3개 있다.", KG)
    context.turn("라온이 마루에게 베풀었다.", KG)
    snapshot = context.snapshot()
    old = next(row for row in snapshot["experience_concepts"]["candidates"]
               if row["scope"]["action"] == "베풀" and row["structural_definition"]["fixed_values"])
    assert old["status"] == "inactive"
    assert context.turn("도윤이 소라에게 베푼 일은 전달 가능한가", KG)["status"] == "unresolved"


def test_actual_app_active_and_corrected_relation_restore_in_separate_processes(tmp_path):
    from tests.test_reasoning_persistence import create_app

    app = create_app(tmp_path)
    chat = app.conversations.create_chat()["id"]
    for text in (
        "베풀다는 상대에게 구슬 2개를 주는 것이다.",
        "민수 구슬은 8개 있다. 지연 구슬은 3개 있다. 가람 구슬은 8개 있다. 하루 구슬은 3개 있다. 서준 구슬은 8개 있다. 유나 구슬은 3개 있다. 도윤 구슬은 8개 있다. 소라 구슬은 3개 있다.",
        "민수가 지연에게 베풀었다.", "가람이 하루에게 베풀었다.",
        "서준이 유나에게 베풀었다.", "도윤이 소라에게 베풀었다.",
        "소라는 전달 허가 상태다", "도윤이 소라에게 베푼 일은 전달 가능한가",
    ):
        app.turn(text, "concept_relation_persistence", conversation_id=chat)

    code = """
import json, sys
from pathlib import Path
from conversation_store import ConversationStore
from views.kgpack_ui import AppState
pack, root, chat, question = map(Path, sys.argv[1:5])
app = AppState(pack, overlay_root=root / 'subprocess-overlay')
app.conversations = ConversationStore(root / 'conversations.json')
result = app.turn(str(question), 'concept_relation_subprocess', conversation_id=str(chat))
print(json.dumps(result['answer'], ensure_ascii=False))
"""

    def restored(question):
        completed = subprocess.run(
            [sys.executable, "-c", code, str(tmp_path / "saved.kgpack"), str(tmp_path), chat, question],
            cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=True,
        )
        return json.loads(completed.stdout)

    active_reason = restored("왜 그렇게 판단했어")
    assert "learned-transfer-permission-relation" in active_reason["answer"]
    assert "소라 transfer_permission approved" in active_reason["answer"]

    app.turn("정정: 소라는 전달 허가 상태다 => 소라는 전달 허가 상태가 아니다",
             "concept_relation_persistence", conversation_id=chat)
    corrected_reason = restored("왜 그렇게 판단했어")
    assert "전달 허가 상태" in corrected_reason["answer"]
    assert "현재 확인되지 않았습니다" in corrected_reason["answer"]
