#!/usr/bin/env python3
"""Per-test coverage capture for ant-node -> stitchgraph-coverage-v1.

Implements the TEMPLATE step of stitchgraph's scaffold-coverage rust kit:
  1. build instrumented test binaries via cargo-llvm-cov's env
  2. enumerate tests per binary, run each test in its own process with its
     own LLVM_PROFILE_FILE
  3. llvm-profdata merge + llvm-cov export (lcov) per test
  4. map covered lines -> enclosing function nodes from the stitchgraph db
  5. emit coverage_modes.json ({"format": "stitchgraph-coverage-v1", ...})
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(os.environ.get("COV_REPO", Path(__file__).resolve().parents[2]))
DB = Path(os.environ.get("COV_STITCHGRAPH_DB", REPO / "stitchgraph.db"))
WORK = Path(os.environ.get("COV_WORKDIR", Path(__file__).resolve().parent / "out" / "covwork"))
OUT = Path(os.environ.get("COV_OUT", Path(__file__).resolve().parent / "out" / "coverage_modes.json"))
WORKERS = int(os.environ.get("COV_WORKERS", "4"))

LLVM_BIN = next(Path.home().glob(f".rustup/toolchains/*/lib/rustlib/{os.uname().machine}-unknown-linux-gnu/bin"))
PROFDATA = str(LLVM_BIN / "llvm-profdata")
LLVMCOV = str(LLVM_BIN / "llvm-cov")


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def llvm_cov_env():
    r = sh(["cargo", "llvm-cov", "show-env", "--export-prefix"], cwd=REPO)
    r.check_returncode()
    env = dict(os.environ)
    for line in r.stdout.splitlines():
        m = re.match(r"export ([A-Z_]+)=(.*)$", line.strip())
        if m:
            env[m.group(1)] = m.group(2).strip("'\"")
    return env


def build_binaries(env):
    r = sh(["cargo", "test", "--no-run", "--features", "test-utils", "--message-format=json"], cwd=REPO, env=env)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-4000:])
        raise SystemExit("instrumented build failed")
    bins = []
    for line in r.stdout.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("reason") == "compiler-artifact" and msg.get("profile", {}).get("test") and msg.get("executable"):
            bins.append(msg["executable"])
    return sorted(set(bins))


def list_tests(binary):
    r = sh([binary, "--list", "--format", "terse"])
    tests = []
    for line in r.stdout.splitlines():
        if line.endswith(": test"):
            tests.append(line[: -len(": test")])
    return tests


def load_function_index():
    """(file -> sorted list of (start, end, node_id)) for Function/Method nodes."""
    db = sqlite3.connect(DB)
    idx = {}
    for nid, kind, loc, f, end in db.execute(
        "SELECT id, kind, location, file, end_line FROM nodes WHERE kind IN ('Function','Method')"
    ):
        m = re.match(r".*:(\d+):\d+$", loc)
        if not m:
            continue
        start = int(m.group(1))
        idx.setdefault(f, []).append((start, int(end or start), nid))
    for f in idx:
        idx[f].sort()
    return idx


FUNC_IDX = None


def lcov_to_functions(lcov_text):
    """Covered lines -> smallest enclosing function node ids."""
    funcs = set()
    cur = None
    for line in lcov_text.splitlines():
        if line.startswith("SF:"):
            p = line[3:]
            try:
                cur = str(Path(p).resolve().relative_to(REPO))
            except ValueError:
                cur = None
        elif cur and line.startswith("DA:"):
            ln, hits = line[3:].split(",")[:2]
            if int(hits) > 0:
                best = None
                for start, end, nid in FUNC_IDX.get(cur, ()):
                    if start <= int(ln) <= end:
                        if best is None or (end - start) < (best[1] - best[0]):
                            best = (start, end, nid)
                    elif start > int(ln):
                        break
                if best:
                    funcs.add(best[2])
    return funcs


def run_one(binary, test, i):
    tdir = WORK / f"t{i:04d}"
    tdir.mkdir(parents=True, exist_ok=True)
    praw = tdir / "cov.profraw"
    env = dict(os.environ, LLVM_PROFILE_FILE=str(praw))
    r = sh([binary, "--exact", test, "--test-threads=1", "--quiet"], env=env, cwd=REPO, timeout=600)
    status = "ok" if r.returncode == 0 else "FAIL"
    raws = list(tdir.glob("*.profraw"))
    if not raws:
        return test, status, set()
    pdata = tdir / "cov.profdata"
    sh([PROFDATA, "merge", "-sparse", *map(str, raws), "-o", str(pdata)])
    r2 = sh([LLVMCOV, "export", "--format=lcov", "--object", binary,
             f"--instr-profile={pdata}", "--ignore-filename-regex", r"(registry|rustc|\.cargo)"])
    funcs = lcov_to_functions(r2.stdout)
    for f in raws:
        f.unlink(missing_ok=True)
    pdata.unlink(missing_ok=True)
    return test, status, funcs


def main():
    global FUNC_IDX
    FUNC_IDX = load_function_index()
    env = llvm_cov_env()
    print("building instrumented test binaries...", flush=True)
    bins = build_binaries(env)
    print(f"{len(bins)} test binaries", flush=True)
    jobs = []
    for b in bins:
        for t in list_tests(b):
            jobs.append((b, t))
    print(f"{len(jobs)} tests to run", flush=True)
    results, failures = {}, []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(run_one, b, t, i) for i, (b, t) in enumerate(jobs)]
        for n, fut in enumerate(futs):
            test, status, funcs = fut.result()
            key = f"{Path(jobs[n][0]).name}::{test}"
            results[key] = sorted(funcs)
            if status != "ok":
                failures.append(key)
            if (n + 1) % 50 == 0:
                print(f"{n + 1}/{len(jobs)} done", flush=True)
    OUT.write_text(json.dumps({"format": "stitchgraph-coverage-v1", "tests": results}))
    print(f"wrote {OUT} ({len(results)} tests, {len(failures)} failed)")
    if failures:
        print("failed tests:")
        for f in failures:
            print("  ", f)


if __name__ == "__main__":
    main()
