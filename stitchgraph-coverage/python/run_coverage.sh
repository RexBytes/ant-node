#!/usr/bin/env bash
# Run the test suite under per-test coverage, then emit the canonical artifact.
# Intended to run inside the sandbox (Docker service below, or your own jail/CI).
set -euo pipefail
pip install --quiet coverage pytest 2>/dev/null || true
# --cov-context=test tags coverage by the running test id
python -m pytest -p no:cacheprovider -q \
  --cov=. --cov-context=test || true      # keep going even if some tests fail
python to_canonical.py . coverage_modes.json
echo "artifact ready: coverage_modes.json  (copy it out; run: stitchgraph find-modes coverage_modes.json)"
