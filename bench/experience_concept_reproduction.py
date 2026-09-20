"""Strict public-App reproduction for experience-derived KG facts.

The script deliberately verifies expected semantic results, rather than
treating an exception-free run as a pass.  ``--expected-quantity`` is an
intentional mismatch control for CI and must make this command exit nonzero.
"""
import argparse
import hashlib
import json
import resource
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import kgpack
from conversation_store import ConversationStore
from views.kgpack_ui import AppState


def _environment(pack):
    return {
        "python": sys.version.split()[0],
        "pack_sha256": hashlib.sha256(pack.read_bytes()).hexdigest(),
        "git_revision": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                         text=True, capture_output=True, check=True).stdout.strip(),
        "worktree_status": subprocess.run(["git", "status", "--short"], cwd=ROOT,
                                            text=True, capture_output=True, check=True).stdout.splitlines(),
    }


def _transfer_execution(records, *, giver, taker, amount, giver_before, taker_before):
    """Verify one executed transfer from its durable event/result record.

    This is deliberately independent of the later quantity query: a receiver
    may look correct even when the giver's decrement was lost.
    """
    event = next((row for row in records
                  if (row.get("event") or {}).get("roles", {}).get("은") == giver
                  and (row.get("event") or {}).get("roles", {}).get("에게") == taker), None)
    if event is None:
        return False, {"reason": "event_missing"}
    envelope = event["event"]
    fixed = (envelope.get("program") or {}).get("signature", {}).get("fixed_values", {})
    effects = {tuple(row) for row in event.get("effects") or []}
    changes = {(row.get("subject"), row.get("predicate"), row.get("before"),
                row.get("after"), row.get("delta")) for row in event.get("state_changes") or []}
    giver_item, taker_item = giver + " 구슬", taker + " 구슬"
    expected = {
        (giver_item, "count", giver_before, giver_before - amount, -amount),
        (taker_item, "count", taker_before, taker_before + amount, amount),
    }
    details = {
        "event_id": envelope.get("id"), "status": event.get("status"),
        "roles": envelope.get("roles"), "defined_amount": fixed.get("n"),
        "effects": sorted(effects), "state_changes": sorted(changes),
        "expected_changes": sorted(expected),
    }
    return (event.get("status") == "executed" and fixed.get("n") == str(amount)
            and {(giver_item, "count_remove", str(amount)), (taker_item, "count_add", str(amount))} <= effects
            and expected <= changes), details


