# stitchgraph Analysis of ant-node — Full Report

**Tool:** [stitchgraph](https://pypi.org/project/stitchgraph/) 3.50.0 — local-first, read-only code
intelligence. It parses source into a symbol/call graph in SQLite and, when given a runtime coverage
trace, fuses that with the static graph to answer behavioural questions. Every result carries a
confidence (0–1) and provenance (`extracted` = parsed/measured directly, `inferred` = derived,
`ambiguous` = name-based guess). It never executes your code — *you* run the tests; stitchgraph does
the maths.

**Target:** `ant-node` @ `a24910d` (`v0.14.2`) · 94 files · 1942 nodes
(92 Module, 180 Class, 1180 Function, 490 Method) · **0 implementation holes**.

This is the **complete** run — the whole stitchgraph command suite, both halves:

| Half | Needs | Status here |
|---|---|---|
| **Static** (structure, hubs, subsystems, chokepoints, cycles, dead code) | just the parse | ✅ run, and re-run **precise** with `rust-analyzer` (3,649 / 5,526 call sites type-resolved) |
| **Git-risk** (churn × centrality) | git history | ✅ run |
| **Behavioural / POD** (modes, core, coupling, gaps, test selection, outliers) | a per-test coverage trace | ✅ **built and run** — instrumented build + **all 676 tests executed, 0 skipped**, 1,154 functions covered |

---

## How the coverage trace (the hard part) was produced

The behavioural half needs `coverage_modes.json` — *which test executed which function* — which only
exists by building the crate under instrumentation and running the suite once per test:

1. `stitchgraph scaffold-coverage --language rust` → generated a `cargo-llvm-cov` capture kit.
2. Installed `cargo-llvm-cov` + `llvm-tools-preview`; one instrumented build (5m17s).
3. Ran **each of the 676 tests in isolation** with a fresh profraw, exported a per-test JSON report,
   mapped covered lines → stitchgraph node-ids via the kit's `spans.json` (~75 min, per-test timeout guard).
4. Result: **676 / 676 tests captured, 0 skipped**, covering **1,154 distinct functions** (matrix
   density 0.74%). Then `stitchgraph find-modes` and the rest — pure maths, no code execution.

Notably, **every unit/integration test ran green in this sandbox** — the e2e tests that need live
networking/EVM were not reached by the enumeration (they're separate `--ignored`/harness-gated
binaries), so the trace is a clean, complete picture of the *unit + integration* behaviour of the
crate. That is the layer where the load-bearing payment/replication/storage logic lives.

---

## PART A — Static structure (precise, rust-analyzer-resolved)

### A1. Orientation — read these first

Top hubs by transitive fan-in (what the most code depends on):

| Symbol | File | Transitive fan-in |
|---|---|---|
| `Error` | `src/error.rs` | 258 |
| `StorageCommitment` | `src/replication/commitment.rs` | 160 |
| `StorageStats` | `src/storage/lmdb.rs` | 151 |
| `LmdbStorage` | `src/storage/lmdb.rs` | 149 |
| `ReplicationConfig` | `src/replication/config.rs` | 130 |
| `PaidList` | `src/replication/paid_list.rs` | 117 |
| `ReplicationProtocolError` | `src/replication/protocol.rs` | 96 |
| `ReplicationMessage.encode` | `src/replication/protocol.rs` | 94 |

The node's spine is: crate-wide `Error` → **replication** (commitments, paid-list, protocol) on top
of **LMDB storage**, with **payment/verification** on the critical path.

### A2. Subsystems (spectral clustering, confidence 1.00) — 8 natural subsystems

| # | Size | What it is (auto-label → reading) | Dominant dirs |
|---|---|---|---|
| 1 | 504 | Node lifecycle + self-upgrade spine (`NodeBuilder`, `RunningNode`, upgrade monitor) | replication 177, upgrade 135, payment 84 |
| 2 | 385 | Devnet / test harness + payment plumbing it exercises | tests 167, payment 67, storage 55 |
| 3 | 204 | Replication audit & neighbour-sync message handling | replication 182 |
| 4 | 203 | Config + pruning/quorum/paid-list policy (CLI → config) | replication 110, config 28 |
| 5 | 202 | Merkle commitment machinery (`MerkleTree`, subtree, leaf hashing) | replication 186 |
| 6 | 159 | Paid-entry sync & closeness verification | replication 145 |
| 7 | 149 | Payment: quoting, pricing, wallet, verified-cache | payment 115 |
| 8 | 62 | Bootstrap-peers config & startup | replication 26, config 15 |

Replication dominates 5 of 8 clusters — it is by far the largest, most interconnected part of the
node. Payment (#7) is a clean, self-contained cluster. Upgrade is real and non-trivial (135 members).

### A3. Structural chokepoints (confidence 1.00)

70 chokepoints (removal fragments the graph); production-code ones that matter most:
`PaymentVerifier`, `PaymentStatus`, `verify_merkle_candidate_closeness` (`payment/verifier.rs`),
`calculate_price` (`pricing.rs`), `parse_rewards_address` (`wallet.rs`), `VerifiedCache.len`
(`cache.rs`), `prune_paid_entries` (`pruning.rs`), `RunningNode.run` (`node.rs`), and the
`{Storage,Upgrade,Payment,Testnet}Config.default` constructors. **The payment/verification path is
both a hub and a chokepoint — the single most structurally critical production area.**

### A4. Dependency cycles — verdict: **spurious (name-collision artifacts), not real**

8 cycles reported, all `green`. The precise (rust-analyzer) re-index is the tell: even *with* type
resolution they stay low-confidence with almost no confident edges —
`LmdbStorage.try_put ↔ put` (0/2), `ChunkTestFixture.compute_address ↔ LmdbStorage.compute_address`
(0/4, and these are in different modules — a pure name clash), the 57-symbol blob (30/1182 confident)
is the `new()`/`default()`/`build()` constructor-name mesh. **Conclusion: ant-node has no real
import/dependency cycles;** these are method-name collisions the graph can't fully disambiguate.
Nothing to fix.

### A5. Dead code & holes

- **Implementation holes: 0** — nothing references a missing/stubbed symbol.
- **Dead code: exactly 1** — `scripts/testnet/churn-test.sh::get_worker_nodes`
  (**hand-verified:** defined at `churn-test.sh:43`, called nowhere). Trivial cleanup. The behavioural
  pass independently confirmed it as the *only* `untested_dead` function.

For a 40k-line codebase: zero holes and one dead shell helper is an excellent result.

---

## PART B — Git risk (churn × centrality)

| Urgency | File | Churn | Risk score |
|---|---|---:|---:|
| 🟠 orange | `src/payment/verifier.rs` | 52 | 93,028 |
| 🟠 orange | `src/replication/types.rs` | 20 | 58,200 |
| 🟢 | `src/replication/mod.rs` | 49 | 33,467 |
| 🟢 | `src/replication/protocol.rs` | 8 | 25,488 |
| 🟢 | `tests/e2e/testnet.rs` | 19 | 19,836 |
| 🟢 | `src/storage/lmdb.rs` | 9 | 12,096 |
| 🟢 | `src/storage/handler.rs` | 27 | 10,638 |

`payment/verifier.rs` is the **#1 risk hotspot** — highest churn in the codebase (52 touches;
verified: 53 commits touch it) *and* high centrality. `replication/types.rs`/`protocol.rs` are risky
via centrality (everything depends on them) — treat their public shapes as a stable ABI.

**Hidden coupling** (15 pairs co-change with no structural edge). Strongest: `payment/mod.rs ↔
storage/handler.rs` (4), `replication/audit.rs ↔ neighbor_sync.rs` (4), `payment/verifier.rs ↔
tests/e2e/mod.rs` (3). The payment ↔ storage-handler seam is worth a look — the two co-evolve through
the handler that orchestrates both.

---

## PART C — Behavioural analysis (POD) — the coverage-grounded half

*All results below are confidence **1.00, `extracted`** — measured from the real 676-test coverage
matrix, not inferred.*

### C1. POD run — functional modes (`find-modes`, confidence 1.00)

Proper-Orthogonal-Decomposition of the test×function coverage matrix (676 tests × 1,154 functions,
density 0.74%, numpy-dense solver). Each **mode** is an independent *behaviour* the suite exercises —
a coherent bundle of functions that light up together — ranked by **energy** (share of behavioural
variance). **16 modes** were found; they capture 61% of cumulative energy:

| # | Energy | Cum. | Behaviour (label) | Modules |
|---:|---:|---:|---|---|
| 1 | 12.9% | 12.9% | **Payment verification + verified-cache** | `payment/verifier.rs`, `payment/cache.rs` |
| 2 | 10.8% | 23.7% | **Merkle-tree build feeding the verifier** | `replication/commitment.rs`, `payment/verifier.rs`, `cache.rs` |
| 3 | 7.0% | 30.7% | **LMDB storage: sizing, disk-space, put/exists** | `storage/lmdb.rs` |
| 4 | 3.8% | 34.5% | Commitment state / keypair rotation | `replication/commitment_state.rs`, `commitment.rs` |
| 5 | 3.6% | 38.1% | Replication config ↔ quorum, byte-parsing | `replication/quorum.rs`, `config.rs` |
| 6 | 3.3% | 41.4% | Upgrade binary-cache | `upgrade/binary_cache.rs` |
| 7 | 3.2% | 44.6% | Storage put gated by verifier | `storage/lmdb.rs`, `payment/verifier.rs`, `cache.rs` |
| 8 | 3.0% | 47.6% | Config defaults / cache capacity | `config.rs` |
| 9 | 2.5% | 50.1% | Quote generation + storage + metrics | `payment/quote.rs`, `storage/lmdb.rs`, `payment/metrics.rs` |
| 10 | 2.1% | 52.2% | Replication scheduling queues | `replication/scheduling.rs`, `types.rs` |
| 11 | 1.8% | 54.0% | Neighbour-sync peer state | `replication/neighbor_sync.rs`, `types.rs`, `scheduling.rs` |
| 12 | 1.7% | 55.7% | Storage-commitment audit over subtree proofs | `replication/storage_commitment_audit.rs`, `commitment.rs`, `subtree.rs` |
| 13 | 1.5% | 57.2% | Paid-list ↔ verified-cache ↔ pricing | `replication/paid_list.rs`, `payment/cache.rs`, `pricing.rs` |
| 14 | 1.4% | 58.7% | Paid-list construction | `replication/paid_list.rs`, `types.rs`, `cache.rs` |
| 15 | 1.3% | 59.9% | Repair proofs / replica hints | `replication/types.rs` |
| 16 | 1.2% | 61.1% | Merkle subtree proof paths | `replication/commitment.rs`, `subtree.rs` |

**Reading:** the suite's behaviour is genuinely dominated by **payment verification** (modes 1, 2, 7,
9, 13 all involve the verifier/cache) — ~30%+ of all behavioural energy. That is exactly where the
network's "payment is always on" policy concentrates risk, and the tests reflect it. **Storage
(mode 3)** and the **Merkle commitment / audit machinery** (modes 2, 4, 12, 16) are the other two
behavioural pillars. Replication scheduling/sync (modes 10, 11) and upgrade (mode 6) are smaller,
well-separated behaviours. No single mode dominates pathologically (top mode 12.9%) — a sign of a
suite that exercises many independent behaviours rather than re-testing one path.

