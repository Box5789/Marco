"""MARCO 1 reasoning gate: the frozen reasoning set and its scorer (goal F2, gate condition 6).

The problems in ``data/benchmarks/reasoning_v1/`` are structured reasoning
problems in declared phrasings: setup statements written only in surface forms
the language packs declare (``styles/*.json`` examples and their declared
variants), then one or more questions.  Each question carries its expected
answer as a semantic structure (``expect``: a count, a total, the holder with
more, the taller one, a place, a proven membership, "cannot be concluded", or a
hold that names what is missing) and the derivation it needs (which setup
statements, which rules).  No expectation is a surface string.

Every problem is played through ``views.kgpack_ui.AppState.turn`` -- the call
behind the UI's ``POST /api/turn`` -- by the dialogue gate's own runner
(``bench/dialogue_gate.py``: same packs, same conversation store, web research
stubbed and counted, ``restart_before`` builds a new ``AppState`` over the saved
conversation).  Setup statements and questions are one conversation, in order.

Every question lands in exactly one bucket:

  correct          the reply states the expected answer (quoted spans removed)
  wrong            the reply concludes something else, or cites retracted evidence
  hold             no conclusion: held, not understood, or no value stated
  execution_error  the turn raised
  unparsed         a setup statement before it was not recorded, so reasoning
                   never started; it leaves the reasoning denominator and is
                   listed with the statement that failed

Gate condition 6 (``docs/ko/2026-09-22-freeze-decision.md``) counts problems: a
problem is unparsed when any of its questions is, wrong when any parsed question
is wrong, correct when every question is correct.  Pass: 95% or more of parsed
problems correct, 0 wrong questions, at most 10% of problems unparsed.

Commands (``python bench/reasoning_gate.py <command>``):

  validate   F2.1  schema, counts, and an independent replay of every expectation
  overlap    F2.1  full-sentence overlap with dialogues_v1, dialogues_dev, dialogues_dev2
                   (the frozen dialogues are read by the overlap script only; no
                   sentence is printed, only problem ids and file names)
  run        F2.2  play every problem through the UI turn handler and score it
  score      F2.2  score a saved answers file (``--expected`` swaps in other expectations)
  digest     F2.4  print (or --write) the directory SHA-256 (alias: hash)
  baseline   F2.4  record the baseline at the main commit this goal started from

``--dataset <dir>`` reads another problem directory with the same schema.
"""
import argparse
import copy
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "bench") not in sys.path:
    sys.path.insert(0, str(ROOT / "bench"))
import dialogue_gate as gate  # noqa: E402

DATASET = ROOT / "data/benchmarks/reasoning_v1"
FROZEN = DATASET / "FROZEN.sha256"
REPORT_DIR = ROOT / "docs/ko/reasoning-gate-2026-09-24"
BASELINE_COMMIT = "70ba9f8"   # main when goal F2 started (2026-09-24)

SCHEMA = "marco1-reasoning-gate-v1"
KINDS = ("count_arithmetic", "transfer_chain", "comparison", "total", "negation", "temporal_order",
         "missing_premise", "correction", "restart", "class_inference")
LANGUAGES = gate.LANGUAGES
BUCKETS = ("correct", "wrong", "hold", "execution_error", "unparsed")
EXPECT_TYPES = ("count", "total", "more", "taller", "location", "yes", "unknown", "hold")
EVENT_TYPES = ("has", "use", "add", "transfer", "located", "move", "planned_move", "negated_move",
               "move_to_where", "taller", "subclass", "isa", "all_action", "action", "revise")
RULES = ("count_update", "transfer", "sum", "compare_counts", "taller_transitive", "negation_kept_apart",
         "negation_blocks", "contradiction", "latest_location", "planned_not_actual", "negated_not_actual",
         "lookup_at_event_time", "subclass_chain", "action_inheritance", "converse_not_derivable",
         "not_derivable", "premise_missing", "correction_replaces", "restore_snapshot")
MINIMUM = {"problems": 100, "per_language": 40, "per_kind": 8}
GATE = {"correct": 0.95, "wrong": 0, "unparsed": 0.10}
OVERLAP_DIRS = ("data/benchmarks/dialogues_v1", "data/benchmarks/dialogues_dev", "data/benchmarks/dialogues_dev2")
NOT_UNDERSTOOD = {"입력이해실패"}   # verdict when the question itself was not read


# ---------------------------------------------------------------------------
# dataset
# ---------------------------------------------------------------------------
def load(directory=DATASET):
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(Path(directory).glob("*.json"))]


def tree_hash(directory=DATASET):
    return gate.tree_hash(directory)


def frozen_hash(path=FROZEN):
    return gate.frozen_hash(path)


def script(problem):
    """The conversation in play order: setup statements, each question after its ``after`` statement."""
    questions = sorted(problem["questions"], key=lambda q: (q["after"], q["q"]))
    turns = []
    for s in problem["setup"]:
        turns.append({"role": "setup", "ref": s["n"], "say": s["say"], "restart_before": bool(s.get("restart_before"))})
        for q in questions:
            if q["after"] == s["n"]:
                turns.append({"role": "question", "ref": q["q"], "say": q["say"],
                              "restart_before": bool(q.get("restart_before"))})
    for n, turn in enumerate(turns, 1):
        turn["n"] = n
    return turns


def as_dialogues(problems):
    """The problems in the dialogue-gate shape its runner and overlap check read."""
    return [{"id": p["id"], "language": p["language"],
             "turns": [{"n": t["n"], "say": t["say"], "restart_before": t["restart_before"]} for t in script(p)]}
            for p in problems]


