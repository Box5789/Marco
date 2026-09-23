"""Measure the numbers README.md states, and check that every package has its document.

    python tools/doc_facts.py packages      # packages without a document; prints 0 when complete
    python tools/doc_facts.py counts        # graphs, nodes, edges, code size
    python tools/doc_facts.py runtime       # cold start, turn latency, memory, imported libraries

Every number is measured from the checkout it runs in, and every report starts
with the commit it measured. A package is a directory with ``__init__.py`` under
one of PACKAGE_ROOTS; its document is ``docs/architecture/<dotted.name>.md`` and
must carry the five headings of the architecture template, in order.
"""
import glob
import json
import os
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_ROOTS = ("marco", "mco", "alma", "polo")
DOC_DIR = os.path.join("docs", "architecture")
HEADINGS = ("## Purpose", "## Owns", "## Does not own", "## Depends on", "## Public interface")


def revision():
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = git("status", "--porcelain", "--untracked-files=no")
    return "%s%s" % (git("rev-parse", "--short", "HEAD"), " (tracked files modified)" if dirty else "")


# ---------------------------------------------------------------- packages

def packages():
    found = []
    for top in PACKAGE_ROOTS:
        base = os.path.join(ROOT, top)
        if not os.path.isfile(os.path.join(base, "__init__.py")):
            continue
        for here, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if not d.startswith((".", "__")))
            if "__init__.py" in files:
                found.append(os.path.relpath(here, ROOT).replace(os.sep, "."))
    return found


def doc_problem(name):
    path = os.path.join(ROOT, DOC_DIR, name + ".md")
    if not os.path.isfile(path):
        return "no file %s" % os.path.relpath(path, ROOT)
    lines = [line.rstrip() for line in open(path, encoding="utf-8")]
    at = 0
    for heading in HEADINGS:
        try:
            at = lines.index(heading, at) + 1
        except ValueError:
            return "%s lacks '%s' (or it is out of order)" % (os.path.relpath(path, ROOT), heading)
    return None


def cmd_packages(verbose):
    names = packages()
    missing = [(n, doc_problem(n)) for n in names if doc_problem(n)]
    if verbose:
        print("commit %s, %d packages" % (revision(), len(names)), file=sys.stderr)
        for n in names:
            print("  %-28s %s" % (n, doc_problem(n) or "ok"), file=sys.stderr)
    print(len(missing))
    return 1 if missing else 0


# ---------------------------------------------------------------- counts

def _graph_files():
    return sorted(glob.glob(os.path.join(ROOT, "graphs", "*.kg")))


def cmd_counts():
    sys.path.insert(0, ROOT)
    os.chdir(ROOT)
    import engine
    engine._shared_net = {}          # count what authors wrote, not the shared dictionary net
    concepts = instances = nulls = axioms = arg_edges = net_edges = failed = 0
    for path in _graph_files():
        try:
            g = engine.read_kg(path)
        except Exception:
            failed += 1
            continue
        concepts += len(g["공통층"]) - len(g["공리"])
        axioms += len(g["공리"])
        instances += len(g["사례층"])
        nulls += len(g["무관층"])
        arg_edges += len(g["엣지"])
        net_edges += len(g.get("개념엣지", []))
    root_py = sorted(glob.glob(os.path.join(ROOT, "*.py")))
    lines = lambda paths: sum(sum(1 for _ in open(p, encoding="utf-8")) for p in paths)
    pkg_py = [p for top in PACKAGE_ROOTS for p in glob.glob(os.path.join(ROOT, top, "**", "*.py"), recursive=True)]
    rows = [
        ("commit", revision()),
        ("graph files (graphs/*.kg)", len(_graph_files())),
        ("graph files that fail to parse", failed),
        ("nodes: concepts", concepts),
        ("nodes: axioms", axioms),
        ("nodes: instances", instances),
        ("nodes: total (concepts + axioms + instances)", concepts + axioms + instances),
        ("null-class entries ([무관])", nulls),
        ("argument edges ([논증])", arg_edges),
        ("concept-network edges ([개념망], authored)", net_edges),
        ("root .py files", len(root_py)),
        ("root .py lines", lines(root_py)),
        ("engine.py lines", lines([os.path.join(ROOT, "engine.py")])),
        ("package .py files (%s)" % ", ".join(PACKAGE_ROOTS), len(pkg_py)),
        ("package .py lines", lines(pkg_py)),
        ("test files (tests/test_*.py)", len(glob.glob(os.path.join(ROOT, "tests", "test_*.py")))),
    ]
    for key, value in rows:
        print("%-46s %s" % (key, value))
    return 0


