# State of ant-node — 2026-07-07

A point-in-time health report on `ant-node` v0.14.2 (commit `a24910d`), produced by
running the full test suite and the complete static + behavioural analysis toolkit of
[stitchgraph 3.47.1](https://pypi.org/project/stitchgraph/3.47.1/) against the repository.

Everything below that came from stitchgraph carries its trust envelope (confidence /
provenance / needs-review); findings flagged as heuristic were hand-verified before
being reported here, and resolution artifacts are called out as such.

---

## TL;DR for devs

1. **The suite is green.** All 670 lib tests pass (2.7 s in release), all 35 PoC
   tests, and 70/70 runnable e2e tests (the 14 "failures" here are all the missing
   `anvil` binary in this sandbox — they run in CI, which installs Foundry).
   `cargo fmt --check` and clippy (`-D warnings`, all targets/features) are clean.
2. **One known, documented, unfixed DoS**: the bootstrap-stall attack
   (`tests/poc_bootstrap_stall.rs`) — a single Byzantine peer can permanently prevent
   bootstrap from draining, which silently disables audits and the reputation system
   on the victim. The PoC currently *passes by asserting the buggy behaviour*. This is
   the highest-value open work item in the repo.
3. **A fresh RUSTSEC advisory will break CI's audit job**: `crossbeam-epoch` 0.9.18
   (RUSTSEC-2026-0204, published 2026-07-06). One-line fix:
   `cargo update -p crossbeam-epoch`.
4. **`src/payment/verifier.rs` and `src/replication/types.rs` are the risk hotspots**
   (churn × graph centrality). Both are large, central, and frequently edited — review
   changes there with extra care and prefer `impact_of` before touching them.
5. **Hidden coupling is real and already biting**: `audit.rs ↔ neighbor_sync.rs`
   co-change with no structural edge — exactly the implicit repair-proof contract
   tracked in issue #1. The recommended fix (shared close-group function + round-trip
   contract test) is still unimplemented.
6. **Three live-testnet tests are `#[ignore]`d** pending a rewrite for saorsa-core
   0.16 (`dht_put`/`dht_get` removed) — that coverage gap is invisible in green CI runs.
7. **Essentially no dead code.** One dead shell function
   (`get_worker_nodes` in `scripts/testnet/churn-test.sh:43`) — that's the entire
   stale-code report. Zero implementation holes (references to missing/stubbed code).

---

## 1. Test suite results

### `cargo test --release` (default features)

| Target | Result |
|---|---|
| lib unit tests | **670 passed, 0 failed** (2.7 s) |
| `poc_d1_bounded_queues` | 6 passed |
| doc-tests | 1 passed, 2 ignored |

### `cargo test --release --features test-utils` (e2e + PoC suites, mirrors CI)

| Target | Result |
|---|---|
| e2e suite (`tests/e2e/`, 25-node in-process testnets) | **70 passed, 14 failed***, 3 ignored (35.8 min) |
| `poc_commitment_audit_attacks` | 19 passed |
| `poc_audit_handler_live` | 8 passed |
| `poc_bootstrap_stall` | 2 passed (by *asserting the unfixed attack* — see §6) |
| `poc_d1_bounded_queues` | 6 passed |
| lib unit tests (also run per-test under coverage) | 670 passed |