# ---------------------------------------------------------------------------
# F2.1 independent replay of the declared events
# ---------------------------------------------------------------------------
def _events(problem, upto, corrected=True):
    """(statement n, event) for statements 1..upto; a correction replaces its target's events."""
    replaced = {}
    if corrected:
        for s in problem["setup"][:upto]:
            for e in s["events"]:
                if e["type"] == "revise":
                    replaced[e["target"]] = e["with"]
    out = []
    for s in problem["setup"][:upto]:
        for e in replaced.get(s["n"], s["events"]):
            if e["type"] != "revise":
                out.append((s["n"], e))
    return out


def _counts(events):
    state = {}
    for _n, e in events:
        kind = e["type"]
        if kind == "has":
            state[(e["holder"], e["item"])] = e["quantity"]
        elif kind in ("use", "add"):
            key = (e["holder"], e["item"])
            state[key] = None if state.get(key) is None else state[key] + (e["quantity"] if kind == "add"
                                                                           else -e["quantity"])
        elif kind == "transfer":
            for key, sign in (((e["from"], e["item"]), -1), ((e["to"], e["item"]), 1)):
                state[key] = None if state.get(key) is None else state[key] + sign * e["quantity"]
    return state


def _places(events):
    where = {}
    for _n, e in events:
        if e["type"] in ("located", "move"):
            where[e["item"]] = e["place"]
        elif e["type"] == "move_to_where":
            where[e["item"]] = where.get(e["where"])
    return where


def _taller(events, a, b):
    """The taller of a and b by the positive statements' transitive closure; None when not concluded."""
    pos = {(e["a"], e["b"]) for _n, e in events if e["type"] == "taller" and e["polarity"]}
    neg = {(e["a"], e["b"]) for _n, e in events if e["type"] == "taller" and not e["polarity"]}
    known = set(pos)
    grown = True
    while grown:
        more = {(x, z) for (x, y) in known for (y2, z) in known if y == y2} - known
        known |= more
        grown = bool(more)
    ab, ba = (a, b) in known, (b, a) in known
    if ab == ba:
        return None
    winner, loser = (a, b) if ab else (b, a)
    return None if (winner, loser) in neg else winner


def _closure(events, member, relation):
    parents = {}
    for _n, e in events:
        if e["type"] == "subclass":
            parents.setdefault(e["sub"], set()).add(e["super"])
    classes = {e["class"] for _n, e in events if e["type"] == "isa" and e["member"] == member}
    todo = list(classes)
    while todo:
        for d in parents.get(todo.pop(), ()):
            if d not in classes:
                classes.add(d)
                todo.append(d)
    if relation == "isa":
        return classes
    return ({e["action"] for _n, e in events if e["type"] == "all_action" and e["class"] in classes}
            | {e["action"] for _n, e in events if e["type"] == "action" and e["member"] == member})


def _mentioned(problem, upto):
    """Every name, item, place and class the setup statements 1..upto mention."""
    words = set()
    for _n, e in _events(problem, upto):
        for key, value in e.items():
            if key not in ("type", "quantity", "polarity") and isinstance(value, str):
                words.add(value)
    return words


def _check_expect(problem, q):
    """Problems with one question's expectation: it must replay from the declared events."""
    at = "%s#q%s" % (problem["id"], q.get("q"))
    e, out = q.get("expect") or {}, []
    events = _events(problem, q["after"])
    typ = e.get("type")
    if typ in ("count", "total"):
        members = [e.get("entity")] if typ == "count" else e.get("members") or []
        if typ == "total" and len(members) < 2:
            out.append("%s: a total needs two or more holders" % at)
        state = _counts(events)
        values = [state.get((m, e.get("item"))) for m in members]
        if None in values or sum(values) != e.get("value"):
            out.append("%s: %s does not replay" % (at, typ))
        if "retracted_value" in e:
            old = [_counts(_events(problem, q["after"], corrected=False)).get((m, e["item"])) for m in members]
            if None in old or sum(old) != e["retracted_value"] or e["retracted_value"] == e.get("value"):
                out.append("%s: retracted value does not replay" % at)
    elif typ == "more":
        a, b = e.get("candidates") or (None, None)
        state = _counts(events)
        va, vb = state.get((a, e.get("item"))), state.get((b, e.get("item")))
        if None in (va, vb) or va == vb or e.get("entity") != (a if va > vb else b):
            out.append("%s: 'more' does not replay" % at)
    elif typ == "taller":
        a, b = e.get("candidates") or (None, None)
        if _taller(events, a, b) != e.get("entity") or e.get("entity") is None:
            out.append("%s: 'taller' does not replay" % at)
    elif typ == "location":
        if _places(events).get(e.get("item")) != e.get("place") or e.get("place") in e.get("other_places", []):
            out.append("%s: place does not replay" % at)
    elif typ == "yes":
        if e.get("object") not in _closure(events, e.get("subject"), e.get("relation")):
            out.append("%s: membership does not replay" % at)
    elif typ == "unknown":
        if e.get("candidates"):
            if _taller(events, *e["candidates"]) is not None:
                out.append("%s: 'unknown' is concluded by the statements" % at)
        elif e.get("object") in _closure(events, e.get("subject"), e.get("relation")):
            out.append("%s: 'unknown' membership is concluded by the statements" % at)
    elif typ == "hold":
        missing = e.get("missing") or {}
        if not e.get("names") or not missing.get("entity") or not missing.get("relation"):
            out.append("%s: a hold names what is missing" % at)
        relation, entity = missing.get("relation"), missing.get("entity")
        if relation == "count" and _counts(events).get((entity, missing.get("item"))) is not None:
            out.append("%s: the held count is known" % at)
        if relation == "location" and entity in _places(events):
            out.append("%s: the held place is known" % at)
        if relation in ("taller", "isa") and entity in _mentioned(problem, q["after"]):
            out.append("%s: the held %s is stated" % (at, relation))
    else:
        out.append("%s: expect.type %r" % (at, typ))
    return out