### C2. Always-on core (`find-core`, confidence 1.00)

Functions executed by the most tests — highest behavioural blast radius; a regression here breaks the
most behaviours:

| Function | Executed by (tests) |
|---|---:|
| `payment/cache.rs::VerifiedCache.with_capacity` | 83 |
| `payment/verifier.rs::EvmVerifierConfig.default` | 76 |
| `payment/verifier.rs::PaymentVerifier.new` | 74 |
| `payment/verifier.rs::PaymentVerifier.check_payment_required` | 55 |
| `payment/cache.rs::VerifiedCache.contains_client_put_verified` | 54 |
| `replication/commitment.rs::MerkleTree.build` | 53 |
| `payment/verifier.rs::PaymentVerifier.verify_payment(_inner)` | 51 |
| `replication/commitment.rs::leaf_hash` / `MerkleTree.root` | 50 / 48 |

The behavioural core **is** the payment-verifier + verified-cache + Merkle-tree triad. This matches
the static hubs and the POD modes from three independent directions.

### C3. Hidden runtime coupling (`find-coupling`, confidence 1.00) — 40 pairs

Functions that **co-execute in tests but never statically call each other** (implicit dependencies):
- `LmdbStorage.check_disk_space_cached ↔ exists` (30 shared tests) — coupled through `put`.
- `MerkleTree.{key_at, node_at, levels_count} ↔ subtree::build_subtree_proof` (23 shared, cross-file)
  — the Merkle/subtree pair moves as one behaviour despite living in separate modules.
