# -*- coding: utf-8 -*-
"""Measure the import graph of this repository. Reads code; changes nothing.

    python tools/import_graph.py                 # HEAD, read straight from git
    python tools/import_graph.py --rev main      # any revision, no checkout
    python tools/import_graph.py --root DIR      # a directory on disk instead
    python tools/import_graph.py --json          # machine-readable, for phase gates
    python tools/import_graph.py --uses engine   # which names each importer takes from engine
    python tools/import_graph.py --targets docs/architecture/target-map.json
                                                 # one row per root file? upward edges once moved?

A *module* is one .py file. A *unit* is a root-level module (each root file is
its own unit) or a top-level directory (`bench`, `tests`, `views`, ...). The
report gives, per unit, edges and in/out degree, and counts import cycles at
both levels. Cycles are counted over edges that run when a module is used
(`top`, `lazy`, `dynamic`) and, separately, over `top` alone — the only edges
that can break at import time.

Edge kinds, from where the import statement sits:
    top     module body or class body — runs when the module is imported
    lazy    inside a function — runs only when the function is called
    main    under `if __name__ == "__main__":` — runs only when the file is a script
    typing  under `if TYPE_CHECKING:` — never runs
    dynamic importlib.import_module("literal") / __import__("literal")
Pack-declared components (`"module:member"` strings in styles/ and axioms/
JSON, loaded by importlib at runtime) are listed separately; they are data, not
code, and are not counted as edges.

Name resolution follows how the repository runs: the root is on sys.path
(conftest.py, and scripts insert it), and a script inside a directory also sees
its own directory first. Relative imports resolve against their package.
"""
import argparse
import ast
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "env", ".mypy_cache", ".pytest_cache"}
PACK_DIRS = ("styles/", "axioms/")
SPEC = re.compile(r'"([A-Za-z_][A-Za-z0-9_.]*):([A-Za-z_][A-Za-z0-9_]*)"')


# ---------------------------------------------------------------- sources