def validate(problems):
    """Return a list of problems; empty means F2.1 holds and every expectation replays."""
    out = []
    ids = [p.get("id") for p in problems]
    if len(set(ids)) != len(ids):
        out.append("duplicate ids")
    if len(problems) < MINIMUM["problems"]:
        out.append("fewer than %d problems: %d" % (MINIMUM["problems"], len(problems)))
    for code in LANGUAGES:
        n = sum(p.get("language") == code for p in problems)
        if n < MINIMUM["per_language"]:
            out.append("fewer than %d %s problems: %d" % (MINIMUM["per_language"], code, n))
    for kind in KINDS:
        n = sum(p.get("kind") == kind for p in problems)
        if n < MINIMUM["per_kind"]:
            out.append("fewer than %d %s problems: %d" % (MINIMUM["per_kind"], kind, n))
    for p in problems:
        where = p.get("id")
        if p.get("schema") != SCHEMA:
            out.append("%s: schema" % where)
        if p.get("language") not in LANGUAGES or p.get("kind") not in KINDS:
            out.append("%s: language/kind" % where)
        if not str(where).startswith(str(p.get("language")) + "-"):
            out.append("%s: id does not start with its language" % where)
        setup, questions = p.get("setup") or [], p.get("questions") or []
        if not setup or not questions:
            out.append("%s: needs setup statements and questions" % where)
            continue
        if [s.get("n") for s in setup] != list(range(1, len(setup) + 1)):
            out.append("%s: setup numbering" % where)
        if [q.get("q") for q in questions] != list(range(1, len(questions) + 1)):
            out.append("%s: question numbering" % where)
        for s in setup:
            if not isinstance(s.get("say"), str) or not s["say"].strip() or not s.get("events"):
                out.append("%s#%s: say/events" % (where, s.get("n")))
            for e in s.get("events") or []:
                if e.get("type") not in EVENT_TYPES:
                    out.append("%s#%s: event type %r" % (where, s.get("n"), e.get("type")))
                if e.get("type") == "revise" and not (isinstance(e.get("target"), int) and 1 <= e["target"] < s["n"]
                                                      and e.get("with")):
                    out.append("%s#%s: a correction revises an earlier statement" % (where, s.get("n")))
        for q in questions:
            at = "%s#q%s" % (where, q.get("q"))
            if not isinstance(q.get("say"), str) or not q["say"].strip():
                out.append("%s: say" % at)
            if not isinstance(q.get("after"), int) or not 1 <= q["after"] <= len(setup):
                out.append("%s: after" % at)
                continue
            e = q.get("expect") or {}
            if any(key in e for key in ("answer", "text", "reply", "say")):
                out.append("%s: surface string in expectation" % at)
            d = q.get("derivation") or {}
            if not isinstance(d.get("facts"), list) or any(not isinstance(n, int) or not 1 <= n <= q["after"]
                                                           for n in d["facts"]):
                out.append("%s: derivation facts" % at)
            if not d.get("rules") or any(rule not in RULES for rule in d["rules"]):
                out.append("%s: derivation rules" % at)
            out += _check_expect(p, q)
        kinds = {e["type"] for s in setup for e in s["events"]}
        types = {q["expect"].get("type") for q in questions}
        restarts = any(s.get("restart_before") for s in setup) or any(q.get("restart_before") for q in questions)
        need = {"count_arithmetic": bool(types & {"count"}) and bool(kinds & {"use", "add"}),
                "transfer_chain": sum(e["type"] == "transfer" for s in setup for e in s["events"]) >= 3,
                "comparison": bool(types & {"more", "taller"}),
                "total": "total" in types,
                "negation": any(e.get("polarity") is False or e["type"] == "negated_move"
                                for s in setup for e in s["events"]),
                "temporal_order": "location" in types and (len([e for s in setup for e in s["events"]
                                                                if e["type"] in ("located", "move")]) >= 2
                                                           or bool(kinds & {"planned_move", "move_to_where"})),
                "missing_premise": "hold" in types,
                "correction": "revise" in kinds,
                "restart": restarts,
                "class_inference": bool(types & {"yes", "unknown"}) and bool(kinds & {"subclass", "all_action"})}
        if p.get("kind") in need and not need[p["kind"]]:
            out.append("%s: does not exercise its kind %s" % (where, p["kind"]))
    return out


def tables(problems):
    """Counts per kind and language: problems and questions."""
    rows = {}
    for kind in KINDS:
        rows[kind] = {}
        for code in LANGUAGES:
            chosen = [p for p in problems if p["kind"] == kind and p["language"] == code]
            rows[kind][code] = {"problems": len(chosen), "questions": sum(len(p["questions"]) for p in chosen)}
    return {"kinds": rows, "problems": len(problems), "questions": sum(len(p["questions"]) for p in problems),
            "by_language": {c: sum(p["language"] == c for p in problems) for c in LANGUAGES},
            "expect_types": {t: sum(q["expect"]["type"] == t for p in problems for q in p["questions"])
                             for t in EXPECT_TYPES}}


