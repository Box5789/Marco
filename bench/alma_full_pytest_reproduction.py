"""Run the complete repository test suite and persist its terminal evidence."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    started = time.time()
    result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8")
    report = {"command": [sys.executable, "-m", "pytest", "-q"], "exit_code": result.returncode,
              "elapsed_seconds": round(time.time() - started, 3), "stdout": result.stdout,
              "stderr": result.stderr}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sys.stdout.buffer.write((json.dumps({key: report[key] for key in ("exit_code", "elapsed_seconds")}) + "\n").encode("utf-8"))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
