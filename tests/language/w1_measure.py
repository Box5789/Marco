"""Publish the W1 measurements.

    KG_ENCODER=문자 python tests/language/w1_measure.py

Writes ``marco/language/measurements/w1-measurements.json`` and
``marco/language/measurements/fluency-sample.md``. Runs the fixed dialogues
(§12 in both languages, the 20 frozen phrasings, the W1 dev dialogues) live and
with the W1-1 meaning block attached in the test, and counts separately:
realized, passed through, check passes, check blocks, holds, wrong assertions
and execution errors.
"""
import copy
import json
import re
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

OUT = ROOT / "marco" / "language" / "measurements"


def _numbers(text):
    return re.findall(r"\d+", re.sub(r"\"[^\"]*\"|'[^']*'|\([^)]*\)|\[[^\]]*\]", " ", text or ""))


def dialogue_run(fields):
    from marco.language.realizer import Realizer
    from test_w1_r5_discourse import fixed_dialogues
    from w1_harness import play
    counts = {"turns": 0, "replies": 0, "realized": 0, "passthrough": 0, "held": 0, "clauses": 0,
              "clauses_parsed": 0, "clauses_overt_only": 0, "check_blocks": 0, "wrong_assertions": 0,
              "execution_errors": 0, "by_intent": {}, "by_frame": {}}
    latencies, rows = [], []
    for dialogue in fixed_dialogues():
        realizer = Realizer()
        timed = _Timed(realizer)
        try:
            turns, _context = play(dialogue["language"], dialogue["turns"], companion=dialogue.get("companion"),
                                   realizer=timed, fields=fields)
        except Exception as exc:  # an execution error is counted, never hidden
            counts["execution_errors"] += 1
            rows.append({"dialogue": dialogue["id"], "error": "%s: %s" % (type(exc).__name__, exc)})
            continue
        latencies += timed.seconds
        for text, result, report in turns:
            counts["turns"] += 1
            if result is None or report is None:
                continue
            counts["replies"] += 1
            if not report.get("realized"):
                counts["passthrough"] += 1
                rows.append({"dialogue": dialogue["id"], "language": dialogue["language"], "input": text,
                             "status": result.get("status"), "answer": result.get("answer"),
                             "realized": False, "reason": report.get("reason")})
                continue
            counts["held" if report.get("held") else "realized"] += 1
            for intent in report.get("acts", []):
                counts["by_intent"][intent] = counts["by_intent"].get(intent, 0) + 1
            for clause in report.get("clauses", []):
                counts["clauses"] += 1
                counts["by_frame"][clause["frame"]] = counts["by_frame"].get(clause["frame"], 0) + 1
                counts["check_blocks"] += sum(1 for a in clause["attempts"]
                                              if not (a.get("check") or {}).get("ok", False))
                if clause.get("parse") == "parsed":
                    counts["clauses_parsed"] += 1
                elif clause.get("candidate"):
                    counts["clauses_overt_only"] += 1
            fact = next((row["fact"] for row in reversed(result.get("transitions") or [])
                         if isinstance(row.get("fact"), list)), None)
            if result.get("status") == "answered" and fact and fact[1] == "count" and \
                    [c for c in report["clauses"] if c.get("frame") == "count"]:
                said = _numbers(result["answer"])
                if not said or said[-1] != str(fact[2]):
                    counts["wrong_assertions"] += 1
            rows.append({"dialogue": dialogue["id"], "language": dialogue["language"], "input": text,
                         "status": result.get("status"), "answer": result.get("answer"), "realized": True,
                         "held": report.get("held"), "acts": report.get("acts"),
                         "candidates": [c.get("candidate") for c in report.get("clauses", [])]})
    return counts, latencies, rows


class _Timed:
    """A realizer whose realize calls are timed."""

    def __init__(self, realizer):
        self.inner = realizer
        self.seconds = []
        self.reports = realizer.reports

    def realize(self, meaning, intent, language):
        start = time.perf_counter()
        text = self.inner.realize(meaning, intent, language)
        self.seconds.append(time.perf_counter() - start)
        return text


def injection_table():
    import test_w1_r3_injected_errors as r3
    from marco.language.realizer import Realizer
    from w1_harness import play
    table = []
    for language, turns in r3.TURNS.items():
        rows, _context = play(language, turns)
        results = [result for _t, result, _r in rows]
        for fault, (mutate, index, frame, reader) in sorted(r3.FAULTS.items()):
            result = results[index]
            path = "styles/%s.json" % language
            clean = Realizer().realize(copy.deepcopy(result), result["status"], path)
            decl = r3.declarations(language)
            mutate(decl)
            faulty = Realizer(overrides={language: decl})
            text, report = faulty.realize_with_report(copy.deepcopy(result), result["status"], path)
            graph = faulty.build_graph(copy.deepcopy(result), path)
            prop = next(p for p in graph["props"] if p["frame"] == frame)
            readers = sorted({f["reader"] for c in report["clauses"] if c["frame"] == frame
                              for a in c["attempts"] for f in (a.get("check") or {}).get("failures", [])})
            table.append({"language": language, "fault": fault, "frame": frame,
                          "would_say": r3._faulty_surface(language, decl, prop), "caught_by": readers,
                          "emitted": text, "held": report.get("held"), "clean": clean})
    return table