# ---------------------------------------------------------------------------
# F2.1 overlap with the dialogue sets (sentences never printed)
# ---------------------------------------------------------------------------
def overlap(problems, rev=None, dirs=OVERLAP_DIRS):
    """Full-sentence overlap of every setup statement and question with the dialogue sets.

    Directories present on disk are read there; a directory absent on disk is
    read at ``rev`` (a branch that has it) when given.  Returns counts and the
    overlapping (problem, turn, file) triples -- never the sentence text.
    """
    dialogues = as_dialogues(problems)
    checked, found, missing = {}, [], []
    for directory in dirs:
        if (ROOT / directory).is_dir():
            source = "disk"
            result = gate.overlaps(dialogues, disk_root=ROOT, dirs=(directory,), owned=())
        elif rev:
            try:
                subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", "%s:%s" % (rev, directory)], check=True,
                               capture_output=True)
            except subprocess.CalledProcessError:
                missing.append(directory)
                continue
            source = "git %s (%s)" % (rev, gate._git("rev-parse", "--short", rev))
            result = gate.overlaps(dialogues, rev=rev, dirs=(directory,), owned=())
        else:
            missing.append(directory)
            continue
        checked[directory] = {"source": source, "files": result["files"]}
        found += [{"problem": row["dialogue"], "turn": row["turn"], "file": row["file"]} for row in result["overlaps"]]
    return {"sentences": len(gate.dialogue_sentences(dialogues)), "checked": checked, "missing": missing,
            "overlaps": found}


# ---------------------------------------------------------------------------
# F2.2 run and score
# ---------------------------------------------------------------------------
def run(problems, code_root=ROOT, progress=None):
    """Play every problem through AppState.turn; return {problem id: [observation per turn in play order]}."""
    return gate.run(as_dialogues(problems), code_root, progress)


def _norm(text):
    return re.sub(r"\s+", " ", (text or "").lower()).strip().strip(" .!?。…\"'“”")


def _named(text, names):
    return {name for name in names if name and gate._mentions(text, name)}


def _retracted_statements(problem, after):
    return [problem["setup"][e["target"] - 1]["say"] for s in problem["setup"][:after]
            for e in s["events"] if e["type"] == "revise"]


def score_question(problem, question, obs):
    """(bucket, reason) for one question whose setup statements were all recorded."""
    e = question["expect"]
    st = gate.status(obs)
    if st == "error":
        return "execution_error", obs.get("error")
    verdict = obs.get("verdict")
    claimed = gate.asserted(obs.get("answer") or "")
    facts = obs.get("facts") or []
    typ = e["type"]
    if typ == "hold":
        if st == "answered":
            # A reply that states a value, carries an answer fact or names anyone
            # the conversation mentions has concluded something it could not know.
            if facts or gate.quantities(claimed) or _named(claimed, set(e["names"]) | _mentioned(
                    problem, question["after"])):
                return "wrong", "confident_answer"
            return "hold", "answered_without_conclusion"
        if st == "observed":
            return "wrong", "recorded_as_statement"
        if verdict in NOT_UNDERSTOOD:
            return "hold", "question_not_understood"
        if st != "held":
            return "hold", st
        if all(gate._mentions(claimed, name) for name in e["names"]):
            return "correct", "held_and_named"
        return "hold", "vague_hold"
    if typ == "unknown":
        if st == "observed":
            return "wrong", "recorded_as_statement"
        if verdict in NOT_UNDERSTOOD:
            return "hold", "question_not_understood"
        if st != "answered":
            return ("correct", "held") if st == "held" else ("hold", st)
        if e.get("candidates"):
            a, b = e["candidates"]
            concluded = {f["subject"] for f in facts if f["predicate"] == "taller"
                         and {f["subject"], f["value"]} == {a, b}}
            named = _named(claimed, e["candidates"])
            if concluded or len(named) == 1:
                return "wrong", "concluded:%s" % sorted(concluded or named)[0]
        elif any((f["subject"], f["predicate"], f["value"]) == (e["subject"], e["relation"], e["object"])
                 for f in facts):
            return "wrong", "concluded_membership"
        return "correct", "no_conclusion"
    # the rest expect a conclusion
    if st != "answered":
        return "hold", "question_not_understood" if verdict in NOT_UNDERSTOOD else st
    if typ in ("count", "total"):
        values = gate.quantities(claimed)
        fact_values = {int(f["value"]) for f in facts if re.fullmatch(r"-?\d+", f["value"])}
        if len(values) == 1:
            value = next(iter(values))
        elif len(values) > 1 and len(fact_values) == 1 and fact_values <= values:
            value = next(iter(fact_values))
        elif not values:
            return "hold", "no_value_stated"
        else:
            return "wrong", "several_values:%s" % sorted(values)
        if value != e["value"]:
            if value == e.get("retracted_value"):
                return "wrong", "retracted_value:%d" % value
            return "wrong", "value:%d" % value
        if typ == "count" and e.get("entity"):
            other = [f["subject"] for f in facts if f["predicate"] == "count" and f["value"] == str(value)
                     and not gate._mentions(f["subject"], e["entity"])]
            same = [f for f in facts if f["predicate"] == "count" and gate._mentions(f["subject"], e["entity"])]
            if other and not same:
                return "wrong", "value_of_other_holder:%s" % other[-1]
        retracted = {_norm(text) for text in _retracted_statements(problem, question["after"])}
        for f in facts:
            if any(_norm(x) in retracted for x in f.get("evidence") or []):
                return "wrong", "retracted_evidence"
        return "correct", "value"
    if typ in ("more", "taller"):
        named = _named(claimed, e["candidates"])
        if named == {e["entity"]}:
            return "correct", "entity"
        if not named:
            return "wrong", "no_candidate_named"
        if e["entity"] not in named:
            return "wrong", ("retracted_entity:%s" if e.get("retracted_entity") in named else "other_entity:%s") % (
                sorted(named)[0])
        return "wrong", "several_candidates_named"
    if typ == "location":
        if not gate._mentions(claimed, e["place"]):
            if e.get("retracted_place") and gate._mentions(claimed, e["retracted_place"]):
                return "wrong", "retracted_place:%s" % e["retracted_place"]
            others = _named(claimed, e.get("other_places", []))
            return ("wrong", "other_place:%s" % sorted(others)[0]) if others else ("wrong", "place_not_named")
        others = _named(claimed, e.get("other_places", []))
        if others:
            return "wrong", "other_place_also_named:%s" % sorted(others)[0]
        return "correct", "place"
    if typ == "yes":
        wanted = (e["subject"].lower(), e["relation"], e["object"].lower())
        if any((f["subject"].lower(), f["predicate"], f["value"].lower()) == wanted for f in facts):
            return "correct", "proven"
        if not facts:
            return "hold", "no_conclusion"
        return "wrong", "not_proven"
    raise ValueError("unknown expectation type %r" % typ)


