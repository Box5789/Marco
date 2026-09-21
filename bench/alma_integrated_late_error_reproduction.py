"""Persist the integrated evaluator's expected late-error evidence separately."""
import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bench import alma_integrated_reproduction as benchmark


def run():
    with patch.object(benchmark.AlmaRuntime, "compress_episodic",
                      side_effect=RuntimeError("injected_late_failure")):
        return benchmark.run()


def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run()
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    sys.stdout.buffer.write(payload.encode("utf-8"))
    return 1 if report.get("terminal") else 0


if __name__ == "__main__":
    raise SystemExit(main())