def learning_table():
    import test_w1_r7_learning as r7
    from marco.language.realizer import Realizer
    out = []
    for language, turns, context, index in (("한국어", r7.KOREAN, {"register": "casual"}, 2),
                                            ("english", r7.ENGLISH, {}, 2)):
        realizer, rows = r7._learn(language, turns, context)
        turn = rows[index][1]
        before = Realizer(context=context).realize(copy.deepcopy(turn), turn["status"], "styles/%s.json" % language)
        after = realizer.realize(copy.deepcopy(turn), turn["status"], "styles/%s.json" % language)
        learned = realizer.learning.list()
        for item in learned:
            realizer.learning.remove(item["id"])
        removed = realizer.realize(copy.deepcopy(turn), turn["status"], "styles/%s.json" % language)
        out.append({"language": language, "context": context, "learned_from": [i["learned"]["source"] for i in learned],
                    "sentence": turns[index], "before": before, "after": after, "after_removal": removed,
                    "rejected": len(realizer.learning.rejected)})
    return out


def two_languages():
    from bench.seven_step_dialogue import SCRIPTS
    from marco.language.realizer import Realizer
    from w1_harness import play
    rows = []
    for language, script in SCRIPTS.items():
        other = "english" if language == "한국어" else "한국어"
        turns, _context = play(language, script["turns"], companion=other)
        realizer = Realizer()
        for text, result, _report in turns:
            graph = realizer.build_graph(copy.deepcopy(result), "styles/%s.json" % language)
            ko, kor = realizer.realize_graph(copy.deepcopy(graph), "한국어")
            en, enr = realizer.realize_graph(copy.deepcopy(graph), "english")
            rows.append({"dialogue": language, "input": text, "한국어": ko, "english": en,
                         "held": [kor["held"], enr["held"]]})
    return rows


def cost():
    from marco.language.realizer import Realizer, packs
    start = time.perf_counter()
    realizer = Realizer()
    for stem in ("한국어", "english"):
        packs._languages.pop(stem, None)
    result = {"status": "answered", "answer": "x", "transitions": [{"fact": ["지연 사과", "count", "4"]}]}
    realizer.realize(result, "answered", "styles/한국어.json")
    realizer.realize({**result, "transitions": [{"fact": ["Jiyeon apples", "count", "4"]}]}, "answered",
                     "styles/english.json")
    first = time.perf_counter() - start
    tracemalloc.start()
    realizer.realize(result, "answered", "styles/한국어.json")
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    sizes = {path.name: path.stat().st_size for path in sorted((ROOT / "marco/language/realizer").glob("*.json"))}
    code = sum(path.stat().st_size for path in (ROOT / "marco/language").rglob("*.py"))
    return {"first_two_realizations_with_pack_load_s": round(first, 3),
            "peak_memory_one_realization_bytes": peak, "declaration_bytes": sizes, "python_bytes": code}


def fluency_sample(rows):
    """A fixed sample for a person to judge: every realized reply of the §12 dialogue and one dev dialogue per language."""
    wanted = {"section12-english", "section12-한국어", "ko-dev-04", "en-dev-04"}
    lines = ["# Fluency sample — for the owner to judge", "",
             "Fixed sample: every reply of the §12 dialogue in each language and dev dialogues ko-dev-04 and "
             "en-dev-04, realized with the W1-1 meaning block attached in the test. "
             "Judgement column is empty on purpose: fluency is judged by a person, not counted.", "",
             "| # | dialogue | input | realized reply | judgement |", "| --- | --- | --- | --- | --- |"]
    n = 0
    for row in rows:
        if row.get("dialogue") in wanted and row.get("realized"):
            n += 1
            cell = lambda s: (s or "").replace("|", "\\|")
            lines.append("| %d | %s | %s | %s | |" % (n, row["dialogue"], cell(row["input"]), cell(row["answer"])))
    return "\n".join(lines) + "\n"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    shim_counts, shim_latency, shim_rows = dialogue_run(fields=True)
    live_counts, live_latency, live_rows = dialogue_run(fields=False)
    from test_w1_r5_discourse import discourse_counts
    discourse_shim, _ = discourse_counts(fields=True)
    discourse_live, _ = discourse_counts(fields=False)

    def latency(values):
        values = sorted(values)
        return {"turns": len(values), "median_ms": round(statistics.median(values) * 1000, 2),
                "p95_ms": round(values[int(0.95 * (len(values) - 1))] * 1000, 2),
                "max_ms": round(values[-1] * 1000, 2)} if values else {}
    report = {
        "dialogues": "section12 x2 + unseen-before 20 + w1_dev_dialogues 12",
        "with_w1_1_fields": {"counts": shim_counts, "discourse": discourse_shim, "realize_latency": latency(shim_latency)},
        "live_seam": {"counts": live_counts, "discourse": discourse_live, "realize_latency": latency(live_latency)},
        "injected_faults": injection_table(),
        "learning": learning_table(),
        "two_languages": two_languages(),
        "cost": cost(),
    }
    (OUT / "w1-measurements.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (OUT / "w1-replies-with-fields.json").write_text(json.dumps(shim_rows, ensure_ascii=False, indent=1) + "\n",
                                                     encoding="utf-8")
    (OUT / "w1-replies-live.json").write_text(json.dumps(live_rows, ensure_ascii=False, indent=1) + "\n",
                                              encoding="utf-8")
    (OUT / "fluency-sample.md").write_text(fluency_sample(shim_rows), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("with_w1_1_fields", "live_seam", "cost")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
