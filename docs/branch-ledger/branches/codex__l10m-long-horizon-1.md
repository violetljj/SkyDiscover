# codex/l10m-long-horizon-1

- Purpose: calibrate Naked, AdaEvolve, and EvoX on consumed Last10m instances over prefix-consistent 200-candidate trajectories.
- Base branch: `codex/l10m-search-funnel-1`.
- Base commit: `c580e29`.
- Task-owned scope: controller checkpoint/resume correctness, durable budget journals, and `benchmarks/blindassist_last10m_long_horizon_1/`.
- Dependencies: consumed L10M-COMP-2 cohort; local authenticated Codex CLI; user-designated AutoDL evaluator endpoint.
- Work performed: added controller-owned checkpoint state, atomic checkpoints, durable external-call accounting, a 32-core remote execution protocol, persistent evaluator transport, bounded launcher, and read-only progress summary.
- Current status: execution protocol frozen after exact-commit remote verification and a zero-model-call transport canary; no formal model calls or formal trajectory receipts created.
- Evidence-backed result: no scientific result yet.
- Claim ceiling: consumed-development horizon behavior within one L10M graph family only.
- Validation: 73 focused tests passed; remote environment verified on 32 visible cores; zero-model-call transport canary passed normal evaluation, confirmed failure classification, and create-once replay.
- Important commits: `8d8fd2b` (recoverable long-horizon engineering baseline); execution-freeze commit pending.
- Integration target: project integration branch after terminal experiment closeout.
- Readiness/blockers: final frozen commit must be deployed and re-canary-verified before formal launch.
- Final disposition: active.
