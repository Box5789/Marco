from bench.alma_graph_asset_reproduction import run


def test_graph_asset_lifecycle_has_lineage_export_restart_and_withdrawal():
    report = run()
    assert all(row["ok"] for row in report["functional_checks"])
    assert report["outcomes"] == {"solved": 1, "safe_hold": 0, "wrong": 0,
                                   "execution_error": 0, "unverifiable": 0}
