# `codex/l10m-diag-1`

- Status: `ready_for_review`
- Owner: project work branch
- Base: `codex/l10m-sky-1` at `16ed351634f35e6b2b81d7f2e3326731d1bedc7b`
- Head reviewed for this record: `38289c687579e400808c4a3f756e41538ada2447`
- Integration target: `main`, after or together with its SKY-1 dependency
- Integrated commit: `not integrated`

## Purpose

Perform a bounded post-hoc objective-sensitivity and policy-reachability audit
after SKY-1 did not establish direct search value.

## Scope and dependencies

- Owns `benchmarks/blindassist_last10m_diag_1/` and its focused benchmark test.
- Depends on the complete `codex/l10m-sky-1` branch and its consumed cohort.
- Uses no fresh blind split and makes no search-model calls.

## Work performed

- Compared the baseline, an instruction-only counterfactual, and a hand-written
  lower-alignment-threshold reachability probe.
- Replayed the frozen development split and consumed SKY-1 cohort without
  changing the evaluator or evidence boundary.

## Result and claim ceiling

Objective sensitivity and a reachable behavioral effect were present, but robust
safe reachability was not established. The threshold probe passed 10/12 consumed
instances with mean substantive delta `+0.007483`; one instance timed out. The
verdict is `OBJECTIVE_SIGNAL_PRESENT_ROBUST_REACHABILITY_NOT_ESTABLISHED`.
Claims are limited to the post-hoc consumed L10M-ORACLE-3 and SKY-1 cohort.

## Validation and evidence

- Primary evidence: `benchmarks/blindassist_last10m_diag_1/receipts/development_audit.json`.
- Reproduction command: `uv run python benchmarks/blindassist_last10m_diag_1/run.py`.
- Focused test: `tests/benchmarks/test_blindassist_last10m_diag_1.py`.
- Exact historical test output is not recorded in this ledger backfill.

## Important commits

- `38289c6`: add the objective/reachability audit and its frozen development receipt.

## Integration notes

Do not integrate this commit without its SKY-1 parent history. DIAG-2 builds on
this result and supersedes its failed robust-reachability probe for subsequent
representation work; DIAG-1 remains useful diagnostic evidence.
