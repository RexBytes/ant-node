#!/usr/bin/env bash
# Per-test coverage capture for ant-node -> stitchgraph-coverage-v1 artifact.
# Wires the scaffold's TEMPLATE step: cargo-llvm-cov instrumentation, one process
# per test, per-test lcov mapped to stitchgraph node ids by line ranges.
# Run inside a sandbox / CI runner. See capture_per_test_coverage.py for details.
#
# Prerequisites:
#   rustup component add llvm-tools
#   cargo install cargo-llvm-cov --locked
#   stitchgraph reindex <repo> --db <repo>/stitchgraph.db   (or set COV_STITCHGRAPH_DB)
#
# Tunables (env): COV_REPO, COV_STITCHGRAPH_DB, COV_WORKDIR, COV_OUT, COV_WORKERS
set -euo pipefail
cd "$(dirname "$0")"
python3 capture_per_test_coverage.py
echo "artifact: ${COV_OUT:-$(dirname "$0")/out/coverage_modes.json}" >&2
