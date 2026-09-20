"""Fixed evaluation for evidence-derived concept overlays."""

from reasoning_context import ReasoningContext


KG = "graphs/graph_일상추론.kg"


def _experiences(context):
    for text in (
        "베풀다는 상대에게 구슬 2개를 주는 것이다.",
        "민수 구슬은 8개 있다. 지연 구슬은 3개 있다. 가람 구슬은 8개 있다. 하루 구슬은 3개 있다. 서준 구슬은 8개 있다. 유나 구슬은 3개 있다. 도윤 구슬은 8개 있다. 소라 구슬은 3개 있다.",
        "민수가 지연에게 베풀었다.", "가람이 하루에게 베풀었다.",
        "서준이 유나에게 베풀었다.", "도윤이 소라에게 베풀었다."):
        assert context.turn(text, KG)["status"] == "observed"


def test_three_distinct_events_create_then_holdout_validates_and_applies_concept():
    context = ReasoningContext()
    for text in (
        "베풀다는 상대에게 구슬 2개를 주는 것이다.",
        "민수 구슬은 8개 있다. 지연 구슬은 3개 있다. 가람 구슬은 8개 있다. 하루 구슬은 3개 있다. 서준 구슬은 8개 있다. 유나 구슬은 3개 있다. 도윤 구슬은 8개 있다. 소라 구슬은 3개 있다.",
        "민수가 지연에게 베풀었다.", "가람이 하루에게 베풀었다.",
        "서준이 유나에게 베풀었다."):
        context.turn(text, KG)
    off = context.snapshot()
    assert not off["experience_concepts"]["applications"]
    assert not [row for row in off["inference_bundles"]["bundles"]
                if row.get("kind") == "concept_application"]
    # This holdout is not part of candidate construction.  Its matching
    # structure validates the overlay, then the same event gains an explicit
    # derived classification that was absent while the overlay was off.
    assert context.turn("도윤이 소라에게 베풀었다.", KG)["status"] == "observed"
    snapshot = context.snapshot()
    concepts = snapshot["experience_concepts"]
    candidate = next(row for row in concepts["candidates"] if row["scope"]["action"] == "베풀")
    assert candidate["status"] == "active"
    assert len(candidate["evidence_event_ids"]) == 3
    assert len(candidate["support_event_ids"]) == 1
    application = next(row for row in concepts["applications"]
                       if row["candidate_id"] == candidate["id"])
    assert application["event_id"] == candidate["support_event_ids"][0]
    bundles = snapshot["inference_bundles"]["bundles"]
    support = next(row for row in bundles
                   if row["id"] == "support:" + application["id"])
    assert support["premise_fact_ids"] == [application["id"]]
    derived = next(row for row in bundles
                   if row["conclusion"] == application["derived_conclusion"])
    assert derived["rule"] == "concept-classification-with-executed-event"
    assert support["id"] in derived["premise_fact_ids"]
    assert "support:%s:status" % application["event_id"] in derived["premise_fact_ids"]


def test_repeated_identical_record_does_not_count_and_counterexample_deactivates_after_restore():
    repeated = ReasoningContext()
    for text in ("베풀다는 상대에게 구슬 2개를 주는 것이다.",
                 "민수 구슬은 12개 있다. 지연 구슬은 3개 있다.",
                 "민수가 지연에게 베풀었다.", "민수가 지연에게 베풀었다.",
                 "민수가 지연에게 베풀었다."):
        repeated.turn(text, KG)
    assert repeated.snapshot()["experience_concepts"]["candidates"] == []

    context = ReasoningContext()
    _experiences(context)
    restored = ReasoningContext()
    restored.restore(context.snapshot())
    # This definition revision changes the declared amount, hence its event
    # is a structural counterexample rather than a renamed support example.
    for text in ("베풀다는 상대에게 구슬 3개를 주는 것이다.",
                 "라온 구슬은 8개 있다. 마루 구슬은 3개 있다.",
                 "라온이 마루에게 베풀었다."):
        restored.turn(text, KG)
    concepts = restored.snapshot()["experience_concepts"]
    old = next(row for row in concepts["candidates"]
               if row["scope"]["action"] == "베풀" and row["structural_definition"]["fixed_values"])
    assert old["status"] == "inactive"
    assert old["counterexample_event_ids"]
    assert not [row for row in concepts["applications"] if row["candidate_id"] == old["id"]]


def test_correcting_a_source_experience_withdraws_active_application():
    context = ReasoningContext()
    _experiences(context)
    before = context.snapshot()["experience_concepts"]
    assert before["applications"]
    # This corrects an original event rather than appending a new one.  It
    # becomes a planned record, so it is no longer evidence for an actual
    # repeated experience and the previous holdout application is withdrawn.
    context.turn("정정: 민수가 지연에게 베풀었다. => 민수가 지연에게 베풀 예정이다.", KG)
    after = context.snapshot()["experience_concepts"]
    assert not after["applications"]
    assert any(row["status"] == "candidate" for row in after["candidates"])


