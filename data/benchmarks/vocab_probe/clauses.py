"""Multi-clause statement probe (goal G3.2): two or three facts in one statement.

200 statements (100 per language) generated from the probe's word lists
(``words.json``: names and item nouns never met by a rule) by the grammar below.
They vary the join (comma, and, a comma and 'and', a list of three, gapping of
the verb, two sentences in one turn, a relative clause, the Korean -고, -며,
그리고, -는데 and the shared predicate after commas), the clause order (which
holder comes first; a count before the transfer it feeds) and the holder count
(two or three; one holder with two items). Every fact the statement carries is
listed; a statement passes when it is recorded and the conversation state is
exactly those facts, nothing unread.

    python data/benchmarks/vocab_probe/clauses.py build     # writes clauses.json
    python data/benchmarks/vocab_probe/clauses.py run [--failures N]
"""
import argparse
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SEED = 20260925
PER_LANGUAGE = 100
EN_JOINS = ["and", "and_elided", "comma", "comma_and", "list3", "gapping", "two_sentences", "two_items",
            "counts_then_transfer", "relative"]
KO_JOINS = ["go", "go_item", "comma_shared", "myeo", "geurigo", "list3", "copula_go", "two_items",
            "neunde_transfer", "relative"]


def _batchim(word):
    ch = word[-1]
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28
    return 0 if ch.lower() in "aeiouy" else 1


def _p(word, pair):
    return word + (pair[0] if _batchim(word) else pair[1])


