# stitchgraph raw outputs

Raw JSON/markdown artifacts backing [`../stitchgraph-analysis.md`](../stitchgraph-analysis.md).
Generated with stitchgraph 3.50.0 against ant-node @ `a24910d` (v0.14.2).

| File | Command | Confidence |
|---|---|---|
| `report-precise.md` | `stitchgraph report` (rust-analyzer `--lsp --precise`) | 1.00 |
| `find-subsystems.json` | `find-subsystems` | 1.00 |
| `find-chokepoints.json` | `find-chokepoints` | 1.00 |
| `risk.json` | `risk` (git churn × centrality) | 0.70 |
| `coverage_modes.json` | per-test coverage trace — **676 tests, 1,154 functions, 0 skipped** (`cargo-llvm-cov`) | measured |
| `find-modes.json` | **POD run** — 16 behavioural modes | 1.00 |
| `find-core.json` | always-on core functions | 1.00 |
| `find-coupling.json` | hidden runtime coupling (40 pairs) | 1.00 |
| `find-gaps.json` | coverage gaps (515 untested-live, 1 untested-dead) | 1.00 |
| `select.json` | `select-tests PaymentVerifier.verify_payment` (236 tests) | 1.00 |
| `redundant-tests.json` | redundant tests (0) | 1.00 |
| `find-outlier-tests.json` | behavioural outlier tests | 1.00 |
| `test-order.json` | fail-fast test order / minimal cover | 1.00 |
| `runtime-risk.json` | churn × behavioural centrality | 0.70 |

`coverage_modes.json` follows the `stitchgraph-coverage-v1` format
(`{test-id: [executed function-ids]}`) and can be re-fed to any behavioural command via
`--coverage`. See the reproduction section of the main report to regenerate.
