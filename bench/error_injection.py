"""Inject a wrong repair rule and a wrong composition rule; the evaluation must catch both.

Each fault is applied to an in-memory copy of one language pack. The seven-step
dialogue check (``bench/seven_step_dialogue.py``) and the repair checks
(``bench/repair_checks.py``) are rerun with the faulty pack; the fault counts
as caught only if at least one check fails, and the clean pack still passes
every check. An evaluation that passes a faulty pack is not trusted.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _model(language, mutate):
    from pack_model import PackModel, descriptor
    path = "styles/%s.json" % language
    pack = json.loads((ROOT / path).read_text(encoding="utf-8"))
    mutate(pack)
    assets = {path: json.dumps(pack, ensure_ascii=False).encode("utf-8")}
    for axiom in sorted((ROOT / "axioms").glob("*.json")):
        assets["axioms/" + axiom.name] = axiom.read_bytes()
    return PackModel({"version": 3, "model": descriptor(assets, path)}, assets)


def _cheap_skip(pack):
    # Wrong repair rule: skipping a typed word costs as little as moving a
    # particle, so a repair may silently drop content.
    pack["수선"]["costs"]["token_skip"] = 1


def _swap_transfer_roles(pack):
    # Wrong composition rule: the transfer rules give to the giver and take
    # from the receiver.
    for row in pack["관계해석"]["examples"]:
        meaning = row["meaning"]
        if "triples" in meaning and [t[1] for t in meaning["triples"]] == ["count_remove", "count_add"]:
            meaning["triples"] = [[meaning["triples"][0][0], "count_add", meaning["triples"][0][2]],
                                  [meaning["triples"][1][0], "count_remove", meaning["triples"][1][2]]]


def _inherit_leading(pack):
    # Wrong composition rule: a gapped conjunct inherits nothing — its subject
    # stays the bare name, so the count lands on the person, not the item.
    pack["생략"].pop("coordination", None)


FAULTS = [("wrong_repair_rule", "token_skip costs 1", _cheap_skip),
          ("wrong_composition_rule", "transfer roles swapped", _swap_transfer_roles),
          ("wrong_composition_rule", "coordination ellipsis removed", _inherit_leading)]


def run():
    from bench.seven_step_dialogue import run as dialogue
    from bench.repair_checks import run as repair_checks
    rows = []
    clean_repairs = repair_checks()
    for language in ("english", "한국어"):
        clean = dialogue(language)
        for kind, what, mutate in FAULTS:
            model = _model(language, mutate)
            faulty = dialogue(language, models={language: model})
            failed = ["step %d" % s["step"] for s in faulty["steps"] if not s["ok"]]
            repaired = repair_checks(models={language: model})
            failed += ["repair: %s" % r["input"] for r in repaired["rows"]
                       if r["language"] == language and r["outcome"] not in ("solved", "correct_hold")]
            clean_ok = (clean["passed"] == clean["total"]
                        and clean_repairs["passed"] == clean_repairs["total"])
            rows.append({"language": language, "kind": kind, "fault": what,
                         "clean_passed": "%d/%d, repair %d/%d" % (clean["passed"], clean["total"],
                                                                 clean_repairs["passed"], clean_repairs["total"]),
                         "faulty_failed": failed,
                         "caught": bool(failed) and clean_ok})
    return {"caught": sum(r["caught"] for r in rows), "total": len(rows), "rows": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args()
    report = run()
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("caught %d/%d" % (report["caught"], report["total"]))
    for row in report["rows"]:
        print(row["language"], row["kind"], row["fault"], "clean", row["clean_passed"],
              "faulty failed", row["faulty_failed"], "caught" if row["caught"] else "NOT CAUGHT")
