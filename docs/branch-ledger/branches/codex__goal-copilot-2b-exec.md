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
- Current status: formal execution complete; both replicates reached their
  terminal 16-call receipts, then BA closed without held-out admission.
- Evidence-backed result: 32/32 calls produced 16 globally unique candidates;
  BA's locked public-development winner retained CLEAN `12/12` and
  COMBINED_MILD `10/12` but remained COMBINED_MODERATE `0/12`, so no held-out
  evaluation occurred and the robustness search signal was not established.
- Claim ceiling:
  `symbolic_consumed_task_search_completed_no_heldout_or_robustness_claim`.
- Validation: focused pytest, Black, Isort, and zero-model transport canary.
- Important commits: `82a516d196dc805c01e750477b729143729abeae`
  implements the formal harness and zero-model canary.
- Integration target: `origin/codex/goal-copilot-2b-exec`; do not merge into
  `main` during the frozen run.
- Readiness/blockers: terminal; no resume, rescue rerun, wider budget, or
  held-out opening is authorized.
- Final disposition: complete on the frozen task branch; retain exact source
  commit `a2692f009cf97c4b2da4b70674f780fb39f5bf23` and terminal BA receipts.
