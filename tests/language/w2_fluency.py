"""W2.6: fluency sample 2 — 40 composed replies from ``data/benchmarks/dialogues_dev2``, 20 per language.

    KG_ENCODER=문자 python tests/language/w2_fluency.py

Plays the development set v2 through the composition gate's runner (the UI's
``AppState.turn``), keeps the replies the realizer composed, draws 20 per
language with a fixed seed, and writes ``marco/language/measurements/fluency-sample-2.md``
with an empty judgement column. Fluency is judged by a person, not counted.
"""
import os
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
SEED = 20260924
PER_LANGUAGE = 20
OUT = ROOT / "marco/language/measurements/fluency-sample-2.md"


def sample(report, seed=SEED, per_language=PER_LANGUAGE):
    """``per_language`` composed rows per language, drawn with ``seed``, in dialogue order."""
    chooser = random.Random(seed)
    chosen = []
    for code in ("ko", "en"):
        rows = [row for row in report["rows"] if row["bucket"] == "composed" and row["language"] == code]
        chosen += sorted(chooser.sample(rows, per_language), key=lambda row: report["rows"].index(row))
    return chosen


def table(report, rows, seed=SEED):
    def cell(text):
        return str(text).replace("|", "\\|").replace("\n", " ")
    counted = report["total"]
    lines = ["# Fluency sample 2 — for the owner to judge", "",
             "Goal W2.6. %d replies drawn at random (seed %d), %d per language, from the replies the realizer "
             "composed on `data/benchmarks/dialogues_dev2/` (%d of %d spoken replies composed), played through "
             "`AppState.turn` as `bench/composition_gate.py` plays it. The judgement column is empty on purpose: "
             "fluency is judged by a person, not counted." % (len(rows), seed, len(rows) // 2, counted["composed"],
                                                                counted["spoken"]),
             "", "Regenerate: `KG_ENCODER=문자 python tests/language/w2_fluency.py`.", "",
             "| # | language | turn | act | input | composed reply | judgement |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for n, row in enumerate(rows, 1):
        lines.append("| %d | %s | %s | %s | %s | %s | |" % (n, row["language"], row["turn"], row["act"],
                                                            cell(row["say"]), cell(row["spoken"])))
    return "\n".join(lines) + "\n"


def main():
    os.environ.setdefault("KG_ENCODER", "문자")
    sys.path.insert(0, str(ROOT / "bench"))
    import composition_gate as cg
    import dialogue_gate as gate
    dialogues = gate.load(ROOT / "data/benchmarks/dialogues_dev2")
    answers = cg.run(dialogues)
    report = cg.score(dialogues, answers)
    # The score keeps a shortened reply; the sample shows each reply whole.
    whole = {"%s#%d" % (d["id"], t["n"]): (answers[d["id"]][i].get("answer") or "")
             for d in dialogues for i, t in enumerate(d["turns"]) if i < len(answers.get(d["id"]) or [])}
    for row in report["rows"]:
        row["spoken"] = whole.get(row["turn"], row["spoken"])
    OUT.write_text(table(report, sample(report)), encoding="utf-8")
    print("wrote", OUT.relative_to(ROOT), "from", report["total"]["composed"], "composed of",
          report["total"]["spoken"])


if __name__ == "__main__":
    main()
