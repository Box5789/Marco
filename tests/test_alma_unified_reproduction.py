from bench.alma_unified_reproduction import run


def test_unified_life_links_learning_memory_environment_restart_and_correction():
    report = run()
    assert report["input_mode"] == "natural_language_dialogue"
    assert all(row["ok"] for row in report["functional_checks"])
    assert report["outcomes"] == {"solved": 2, "safe_hold": 0, "wrong": 0,
                                   "execution_error": 0, "unverifiable": 0}