- `quorum::build_evidence ↔ collect_present_sources` (21) — evidence assembly.
- `PaymentVerifier.attach_storage ↔ handler::create_test_protocol_with_reserve` (17, cross-file).

These are the seams where a change on one side silently needs the other — worth an eye during refactors.

### C4. Coverage gaps (`find-gaps`, confidence 1.00)

- **1,154 tested**, **515 untested-live**, **1 untested-dead** (the shell helper), 1,670 functions total.
- The 515 untested-live split into ~295 in scripts/deploy/build tooling and **220 in `src/`** — and
  those 220 are overwhelmingly **entry-point / wiring code the unit suite structurally can't reach**:
  `bin/ant-node/main.rs::main`, `Cli.into_config`, `init_logging`, `platform::disable_app_nap`,
  `NodeConfig::{from_file,to_file,development,testnet}`, client bootstrap. These are exercised by the
  e2e/harness tests (not run here) and by actually launching the node — **not genuine test holes** so
  much as the boundary between unit-testable logic and process wiring. The **highest-value real gap to
  close** would be unit coverage for the `NodeConfig` file round-trip and `Cli.into_config` mapping.

### C5. Test-suite health (`redundant-tests`, `test-order`, `find-outlier-tests`)

- **Redundant tests: 0.** No two tests share an identical coverage profile. For 676 tests that's
  remarkable suite hygiene — nothing is trivially deletable as a duplicate.
