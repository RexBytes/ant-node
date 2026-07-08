# stitchgraph report

## Orientation

- Nodes indexed: 1942
- By kind: {'Module': 92, 'Class': 180, 'Function': 1180, 'Method': 490}
- Read these first (hubs): ['Error', 'StorageCommitment', 'StorageStats', 'LmdbStorage', 'ReplicationConfig', 'PaidList', 'ReplicationProtocolError', 'ReplicationMessage.encode']

## 🔴 Fix now

- (none)

## 🟠 Look closer

- (none)

## 🟢 Cleanup

- Stale code candidates: 1 (confidence 0.60, verify before removing)
  - scripts/testnet/churn-test.sh::get_worker_nodes
- **cycle** `PaidList.remove` — circular dependency among 3 symbols; rests mostly on name-ambiguous/heuristic edges (0/5 confident) — verify before acting
- **cycle** `ChunkTestFixture.compute_address` — circular dependency among 2 symbols; rests mostly on name-ambiguous/heuristic edges (0/4 confident) — verify before acting
- **cycle** `LmdbStorage.try_put` — circular dependency among 2 symbols; rests mostly on name-ambiguous/heuristic edges (0/2 confident) — verify before acting
- **cycle** `NeighborSyncState.new_cycle` — circular dependency among 57 symbols; rests mostly on name-ambiguous/heuristic edges (30/1182 confident) — verify before acting
- **cycle** `ReplicationQueues.contains_key` — circular dependency among 2 symbols; rests mostly on name-ambiguous/heuristic edges (0/4 confident) — verify before acting
- **cycle** `TestNode.peer_count` — circular dependency among 2 symbols; rests mostly on name-ambiguous/heuristic edges (0/4 confident) — verify before acting
- **cycle** `TestNetwork.start_regular_nodes` — circular dependency among 8 symbols; rests mostly on name-ambiguous/heuristic edges (8/20 confident) — verify before acting
- **cycle** `TestNode.shutdown` — circular dependency among 3 symbols; rests mostly on name-ambiguous/heuristic edges (0/9 confident) — verify before acting

## Risk (git × structure)

- orange src/payment/verifier.rs (churn 52, risk 93028.0)
- orange src/replication/types.rs (churn 20, risk 58200.0)
- green src/replication/mod.rs (churn 49, risk 33467.0)
- green src/replication/protocol.rs (churn 8, risk 25488.0)
- green tests/e2e/testnet.rs (churn 19, risk 19836.0)
- Hidden coupling pairs: 15 (co-change with no structural edge)