def misread(problem, n, obs):
    """Recorded state rows that disagree with the statement's declared events (diagnostic, no bucket).

    A statement recorded with another value than it declares is a reading
    failure that would surface later as a wrong answer; listing it keeps
    parsing and reasoning apart when a wrong is read.
    """
    events = _events(problem, n)
    counts, places = _counts(events), _places(events)
    statement = problem["setup"][n - 1]
    declared = [w for e in statement["events"] for w in (e["with"] if e["type"] == "revise" else [e])]
    out = []
    for e in declared:
        keys = []
        if e["type"] in ("has", "use", "add"):
            keys = [(e["holder"], e["item"])]
        elif e["type"] == "transfer":
            keys = [(e["from"], e["item"]), (e["to"], e["item"])]
        for holder, item in keys:
            got = gate._subject_value(obs, holder or item, item)
            if got is not None and got != str(counts.get((holder, item))):
                out.append({"holder": holder, "item": item, "declared": counts.get((holder, item)), "recorded": got})
        if e["type"] in ("located", "move"):
            rows = [r for r in obs.get("state") or [] if r["subject"] == e["item"]]
            if rows and rows[-1]["value"] != places.get(e["item"]):
                out.append({"item": e["item"], "declared": places.get(e["item"]), "recorded": rows[-1]["value"]})
    return out


def _counts_row(rows):
    out = {k: 0 for k in BUCKETS}
    for row in rows:
        out[row["bucket"]] += 1
    out["n"] = len(rows)
    out["parsed"] = out["n"] - out["unparsed"]
    out["accuracy"] = round(out["correct"] / out["parsed"], 4) if out["parsed"] else None
    return out