def main(argv=None):
    options = argparse.ArgumentParser()
    options.add_argument("--expected-quantity", default="5",
                         help="expected pre-correction quantity; mismatch is a failure control")
    args = options.parse_args(argv)
    counts = {name: 0 for name in ("solved", "safe_hold", "wrong", "execution_error", "unverifiable")}
    checks = []

    def verify(name, expected, actual, *, safe_hold=False, evidence=None):
        if actual is None:
            bucket, ok = "unverifiable", False
        elif actual == expected:
            bucket, ok = ("safe_hold" if safe_hold else "solved"), True
        else:
            bucket, ok = "wrong", False
        counts[bucket] += 1
        checks.append({"name": name, "expected": expected, "actual": actual,
                       "bucket": bucket, "ok": ok, "evidence": evidence})
        return ok

    def execution_error(name, exc):
        counts["execution_error"] += 1
        checks.append({"name": name, "bucket": "execution_error", "ok": False,
                       "error": repr(exc)})

    with TemporaryDirectory(prefix="nai-concept-repro-") as folder:
        root = Path(folder)
        pack = root / "evaluation.kgpack"
        started = time.perf_counter()
        tracemalloc.start()
        kgpack.write_pack(pack, [ROOT / "graphs/graph_일상추론.kg"] + kgpack.model_files(ROOT), root=ROOT)
        app = AppState(pack, overlay_root=root / "overlay")
        app.conversations = ConversationStore(root / "conversations.json")
        chat = app.conversations.create_chat(title="고정 경험-개념 평가")["id"]
        setup_ms = (time.perf_counter() - started) * 1000
        preparations = [
            "베풀다는 상대에게 구슬 2개를 주는 것이다.",
            "민수 구슬은 8개 있다. 지연 구슬은 3개 있다. 가람 구슬은 8개 있다. 하루 구슬은 3개 있다. 서준 구슬은 8개 있다. 유나 구슬은 3개 있다. 도윤 구슬은 8개 있다. 소라 구슬은 3개 있다.",
        ]
        actions = [
            "민수가 지연에게 베풀었다.", "가람이 하루에게 베풀었다.",
            "서준이 유나에게 베풀었다.", "도윤이 소라에게 베풀었다.",
        ]
        dialogue_rows, preparation_rows = [], []
        for text in preparations:
            began = time.perf_counter()
            try:
                result = app.turn(text, "fixed_experience_evaluation", conversation_id=chat)
                preparation_rows.append({"input": text, "phase": result.get("phase"),
                                         "elapsed_ms": round((time.perf_counter() - began) * 1000, 3)})
            except Exception as exc:  # report then continue to preserve the classification ledger
                execution_error("preparation:%s" % text, exc)
                preparation_rows.append({"input": text, "bucket": "execution_error", "error": repr(exc)})
        for text in actions:
            began = time.perf_counter()
            try:
                result = app.turn(text, "fixed_experience_evaluation", conversation_id=chat)
                dialogue_rows.append({"input": text, "phase": result.get("phase"),
                                      "elapsed_ms": round((time.perf_counter() - began) * 1000, 3)})
            except Exception as exc:
                execution_error("action:%s" % text, exc)
                dialogue_rows.append({"input": text, "bucket": "execution_error", "error": repr(exc)})

        records = app.reasoning_contexts["chat_" + chat].snapshot()["events"]
        for giver, taker in (("민수", "지연"), ("가람", "하루"), ("서준", "유나"), ("도윤", "소라")):
            ok, details = _transfer_execution(records, giver=giver, taker=taker,
                                              amount=2, giver_before=8, taker_before=3)
            verify("execution:%s_to_%s" % (giver, taker), True, ok, evidence=details)

        quantity_result = app.turn("지금 소라 구슬은 몇 개야?", "fixed_experience_evaluation", conversation_id=chat)["answer"]
        verify("quantity:receiver_state", args.expected_quantity + "개입니다.", quantity_result.get("answer"))

        # Quantity relationship: the learned transfer structure and a human
        # supplied recipient permission are separate premises of the pack
        # rule.  The following reason is an actual app response, not a stored
        # question-specific answer.
        app.turn("소라는 전달 허가 상태다", "fixed_experience_evaluation", conversation_id=chat)
        quantity_relation = app.turn("도윤이 소라에게 베푼 일은 전달 가능한가",
                                     "fixed_experience_evaluation", conversation_id=chat)["answer"]
        verify("quantity:learned_relation", "전달 가능합니다.", quantity_relation.get("answer"))
        quantity_reason = app.turn("왜 그렇게 판단했어", "fixed_experience_evaluation", conversation_id=chat)["answer"]
        verify("quantity:reason_rule", True,
               all(value in quantity_reason.get("answer", "") for value in
                   ("도윤이 소라에게 베풀었다", "count_add", "소라 transfer_permission approved",
                    "learned-transfer-permission-relation", "v0", "v1")),
               evidence=quantity_reason.get("answer"))

        question = "도윤이 소라에게 베푼 것은 어떤 개념이야?"
        enabled = app.turn(question, "fixed_experience_evaluation", conversation_id=chat)["answer"]
        learned = next((row for row in enabled["reasoning"]["transitions"]
                        if row.get("evidence", {}).get("kind") == "concept_application"), None)
        candidate_id = learned and learned["evidence"].get("candidate_id")
        expected_concept = candidate_id + "입니다." if candidate_id else None
        verify("active:natural_concept_query", expected_concept, enabled.get("answer"),
               evidence={"verdict": enabled.get("trace", {}).get("verdict")})
        active_state = app.conversations.reasoning_state(chat)
        event_id = learned and learned["evidence"].get("event_id")
        active_bundles = active_state.get("inference_bundles", {}).get("bundles", [])
        classification = next((row for row in active_bundles
                               if row.get("conclusion") == [event_id, "classified_by", candidate_id]), None)
        verify("active:pack_rule_provenance", "concept-classification-with-executed-event",
               classification and classification.get("rule"), evidence=classification)

        # Structural control: ordinary parser.answer queries consume facts
        # generated by the saved event ledger, never injected concept rows.
        context = app.reasoning_contexts["chat_" + chat]
        parser = context._parser()
        ordinary_facts = context._common_inference_facts(parser)
        membership = parser.answer({"facts": ordinary_facts,
                                    "query": [{"triple": [event_id, "instance_of", "?concept"],
                                               "render": ["$concept"]}]})
        classified = parser.answer({"facts": ordinary_facts,
                                    "query": [{"triple": [event_id, "classified_by", "?concept"],
                                               "render": ["$concept"]}]})
        verify("active:ordinary_instance_query", candidate_id, membership and membership.get("answer"))
        verify("active:ordinary_pack_rule_query", candidate_id, classified and classified.get("answer"))

        # Restart an active snapshot before touching the A/B switch.
        active_restart = AppState(pack, overlay_root=root / "active-restart-overlay")
        active_restart.conversations = ConversationStore(root / "conversations.json")
        active_answer = active_restart.turn(question, "fixed_experience_active_restart", conversation_id=chat)["answer"]
        active_restored = active_restart.conversations.reasoning_state(chat)
        verify("active:restart_answer", expected_concept, active_answer.get("answer"))
        verify("active:restart_provenance", classification and classification.get("id"),
               next((row.get("id") for row in active_restored.get("inference_bundles", {}).get("bundles", [])
                     if row.get("conclusion") == [event_id, "classified_by", candidate_id]), None))

        # A/B has the same conversation, pack and question; B changes only
        # the learned candidate switch.  Native quantity remains available.
        context.concepts.disabled_ids.add(candidate_id)
        disabled = app.turn(question, "fixed_experience_disabled", conversation_id=chat)["answer"]
        verify("disabled:natural_concept_query", "조건부족", disabled.get("trace", {}).get("verdict"), safe_hold=True)
        disabled_relation = app.turn("도윤이 소라에게 베푼 일은 전달 가능한가",
                                     "fixed_experience_disabled", conversation_id=chat)["answer"]
        verify("disabled:concept_relation", "조건부족", disabled_relation.get("trace", {}).get("verdict"), safe_hold=True)
        quantity = app.turn("지금 소라 구슬은 몇 개야?", "fixed_experience_disabled", conversation_id=chat)["answer"]
        verify("disabled:independent_quantity", args.expected_quantity + "개입니다.", quantity.get("answer"))

        # Correction deliberately starts from active learning, not disabled
        # learning.  It removes the first training event while the unrelated
        # quantity proof for 소라 remains.
        context.concepts.disabled_ids.clear()
        app.turn("정정: 소라는 전달 허가 상태다 => 소라는 전달 허가 상태가 아니다",
                 "fixed_experience_premise_corrected", conversation_id=chat)
        missing_relation = app.turn("도윤이 소라에게 베푼 일은 전달 가능한가",
                                    "fixed_experience_premise_corrected", conversation_id=chat)["answer"]
        verify("premise_corrected:relation_withdrawn", "조건부족",
               missing_relation.get("trace", {}).get("verdict"), safe_hold=True)
        missing_reason = app.turn("왜 그렇게 판단했어", "fixed_experience_premise_corrected", conversation_id=chat)["answer"]
        verify("premise_corrected:reason_names_missing_premise", True,
               "전달 허가 상태" in missing_reason.get("answer", ""), evidence=missing_reason.get("answer"))
        app.turn("정정: 소라는 전달 허가 상태가 아니다 => 소라는 전달 허가 상태다",
                 "fixed_experience_premise_restored", conversation_id=chat)
        restored_relation = app.turn("도윤이 소라에게 베푼 일은 전달 가능한가",
                                     "fixed_experience_premise_restored", conversation_id=chat)["answer"]
        verify("premise_restored:relation", "전달 가능합니다.", restored_relation.get("answer"))
        correction = app.turn("정정: 민수가 지연에게 베풀었다. => 민수가 지연에게 베풀 예정이다.",
                              "fixed_experience_corrected", conversation_id=chat)["answer"]
        verify("corrected:correction_observed", "상태기억", correction.get("trace", {}).get("verdict"))
        withdrawn = app.turn(question, "fixed_experience_corrected", conversation_id=chat)["answer"]
        verify("corrected:learned_result_withdrawn", "조건부족", withdrawn.get("trace", {}).get("verdict"), safe_hold=True)
        independent = app.turn("지금 소라 구슬은 몇 개야?", "fixed_experience_corrected", conversation_id=chat)["answer"]
        verify("corrected:independent_proof", args.expected_quantity + "개입니다.", independent.get("answer"))
        corrected_state = app.conversations.reasoning_state(chat)
        verify("corrected:no_applications", [], corrected_state.get("experience_concepts", {}).get("applications"))

        corrected_restart = AppState(pack, overlay_root=root / "corrected-restart-overlay")
        corrected_restart.conversations = ConversationStore(root / "conversations.json")
        corrected_answer = corrected_restart.turn(question, "fixed_experience_corrected_restart", conversation_id=chat)["answer"]
        corrected_restored = corrected_restart.conversations.reasoning_state(chat)
        verify("corrected:restart_safe_hold", "조건부족", corrected_answer.get("trace", {}).get("verdict"), safe_hold=True)
        verify("corrected:restart_overlay", [], corrected_restored.get("experience_concepts", {}).get("applications"))

        # Location is a separate conversation/domain but intentionally uses
        # the same event, role-occurrence, concept-application, pack-rule and
        # reason construction code path.
        location_chat = app.conversations.create_chat(title="고정 위치-개념 평가")["id"]
        for text in (
            "옮기다는 내가 물건을 서랍으로 옮기는 것이다.",
            "공책은 책상에 있었다.", "하루가 공책을 옮겼다.",
            "가람이 연필을 옮겼다.", "서준이 공을 옮겼다.", "도윤이 지우개를 옮겼다.",
            "지우개는 배치 허가 상태다",
        ):
            app.turn(text, "fixed_location_relation", conversation_id=location_chat)
        location_relation = app.turn("도윤이 지우개를 옮긴 일은 배치 가능한가",
                                     "fixed_location_relation", conversation_id=location_chat)["answer"]
        verify("location:learned_relation", "배치 가능합니다.", location_relation.get("answer"))
        location_reason = app.turn("왜 그렇게 판단했어", "fixed_location_relation", conversation_id=location_chat)["answer"]
        verify("location:reason_rule", True,
               all(value in location_reason.get("answer", "") for value in
                   ("도윤이 지우개를 옮겼다", "location", "지우개 placement_permission approved",
                    "learned-placement-permission-relation", "v0", "v1")),
               evidence=location_reason.get("answer"))

        _now, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_bytes = rss if sys.platform == "darwin" else rss * 1024
        report = {
            "environment": _environment(pack),
            "preparations": preparation_rows,
            "dialogue": dialogue_rows,
            "checks": checks,
            "outcome_unit": "expected-result verification rows, not a count of solved problems",
            "outcomes": counts,
            "candidate": {"id": candidate_id, "event_id": event_id},
            "active_snapshot": {"experience_concepts": active_state.get("experience_concepts"),
                                "classification": classification},
            "corrected_snapshot": {"experience_concepts": corrected_state.get("experience_concepts")},
            "initial_setup_ms": round(setup_ms, 3),
            "repeat_execution": {"turn_count": len(dialogue_rows),
                                 "total_ms": round(sum(row.get("elapsed_ms", 0) for row in dialogue_rows), 3)},
            "total_reproduction_ms": round((time.perf_counter() - started) * 1000, 3),
            "tracemalloc_peak_bytes": peak,
            "process_max_rss_bytes": rss_bytes,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not (counts["wrong"] or counts["execution_error"] or counts["unverifiable"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
