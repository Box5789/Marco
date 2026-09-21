from bench.alma_regression_reproduction import run


def test_completion_review_regressions_now_have_normal_expectations():
    report = run()
    assert all(row["ok"] for row in report["functional_checks"])
    assert report["outcomes"] == {"solved": 0, "safe_hold": 0, "wrong": 0,
                                   "execution_error": 0, "unverifiable": 0}
