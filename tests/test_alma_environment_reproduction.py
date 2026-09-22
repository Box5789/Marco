from bench.alma_environment_reproduction import run


def test_fixed_environment_reports_functional_checks_separately_from_problem_outcome():
    report = run()
    assert report["outcomes"] == {"solved": 1, "safe_hold": 1, "wrong": 0,
                                   "execution_error": 0, "unverifiable": 0}
    assert all(row["ok"] for row in report["functional_checks"])
    assert report["independent_problems"] == [
        {"id": "environment-water-goal", "split": "independent environment outcome",
         "expected": "achieved", "actual": "achieved", "ok": True},
        {"id": "environment-read-failure-hold", "split": "same initial observation, failed relevant read",
         "expected": "safe_hold", "actual": "safe_hold", "ok": True},
    ]
