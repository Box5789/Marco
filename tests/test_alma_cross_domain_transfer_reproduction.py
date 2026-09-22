from bench.alma_cross_domain_transfer_reproduction import run


def test_cross_domain_transfer_reproduction_keeps_effects_lineage_and_counterexample_separate():
    report = run()
    assert all(row["ok"] for row in report["functional_checks"])
    assert report["independent_problems"] == [
        {"id": "unseen-action-structure-5", "split": "post-activation application",
         "expected": "event:5", "actual": "event:5", "ok": True},
        {"id": "unseen-action-structure-6", "split": "final independent evaluation",
         "expected": "event:6", "actual": "event:6", "ok": True},
    ]
    assert report["outcomes"] == {"solved": 2, "safe_hold": 0, "wrong": 0,
                                   "execution_error": 0, "unverifiable": 0}