def _plural(word):
    """The probe generator's own plural (``build.py``), loaded by path: the
    repository root has a ``build`` module of its own."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("vocab_probe_build", HERE / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.plural(word)


def _en(join, people, item, other, amounts, order):
    """(statement, {subject: count})."""
    many, second_many = _plural(item), _plural(other)
    a, b, c = people
    x, y, z = amounts
    if order:
        (a, x), (b, y) = (b, y), (a, x)
    if join == "and":
        return "%s has %d %s and %s has %d %s." % (a, x, many, b, y, many), {(a, many): x, (b, many): y}
    if join == "and_elided":
        return "%s has %d %s and %s has %d." % (a, x, many, b, y), {(a, many): x, (b, many): y}
    if join == "comma":
        return "%s has %d %s, %s has %d." % (a, x, many, b, y), {(a, many): x, (b, many): y}
    if join == "comma_and":
        return "%s has %d %s, and %s has %d." % (a, x, many, b, y), {(a, many): x, (b, many): y}
    if join == "list3":
        return ("%s has %d %s, %s has %d, and %s has %d." % (a, x, many, b, y, c, z),
                {(a, many): x, (b, many): y, (c, many): z})
    if join == "gapping":
        return "%s has %d %s and %s %d." % (a, x, many, b, y), {(a, many): x, (b, many): y}
    if join == "two_sentences":
        return "%s has %d %s. %s has %d." % (a, x, many, b, y), {(a, many): x, (b, many): y}
    if join == "two_items":
        if order:
            return ("%s has %d %s and %d %s." % (a, y, second_many, x, many),
                    {(a, second_many): y, (a, many): x})
        return "%s has %d %s and %d %s." % (a, x, many, y, second_many), {(a, many): x, (a, second_many): y}
    k = min(z, x - 1)
    if join == "counts_then_transfer":
        return ("%s has %d %s and %s has %d, and %s gave %s %d." % (a, x, many, b, y, a, b, k),
                {(a, many): x - k, (b, many): y + k})
    # relative: the giver's count in a relative clause, the receiver's before it
    return ("%s has %d %s, and %s, who has %d, gave %s %d." % (b, y, many, a, x, b, k),
            {(a, many): x - k, (b, many): y + k})


def _ko(join, people, item, other, amounts, order):
    a, b, c = people
    x, y, z = amounts
    if order:
        (a, x), (b, y) = (b, y), (a, x)
    s, t = _p(item, ("이", "가")), _p(other, ("이", "가"))
    top = lambda name: _p(name, ("은", "는"))       # noqa: E731
    if join == "go":
        return "%s %s %d개 있고 %s %d개 있어." % (top(a), s, x, top(b), y), {(a, item): x, (b, item): y}
    if join == "go_item":
        return "%s %s %d개 있고 %s %s %d개 있어." % (top(a), s, x, top(b), s, y), {(a, item): x, (b, item): y}
    if join == "comma_shared":
        return "%s %s %d개, %s %d개 있어." % (top(a), s, x, top(b), y), {(a, item): x, (b, item): y}
    if join == "myeo":
        return "%s %s %d개 있으며 %s %d개 있다." % (top(a), s, x, top(b), y), {(a, item): x, (b, item): y}
    if join == "geurigo":
        return "%s %s %d개 있어. 그리고 %s %d개 있어." % (top(a), s, x, top(b), y), {(a, item): x, (b, item): y}
    if join == "list3":
        return ("%s %s %d개, %s %d개, %s %d개 있어." % (top(a), s, x, top(b), y, top(c), z),
                {(a, item): x, (b, item): y, (c, item): z})
    if join == "copula_go":
        return ("%s의 %s %d개이고, %s의 %s %d개야." % (a, top(item), x, b, top(item), y),
                {(a, item): x, (b, item): y})
    if join == "two_items":
        if order:
            return "%s %s %d개, %s %d개 있어." % (top(a), t, y, s, x), {(a, other): y, (a, item): x}
        return "%s %s %d개, %s %d개 있어." % (top(a), s, x, t, y), {(a, item): x, (a, other): y}
    k = min(z, x - 1)
    if join == "neunde_transfer":
        return ("%s %s %d개, %s %d개 있었는데 %s %s에게 %s %d개를 줬어." % (top(a), s, x, top(b), y, _p(a, ("이", "가")),
                                                              b, item, k),
                {(a, item): x - k, (b, item): y + k})
    # relative: the giver described by a relative clause
    return ("%s %s %d개 있고, %s %d개 가진 %s %s에게 %d개를 줬어." % (top(b), s, y, _p(item, ("을", "를")), x,
                                                         _p(a, ("이", "가")), b, k),
            {(a, item): x - k, (b, item): y + k})


def generate():
    words = json.loads((HERE / "words.json").read_text(encoding="utf-8"))
    rng = random.Random(SEED)
    cases = []
    for language, joins, grammar in (("en", EN_JOINS, _en), ("ko", KO_JOINS, _ko)):
        names = [row["name"] for row in words["names"] if (row["script"] == "latin") == (language == "en")]
        items = [row["en" if language == "en" else "ko"] for row in words["items"]]
        for index in range(PER_LANGUAGE):
            join = joins[index % len(joins)]
            order = (index // len(joins)) % 2
            people = rng.sample(names, 3)
            item, other = rng.sample(items, 2)
            while True:
                amounts = [rng.randint(2, 9) for _ in range(3)]
                if len(set(amounts)) == 3:
                    break
            statement, facts = grammar(join, people, item, other, amounts, order)
            cases.append({"language": language, "join": join, "order": order,
                          "holders": len({holder for holder, _item in facts}), "statement": statement,
                          "facts": [{"holder": h, "item": i, "count": n} for (h, i), n in facts.items()]})
    return cases


def run(cases):
    """Each statement in its own conversation, through the UI turn handler; the state it leaves."""
    import tempfile
    from unittest.mock import patch
    sys.path.insert(0, str(ROOT))
    import bench.dialogue_gate as gate
    kgpack, ConversationStore, AppState = gate._import_code(ROOT)
    out = []
    with tempfile.TemporaryDirectory(prefix="nai-clause-probe-") as temporary:
        folder = Path(temporary)
        packs = {}
        for code, style in gate.LANGUAGES.items():
            pack = folder / ("probe-%s.kgpack" % code)
            kgpack.write_pack(pack, [ROOT / "graphs/graph_일상추론.kg"] + kgpack.model_files(ROOT), root=ROOT,
                              language="styles/%s.json" % style)
            packs[code] = pack
        for index, case in enumerate(cases):
            home = folder / ("c%03d" % index)
            app = AppState(packs[case["language"]], overlay_root=home / "overlay")
            app.conversations = ConversationStore(home / "conversations.json")
            chat = app.conversations.create_chat()["id"]
            offline = {"query": case["statement"], "sources": [], "verified": False}
            with patch.object(app.goals, "research", return_value=offline):
                result = app.turn(case["statement"], "clauseprobe_%03d" % index, conversation_id=chat)
            observation = gate.observe(result, 0, 0)
            context = app.reasoning_contexts.get("chat_" + chat)
            state = {tuple(row[:2]): row[2] for row in (context.current_state() if context else [])}
            got = {subject: value for (subject, predicate), value in state.items() if predicate == "count"}
            want = {"%s %s" % (f["holder"], f["item"]): str(f["count"]) for f in case["facts"]}
            ok = gate.status(observation) == "observed" and got == want
            out.append({**case, "pass": ok, "status": gate.status(observation), "state": got,
                        "reply": observation.get("answer")})
    return out


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["build", "run", "check"])
    parser.add_argument("--failures", type=int, default=0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.command == "build":
        cases = generate()
        (HERE / "clauses.json").write_text(json.dumps({"seed": SEED, "cases": cases}, ensure_ascii=False, indent=1)
                                           + "\n", encoding="utf-8")
        print("statements", len(cases))
        return 0
    cases = json.loads((HERE / "clauses.json").read_text(encoding="utf-8"))["cases"]
    if args.command == "check":
        same = cases == generate()
        print("clauses.json matches its generator:", same)
        return 0 if same else 1
    results = run(cases)
    table = {}
    for row in results:
        cell = table.setdefault((row["language"], row["join"]), [0, 0])
        cell[0] += row["pass"]
        cell[1] += 1
    for (language, join), (passed, n) in sorted(table.items()):
        print("%s %-22s %3d/%d" % (language, join, passed, n))
    total = sum(row["pass"] for row in results)
    print("total %d/%d = %.1f%%" % (total, len(results), 100.0 * total / len(results)))
    for row in [r for r in results if not r["pass"]][:args.failures]:
        print(row["language"], row["join"], row["status"], "|", row["statement"], "|", row["state"], "|",
              (row["reply"] or "")[:100])
    if args.out:
        args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
