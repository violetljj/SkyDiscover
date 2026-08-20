# `codex/goal-copilot-2b-exec`

- Purpose: implement the separately authorized, fail-closed GC2-B Sky execution
  adapter and zero-model transport canary.
- Base branch: `origin/codex/goal-copilot-2b-protocol`.
- Base commit: `3b5fc8ba3e16027898c594a6eaec945b3e409577`.
- Task-owned scope: formal GC2-B config/harness/canary, focused tests, and this
  branch ledger.
- Dependencies: exact BlindAssist public SearchTaskBundle and formal run seal.
- Work performed: added two-by-16 best-of-n configuration, exact seal and bundle
  checks, reuse of the frozen GC1 journal/budget mechanics, and a zero-model
  bundle/config/evaluator canary.
- Current status: implementation and focused tests complete; formal execution
  may start only after BA publishes a matching model-call-authorizing run seal.
- Evidence-backed result: focused mechanics and transport checks only; no search
  result at branch creation time.
- Claim ceiling: `symbolic_consumed_task_noise_robust_search_signal_only` after
  a valid terminal run; currently engineering readiness only.
- Validation: focused pytest, Black, Isort, and zero-model transport canary.
- Important commits: `82a516d196dc805c01e750477b729143729abeae`
  implements the formal harness and zero-model canary.
- Integration target: `origin/codex/goal-copilot-2b-exec`; do not merge into
  `main` during the frozen run.
- Readiness/blockers: provider identity, immutable bundle, encrypted held-out
  envelope, checklist, and formal run seal must all match.
- Final disposition: pending formal execution and terminal receipt.
