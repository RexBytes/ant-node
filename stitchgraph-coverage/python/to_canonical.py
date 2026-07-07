#!/usr/bin/env python3
"""Convert coverage.py per-test contexts (.coverage) into the canonical stitchgraph artifact.
Runs INSIDE the sandbox after the suite. Maps covered lines -> functions via AST. No stitchgraph needed."""
import ast, os, json, sys
import coverage

SRC = sys.argv[1] if len(sys.argv) > 1 else "."
OUT = sys.argv[2] if len(sys.argv) > 2 else "coverage_modes.json"

def func_ranges(path):
    """(qualified_name, lineno, end_lineno) for every def, with class/function nesting qualified as
    Class.method / outer.inner — matching stitchgraph node ids (path::Class.method), so distinct
    same-named methods stay distinct instead of collapsing to one id."""
    try: tree = ast.parse(open(path, encoding="utf-8").read())
    except Exception: return []
    out = []
    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = prefix + child.name
                out.append((qual, child.lineno, child.end_lineno or child.lineno))
                visit(child, qual + ".")
            elif isinstance(child, ast.ClassDef):
                visit(child, prefix + child.name + ".")
            else:
                visit(child, prefix)
    visit(tree, "")
    return out

cov = coverage.Coverage(); cov.load(); data = cov.get_data()
tests = {}
for f in data.measured_files():
    if not f.endswith(".py"): continue
    rel = os.path.relpath(f, SRC)      # always relative (SRC='.' → relative to cwd) for clean ids
    ranges = func_ranges(f)
    try: cbl = data.contexts_by_lineno(f)
    except Exception: continue
    for ln, ctxs in cbl.items():
        # attribute the line to the INNERMOST enclosing def only (smallest span), so a line inside
        # a nested function isn't also credited to its parent (which may not have executed).
        best = None
        for (name, lo, hi) in ranges:
            if lo <= ln <= hi and (best is None or (hi - lo) < (best[2] - best[1])):
                best = (name, lo, hi)
        if best is None: continue
        for c in ctxs:
            if "::" not in c: continue          # keep real pytest test ids only
            tests.setdefault(c, set()).add(f"{rel}::{best[0]}")
out = {"format": "stitchgraph-coverage-v1",
       "tests": {t: sorted(fs) for t, fs in tests.items()}}
json.dump(out, open(OUT, "w"), indent=0)
print(f"wrote {OUT}: {len(out['tests'])} tests, "
      f"{len({x for fs in out['tests'].values() for x in fs})} functions")
