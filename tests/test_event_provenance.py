"""Regression cases for the durable event/proof ledger."""

from graph_inference import closure_with_provenance
from reasoning_context import ReasoningContext


KG = "graphs/graph_일상추론.kg"


def test_independent_proof_bundles_survive_one_support_becoming_invalid():
    facts = [
        {"id": "fact:p", "triple": ["a", "p", "b"], "evidence": {}},
        {"id": "fact:q", "triple": ["a", "q", "b"], "evidence": {}},
    ]
    rules = [
        {"id": "via-p", "version": "r1", "body": [["?x", "p", "?y"]],
         "head": ["?x", "reachable", "?y"]},
        {"id": "via-q", "version": "r2", "body": [["?x", "q", "?y"]],
         "head": ["?x", "reachable", "?y"]},
    ]
    result = closure_with_provenance(facts, rules)
    target = ("a", "reachable", "b")
    assert result["complete"] is True
    assert {row["rule"] for row in result["proof_bundles"][target]} == {"via-p", "via-q"}

    corrected = closure_with_provenance(facts[1:], rules)
    assert target in corrected["facts"]
    assert [row["rule"] for row in corrected["proof_bundles"][target]] == ["via-q"]


def test_provenance_limit_is_not_reported_as_a_complete_search():
    result = closure_with_provenance(
        [{"id": "fact:seed", "triple": ["a", "p", "b"], "evidence": {}}],
        [{"id": "r", "body": [["?x", "p", "?y"]], "head": ["?x", "r", "?y"]}],
        search_limit=1,
    )
    assert result["complete"] is False
    assert result["reason"] == "proof_or_search_limit"


def test_provenance_cycle_without_a_ground_fact_cannot_create_its_own_support():
    result = closure_with_provenance([], [
        {"id": "p-to-q", "body": [["?x", "p", "?y"]], "head": ["?x", "q", "?y"]},
        {"id": "q-to-p", "body": [["?x", "q", "?y"]], "head": ["?x", "p", "?y"]},
    ])
    assert result["facts"] == {}
    assert result["complete"] is True


def test_event_id_and_program_survive_role_correction_and_restore():
    context = ReasoningContext()
    for text in ("베풀다는 상대에게 구슬 2개를 주는 것이다.",
                 "민수 구슬은 8개 있다. 지연 구슬은 3개 있다. 가람 구슬은 1개 있다.",
                 "민수가 지연에게 베풀었다."):
        assert context.turn(text, KG)["status"] == "observed"
    before = context.snapshot()
    event_row = next(row for row in before["events"] if row["event"]["action"] == "베풀")
    event = event_row["event"]
    assert event["program"]["definition_version"] == event["definition_version"]
    assert before["inference_bundles"]["complete"] is True
    assert {change["operation"] for change in event_row["state_changes"]} == {"quantity_update"}

    context.turn("정정: 민수가 지연에게 베풀었다. => 민수가 가람에게 베풀었다.", KG)
    after = context.snapshot()
    corrected = next(row for row in after["events"] if row["event"]["action"] == "베풀")["event"]
    assert corrected["id"] == event["id"]
    assert after["event_revisions"][-1]["event_id"] == event["id"]

    restored = ReasoningContext()
    restored.restore(after)
    replayed = next(row for row in restored.snapshot()["events"]
                    if row["event"]["action"] == "베풀")["event"]
    assert replayed["id"] == event["id"]
    assert restored.turn("지금 가람 구슬은 몇 개야?", KG)["answer"] == "3개입니다."


def test_restored_snapshot_answers_from_saved_semantic_replay_not_old_text_parse(monkeypatch):
    context = ReasoningContext()
    history = ("베풀다는 상대에게 구슬 2개를 주는 것이다.",
               "민수 구슬은 8개 있다.", "지연 구슬은 3개 있다.",
               "민수가 지연에게 베풀었다.")
    for text in history:
        context.turn(text, KG)
    restored = ReasoningContext()
    restored.restore(context.snapshot())
    parser = restored._parser()
    original = parser.parse

    def parse_only_new(text, *args, **kwargs):
        if text in history:
            raise AssertionError("restored history must use the saved replay record")
        return original(text, *args, **kwargs)

    monkeypatch.setattr(parser, "parse", parse_only_new)
    assert restored.turn("지금 지연 구슬은 몇 개야?", KG)["answer"] == "5개입니다."


def test_social_pack_records_explicit_promise_and_cancellation_not_the_promised_act():
    context = ReasoningContext()
    for text in ("약속하다는 내가 상대에게 약속을 만드는 것이다.",
                 "취소하다는 내가 상대와 약속을 취소 상태로 만드는 것이다.",
                 "민수가 지연에게 약속했다."):
        assert context.turn(text, KG)["status"] == "observed"
    assert context.turn("민수와 지연의 약속 상태가 어때?", KG)["answer"] == "active입니다."
    # No location/quantity fact is inferred merely because somebody promised.
    assert context.turn("지금 민수 구슬은 몇 개야?", KG)["status"] == "unresolved"
    context.turn("민수가 지연과 취소했다.", KG)
    assert context.turn("민수와 지연의 약속 상태가 어때?", KG)["answer"] == "cancelled입니다."


def test_negative_event_is_persisted_without_becoming_an_actual_effect():
    context = ReasoningContext()
    for text in ("베풀다는 상대에게 구슬 2개를 주는 것이다.",
                 "민수 구슬은 8개 있다.", "민수가 지연에게 베풀지 않았다."):
        context.turn(text, KG)
    negative = next(row for row in context.snapshot()["events"]
                    if row["status"] == "negative")
    assert negative["event"]["polarity"] is False
    assert negative["effects"] == []
    assert context.turn("지금 민수 구슬은 몇 개야?", KG)["answer"] == "8개입니다."


def test_app_restart_reads_saved_replay_record_before_answering(tmp_path):
    from tests.test_reasoning_persistence import create_app

    app = create_app(tmp_path)
    chat = app.conversations.create_chat()["id"]
    for text in ("베풀다는 상대에게 구슬 2개를 주는 것이다.",
                 "민수 구슬은 8개 있다.", "지연 구슬은 3개 있다.",
                 "민수가 지연에게 베풀었다."):
        app.turn(text, "saved_semantic_replay", conversation_id=chat)
    saved = app.conversations.reasoning_state(chat)
    assert saved["replay"]["facts"]

    restarted = create_app(tmp_path)
    result = restarted.turn("지금 지연 구슬은 몇 개야?", "saved_semantic_replay_new",
                            conversation_id=chat)
    assert result["answer"]["answer"] == "5개입니다."
    assert result["answer"]["verification"]["replay_scope"] == "same_input"
