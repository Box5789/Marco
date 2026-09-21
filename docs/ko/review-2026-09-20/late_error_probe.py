"""Inject a late local checkpoint error into the ALMA evaluator, not product code."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("KG_ENCODER", "문자")
from bench import alma_integrated_reproduction as benchmark

if __name__ == "__main__":
    output = Path(__file__).with_name("alma-late-error.json")
    with patch.object(benchmark.AlmaRuntime, "compress_episodic", side_effect=RuntimeError("review_late_stage_failure")):
        raise SystemExit(benchmark.main(["--output", str(output)]))