def score(problems, answers, expected=None, meta=None):
    """Score saved observations.  ``expected`` ({problem id: [expect per question]}) overrides the file's."""
    rows, setups, problem_rows = [], [], []
    for p in problems:
        turns = script(p)
        got = answers.get(p["id"]) or []
        observations = [got[i] if i < len(got) else {"error": "no observation recorded"} for i in range(len(turns))]
        failed = []
        swapped = (expected or {}).get(p["id"])
        mine = []
        for turn, obs in zip(turns, observations):
            if turn["role"] == "setup":
                st = gate.status(obs)
                entry = {"problem": p["id"], "language": p["language"], "kind": p["kind"], "n": turn["ref"],
                         "say": turn["say"], "status": st, "verdict": obs.get("verdict"),
                         "recorded": st == "observed", "reply": (obs.get("answer") or obs.get("error") or "")[:300]}
                if entry["recorded"]:
                    entry["misread"] = misread(p, turn["ref"], obs)
                setups.append(entry)
                if not entry["recorded"]:
                    failed.append(entry)
                continue
            q = next(q for q in p["questions"] if q["q"] == turn["ref"])
            if swapped is not None:
                q = dict(q, expect=swapped[q["q"] - 1])
            if failed:
                bucket, reason = "unparsed", "setup %s not recorded" % ",".join(str(f["n"]) for f in failed)
            else:
                bucket, reason = score_question(p, q, obs)
            row = {"problem": p["id"], "language": p["language"], "kind": p["kind"], "q": q["q"], "say": q["say"],
                   "expect": q["expect"], "bucket": bucket, "reason": reason, "status": gate.status(obs),
                   "verdict": obs.get("verdict"), "answer": (obs.get("answer") or obs.get("error") or "")[:300],
                   "evidence": bool(obs.get("facts") or obs.get("evidence")),
                   "research_calls": obs.get("research_calls")}
            if failed:
                row["failed_statements"] = [{"n": f["n"], "say": f["say"], "reply": f["reply"]} for f in failed]
            rows.append(row)
            mine.append(row)
        buckets = [r["bucket"] for r in mine]
        problem_bucket = next(b for b in ("unparsed", "wrong", "execution_error", "hold", "correct")
                              if b in buckets or b == "correct")
        problem_rows.append({"problem": p["id"], "language": p["language"], "kind": p["kind"],
                             "bucket": problem_bucket, "questions": len(mine)})
    parsed_problems = [r for r in problem_rows if r["bucket"] != "unparsed"]
    wrong_questions = sum(r["bucket"] == "wrong" for r in rows)
    correct_problems = sum(r["bucket"] == "correct" for r in parsed_problems)
    unparsed_problems = len(problem_rows) - len(parsed_problems)
    gate_row = {
        "problems": len(problem_rows), "parsed": len(parsed_problems), "correct": correct_problems,
        "wrong_questions": wrong_questions, "unparsed": unparsed_problems,
        "accuracy": round(correct_problems / len(parsed_problems), 4) if parsed_problems else None,
        "unparsed_share": round(unparsed_problems / len(problem_rows), 4) if problem_rows else None,
        "needed": math.ceil(GATE["correct"] * len(parsed_problems)),
        "threshold": GATE,
        "denominator": "problems whose every setup statement was recorded (%d of %d); a problem is correct "
                       "when every question is correct; wrong counts questions" % (
                           len(parsed_problems), len(problem_rows))}
    gate_row["passed"] = bool(parsed_problems) and correct_problems >= gate_row["needed"] and \
        wrong_questions <= GATE["wrong"] and gate_row["unparsed_share"] <= GATE["unparsed"]
    by_kind = {k: {c: _counts_row([r for r in rows if r["kind"] == k and r["language"] == c]) for c in LANGUAGES}
               for k in KINDS}
    for k in KINDS:
        by_kind[k]["all"] = _counts_row([r for r in rows if r["kind"] == k])
    unparsed = []
    for s in setups:
        if not s["recorded"]:
            unparsed.append({"problem": s["problem"], "language": s["language"], "kind": s["kind"], "n": s["n"],
                             "say": s["say"], "status": s["status"], "verdict": s["verdict"], "reply": s["reply"],
                             "questions_unparsed": sum(1 for r in rows if r["problem"] == s["problem"]
                                                       and r["bucket"] == "unparsed")})
    return {
        "schema": SCHEMA + "-report", "meta": meta or {},
        "dataset": {"problems": len(problems), "questions": len(rows), "setup_statements": len(setups),
                    "by_language": {c: sum(p["language"] == c for p in problems) for c in LANGUAGES}},
        "questions": dict(_counts_row(rows), denominator="parsed questions: every question whose setup "
                                                          "statements were all recorded (unparsed reported apart)"),
        "by_language": {c: _counts_row([r for r in rows if r["language"] == c]) for c in LANGUAGES},
        "by_kind": by_kind,
        "gate": gate_row,
        "problems": {b: sum(r["bucket"] == b for r in problem_rows) for b in BUCKETS},
        "setup": {"statements": len(setups), "recorded": sum(s["recorded"] for s in setups),
                  "recorded_with_another_value": [dict(problem=s["problem"], n=s["n"], say=s["say"], rows=s["misread"])
                                                  for s in setups if s.get("misread")]},
        "unparsed": unparsed,
        "failures": [r for r in rows if r["bucket"] != "correct"],
        "rows": rows,
        "problem_rows": problem_rows,
    }


def format_report(report):
    q, g = report["questions"], report["gate"]

    def pct(x):
        return "%.1f%%" % (100 * x) if x is not None else "n/a"
    lines = ["problems %d  questions %d  setup statements %d (recorded %d)  ko %d  en %d" % (
        report["dataset"]["problems"], report["dataset"]["questions"], report["setup"]["statements"],
        report["setup"]["recorded"], report["dataset"]["by_language"]["ko"], report["dataset"]["by_language"]["en"]),
        "QUESTIONS parsed %d of %d: correct %d  wrong %d  hold %d  execution_error %d  -> %s;  unparsed %d" % (
            q["parsed"], q["n"], q["correct"], q["wrong"], q["hold"], q["execution_error"], pct(q["accuracy"]),
            q["unparsed"]),
        "denominator: " + q["denominator"],
        "GATE 6 problems parsed %d of %d: correct %d (%s, needs %d = 95%%), wrong questions %d (needs 0), "
        "unparsed %d (%s, at most 10%%) -> %s" % (
            g["parsed"], g["problems"], g["correct"], pct(g["accuracy"]), g["needed"], g["wrong_questions"],
            g["unparsed"], pct(g["unparsed_share"]), "PASS" if g["passed"] else "FAIL"),
        "", "%-18s %-3s %4s %6s %7s %5s %4s %5s %8s" % ("kind", "", "N", "parsed", "correct", "wrong", "hold",
                                                      "error", "unparsed")]
    for kind, row in report["by_kind"].items():
        for code in list(LANGUAGES) + ["all"]:
            c = row[code]
            if not c["n"]:
                lines.append("%-18s %-3s %4d   (no problems in this language)" % (kind, code, 0))
                continue
            lines.append("%-18s %-3s %4d %6d %7d %5d %4d %5d %8d" % (
                kind, code, c["n"], c["parsed"], c["correct"], c["wrong"], c["hold"], c["execution_error"],
                c["unparsed"]))
    for code, c in report["by_language"].items():
        lines.append("%-18s %-3s %4d %6d %7d %5d %4d %5d %8d" % (
            "language", code, c["n"], c["parsed"], c["correct"], c["wrong"], c["hold"], c["execution_error"],
            c["unparsed"]))
    lines += ["", "setup statements recorded with another value than declared: %d" % len(
        report["setup"]["recorded_with_another_value"])]
    for m in report["setup"]["recorded_with_another_value"]:
        lines.append("  %s#%d %r %s" % (m["problem"], m["n"], m["say"], json.dumps(m["rows"], ensure_ascii=False)))
    lines += ["unparsed: %d setup statements not recorded" % len(report["unparsed"])]
    for u in report["unparsed"]:
        lines.append("  %s#%d %r -> %s (%d questions)" % (u["problem"], u["n"], u["say"], u["reply"][:90],
                                                         u["questions_unparsed"]))
    lines.append("failures listed: %d (full list in the JSON report)" % len(report["failures"]))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# synthetic answers and expectations (error-injection tests)