def git_files(rev, root):
    out = subprocess.run(["git", "-C", root, "ls-tree", "-r", "-z", "--name-only", rev],
                         check=True, capture_output=True).stdout
    paths = [p.decode("utf-8") for p in out.split(b"\0") if p]
    wanted = [p for p in paths if p.endswith(".py")
              or (p.endswith(".json") and p.startswith(PACK_DIRS))]
    proc = subprocess.Popen(["git", "-C", root, "cat-file", "--batch"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    request = "".join(f"{rev}:{p}\n" for p in wanted).encode("utf-8")
    data, _ = proc.communicate(request)
    files, pos = {}, 0
    for path in wanted:
        end = data.index(b"\n", pos)
        header = data[pos:end].split()
        size = int(header[2])
        files[path] = data[end + 1:end + 1 + size].decode("utf-8", errors="replace")
        pos = end + 1 + size + 1
    return files


def disk_files(root):
    files = {}
    for here, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for name in names:
            path = os.path.relpath(os.path.join(here, name), root).replace(os.sep, "/")
            if name.endswith(".py") or (name.endswith(".json") and path.startswith(PACK_DIRS)):
                with open(os.path.join(here, name), encoding="utf-8", errors="replace") as f:
                    files[path] = f.read()
    return files


# ---------------------------------------------------------------- modules

def module_name(path):
    parts = path[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def unit_of(module):
    return module.split(".")[0]


class Index:
    def __init__(self, paths):
        self.path_of = {module_name(p): p for p in paths}
        self.path_inserted = []
        self.modules = set(self.path_of)
        self.packages = {module_name(p) for p in paths if p.endswith("/__init__.py")}
        # a plain directory with .py files is importable as a namespace package
        self.namespaces = {".".join(p.split("/")[:i]) for p in paths
                           for i in range(1, p.count("/") + 1)}

    def exists(self, name):
        return name in self.modules or name in self.namespaces

    def resolve(self, importer, name, members=()):
        """Internal targets of one import statement, or [] when it is external."""
        path = self.path_of[importer]
        directory = path.rsplit("/", 1)[0] if "/" in path else ""
        bases = [name]
        if directory and not self._in_package(importer):
            bases.insert(0, directory.replace("/", ".") + "." + name)  # script sees its own dir
        if not any(self.exists(b) for b in bases):
            # a script that did sys.path.insert(0, ROOT / "bench"): one unique match in a plain dir
            head = name.split(".")[0]
            found = [m for m in self.modules if m.count(".") == 1 and m.endswith("." + head)
                     and m.split(".")[0] not in self.packages]
            if len(found) == 1:
                bases.append(found[0] + name[len(head):])
                self.path_inserted.append(f"{path}: {name} -> {found[0]}")
        for base in bases:
            if not self.exists(base):
                continue
            targets = []
            for member in members:
                sub = f"{base}.{member}"
                if sub in self.modules:
                    targets.append(sub)
            if base in self.modules and (not members or len(targets) < len(members)):
                targets.append(base)
            return targets or [base]
        return []

    def resolve_relative(self, importer, level, name, members):
        package = importer if importer in self.packages else importer.rsplit(".", 1)[0]
        parts = package.split(".")
        if level > 1:
            parts = parts[:len(parts) - (level - 1)]
        base = ".".join(p for p in parts + ([name] if name else []) if p)
        targets = [f"{base}.{m}" for m in members if f"{base}.{m}" in self.modules]
        if base in self.modules and len(targets) < len(members or [None]):
            targets.append(base)
        return targets

    def _in_package(self, module):
        return module.rsplit(".", 1)[0] in self.packages if "." in module else False


# ---------------------------------------------------------------- statements

def is_type_checking(test):
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or \
           (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")


def is_main_guard(test):
    return (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
            and test.left.id == "__name__" and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value == "__main__")


def imports_in(tree):
    """Yield (kind, level, name, members, line) for every import in a module."""
    def walk(node, kind):
        for child in ast.iter_child_nodes(node):
            child_kind = kind
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) and kind == "top":
                child_kind = "lazy"
            if isinstance(child, ast.If) and kind == "top" and is_main_guard(child.test):
                for sub in child.body:
                    yield from walk_one(sub, "main")
                for sub in child.orelse:
                    yield from walk_one(sub, kind)
                continue
            if isinstance(child, ast.If) and is_type_checking(child.test):
                for sub in child.body:
                    yield from walk_one(sub, "typing")
                for sub in child.orelse:
                    yield from walk_one(sub, kind)
                continue
            yield from walk_one(child, child_kind)

    def walk_one(node, kind):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield kind, 0, alias.name, (), node.lineno
        elif isinstance(node, ast.ImportFrom):
            yield kind, node.level, node.module or "", tuple(a.name for a in node.names), node.lineno
        elif isinstance(node, ast.Call):
            literal = node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if literal and called in ("import_module", "__import__"):
                yield "dynamic", 0, node.args[0].value, (), node.lineno
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) and kind in ("top", "main"):
            kind = "lazy"
        yield from walk(node, kind)

    yield from walk(tree, "top")


# ---------------------------------------------------------------- graph

def build(files):
    paths = sorted(p for p in files if p.endswith(".py"))
    index = Index(paths)
    edges = {}           # (src, dst) -> strongest kind
    unresolved = []      # dynamic imports with a literal name that match nothing
    external = defaultdict(set)
    parse_errors = []
    rank = {"top": 0, "dynamic": 1, "lazy": 2, "main": 3, "typing": 4}
    for path in paths:
        src = module_name(path)
        try:
            tree = ast.parse(files[path], filename=path)
        except SyntaxError as error:
            parse_errors.append(f"{path}:{error.lineno}: {error.msg}")
            continue
        for kind, level, name, members, line in imports_in(tree):
            if level:
                targets = index.resolve_relative(src, level, name, members)
            else:
                targets = index.resolve(src, name, members)
            if not targets:
                if kind == "dynamic" and name.split(".")[0] not in sys.stdlib_module_names:
                    unresolved.append(f"{path}:{line}: import_module({name!r})")
                elif not level:
                    external[unit_of(src)].add(name.split(".")[0])
                continue
            for dst in targets:
                if dst == src:
                    continue
                old = edges.get((src, dst))
                if old is None or rank[kind] < rank[old]:
                    edges[(src, dst)] = kind
    pack = []
    for path in sorted(p for p in files if p.endswith(".json")):
        for match in SPEC.finditer(files[path]):
            if index.exists(match.group(1)):
                pack.append((path, match.group(1), match.group(2)))
    return index, edges, unresolved, external, parse_errors, pack


def sccs(nodes, adjacency):
    """Tarjan, iterative. Returns components with more than one node or a self-loop."""
    counter, stack, on, low, num, found = [0], [], set(), {}, {}, []
    for start in sorted(nodes):
        if start in num:
            continue
        work = [(start, iter(sorted(adjacency.get(start, ()))))]
        num[start] = low[start] = counter[0]; counter[0] += 1
        stack.append(start); on.add(start)
        while work:
            node, it = work[-1]
            advanced = False
            for nxt in it:
                if nxt not in num:
                    num[nxt] = low[nxt] = counter[0]; counter[0] += 1
                    stack.append(nxt); on.add(nxt)
                    work.append((nxt, iter(sorted(adjacency.get(nxt, ())))))
                    advanced = True
                    break
                if nxt in on:
                    low[node] = min(low[node], num[nxt])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == num[node]:
                component = []
                while True:
                    top = stack.pop(); on.discard(top); component.append(top)
                    if top == node:
                        break
                if len(component) > 1 or node in adjacency.get(node, ()):
                    found.append(sorted(component))
    return sorted(found, key=lambda c: (-len(c), c))


def count_cycles(component, adjacency, cap):
    """Elementary cycles inside one strongly connected component (Johnson), up to cap."""
    nodes = sorted(component)
    members = set(nodes)
    total = 0
    for i, start in enumerate(nodes):
        allowed = set(nodes[i:])
        blocked, blocked_by = set(), defaultdict(set)

        def unblock(node):
            pending = [node]
            while pending:
                n = pending.pop()
                if n in blocked:
                    blocked.discard(n)
                    pending.extend(blocked_by.pop(n, ()))

        path = [start]
        blocked.add(start)
        work = [(start, iter(sorted(n for n in adjacency.get(start, ()) if n in allowed and n in members)))]
        closed = {start: False}
        while work:
            node, it = work[-1]
            moved = False
            for nxt in it:
                if nxt == start:
                    total += 1
                    closed[node] = True
                    if total >= cap:
                        return total, False
                elif nxt not in blocked:
                    path.append(nxt); blocked.add(nxt); closed[nxt] = False
                    work.append((nxt, iter(sorted(n for n in adjacency.get(nxt, ()) if n in allowed and n in members))))
                    moved = True
                    break
            if moved:
                continue
            work.pop(); path.pop()
            if closed[node]:
                unblock(node)
            else:
                for n in adjacency.get(node, ()):
                    if n in allowed and n in members:
                        blocked_by[n].add(node)
            if work:
                parent = work[-1][0]
                closed[parent] = closed[parent] or closed[node]
    return total, True


def cycle_report(nodes, pairs, cap):
    adjacency = defaultdict(set)
    for src, dst in pairs:
        adjacency[src].add(dst)
    components = sccs(nodes, adjacency)
    elementary, exact = 0, True
    for component in components:
        found, complete = count_cycles(component, adjacency, cap - elementary)
        elementary += found
        exact = exact and complete
        if not exact:
            break
    return {"scc_count": len(components),
            "scc_sizes": [len(c) for c in components],
            "sccs": components,
            "elementary_cycles": elementary,
            "elementary_exact": exact}


def measure(files, cap):
    index, edges, unresolved, external, parse_errors, pack = build(files)
    modules = sorted(index.modules)
    units = sorted({unit_of(m) for m in modules})
    root_units = sorted(unit_of(m) for m in modules if "." not in m and index.path_of[m].count("/") == 0)
    run_edges = {e for e, k in edges.items() if k in ("top", "dynamic", "lazy")}  # can run when used
    top_edges = {e for e, k in edges.items() if k == "top"}

    unit_edges = defaultdict(lambda: defaultdict(int))
    for (src, dst), kind in edges.items():
        a, b = unit_of(src), unit_of(dst)
        if a != b:
            unit_edges[(a, b)][kind] += 1

    rows = []
    for unit in units:
        out_u = {b for (a, b) in unit_edges if a == unit}
        in_u = {a for (a, b) in unit_edges if b == unit}
        out_m = {d for (s, d) in edges if unit_of(s) == unit and unit_of(d) != unit}
        in_m = {s for (s, d) in edges if unit_of(d) == unit and unit_of(s) != unit}
        rows.append({
            "unit": unit,
            "kind": "root" if unit in root_units else "dir",
            "files": sum(1 for m in modules if unit_of(m) == unit),
            "out_units": len(out_u), "in_units": len(in_u),
            "out_modules": len(out_m), "in_modules": len(in_m),
            "in_tests": len({s for s in in_m if unit_of(s) == "tests"}),
            "in_root": len({s for s in in_m if unit_of(s) in root_units}),
            "lazy_out": sum(1 for (s, d), k in edges.items()
                            if unit_of(s) == unit and unit_of(d) != unit and k == "lazy"),
            "top_out": sum(1 for (s, d), k in edges.items()
                           if unit_of(s) == unit and unit_of(d) != unit and k == "top"),
        })

    root_set = set(root_units)
    root_pairs_all = {(s, d) for (s, d) in run_edges if s in root_set and d in root_set}
    root_pairs_top = {(s, d) for (s, d) in top_edges if s in root_set and d in root_set}
    unit_pairs = {(a, b) for (a, b), kinds in unit_edges.items()
                  if any(k in kinds for k in ("top", "dynamic", "lazy"))}
    unit_pairs_top = {(a, b) for (a, b), kinds in unit_edges.items() if "top" in kinds}
    kinds = defaultdict(int)
    for kind in edges.values():
        kinds[kind] += 1
    return {
        "python_files": len(modules),
        "root_py_files": len(root_units),
        "units": len(units),
        "dir_units": [u for u in units if u not in root_set],
        "module_edges": len(edges),
        "module_edges_by_kind": dict(sorted(kinds.items())),
        "unit_edges": len(unit_edges),
        "root_to_root_edges": {"runtime": len(root_pairs_all), "top": len(root_pairs_top)},
        "cycles": {
            "all_modules_runtime": cycle_report(modules, run_edges, cap),
            "all_modules_top": cycle_report(modules, top_edges, cap),
            "root_modules_runtime": cycle_report(root_units, root_pairs_all, cap),
            "root_modules_top": cycle_report(root_units, root_pairs_top, cap),
            "units_runtime": cycle_report(units, unit_pairs, cap),
            "units_top": cycle_report(units, unit_pairs_top, cap),
        },
        "rows": rows,
        "root_edges": sorted([s, d, edges[(s, d)]] for (s, d) in edges if s in root_set and d in root_set),
        "pack_declared": [list(p) for p in pack],
        "unresolved_dynamic": unresolved,
        "path_inserted": sorted(set(index.path_inserted)),
        "external_by_unit": {u: sorted(n for n in names if n not in sys.stdlib_module_names)
                             for u, names in sorted(external.items())},
        "parse_errors": parse_errors,
    }


def uses(files, target):
    """{importer module: sorted names it takes from `target`} — `from target import x`
    and `alias.x` after `import target [as alias]`, at any depth in the file."""
    index = Index(sorted(p for p in files if p.endswith(".py")))
    found = {}
    for path in sorted(p for p in files if p.endswith(".py")):
        src = module_name(path)
        if src == target:
            continue
        try:
            tree = ast.parse(files[path], filename=path)
        except SyntaxError:
            continue
        names, aliases = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if target in index.resolve(src, alias.name):
                        aliases.add((alias.asname or alias.name).split(".")[0] if alias.asname
                                    else alias.name)
            elif isinstance(node, ast.ImportFrom) and not node.level:
                if target in index.resolve(src, node.module or "", ()):
                    names.update(a.name for a in node.names)
        if aliases:
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    dotted = ast.unparse(node.value)
                    if dotted in aliases:
                        names.add(node.attr)
        if names or aliases:
            found[src] = sorted(names) or ["(module only)"]
    return found


def _top_level_lines(tree):
    """({name: line}, {name: (module, level, member)}) for module-level bindings.
    The second map holds names that only re-bind something imported — `from m
    import x`, `import m as y`, or `x = m.x` — so they are traced to `m`."""
    lines, bound, aliases = {}, {}, {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                name = a.asname or a.name.split(".")[0]
                lines.setdefault(name, node.lineno)
                bound[name] = (a.name if a.asname else name, 0, None)
                aliases[name] = a.name if a.asname else name
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                name = a.asname or a.name
                lines.setdefault(name, node.lineno)
                bound[name] = (node.module or "", node.level, a.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            lines.setdefault(node.name, node.lineno)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)]
            for name in names:
                lines.setdefault(name, node.lineno)
            values = node.value.elts if isinstance(node.value, ast.Tuple) else [node.value]
            if (len(values) == len(names) and values
                    and all(isinstance(v, ast.Attribute) and isinstance(v.value, ast.Name)
                            and v.value.id in aliases for v in values)):
                for name, value in zip(names, values):
                    bound[name] = (aliases[value.value.id], 0, value.attr)
    return lines, bound


def check_targets(files, map_path):
    """Check a target map against the code: one row per root module, and which
    import edges would point to a higher layer once files sit at their targets.
    Nothing is moved; the moved graph is predicted from today's statements.

    `splits` in the map give line ranges of one module that go to different
    targets. An import is then attributed by the line it sits on (source side)
    and by the line that defines each imported name (target side), and calls
    between the parts of one split module are counted as the imports they will
    become."""
    with open(map_path, encoding="utf-8") as f:
        spec = json.load(f)
    layers, modules, splits = spec["layers"], spec["modules"], spec.get("splits", {})
    paths = sorted(p for p in files if p.endswith(".py"))
    index = Index(paths)
    roots = sorted(m for m in index.modules if index.path_of[m].count("/") == 0)
    missing = [m for m in roots if m not in modules]
    tbd = sorted(m for m, t in modules.items() if not t or "TBD" in t.upper())
    extra = sorted(m for m in modules if m not in index.modules)
    trees, defined, rebound = {}, {}, {}
    for path in paths:
        try:
            trees[module_name(path)] = ast.parse(files[path], filename=path)
        except SyntaxError:
            pass
    split_gaps = {}
    for module, ranges in splits.items():
        tree = trees.get(module)
        if tree is None:
            split_gaps[module] = "module not found"
            continue
        defined[module], rebound[module] = _top_level_lines(tree)
        length = files[index.path_of[module]].count("\n")
        covered = sorted((a, b) for a, b, _ in ranges)
        expect, gaps = 1, []
        for a, b in covered:
            if a != expect:
                gaps.append(f"{expect}-{a - 1}" if a > expect else f"overlap at {a}")
            expect = b + 1
        if expect <= length:
            gaps.append(f"{expect}-{length}")
        if gaps:
            split_gaps[module] = gaps

    def primary(module):
        if module in modules:
            return modules[module]
        return module.split(".")[0]          # bench.x -> bench, tests.x -> tests

    def part(module, line):
        for a, b, target in splits.get(module, ()):
            if a <= line <= b:
                return target
        return primary(module)

    def name_target(module, name, depth=0):
        """Target that will own `name` of `module`; None when it is not ours."""
        if name in rebound.get(module, {}) and depth < 5:
            source, level, member = rebound[module][name]
            found = (index.resolve_relative(module, level, source, (member,) if member else ())
                     if level else index.resolve(module, source, (member,) if member else ()))
            if not found:
                return None                    # numpy, re, ... re-bound in this module
            dst = found[0]
            if member and dst.endswith("." + member):
                return primary(dst)
            return name_target(dst, member, depth + 1) if member else primary(dst)
        line = defined.get(module, {}).get(name)
        return part(module, line) if line else primary(module)

    def layer(name):
        best = None
        for prefix, value in layers.items():
            if name == prefix or name.startswith(prefix + "."):
                if best is None or len(prefix) > len(best[0]):
                    best = (prefix, value)
        return best[1] if best else None

    def package(name):
        parts = name.split(".")
        if parts[0] == "marco":
            return ".".join(parts[:2])
        return parts[0]

    edges = {}                                # (target_a, target_b) -> {"kind", "via"}
    rank = {"top": 0, "dynamic": 1, "lazy": 2}

    def add(a, b, kind, via):
        if a == b or kind not in rank:
            return
        old = edges.get((a, b))
        if old is None or rank[kind] < rank[old["kind"]]:
            edges[(a, b)] = {"kind": kind, "via": via}

    for src, tree in trees.items():
        path = index.path_of[src]
        attrs = defaultdict(set)              # alias -> attribute names used
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                attrs[node.value.id].add(node.attr)
        for kind, level, name, members, line in imports_in(tree):
            if level:
                targets = index.resolve_relative(src, level, name, members)
            else:
                targets = index.resolve(src, name, members)
            a = part(src, line)
            for dst in targets:
                if dst == src:
                    continue
                if dst in splits and members and not any(f"{dst}.{m}" in index.modules for m in members):
                    names = members
                elif dst in splits:
                    alias = name.split(".")[0]
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for item in node.names:
                                if item.name == name and item.asname:
                                    alias = item.asname
                    names = sorted(attrs.get(alias, ())) or [None]
                else:
                    names = [None]
                for member in names:
                    b = name_target(dst, member) if member else primary(dst)
                    if b is not None:
                        add(a, b, kind, f"{path}:{line} {src} -> {dst}{'.' + member if member else ''}")
        if src in splits:                     # calls between parts become imports
            local = defined[src]
            for node in tree.body:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue                  # counted above as real imports
                a = part(src, node.lineno)
                lazy = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Name) and sub.id in local and isinstance(sub.ctx, ast.Load):
                        b = name_target(src, sub.id)
                        if b is not None:
                            add(a, b, "lazy" if lazy else "top",
                                f"{path}:{getattr(sub, 'lineno', node.lineno)} {src}.{sub.id} (inside {src})")

    unknown = sorted({t for pair in edges for t in pair if layer(t) is None}
                     | {primary(m) for m in index.modules if layer(primary(m)) is None})
    upward = []
    for (a, b), info in sorted(edges.items()):
        la, lb = layer(a), layer(b)
        if la is not None and lb is not None and lb > la:
            upward.append({"target_from": a, "target_to": b, "layers": [la, lb],
                           "kind": info["kind"], "via": info["via"]})
    pairs = {(package(a), package(b)) for a, b in edges if package(a) != package(b)}
    packages = sorted({package(t) for pair in edges for t in pair})
    remaining = sorted(m for m in roots if primary(m).startswith("root."))
    return {"map": map_path, "root_modules": len(roots), "rows": sum(1 for m in modules if m in roots),
            "missing_rows": missing, "tbd_rows": tbd, "extra_rows": extra,
            "unknown_layer": unknown, "split_gaps": split_gaps,
            "target_edges": len(edges), "upward_edges": upward,
            "upward_top": sum(1 for e in upward if e["kind"] == "top"),
            "package_cycles": cycle_report(packages, pairs, 100000),
            "root_files_after_phase5": remaining}


def print_targets(result):
    print(f"target map: {result['map']}")
    print(f"root modules: {result['root_modules']}  rows: {result['rows']}  "
          f"missing: {len(result['missing_rows'])}  TBD: {len(result['tbd_rows'])}  "
          f"extra: {len(result['extra_rows'])}  no layer: {len(result['unknown_layer'])}")
    for name in ("missing_rows", "tbd_rows", "extra_rows", "unknown_layer"):
        for item in result[name]:
            print(f"  {name}: {item}")
    for module, gaps in result["split_gaps"].items():
        print(f"  split does not cover {module}: {gaps}")
    upward = result["upward_edges"]
    print(f"target-level edges: {result['target_edges']}  "
          f"upward: {len(upward)} (top-level {result['upward_top']})")
    for e in upward:
        print(f"  {e['target_from']} (L{e['layers'][0]}) -> {e['target_to']} (L{e['layers'][1]}) "
              f"[{e['kind']}]  e.g. {e['via']}")
    cycles = result["package_cycles"]
    print(f"package-level cycles after move: SCCs {cycles['scc_count']} "
          f"sizes {cycles['scc_sizes']} elementary {cycles['elementary_cycles']}")
    for component in cycles["sccs"]:
        print(f"  SCC: {' '.join(component)}")
    print(f"root .py files left after Phase 5: {len(result['root_files_after_phase5'])} "
          f"({' '.join(result['root_files_after_phase5'])})")


# ---------------------------------------------------------------- report

def print_report(result, label):
    print(f"source: {label}")
    print(f"python files: {result['python_files']}  root .py: {result['root_py_files']}  "
          f"units: {result['units']} (dirs: {', '.join(result['dir_units'])})")
    print(f"module edges: {result['module_edges']} {result['module_edges_by_kind']}  "
          f"unit edges: {result['unit_edges']}  "
          f"root->root: runtime {result['root_to_root_edges']['runtime']}, top {result['root_to_root_edges']['top']}")
    print()
    print("cycles                  SCCs  sizes                      elementary")
    for name, report in result["cycles"].items():
        count = report["elementary_cycles"]
        shown = f"{count}" if report["elementary_exact"] else f">={count} (cap)"
        sizes = ",".join(map(str, report["scc_sizes"])) or "-"
        print(f"  {name:22s}{report['scc_count']:4d}  {sizes[:26]:26s} {shown}")
    print()
    header = ("unit", "kind", "files", "out_u", "in_u", "out_m", "in_m", "in_root", "in_tests", "top_out", "lazy_out")
    print("  ".join(f"{h:>8s}" if i else f"{h:28s}" for i, h in enumerate(header)))
    for row in sorted(result["rows"], key=lambda r: (r["kind"] != "root", -r["in_modules"], r["unit"])):
        values = (row["unit"], row["kind"], row["files"], row["out_units"], row["in_units"],
                  row["out_modules"], row["in_modules"], row["in_root"], row["in_tests"],
                  row["top_out"], row["lazy_out"])
        print("  ".join(f"{str(v):>8s}" if i else f"{str(v):28s}" for i, v in enumerate(values)))
    print()
    for name in ("root_modules_top", "root_modules_runtime"):
        for component in result["cycles"][name]["sccs"]:
            print(f"{name} SCC ({len(component)}): {' '.join(component)}")
    if result["pack_declared"]:
        print()
        for path, module, member in result["pack_declared"]:
            print(f"pack-declared: {path} -> {module}:{member}")
    for line in result["path_inserted"]:
        print(f"resolved via sys.path insert: {line}")
    for line in result["unresolved_dynamic"]:
        print(f"unresolved dynamic: {line}")
    for unit, names in result["external_by_unit"].items():
        if names:
            print(f"third-party ({unit}): {' '.join(names)}")
    for line in result["parse_errors"]:
        print(f"parse error: {line}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--rev", help="git revision to read (default HEAD)")
    parser.add_argument("--root", help="read a directory on disk instead of git")
    parser.add_argument("--json", action="store_true", help="print JSON")
    parser.add_argument("--cap", type=int, default=100000, help="stop counting elementary cycles here")
    parser.add_argument("--uses", metavar="MODULE", help="list the names each importer takes from MODULE")
    parser.add_argument("--targets", metavar="MAP", help="check a target map (docs/architecture/target-map.json)")
    args = parser.parse_args(argv)
    if args.root:
        files, label = disk_files(os.path.abspath(args.root)), os.path.abspath(args.root)
    else:
        rev = args.rev or "HEAD"
        commit = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", rev],
                                check=True, capture_output=True, text=True).stdout.strip()
        files, label = git_files(rev, ROOT), f"{rev} ({commit})"
    if args.targets:
        result = check_targets(files, args.targets)
        result["source"] = label
        if args.json:
            json.dump(result, sys.stdout, ensure_ascii=False, indent=1)
            print()
        else:
            print(f"source: {label}")
            print_targets(result)
        return
    if args.uses:
        found = uses(files, args.uses)
        if args.json:
            json.dump({"source": label, "module": args.uses, "uses": found}, sys.stdout,
                      ensure_ascii=False, indent=1)
            print()
        else:
            print(f"source: {label}  module: {args.uses}  importers: {len(found)}")
            for importer, names in sorted(found.items()):
                print(f"  {importer}: {' '.join(names)}")
        return
    result = measure(files, args.cap)
    if args.json:
        result["source"] = label
        json.dump(result, sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        print_report(result, label)


if __name__ == "__main__":
    main()
