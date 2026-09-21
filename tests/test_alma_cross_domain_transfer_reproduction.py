from bench.alma_cross_domain_transfer_reproduction import run


def test_cross_domain_transfer_reproduction_keeps_effects_lineage_and_counterexample_separate():
    report = run()
    assert all(row["ok"] for row in report["functional_checks"])
    assert report["outcomes"] == {"solved": 1, "safe_hold": 0, "wrong": 0,
                                   "execution_error": 0, "unverifiable": 0}