\* **All 14 failures are environmental, not code failures**: each dies in
`evmlib::testnet::Testnet::new()` with
`SpawnFailed("could not spawn node: No such file or directory")` — the `anvil`
binary (Foundry) is not installable in this sandbox (GitHub binary downloads are
blocked). The failing set is exactly the EVM-payment e2e tests
(`anvil`, `chunk-rejected-without-payment`, `network_with_evm`, 5×
`merkle_payment` attacks, `payment_flow` helper, 5× `security_attacks`). The same
14 tests run in CI, which installs Foundry v1.7.1 before the e2e step. The 3 ignored are the
live-testnet tests awaiting the saorsa-core 0.16 rewrite (TL;DR #6).

### Lints

- `cargo fmt --all -- --check`: **clean**.
- `cargo clippy --all-targets --all-features -- -D warnings` (CI's exact flags):
  **clean** — zero warnings across all targets, including the panic/unwrap/expect
  lints the project standards mandate.

### Dependency audit

`cargo audit` (685 locked crates, advisory DB of 2026-07-07): **1 vulnerability, 9 warnings.**

- 🔴 **RUSTSEC-2026-0204 — `crossbeam-epoch` 0.9.18** (published **2026-07-06**, the
  day before this report): invalid pointer dereference in the `fmt::Pointer` impl.
  Fixed in ≥ 0.9.20. Transitive via `rayon` ← `saorsa-pqc`/`saorsa-core` (the PQC
  stack); 0.9.20 is semver-compatible, so **`cargo update -p crossbeam-epoch` is the
  whole fix** — do it before the next CI run, because the CI `cargo audit` job will
  go red on this advisory.
- ⚠️ Unsound: `anyhow` 1.0.102 (RUSTSEC-2026-0190, `Error::downcast_mut()` —
  ant-node uses anyhow pervasively; worth a bump when a fixed release lands).
- ⚠️ Unmaintained: `atomic-polyfill`, `bincode` 1.3.3, `derivative`, `paste`,
  `proc-macro-error2`, `rustls-pemfile`. `bincode` 1.x matters most — it sits on
  the wire/serialization path of several deps; the ecosystem is moving to bincode 2.
- ⚠️ Yanked: `bitcoin-io` 0.1.100, `bitcoin_hashes` 0.14.100 (pulled in via the EVM
  stack).

---

## 2. What changed since the 0.14.2 release (stitchgraph `graph-diff`)

Diffing the indexed graph at `HEAD` against commit `3df630c` (the 0.14.2 release
merge) shows the delta is **confined to the prune-audit-challenge path** — matching
the two audit-timeout commits (`1e2075a`, `a35f8eb`):

- New edges only in HEAD: `encode_prune_audit_challenge` → `key_count`/`len`,
  `send_prune_audit_challenge` → `audit_response_timeout`/`key_count`,
  `peer_proves_record` → `key_count`.
- Bodies changed: `ReplicationConfig.default` (similarity 0.53),
  `encode_prune_audit_challenge` (0.79), `send_prune_audit_challenge` (0.89).
- **No nodes added or removed.** No unrelated drift.

---

## 3. Shape of the codebase (stitchgraph `orient` / `find-subsystems`)

- 41.5k lines of Rust across 53 `src/` files; 94 files indexed → **1,942 graph nodes**
  (92 modules, 180 types, 1,180 functions, 490 methods).
- The graph's top hubs (read these first when onboarding): `Error` (src/error.rs),
  `StorageCommitment`, `StorageStats`/`LmdbStorage`, `ReplicationConfig`, `PaidList`,
  `BuiltCommitment`, `ReplicationProtocolError`.
- Subsystem weight: **replication is half the codebase** (864 nodes; 594 functions),
  payment is 282 nodes, storage 81. The replication subsystem depends on payment
  (`cache`, `verifier`, `quote`, `wallet`) and storage handler files — and vice versa;
  the two are tightly interlocked by design (paid-list gating).
- The end-to-end write path traces cleanly in 6 hops:
  `main → RunningNode.run → start_protocol_routing → AntProtocol.try_handle_request →
  handle_put → handle_put_inner → LmdbStorage.put`.

## 4. Risk hotspots (stitchgraph `risk`, churn × centrality)

| Urgency | File | Churn (commits) | Centrality | Why it matters |
|---|---|---|---|---|
| 🟠 | `src/payment/verifier.rs` | 52 | 1,485 | 4.2k lines; payment verification is security-critical and always-on |
| 🟠 | `src/replication/types.rs` | 20 | 2,578 | Highest centrality in the repo; carries the implicit repair-proof contract (issue #1) |
| 🟢 | `src/replication/mod.rs` | 49 | 536 | 4.9k lines, the replication engine loop |
| 🟢 | `src/replication/protocol.rs` | 8 | 2,832 | Wire format — low churn but everything depends on it |
| 🟢 | `src/storage/lmdb.rs` | 9 | 1,344 | Storage engine |

**Hidden coupling** (files that co-change in git with *no* structural edge — the
signal that surfaced issue #1): top pairs are `audit.rs ↔ neighbor_sync.rs` (4×),
`payment/mod.rs ↔ storage/handler.rs` (4×), and a cluster of
`commitment_audit.rs ↔ {commitment, config, mod, protocol, pruning}.rs` (2× each).
41 pairs total. When touching any of these, grep for the sibling and check the
contract by hand — the compiler will not.

## 5. Structural findings (stitchgraph `scan` / `find-stale` / `find-holes` / `find-chokepoints`)

- **No 🔴 or 🟠 structural findings.** All 10 scan findings are 🟢 cleanup-tier,
  and every one is flagged by stitchgraph itself as resting on name-ambiguous edges
  (0/N confident). Spot-checks confirm they are resolution artifacts, e.g. the
  reported `LmdbStorage.put ↔ try_put` "cycle" is actually `put → try_put → db.put`
  (the heed LMDB handle) — no recursion. The `Responder.new` / `LmdbStorage.new`
  "god objects" (fan-in 451) are `new`-name collisions across 180 types.
- **Dead code: one item.** `get_worker_nodes` in `scripts/testnet/churn-test.sh:43`
  is defined and never called anywhere (hand-verified). Safe to delete.
- **Implementation holes: zero.** No references to missing or stubbed symbols.
- **Chokepoints** (cut vertices whose removal fragments the graph): the top ones are
  small utility roots — `VerifiedCache.len`, `calculate_price`,
  `StorageConfig/UpgradeConfig::default`, `PaymentVerifier`,
  `prune_paid_entries`, `verify_path` — 70 total, none alarming, but they are the
  single points where a signature change ripples furthest per line of code.

## 6. Known unfixed attack: bootstrap stall (documented in-repo)

`tests/poc_bootstrap_stall.rs` is a **regression marker for an unfixed DoS**:

> A single Byzantine peer that keeps sending over-cap `NeighborSyncRequest`s never
> gets a "clean admission cycle", so it stays in `capacity_rejected_sources`
> forever, `check_bootstrap_drained` never returns true, and the victim never
> completes bootstrap. While bootstrapping: audits are paused (audit_tick returns
> `Idle`), so bad peers accrue no trust penalties — the entire reputation system on
> that victim is disabled, for free, by well-formed messages.

The PoC *passes by asserting the victim never drains*. The file itself sketches fix
shapes (per-source rate limits, capacity-reject decay, trust-event escalation) and
requires the fix to land with a test asserting bounded drain. **Devs should treat
this as the top open security item** — it is easy to forget because CI is green.

## 7. Behavioural analysis (stitchgraph runtime toolkit)

stitchgraph's behavioural toolkit consumes a per-test coverage matrix. Its
`scaffold-coverage` kit ships Rust as a template ("wire cargo-llvm-cov per test");
that wiring was completed for this report: each test runs in its own process under
`cargo-llvm-cov` instrumentation, per-test LCOV is mapped back to graph node IDs by
line ranges, producing a `stitchgraph-coverage-v1` artifact.

**Artifact**: 792 tests captured (per-test function-level coverage), 790 mapped to
graph node IDs. 14 tests failed in this environment — all Anvil/EVM-dependent e2e
tests (the Anvil binary can't be fetched here); their partial coverage is included,
so payment-verifier gap numbers below are slightly overstated.

### `find-modes` — the POD (behavioural modes)

- The suite exercises **16 dominant behavioural modes** (intrinsic dimensionality
  42 at the energy threshold). The top mode (44.6% of coverage energy) is the
  test-harness storage/quote/verifier attach path — i.e. most tests share the same
  setup spine. The next modes are cleanly interpretable: Merkle tree build/hash
  (9.9%), payment verify + cache (5.6%), LMDB space accounting (3.7%), commitment
  state (2.2%), audit protocol (1.9%), quorum/config decoding (1.6%).
- **A minimal covering set of 124 tests (16% of the suite) reaches every function
  any test reaches.** `test-order` puts `test_prune_veto_for_committed_out_of_range_key`
  first (205 new functions), then `test_late_joiner_replicates_responsible_chunks`
  (+58) — a fast smoke prefix for CI.
- **992 coverage-identical test pairs / 130 groups (311 tests)** — mostly
  legitimately parametrized variants (e.g. the `quorum.rs` family); a consolidation
  review aid, not a delete list.

### `find-gaps` — live code no test executes

Of 1,670 functions, **695 are executed by tests, 974 are live-but-untested** (776 of
those in `src/`, the rest scripts/bins). Heaviest untested files:
`payment/verifier.rs` (78 — partly the failed EVM tests), `replication/audit.rs`
(37), `replication/types.rs` (35), `replication/protocol.rs` (32). Note the overlap
with the churn hotspots in §4: **the two files most likely to change are also among
the least executed by tests.** Exactly **1 untested-dead** function is reported —
the same `churn-test.sh::get_worker_nodes` that `find-stale` flagged statically
(the two independent analyses agree).

### `audit-graph` — the static graph vs runtime ground truth

Static reachability achieved **0.999 recall** against actually-executed functions
(757 tests audited), with 19.6× overapproximation (expected: static reach is a
superset). The only systematically missed functions are trait-dispatch impls —
`FetchCandidate.partial_cmp/eq/cmp`, `ReplicationProtocolError.fmt` — the classic
dynamic-dispatch blind spot. The static findings in this report can be trusted.

### `find-core` / `find-coupling` / `runtime-risk`

- **Always-on core**: `VerifiedCache.with_capacity` (131 tests), `PaymentVerifier.new`
  (122), `LmdbStorage.new` + `compute_map_size` (98 each) — regressions here fail
  a sixth of the suite at once.
- **Hidden coupling (runtime)**: 35 cross-file pairs co-run with no static edge and
  no common caller. Nearly all involve `PaymentVerifier.attach_p2p_node` ↔ the
  `ReplicationEngine.start_*` loops: node startup wires these via spawned async
  tasks, which severs static call edges. Anyone reordering startup in
  `RunningNode.run` should know the payment attach and replication loops are
  sequenced by convention only.
- **`runtime-risk`** (churn × behavioural centrality) promotes
  `src/replication/mod.rs` to 🟠 alongside `payment/verifier.rs` — the engine file
  is executed by more behaviours than its static centrality suggests.

### `select-tests` — demo on the actual release-to-HEAD changeset

For the two functions that changed since 0.14.2
(`encode_prune_audit_challenge`, `send_prune_audit_challenge`): runtime evidence
says **3 e2e prune tests actually executed them**
(`prune_deletes_at_proof_threshold_and_retains_below_it`,
`test_prune_pass_requires_remote_confirmation_before_delete`,
`test_prune_veto_for_committed_out_of_range_key`); the static blast radius adds 137
more candidates. Running those 3 first is the fast regression check for that change.

## 8. Project pulse

- **Activity**: 235 commits since 2026-05-01; last commit 2026-07-03. Main authors
  all-time: Chris O'Neil (159), Warm Beer (71), grumbach (40), Mick van Dijke (17).
- **Open issues**: 1 — the repair-proof implicit-contract hardening (issue #1, itself
  produced by a previous stitchgraph hidden-coupling run; today's run reproduces the
  same signal). **Open PRs: 0.**
- **CI** (`.github/workflows/ci.yml`): fmt, clippy `-D warnings`, lib + e2e
  (`--test-threads=1`) + all three PoC suites with `test-utils`, docs build,
  `--no-default-features` build and test, and `cargo audit`. ADR governance is
  enforced by a dedicated workflow; three ADRs are in `docs/adr/`.
- **Docs**: unusually strong — full replication spec (`REPLICATION_DESIGN.md`),
  infrastructure runbook, testnet plans, ADRs.

## 9. Recommended actions, ranked

1. **`cargo update -p crossbeam-epoch`** — one line, unblocks the CI audit job
   before RUSTSEC-2026-0204 turns it red.
2. **Fix the bootstrap-stall DoS** (§6) — an in-repo PoC, a sketched fix space, and a
   required follow-up test already exist; this is shovel-ready.
3. **Implement issue #1's options A + C** (shared `close_group_for()` + a
   producer→consumer round-trip contract test) — today's risk run shows the
   `audit ↔ neighbor_sync` co-change signal is still live.
4. **Rewrite the three `#[ignore]`d live-testnet tests** for saorsa-core 0.16 so
   live-network coverage returns.
5. **Delete `get_worker_nodes`** from `scripts/testnet/churn-test.sh` (verified dead).
6. **Backfill tests where churn meets zero coverage** (§7 find-gaps): start with the
   untested-live functions in `replication/audit.rs` and `replication/types.rs`.
7. When editing `payment/verifier.rs` or `replication/types.rs`, run
   `stitchgraph impact-of <symbol>` first — these are the two files where churn and
   blast radius multiply.

---

## Appendix: how this report was produced

```bash
pip install stitchgraph==3.47.1            # 12/12 grammars load (stitchgraph doctor)
stitchgraph reindex . --db antnode.db      # 94 files, 1,942 nodes, 0 holes
stitchgraph orient|scan|find-stale|find-holes|find-chokepoints|find-subsystems|risk|report
stitchgraph impact-of PaymentVerifier / LmdbStorage
stitchgraph trace-path "src/bin/ant-node/main.rs::main" "src/storage/lmdb.rs::LmdbStorage.put"
stitchgraph summarize-subsystem src/{replication,payment,storage}
stitchgraph graph-diff <db@3df630c>        # release-to-HEAD structural diff
stitchgraph scaffold-coverage              # Rust per-test wiring completed and
                                           # committed at stitchgraph-coverage/rust/
stitchgraph find-modes / find-gaps / find-core / redundant-tests / test-order / ...

cargo test --release                        # and --features test-utils
cargo fmt --all -- --check
cargo clippy --all-targets --all-features -- -D warnings
cargo audit
```

Static results carry stitchgraph's provenance envelope; every `needs_review`
finding cited here was verified by hand before inclusion.