# ---------------------------------------------------------------------------
def _perfect(q, wrong=False):
    e = q["expect"]
    base = {"phase": "answer", "facts": [], "state": [], "corrections": [], "evidence": [],
            "observation_turns": None, "research_calls": 0}
    typ = e["type"]
    if typ in ("count", "total"):
        value = e["value"] + (1 if wrong else 0)
        subject = e.get("entity") or " ".join(e.get("members") or []) or e["item"]
        return dict(base, verdict="계산완료", known=True, answer="%d." % value,
                    facts=[{"subject": "%s %s" % (subject, e["item"]), "predicate": "count", "value": str(value),
                            "evidence": []}])
    if typ in ("more", "taller"):
        name = e["entity"] if not wrong else next(c for c in e["candidates"] if c != e["entity"])
        return dict(base, verdict="계산완료", known=True, answer=name + ".")
    if typ == "location":
        place = e["place"] if not wrong else "nowhere"
        return dict(base, verdict="계산완료", known=True, answer=place + ".",
                    facts=[{"subject": e["item"], "predicate": "location", "value": place, "evidence": []}])
    if typ == "yes":
        obj = e["object"] if not wrong else e["object"] + "x"
        return dict(base, verdict="계산완료", known=True, answer="yes.",
                    facts=[{"subject": e["subject"], "predicate": e["relation"], "value": obj, "evidence": []}])
    if typ == "unknown":
        if not wrong:
            return dict(base, verdict="조건부족", known=False, answer="?")
        if e.get("candidates"):
            return dict(base, verdict="계산완료", known=True, answer=e["candidates"][0] + ".")
        return dict(base, verdict="계산완료", known=True, answer="yes.",
                    facts=[{"subject": e["subject"], "predicate": e["relation"], "value": e["object"], "evidence": []}])
    if typ == "hold":
        if not wrong:
            return dict(base, verdict="조건부족", known=False, answer="%s: not stated." % ", ".join(e["names"]))
        return dict(base, verdict="계산완료", known=True, answer="7.",
                    facts=[{"subject": "x", "predicate": "count", "value": "7", "evidence": []}])
    raise ValueError(typ)


def synthesize(problems, mode):
    """An answers file built from the expectations: ``perfect`` or deliberately ``wrong``."""
    assert mode in ("perfect", "wrong")
    answers = {}
    for p in problems:
        rows = []
        for turn in script(p):
            if turn["role"] == "setup":
                rows.append({"phase": "answer", "verdict": "상태기억", "known": False, "answer": "recorded",
                             "facts": [], "state": [], "corrections": [], "evidence": [], "research_calls": 0})
            else:
                q = next(q for q in p["questions"] if q["q"] == turn["ref"])
                rows.append(_perfect(q, wrong=mode == "wrong"))
        answers[p["id"]] = rows
    return answers


def wrong_expectations(problems):
    """An expected-answers file that is wrong everywhere: every expectation changed to another answer."""
    out = {}
    for p in problems:
        rows = []
        for q in p["questions"]:
            e = copy.deepcopy(q["expect"])
            typ = e["type"]
            if typ in ("count", "total"):
                e["value"] += 1
                e.pop("retracted_value", None)
            elif typ in ("more", "taller"):
                e["entity"] = next(c for c in e["candidates"] if c != e["entity"])
            elif typ == "location":
                e["other_places"] = [e["place"]]
                e["place"] = "nowhere"
            elif typ == "yes":
                e = {"type": "unknown", "subject": e["subject"], "relation": e["relation"], "object": e["object"]}
            elif typ == "unknown":
                e = ({"type": "taller", "candidates": e["candidates"], "entity": e["candidates"][0]}
                     if e.get("candidates") else dict(e, type="yes"))
            elif typ == "hold":
                e = {"type": "count", "entity": e["missing"]["entity"], "item": e["missing"].get("item", "x"),
                     "value": 7}
            rows.append(e)
        out[p["id"]] = rows
    return out


# ---------------------------------------------------------------------------
# F2.4 baseline at a revision
# ---------------------------------------------------------------------------
def run_at_revision(rev, dataset=DATASET):
    """Export ``rev`` without git metadata and play the problems against that code in a subprocess."""
    with tempfile.TemporaryDirectory(prefix="nai-reasoning-code-") as temporary:
        export = Path(temporary) / "code"
        export.mkdir()
        archive = subprocess.run(["git", "-C", str(ROOT), "archive", rev], check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(export)], input=archive, check=True)
        out = Path(temporary) / "answers.json"
        env = dict(os.environ)
        env.setdefault("KG_ENCODER", "문자")
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "run", "--code-root", str(export),
                        "--answers-out", str(out), "--quiet", "--dataset", str(Path(dataset).resolve())],
                       check=True, env=env, cwd=str(export))
        return json.loads(out.read_text(encoding="utf-8"))


