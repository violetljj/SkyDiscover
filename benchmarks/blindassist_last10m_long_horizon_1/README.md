# L10M-LONG-HORIZON-1

Consumed-development calibration of the original `incumbent_only` (Naked),
AdaEvolve, and EvoX mechanisms over one prefix-consistent 200-candidate
trajectory. It never reads fresh or hidden outcomes and cannot support a
superiority claim.

The formal matrix is 12 consumed instances by 3 local seeds by 3 arms (108
independent trajectories). Each trajectory is serial. The local control plane
owns Codex calls, budgets, checkpoints, journals, and terminal receipts; the
AutoDL host runs only persistent evaluator workers. On the verified 32-core
container, at most 26 single-threaded evaluator processes are admitted, with 6
cores reserved for the OS and supervision. Local trajectory concurrency remains
10 because model/provider throughput is a separate bottleneck.

Every accepted iteration creates an atomic recovery checkpoint. Scientific
observations are read at iterations 10, 20, ..., 200. An interrupted external
call is counted as `in_doubt`; that trajectory is sealed and never silently
rerun. A clean interruption may resume from the latest complete checkpoint.

Formal launch remains blocked until `protocol.json` is marked
`EXECUTION_PROTOCOL_FROZEN`, the immutable execution manifest exists, the exact
remote commit verifies, and the zero-model-call transport canary passes.

Read-only progress:

```powershell
uv run python benchmarks/blindassist_last10m_long_horizon_1/progress.py `
  --run-root E:\SkyDiscover_runs\L10M-LONG-HORIZON-1
```
