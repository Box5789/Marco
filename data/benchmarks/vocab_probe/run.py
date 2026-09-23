"""Play the open-vocabulary probe through the UI turn handler and count it (goal G3.1).

Each case is its own two-turn conversation, played exactly as the dialogue gate
plays a dialogue (``bench.dialogue_gate.run``: ``views.kgpack_ui.AppState.turn``,
research stubbed). A case passes when the statement is recorded and the question
is answered with the stated amount (items, names) or names the place (places).

    python data/benchmarks/vocab_probe/run.py [--kind item|place|name] [--language en|ko]
                                              [--out results.json] [--failures N]
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))


def cases(kind=None, language=None):
    rows = json.loads((HERE / "probe.json").read_text(encoding="utf-8"))["cases"]
    return [row for row in rows if (kind is None or row["kind"] == kind)
            and (language is None or row["language"] == language)]


def judge(case, statement, question):
    import bench.dialogue_gate as gate
    if gate.status(statement) != "observed":
        return "not_recorded"
    if gate.status(question) != "answered":
        return "not_answered"
    text = question.get("answer") or ""
    if "count" in case["expect"]:
        return "pass" if gate.quantities(gate.asserted(text)) == {case["expect"]["count"]} else "wrong"
    place = case["expect"]["place"]
    found = (re.search(r"(?<![a-z])%s(?![a-z])" % re.escape(place), text.lower()) if place.isascii()
             else place in text)
    return "pass" if found else "wrong"


def play(selected, code_root=ROOT):
    import bench.dialogue_gate as gate
    dialogues = [{"id": "probe_%04d" % i, "language": case["language"],
                  "turns": [{"n": 1, "say": case["statement"]}, {"n": 2, "say": case["question"]}]}
                 for i, case in enumerate(selected)]
    answers = gate.run(dialogues, code_root)
    out = []
    for case, dialogue in zip(selected, dialogues):
        statement, question = answers[dialogue["id"]]
        out.append({**case, "outcome": judge(case, statement, question),
                    "replies": [statement.get("answer"), question.get("answer")]})
    return out


def summary(results):
    table = {}
    for row in results:
        key = "%s/%s" % (row["kind"], row["language"])
        cell = table.setdefault(key, {"n": 0, "pass": 0})
        cell["n"] += 1
        if row["outcome"] == "pass":
            cell["pass"] += 1
        else:
            cell[row["outcome"]] = cell.get(row["outcome"], 0) + 1
    total = {"n": len(results), "pass": sum(row["outcome"] == "pass" for row in results)}
    total["rate"] = round(total["pass"] / total["n"], 4) if total["n"] else None
    return {"by_kind_language": table, "total": total}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind")
    parser.add_argument("--language")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--failures", type=int, default=0, help="print this many failing cases")
    args = parser.parse_args(argv)
    results = play(cases(args.kind, args.language))
    report = summary(results)
    for key, cell in sorted(report["by_kind_language"].items()):
        print("%-10s %4d/%-4d %s" % (key, cell["pass"], cell["n"],
                                     {k: v for k, v in cell.items() if k not in ("n", "pass")}))
    print("total %d/%d = %.1f%%" % (report["total"]["pass"], report["total"]["n"], 100 * report["total"]["rate"]))
    failing = [row for row in results if row["outcome"] != "pass"]
    for row in failing[:args.failures]:
        print(row["kind"], row["language"], row["outcome"], "|", row["statement"], "|", row["question"], "|",
              (row["replies"][0] or "")[:80], "|", (row["replies"][1] or "")[:80])
    if args.out:
        args.out.write_text(json.dumps({"summary": report, "results": results}, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