def _meta(code_root, dataset=DATASET):
    frozen = Path(dataset) / FROZEN.name
    meta = {"dataset": str(Path(dataset).resolve().relative_to(ROOT)) if Path(dataset).resolve().is_relative_to(ROOT)
            else str(dataset), "dataset_sha256": tree_hash(dataset),
            "frozen_sha256": frozen_hash(frozen) if frozen.exists() else None,
            "encoder": os.environ.get("KG_ENCODER", "문자"), "entry": "views.kgpack_ui.AppState.turn",
            "runner": "bench/dialogue_gate.py run()", "research": "stubbed; calls counted",
            "python": sys.version.split()[0]}
    try:
        meta["code_commit"] = subprocess.run(["git", "-C", str(code_root), "rev-parse", "HEAD"], check=True,
                                             capture_output=True, text=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        meta["code_commit"] = None
    return meta


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dataset", type=Path, default=DATASET, help="problem directory (default: the frozen set)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", parents=[common])
    p = sub.add_parser("overlap", parents=[common])
    p.add_argument("--rev", help="read a dialogue directory missing on disk at this revision (e.g. a branch)")
    p = sub.add_parser("run", parents=[common])
    p.add_argument("--code-root", default=str(ROOT))
    p.add_argument("--code-rev", help="export this revision and play the problems against it")
    p.add_argument("--answers-out", type=Path)
    p.add_argument("--report-out", type=Path)
    p.add_argument("--quiet", action="store_true")
    p = sub.add_parser("score", parents=[common])
    p.add_argument("answers", type=Path)
    p.add_argument("--expected", type=Path, help="JSON {problem id: [expect per question]} replacing the file's")
    p.add_argument("--report-out", type=Path)
    p = sub.add_parser("digest", aliases=["hash"], parents=[common])
    p.add_argument("--write", action="store_true")
    p = sub.add_parser("baseline", parents=[common])
    p.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    dataset = args.dataset.resolve()
    problems = load(dataset)

    if args.command == "validate":
        issues = validate(problems)
        t = tables(problems)
        print("problems %d  questions %d  %s" % (t["problems"], t["questions"], json.dumps(t["by_language"])))
        print("%-18s %8s %8s %8s %8s" % ("kind", "ko prob", "ko q", "en prob", "en q"))
        for kind, row in t["kinds"].items():
            print("%-18s %8d %8d %8d %8d" % (kind, row["ko"]["problems"], row["ko"]["questions"],
                                             row["en"]["problems"], row["en"]["questions"]))
        print("expectation types:", json.dumps(t["expect_types"]))
        print("problems: %d" % len(issues))
        for item in issues:
            print("  " + item)
        return 1 if issues else 0
    if args.command == "overlap":
        result = overlap(problems, rev=args.rev)
        print("problem sentences %d" % result["sentences"])
        for directory, row in result["checked"].items():
            print("  %-34s %-28s files %d" % (directory, row["source"], row["files"]))
        for directory in result["missing"]:
            print("  %-34s not found (give --rev <branch> to read it from git)" % directory)
        print("overlaps %d" % len(result["overlaps"]))
        for row in result["overlaps"]:
            print("  %(problem)s turn %(turn)d shares a full sentence with %(file)s" % row)
        return 1 if result["overlaps"] or result["missing"] else 0
    if args.command in ("digest", "hash"):
        digest, frozen = tree_hash(dataset), dataset / FROZEN.name
        if args.write:
            label = dataset.relative_to(ROOT).as_posix() if dataset.is_relative_to(ROOT) else str(dataset)
            frozen.write_text("%s  %s\n" % (digest, label), encoding="utf-8")
        print(digest, "frozen" if frozen.exists() and frozen_hash(frozen) == digest else "NOT FROZEN")
        return 0
    expected = None
    if args.command == "score":
        saved = json.loads(args.answers.read_text(encoding="utf-8"))
        answers, meta, out = saved["answers"], saved.get("meta", {}), args.report_out
        if args.expected:
            expected = json.loads(args.expected.read_text(encoding="utf-8"))
            meta = dict(meta, expected_override=str(args.expected))
    elif args.command == "baseline":
        out = REPORT_DIR / "baseline.json"
        if out.exists() and not args.force:
            print("baseline already recorded: %s" % out)
            return 2
        saved = run_at_revision(BASELINE_COMMIT, dataset)
        answers, meta = saved["answers"], saved["meta"]
        meta.update(code_commit=gate._git("rev-parse", BASELINE_COMMIT),
                    rule="main when goal F2 started; code exported with git archive, dataset from this checkout")
    elif args.code_rev:
        saved = run_at_revision(args.code_rev, dataset)
        answers, meta, out = saved["answers"], saved["meta"], args.report_out
        meta["code_commit"] = gate._git("rev-parse", args.code_rev)
    else:
        start = time.perf_counter()
        progress = None if args.quiet else (lambda pid, rows: print(
            pid, " ".join("E" if r.get("error") else gate.status(r)[0] for r in rows), flush=True))
        answers = run(problems, args.code_root, progress)
        meta = _meta(args.code_root, dataset)
        meta["seconds"] = round(time.perf_counter() - start, 1)
        out = args.report_out
        if args.answers_out:
            args.answers_out.write_text(json.dumps({"meta": meta, "answers": answers}, ensure_ascii=False,
                                                   indent=1) + "\n", encoding="utf-8")
            if args.quiet:
                return 0
    report = score(problems, answers, expected, meta)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