def test_app_dialogue_persists_active_overlay_and_its_derived_application(tmp_path):
    from tests.test_reasoning_persistence import create_app

    app = create_app(tmp_path)
    chat = app.conversations.create_chat()["id"]
    for text in (
        "베풀다는 상대에게 구슬 2개를 주는 것이다.",
        "민수 구슬은 8개 있다. 지연 구슬은 3개 있다. 가람 구슬은 8개 있다. 하루 구슬은 3개 있다. 서준 구슬은 8개 있다. 유나 구슬은 3개 있다. 도윤 구슬은 8개 있다. 소라 구슬은 3개 있다.",
        "민수가 지연에게 베풀었다.", "가람이 하루에게 베풀었다.",
        "서준이 유나에게 베풀었다.", "도윤이 소라에게 베풀었다."):
        app.turn(text, "concept_overlay", conversation_id=chat)
    saved = app.conversations.reasoning_state(chat)["experience_concepts"]
    assert any(row["status"] == "active" for row in saved["candidates"])
    assert saved["applications"]
    restarted = create_app(tmp_path)
    # Loading the actual persisted AppState conversation restores the overlay
    # before a new query; it remains isolated from every other conversation.
    restarted.turn("지금 지연 구슬은 몇 개야?", "concept_overlay", conversation_id=chat)
    restored = restarted.reasoning_contexts["chat_" + chat].snapshot()["experience_concepts"]
    assert restored["applications"] == saved["applications"]


def test_active_concept_changes_a_natural_app_query_and_exposes_its_learning_chain(tmp_path):
    from tests.test_reasoning_persistence import create_app

    app = create_app(tmp_path)
    chat = app.conversations.create_chat()["id"]
    for text in (
        "베풀다는 상대에게 구슬 2개를 주는 것이다.",
        "민수 구슬은 8개 있다. 지연 구슬은 3개 있다. 가람 구슬은 8개 있다. 하루 구슬은 3개 있다. 서준 구슬은 8개 있다. 유나 구슬은 3개 있다. 도윤 구슬은 8개 있다. 소라 구슬은 3개 있다.",
        "민수가 지연에게 베풀었다.", "가람이 하루에게 베풀었다.",
        "서준이 유나에게 베풀었다.", "도윤이 소라에게 베풀었다."):
        app.turn(text, "concept_answer", conversation_id=chat)
    question = "도윤이 소라에게 베푼 것은 어떤 개념이야?"
    enabled = app.turn(question, "concept_answer", conversation_id=chat)["answer"]
    assert enabled["trace"]["verdict"] == "계산완료"
    learned = next(row for row in enabled["reasoning"]["transitions"]
                   if row.get("evidence", {}).get("kind") == "concept_application")
    candidate_id = learned["evidence"]["candidate_id"]
    assert learned["evidence"]["premise_event_ids"]
    assert learned["evidence"]["validation_event_ids"]
    derived = next(row for row in enabled["reasoning"]["transitions"]
                   if row.get("rule") == "concept-classification-with-executed-event")
    assert len(derived["parents"]) == 2
    assert derived["fact"][1] == "classified_by"

    # This is the A/B evaluation switch: the same conversation, model, pack,
    # state and question, with only this learned overlay candidate disabled.
    context = app.reasoning_contexts["chat_" + chat]
    context.concepts.disabled_ids.add(candidate_id)
    disabled = app.turn(question, "concept_answer_disabled", conversation_id=chat)["answer"]
    assert disabled["trace"]["verdict"] == "조건부족"
    # Unrelated native state reasoning is unchanged by the overlay switch.
    assert app.turn("지금 지연 구슬은 몇 개야?", "concept_answer_disabled", conversation_id=chat)["answer"]["answer"] == "5개입니다."
    context.concepts.disabled_ids.clear()
    app.turn("정정: 민수가 지연에게 베풀었다. => 민수가 지연에게 베풀 예정이다.",
             "concept_answer_retract", conversation_id=chat)
    withdrawn = app.turn(question, "concept_answer_retract", conversation_id=chat)["answer"]
    assert withdrawn["trace"]["verdict"] == "조건부족"
    restarted = create_app(tmp_path)
    restarted.turn(question, "concept_answer_retract", conversation_id=chat)
    assert not restarted.reasoning_contexts["chat_" + chat].snapshot()["experience_concepts"]["applications"]


def test_concept_membership_and_pack_rule_use_the_regular_parser_answer_path():
    context = ReasoningContext()
    _experiences(context)
    parser = context._parser()
    application = context.snapshot()["experience_concepts"]["applications"][0]
    facts = context._common_inference_facts(parser)
    membership = parser.answer({"facts": facts,
                                "query": [{"triple": [application["event_id"], "instance_of", "?concept"],
                                           "render": ["$concept"]}]})
    classified = parser.answer({"facts": facts,
                                "query": [{"triple": [application["event_id"], "classified_by", "?concept"],
                                           "render": ["$concept"]}]})
    assert membership["answer"] == classified["answer"] == application["candidate_id"]
    assert any(row.get("rule") == "concept-classification-with-executed-event"
               for row in classified["transitions"])

    # Only disabling the learned application removes both ordinary queries;
    # the independent execution premise remains an asserted event fact.
    context.concepts.disabled_ids.add(application["candidate_id"])
    disabled = context._common_inference_facts(parser)
    assert any(row["triple"] == [application["event_id"], "event_status", "executed"]
               for row in disabled)
    assert parser.answer({"facts": disabled,
                          "query": [{"triple": [application["event_id"], "instance_of", "?concept"],
                                     "render": ["$concept"]}]}) is None
    assert parser.answer({"facts": disabled,
                          "query": [{"triple": [application["event_id"], "classified_by", "?concept"],
                                     "render": ["$concept"]}]}) is None
