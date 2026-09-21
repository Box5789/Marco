from bench.alma_structural_transfer_reproduction import run


def test_cross_action_structure_keeps_lineage_and_rejects_a_different_shape():
    report = run()
    assert all(row["ok"] for row in report["functional_checks"])
    assert report["outcomes"] == {"solved": 2, "safe_hold": 0, "wrong": 0,
                                   "execution_error": 0, "unverifiable": 0}
