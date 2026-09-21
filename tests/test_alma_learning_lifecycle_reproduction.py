from bench.alma_learning_lifecycle_reproduction import run


def test_learning_lifecycle_has_disjoint_construction_validation_and_application():
    report = run()
    assert all(row["ok"] for row in report["functional_checks"])
    assert all(row["ok"] for row in report["independent_problems"])
    assert report["outcomes"] == {"solved": 1, "safe_hold": 3, "wrong": 0,
                                   "execution_error": 0, "unverifiable": 0}