- **Fail-fast order / minimal cover: all 676.** Every test contributes at least one function no
  earlier test reached — i.e. the *minimal covering set is the whole suite*; there is no fat prefix
  that covers everything. Front-loaded order starts
  `storage::handler::test_quote_already_stored_flag` (+47 new fns),
  `storage_commitment_audit::closeness_is_observe_only…` (+43),
  `verifier::test_legacy_median_tie_accepts_paid_candidate` (+29) — run these first to accrue coverage
  fastest.
- **Behavioural outlier tests** (unique behaviour vs everything-touching smoke): the upgrade
  `release_cache` round-trip/TTL tests and `upgrade::monitor` selection tests have the highest
  residuals (~0.97) — they exercise behaviour almost nothing else does. Good (they're pulling their
  weight); also means upgrade behaviour rests on few tests — keep them.

### C6. Runtime risk (`runtime-risk`, confidence 0.70) — churn × *behavioural* centrality

Re-scoring the git-risk hotspots using how many *behaviours* (not just static edges) touch each file:

| Urgency | File | Churn | Behavioural centrality | Risk |
|---|---|---:|---:|---:|
| 🟠 orange | `src/payment/verifier.rs` | 52 | 1087 | 56,524 |
| 🟢 | `src/replication/types.rs` | 20 | 243 | 4,860 |
| 🟢 | `src/replication/config.rs` | 23 | 165 | 3,795 |
| 🟢 | `src/storage/handler.rs` | 27 | 132 | 3,564 |
| 🟢 | `src/storage/lmdb.rs` | 9 | 382 | 3,438 |

