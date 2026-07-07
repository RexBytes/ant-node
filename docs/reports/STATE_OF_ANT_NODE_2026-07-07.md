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

The suite decomposes (POD/SVD of the per-test coverage matrix) into **16 dominant
behavioural modes** — statistically independent bundles of functions that tend to
be exercised together — capturing the bulk of coverage variance at an intrinsic
dimensionality of 42. Each mode is what a group of tests *actually does at runtime*,
which is why several cross module boundaries. Read top-down: mode 1 is the shared
setup spine every test pays for; the rest are the distinct behaviours the suite
verifies.

| # | Energy | What this mode exercises | Primary modules | Representative tests |
|--:|--:|---|---|---|
| 1 | **44.6%** | **Node/test-harness setup spine** — spin up LMDB storage, build a quote generator, attach the payment verifier. Nearly every test pays this cost, which is why it dominates. | `storage/lmdb.rs`, `payment/quote.rs`, `payment/verifier.rs` | `test_late_joiner_replicates_responsible_chunks` |
| 2 | 9.9% | **Merkle commitment build & verify** — leaf/node hashing, tree build, sign/verify the storage commitment payload. | `replication/commitment.rs` | `honest_responder_passes_audit`, `fabricated_fraction_is_caught…` |
| 3 | 5.6% | **Payment verification + verified-cache** — `verify_payment` path, EVM config, "already paid?" cache lookups. | `payment/verifier.rs`, `payment/cache.rs` | `test_legacy_paid_median_full_path_accepted` |
| 4 | 3.7% | **LMDB store/space accounting** — put/try_put, address compute, disk-space checks, map sizing. | `storage/lmdb.rs` | `test_put_and_get_chunk`, `test_chunk_persist_across_restart` |
| 5 | 2.2% | **Commitment state rotation** — build-from-tree, rotate current/recent slots, prune retired slots. | `replication/commitment_state.rs`, `commitment.rs` | `retire_current_hides_current_but_keeps_recent…` |
| 6 | 1.9% | **Storage-bound audit challenge** — compute audit digest, serve raw bytes, sample-count/limit config. | `storage/lmdb.rs`, `replication/{config,protocol}.rs` | `prune_deletes_at_proof_threshold…` |
| 7 | 1.6% | **Quorum & config decoding** — quorum/confirm thresholds, key-evidence evaluation, xor-name/peer-id decode. | `replication/quorum.rs`, `config.rs` | `paid_list_majority_uses_self_inclusive_paid_group_size` |
| 8 | 1.5% | **Signed binary-upgrade cache** — verify-key handling, archive fetch, oversized/wrong-size rejection. | `upgrade/binary_cache.rs` | `test_wrong_size_signature_is_rejected_before_copy` |
| 9 | 1.4% | **Quote pricing** — `calculate_price`, records-stored derivation, quoting metrics. | `payment/{verifier,quote,pricing}.rs` | `scenario_1_and_24_fresh_replication…` |
| 10 | 1.4% | **Config defaults** — the `*Config::default` family (payment, storage, upgrade, node). | `config.rs` | `test_build_upgrade_monitor_staged_rollout_enabled` |
| 11 | 1.3% | **Verifier construction** — verifier/quote/cache wiring, test-verifier + candidate-node fixtures. | `payment/{verifier,quote,cache}.rs` | `prune_deletes_at_proof_threshold…` |
| 12 | 1.1% | **Replication queue admission** — queue new, dedupe by key, add-pending-verify. | `replication/scheduling.rs`, `payment/{quote,metrics}.rs` | `scenario_3_neighbor_sync_quorum_pass_full_pipeline` |
| 13 | 1.1% | **Audit-attack PoC harness** — responder/keypair/content fixtures for the commitment-audit attack suite. | `tests/poc_commitment_audit_attacks.rs` | `relay_unable_to_serve_bytes_fails_deterministically…` |
| 14 | 1.0% | **Repair-proof maturity** — record/mature replica-hint, reconcile close group (the issue #1 contract). | `replication/{scheduling,types}.rs`, `payment/cache.rs` | `test_prune_pass_requires_remote_confirmation_before_delete` |
| 15 | 1.0% | **Admission + paid-list gate** — admitted?, send replication response, paid-list membership. | `replication/{scheduling,mod,paid_list}.rs` | `scenario_8_duplicate_key_not_double_queued` |
| 16 | 0.8% | **Neighbor-sync scheduling** — cycle setup, peer selection, cooldown, batch selection, paid-list counts. | `replication/{neighbor_sync,paid_list,types}.rs` | `scenario_38_mid_cycle_peer_join_prioritized` |

Two things worth noting from the decomposition: mode 1 alone is 44.6% of the energy —
tests spend most of their runtime in shared setup, so *behaviour*-level differences
between tests are concentrated in the long tail (modes 2–16). And modes 14–16 map
almost exactly onto the replication security machinery (repair proofs, admission
gate, neighbor-sync) that §4's hidden-coupling and issue #1 flag — the suite does
exercise those paths, it just does so through a handful of e2e scenarios (see
`coverage-drift`, §11).

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

### `find-outlier-tests` — tests that stand alone behaviourally

All 20 top outliers are the **unique** kind (high residual against the mode basis,
tiny breadth) — tests that exercise a behaviour almost nothing else touches:
`test_write_read_roundtrip` and the `release_cache` TTL/repo tests (0.90+ residual),
`apply_revocation_strips_on_digest_mismatch_retains_on_timeout`, and the
commitment-credit `forget_*` / `per_key_cap_evicts_oldest` tests. **These are your
highest-value-per-test cases** — losing one loses coverage of a behaviour no other
test provides, so they should never be deleted in a redundancy pass and are the
first tests to protect when refactoring their subsystem. (No `smoke`-kind outliers,
i.e. no single test touches everything — a healthy sign.)

### `co-change` — what moves with `PaymentVerifier.verify_payment`

For change planning: the functions most behaviourally coupled to `verify_payment`
(share the most tests, so edit them together and test them together) are
`verify_payment_inner` and `payment_proof_type_label` (score 1.0, 63 shared tests),
`check_payment_required` (0.97), then `VerifiedCache` insert/contains. This is the
runtime-grounded neighbourhood to review as a unit when touching payment
verification — distinct from `impact_of`'s static blast radius.

### `feature-map`

Feeds the mode table above: it expands each of the 16 modes into its implementing
functions × files × the tests that express it (757 tests, 694 functions, matrix
density 2.5%). Useful as the drill-down behind any single mode — e.g. "show me every
function and test in the Merkle-commitment mode."

### `select-tests` — demo on the actual release-to-HEAD changeset

For the two functions that changed since 0.14.2
(`encode_prune_audit_challenge`, `send_prune_audit_challenge`): runtime evidence
says **3 e2e prune tests actually executed them**
(`prune_deletes_at_proof_threshold_and_retains_below_it`,
`test_prune_pass_requires_remote_confirmation_before_delete`,
`test_prune_veto_for_committed_out_of_range_key`); the static blast radius adds 137
more candidates. Running those 3 first is the fast regression check for that change.

## 8. Navigation & query operations (for day-to-day dev / agent use)

Beyond the repo-wide analyses, stitchgraph exposes per-symbol queries that are the
fast way to answer "who calls this / where does this flow / where's the code that
does X" without grepping. Verified working on this index:

- **`trace-path <src> <sink>`** — full call path between two symbols. E.g.
  `main → RunningNode.run → start_protocol_routing → try_handle_request →
  handle_put → handle_put_inner → LmdbStorage.put` (6 hops, §3). This is the fastest
  way to understand an end-to-end flow.
- **`get-callees <symbol>`** / **`get-callers <symbol>`** — direct edges in/out of a
  function. ⚠️ **Rust caveat**: calls wrapped in a macro (`assert!(verify_path(…))`)
  are recorded as REFERENCES, not CALLS, so `get-callers` can report a confident
  *empty* for a function that is in fact called only from `assert!`/`debug_assert!`
  (e.g. `commitment.rs::verify_path`). Cross-check with `find-symbol` references
  before trusting a "no callers" result.
- **`find-symbol <name>`** — all definitions of a name (handles the `new`/`put`
  overload collisions by listing each distinct node).
- **`get-matrix <subsystem>`** — bounded call/PDG/value-flow submatrix for one file,
  compact enough to hand to an LLM. Ran clean on `payment/pricing.rs`.
- **`find-similar <snippet>`** (semantic or `--mode structure` for body-shape clone
  detection) and **`find-component <purpose>`** (locate the public symbol that does
  X) — both work but return honestly low confidence (0.7–0.9) on this repo; treat as
  ranked leads, not answers. `find-component "decide which records to delete when
  storage is full"` correctly surfaced `LmdbStorage.delete` and the quote
  records-stored path.
- **`summarize-subsystem <path>`** — node counts, public surface, and cross-file
  dependencies for a directory; used to build §3.
- **`type-at <file> <line>`** — LSP-only; returns the resolved type at a position
  (needs a site rust-analyzer has type info for).

For agents: the shipped `AGENTS.md` rules of engagement apply — query the graph
before grepping, `impact_of` before editing, and respect the envelope
(`needs_review: true` = "unreached by analysis", not "proven dead").

## 9. Project pulse

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

## 10. Recommended actions, ranked

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

## 11. Addendum: full re-run with `--lsp` (rust-analyzer)

The entire battery above was re-run against an index built with
`stitchgraph reindex . --lsp` (rust-analyzer 1.94.1 as the type oracle;
3m15s; **5,526 call sites queried, 3,462 resolved to confident type-grade
edges**). Net effect at the graph level: +919 `extracted` edges and 862
name-ambiguous widened groups collapsed. What that changed — and didn't:

**Conclusions that held identically** (name-based ≙ LSP): every headline finding.
Same single dead function in ant-node code, zero holes, same risk hotspots, same
hidden-coupling pairs, same release-to-HEAD graph-diff delta, identical behavioural
results (16 modes, dimensionality 42, 124-test minimal cover, audit-graph recall
0.999 with the same trait-dispatch misses). The report's substance is
resolution-strategy-independent, which is itself a useful robustness check.

**What LSP genuinely improved:**
- 862 previously widened (multi-candidate) call sites now have a single confident
  target — drill-down ops (`get-callees`, `get-matrix`) return sharper edges.
- With the whole-suite trace also fused via `ingest-trace`, `find-stale`
  confidence rose from 0.60 to **0.78** ("not reached statically AND not executed
  in the trace").

**What LSP did not fix** (useful to know before reaching for it):
- The 🟢 scan artifacts (the `put ↔ try_put` "cycle", the `*.new` "god objects")
  persist unchanged, still resting on 0-confident name edges. The heuristic
  fallback edges for *external* targets (e.g. heed's `Database::put`) remain in
  the graph alongside the LSP resolutions.
- `impact_of PaymentVerifier` stays ambiguous (0.47, blast radius 1,412) — the
  radius is dominated by bare-name REFERENCES edges, not call sites.

**Two sharp edges found while validating** (relevant to anyone scripting stitchgraph):
- `get-callers` on `verify_path` returns a *confident empty* on both indexes,
  although nine tests call it — every call site is wrapped in `assert!(...)`,
  and macro-wrapped calls are extracted as REFERENCES, not CALLS. In macro-heavy
  Rust, "no callers" needs a REFERENCES cross-check before you believe it.
- New this run: `find-stale` flags `func_ranges` in the committed coverage kit's
  `to_canonical.py` even though module-level code calls it (and the graph contains
  that CALLS edge) — a genuine false positive, reported upstream to stitchgraph.

### `coverage-drift` — what the e2e layer uniquely buys (new in this run)

Comparing the suite without e2e (705 tests) against the full suite: the e2e layer
adds test exposure for **194 functions that nothing else executes** — including
`PaymentVerifier.attach_p2p_node`, the whole `replication/admission.rs` gate
(`admit_hints`, `is_in_paid_close_group`), and the engine start-up loops. Lost: 0.
If e2e is ever skipped "because it's slow", those 194 functions are untested.

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
