from unittest.mock import patch

from bench.alma_integrated_reproduction import AlmaRuntime, run


def test_fixed_alma_life_reproduction_has_no_wrong_checks():
    report = run()
    assert report["input_mode"] == "natural_language_dialogue"
    assert report["functional_checks"] == {"solved": 50, "wrong": 0}
    assert report["outcomes"] == {"solved": 3, "safe_hold": 2,
                                   "wrong": 0, "execution_error": 0, "unverifiable": 0}
    assert [{key: row[key] for key in row if key != "source_event_id"}
            for row in report["independent_problems"]] == [
        {"id": "four-domain-plans-only-hold", "split": "planned_world:3, natural_mental:2",
         "expected": "safe_hold", "actual": "safe_hold", "outcome": "safe_hold"},
        {"id": "social-post-activation-application", "split": "construction:3, validation:1, post_activation_application:1",
         "expected": "answered", "actual": "answered", "outcome": "solved"},
        {"id": "four-domain-post-activation-recall", "split": "world_construction:3, natural_mental_validation:1, natural_mental_application:1",
         "expected": "answered", "actual": "answered", "outcome": "solved"},
        {"id": "four-domain-counterexample-hold", "split": "world_construction:3, natural_mental_validation:1, counterexample:1",
         "expected": "safe_hold", "actual": "safe_hold", "outcome": "safe_hold"},
        {"id": "four-domain-post-counterexample-recall", "split": "world_construction:3, natural_mental_validation:1, new_natural_application:1",
         "expected": "answered", "actual": "answered", "outcome": "solved"},
    ]
    assert all(row["ok"] for row in report["checks"])
    assert {"learning_ms", "cycle_first_budget_ms", "restart_resume_ms", "episodic_save_ms",
            "long_term_search_ms"} <= set(report["costs"])
    assert report["shortcut_costs"]["preparation_validation_rule_scans"]["rule_scans"] > report["shortcut_costs"]["original_rule_scans"]["rule_scans"]
    assert report["shortcut_costs"]["repeated_rule_scans"]["rule_scans"] < report["shortcut_costs"]["original_rule_scans"]["rule_scans"]
    assert report["tracemalloc_peak_bytes"] > 0
    assert report["process_max_rss_supported"] is False and report["process_max_rss_bytes"] is None


def test_late_evaluator_error_keeps_completed_checks_costs_and_stage():
    with patch.object(AlmaRuntime, "compress_episodic", side_effect=RuntimeError("injected late failure")):
        report = run()
    assert report["terminal"] == "execution_error" and report["failed_stage"] == "episodic_save"
    assert report["input_mode"] == "natural_language_dialogue"
    assert report["checks"] and report["costs"]["learning_ms"] > 0
    assert report["outcomes"]["execution_error"] == 1