`payment/verifier.rs` is the runaway #1 by behavioural centrality too — an order of magnitude above
the field. The static and behavioural risk models **agree** on the single most important file.

### C7. Test selection example (`select-tests`, confidence 1.00)

For a change to `PaymentVerifier.verify_payment`, stitchgraph fuses runtime coverage with the static
blast radius and recommends **236 tests** — 51 that *actually executed* the function plus 185 in its
structural blast radius. That's the precise "what to run for this change" set, ~35% of the suite.

---

## Cross-cutting synthesis

Four independent lenses — static hubs, git churn, POD energy, behavioural core — **all point at the
same place**: `payment/verifier.rs` + `payment/cache.rs` + the Merkle `commitment.rs` triad is the
heart of ant-node. It is simultaneously the top structural hub, the #1 churn/risk hotspot, the #1 POD
mode (12.9% energy), and the always-on behavioural core (executed by 50–83 tests each). This is a
coherent, well-tested design where the most important code is also the most exercised — but it is the
place to spend review and stability discipline, and any regression there has the widest behavioural
blast radius.

## Recommendations

1. **Protect `payment/verifier.rs` first** — it wins every risk lens. Keep its 50+ tests green, review
   changes there hardest, treat `PaymentVerifier.verify_payment` as a stability-critical API.
2. **Treat `replication/types.rs` and `protocol.rs` as a stable ABI** — risky through centrality, not
   churn; changing their shapes ripples widely.
3. **Close the one real unit gap:** add coverage for `NodeConfig` file round-trip
   (`from_file`/`to_file`) and `Cli.into_config`. The rest of the 220 `src/` "gaps" are process-wiring
   reached only by e2e/launch, not test holes.
4. **Delete dead code:** `get_worker_nodes` in `scripts/testnet/churn-test.sh` (unused; trivial).
5. **No dependency-cycle work needed** — the 8 flagged cycles are confirmed name-collision artifacts,
   not real cycles.
6. **Suite is healthy** — 0 redundant tests, 0 holes, no minimal-cover fat. Don't prune; if anything,
   guard the low-redundancy upgrade tests (C5 outliers).

---

## Reproduction

```bash
pip install stitchgraph                                   # 3.50.0
# Static (fast) + precise:
rustup component add rust-analyzer
stitchgraph reindex . --lsp --precise --db sg.db          # 3,649/5,526 sites type-resolved
stitchgraph orient|find-subsystems|find-chokepoints|scan|find-stale|risk --db sg.db
# Behavioural (POD) — the coverage half:
rustup component add llvm-tools-preview && cargo install cargo-llvm-cov
stitchgraph scaffold-coverage --language rust --out-dir cov-kit --db sg.db
bash cov-kit/run_coverage.sh                              # 676 tests → coverage_modes.json
stitchgraph find-modes  --coverage coverage_modes.json --db sg.db   # the POD run + 16 modes
stitchgraph find-core|find-coupling|find-gaps|select-tests|redundant-tests \
            find-outlier-tests|test-order|runtime-risk   --coverage coverage_modes.json --db sg.db
```

*Static findings: confidence 1.00 (precise, rust-analyzer). Git-risk / runtime-risk: 0.70.
Behavioural findings: confidence 1.00 — measured from a complete 676-test / 1,154-function coverage
matrix. Dead-code/cycle candidates flagged `needs_review` are hand-verified in the text above.*
