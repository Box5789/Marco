from bench.alma_integrated_late_error_reproduction import run


def test_late_error_reproduction_preserves_prior_integrated_evidence():
    report = run()
    assert report["terminal"] == "execution_error"
    assert report["failed_stage"] == "episodic_save"
    assert report["functional_checks"]["solved"] == 46
    assert report["costs"]["learning_ms"] > 0
