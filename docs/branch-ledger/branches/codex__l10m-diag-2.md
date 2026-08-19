# `codex/l10m-diag-2`

- Status: `ready_for_review`
- Owner: project work branch
- Base: `codex/l10m-diag-1` at `38289c687579e400808c4a3f756e41538ada2447`
- Head reviewed for this record: `5542cec2ccb6f5a90f7ceaa464e0b023213d1217`
- Integration target: `main`, after or together with SKY-1 and DIAG-1 dependencies
- Integrated commit: `not integrated`

## Purpose

Diagnose DIAG-1's single timeout and test whether a structured temporal policy
representation makes robust behavior reachable on the consumed diagnostic
cohort without changing the evaluator.

## Scope and dependencies

- Owns `benchmarks/blindassist_last10m_diag_2/` and its focused benchmark test.
- Depends on the complete SKY-1 and DIAG-1 branch history.
- Uses consumed data, makes no search calls, and does not establish automated
  search value or fresh/blind superiority.

## Work performed

- Added step-level traces for the DIAG-1 and structured temporal policies.
- Identified repeated non-transitioning steering without a progress contract as
  the timeout mechanism.
- Added a decomposed policy prototype with safety, tracking, move proposal,
  progress, and decision contracts.

## Result and claim ceiling

The structured policy passed the behavioral gate on 11/12 consumed instances,
had mean substantive delta `+0.013542`, and achieved 12/12 robust-safe outcomes.
The frozen verdict is `STRUCTURED_REPRESENTATION_ROBUST_REACHABILITY_ESTABLISHED`.
This is post-hoc consumed-data diagnostic evidence, not real-world safety,
generality, or automated search-value evidence.

## Validation and evidence

- Primary evidence: `benchmarks/blindassist_last10m_diag_2/receipts/development_audit.json`.
- Reproduction command: `uv run python benchmarks/blindassist_last10m_diag_2/run.py`.
- Focused test: `tests/benchmarks/test_blindassist_last10m_diag_2.py`.
- Exact historical test output is not recorded in this ledger backfill.

## Important commits

- `5542cec`: add the structured representation audit and frozen receipt.

## Integration notes

Review and integrate the dependency chain in order: SKY-1, DIAG-1, then DIAG-2,
or integrate the cumulative DIAG-2 head after confirming the full diff. The
receipt authorizes a subsequent search restart within its claim ceiling; it does
not itself prove that search can discover the structured policy.
