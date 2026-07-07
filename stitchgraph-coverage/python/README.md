# stitchgraph per-test coverage kit — python

`find_modes` needs a **per-test coverage artifact**: which test executed which function. Producing it
means *running this project's test suite*, which runs arbitrary code — so do it in a **sandbox**, never
on your host. This kit gives three interchangeable ways to produce the canonical artifact
`coverage_modes.json`. stitchgraph did NOT run anything to make this kit — you run it, jailed.

Coverage tool for python: **coverage.py (`pytest --cov --cov-context=test`)**

## Option 1 — Docker (most isolated; recommended)
```
docker compose run --rm coverage        # no network, non-root, read-only rootfs, capped
# → ./out/coverage_modes.json
```

## Option 2 — plain shell (if you already have a sandbox / CI runner / devcontainer)
```
bash run_coverage.sh                     # → coverage_modes.json
```

## Option 3 — CI (GitHub Actions)
```yaml
- run: bash run_coverage.sh
- uses: actions/upload-artifact@v4
  with: { name: coverage_modes, path: coverage_modes.json }
```

## Then, back on your machine (no code execution — pure math):
```
stitchgraph find-modes coverage_modes.json      # behavioural modes, dimensionality, minimal test set
```

## Canonical artifact format (`stitchgraph-coverage-v1`)
```json
{
  "format": "stitchgraph-coverage-v1",
  "tests": {
    "tests/test_x.py::test_a": ["src/pkg/mod.py::func1", "src/pkg/mod.py::Class.method"],
    "...": ["..."]
  }
}
```
Keys = test ids; values = the functions that test executed (ids like `path::qualified.name`, matching
stitchgraph's node ids so `find_modes` can label modes by module). Any per-test coverage tool that can
emit this works. Keys are opaque labels — some tools suffix a phase (coverage.py's `--cov-context=test`
emits e.g. `tests/test_x.py::test_a|run`); that is fine, only the function-id *values* must match node ids.
