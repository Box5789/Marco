"""The public reproduction must fail when an expected result is wrong."""
import json
from pathlib import Path
import subprocess
import sys

import action_runtime
from bench import experience_concept_reproduction


ROOT = Path(__file__).resolve().parents[1]


def test_experience_reproduction_rejects_an_intentionally_wrong_expected_value():
    completed = subprocess.run(
        [sys.executable, "bench/experience_concept_reproduction.py", "--expected-quantity", "999"],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert completed.returncode != 0
    report = json.loads(completed.stdout)
    assert report["outcomes"]["wrong"] >= 1
    assert report["outcomes"]["execution_error"] == 0
    assert report["outcomes"]["unverifiable"] == 0


def test_experience_reproduction_rejects_a_lost_giver_decrement(monkeypatch, capsys):
    real_execute = action_runtime.execute

    def broken_execute(*args, **kwargs):
        result = real_execute(*args, **kwargs)
        # Isolated evaluator control: simulate a runtime that accidentally
        # emits a zero decrement while leaving the receiver's add intact.
        for triple in result.get("facts", []):
            if len(triple) == 3 and triple[1] == "count_remove":
                triple[2] = "0"
        return result

    monkeypatch.setattr(action_runtime, "execute", broken_execute)
    assert experience_concept_reproduction.main([]) != 0
    report = json.loads(capsys.readouterr().out)
    giver_check = next(row for row in report["checks"]
                       if row["name"] == "execution:도윤_to_소라")
    assert giver_check["bucket"] == "wrong"
    assert giver_check["evidence"]["state_changes"] != giver_check["evidence"]["expected_changes"]