# ---------------------------------------------------------------- runtime

def _questions():
    """A fixed question set: the 24 out-of-domain questions of the routing
    benchmark, plus the first instance phrasing of every 20th graph file."""
    out = json.load(open(os.path.join(ROOT, "data", "benchmarks", "라우팅_밖.json"), encoding="utf-8"))
    import engine
    inside = []
    for path in _graph_files()[::20]:
        g = engine.read_kg(path)
        for phrasings in g["사례층"].values():
            if phrasings:
                inside.append(phrasings[0])
                break
    return list(out) + inside


def _probe():
    import resource
    before = {m.split(".")[0] for m in list(sys.modules)}      # interpreter start-up, site hooks
    sys.path.insert(0, ROOT)
    os.chdir(ROOT)
    start = time.perf_counter()
    import engine
    import_ms = (time.perf_counter() - start) * 1000
    start = time.perf_counter()
    index = engine._index_slots["색인"] = engine.graph_index()      # the router's own cache slot
    index_ms = (time.perf_counter() - start) * 1000
    questions = _questions()
    times = []
    for q in questions:
        start = time.perf_counter()
        engine.answer(q)
        times.append((time.perf_counter() - start) * 1000)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_mb = rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024
    stdlib = set(sys.stdlib_module_names)
    local = {os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(ROOT, "*.py"))}
    local |= set(PACKAGE_ROOTS)
    third = sorted({m.split(".")[0] for m in list(sys.modules)} - before - stdlib - local)
    third = [m for m in third if not m.startswith("_")]
    first_ms, times = times[0], times[1:]      # the first turn also builds what the engine loads lazily
    times_sorted = sorted(times)
    print(json.dumps({
        "import_engine_ms": round(import_ms, 1),
        "graph_index_ms": round(index_ms, 1),
        "router_index_graphs": len(index["공통층"]),
        "questions": len(times) + 1,
        "first_turn_ms": round(first_ms, 1),
        "turn_ms_median": round(statistics.median(times), 1),
        "turn_ms_p95": round(times_sorted[int(0.95 * (len(times_sorted) - 1))], 1),
        "turn_ms_max": round(times_sorted[-1], 1),
        "max_rss_mb": round(rss_mb, 1),
        "torch_imported": "torch" in sys.modules,
        "third_party_modules": third,
    }))


def cmd_runtime():
    env = dict(os.environ, KG_ENCODER=os.environ.get("KG_ENCODER", "문자"))
    run = lambda: subprocess.run([sys.executable, os.path.abspath(__file__), "_probe"],
                                 cwd=ROOT, env=env, capture_output=True, text=True)
    first = run()                    # warms the on-disk index and vector caches; not reported
    second = run()
    for done in (first, second):
        if done.returncode:
            sys.stderr.write(done.stderr)
            return done.returncode
    warm = json.loads(second.stdout.strip().splitlines()[-1])
    print("%-46s %s" % ("commit", revision()))
    print("%-46s %s" % ("encoder (KG_ENCODER)", env["KG_ENCODER"]))
    print("%-46s %s" % ("python", sys.version.split()[0]))
    print("%-46s %s" % ("graphs in the router index", warm["router_index_graphs"]))
    print("%-46s %s" % ("questions timed (engine.answer)", warm["questions"]))
    print("%-46s %s" % ("start-up: import engine ms", warm["import_engine_ms"]))
    print("%-46s %s" % ("start-up: build index from cache ms", warm["graph_index_ms"]))
    print("%-46s %s" % ("first turn ms (engine loads the rest lazily)", warm["first_turn_ms"]))
    print("%-46s %s" % ("turn latency median ms (turns 2..n)", warm["turn_ms_median"]))
    print("%-46s %s" % ("turn latency p95 ms (turns 2..n)", warm["turn_ms_p95"]))
    print("%-46s %s" % ("turn latency max ms (turns 2..n)", warm["turn_ms_max"]))
    print("%-46s %s" % ("peak resident memory MB", warm["max_rss_mb"]))
    print("%-46s %s" % ("torch imported", warm["torch_imported"]))
    print("%-46s %s" % ("third-party modules the engine loaded", ", ".join(warm["third_party_modules"]) or "none"))
    return 0


def main(argv):
    if not argv or argv[0] not in ("packages", "counts", "runtime", "_probe"):
        print(__doc__)
        return 2
    if argv[0] == "packages":
        return cmd_packages("-v" in argv)
    if argv[0] == "counts":
        return cmd_counts()
    if argv[0] == "runtime":
        return cmd_runtime()
    _probe()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
