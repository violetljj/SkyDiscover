# `codex/l10m-struct-search-1`

- Status: `complete_ready_for_review`
- Owner: project work branch
- Base: `codex/l10m-diag-2` at `5542cec2ccb6f5a90f7ceaa464e0b023213d1217`
- Integration target: `main`, after the SKY-1, DIAG-1, and DIAG-2 dependency chain
- Integrated commit: `not integrated`

## Purpose

Test whether equal-budget automated search can discover a qualifying policy in
an expert-designed structured temporal language on a new blind cohort, without
seeding the DIAG-2 oracle implementation.

## Scope and dependencies

- Owns `benchmarks/blindassist_last10m_struct_search_1/` and its focused test.
- Depends on the cumulative DIAG-2 head.
- Stores the private create-once cohort outside Git at the task-owned sealed
  root; the repository contains only logical paths and hashes.
- Uses Naked Structured, EvoX Structured, and Sky+EvoX Structured arms with
  equal six-call ceilings on 12 fresh instances.

## Work performed

- Froze the structured candidate language, primary endpoint, failure semantics,
  recovery ceiling, model, CLI version, budgets, and three-arm comparison.
- Kept the initial progress contract memory-free and excluded the DIAG-2 trace,
  failed-action implementation, and oracle source from search inputs.
- Added a static capability guard that rejects imports, file/process/network
  access paths, dunder traversal, and oracle implementation markers.
- Materialized and hash-bound a new external create-once 12-instance cohort.
- Passed the post-format mechanical preflight and froze the execution manifest.

## Result and claim ceiling

All 36 arm units and 12 paired adjudications completed without arm failure or
hidden feedback to search. Neither search arm passed the conjunctive absolute
gate. EvoX mean substantive delta was `+0.0041667`; Sky+EvoX was exactly
`+0.0050000` and robust-safe on 10/12 under the intended tie semantics. The
frozen verdict is `STRUCTURED_TEMPORAL_SEARCHABILITY_NOT_ESTABLISHED`.

The primary analyzer undercounted robust-safe zero-value ties (recorded counts
9/8/9 versus intended 12/12/10 for Naked/EvoX/Sky+EvoX). The immutable audit
shows the defect is decision-invariant. No receipt was rewritten and no unit was
rerun. The maximum claim remains confined to the expert-designed language and
one frozen L10M graph family; it is not real-world safety or general search
evidence.

## Validation

- `uv run pytest tests/benchmarks/test_blindassist_last10m_struct_search_1.py -v`
  (`10 passed`).
- `uv run black --check benchmarks/blindassist_last10m_struct_search_1 tests/benchmarks/test_blindassist_last10m_struct_search_1.py`.
- `uv run isort --check-only benchmarks/blindassist_last10m_struct_search_1 tests/benchmarks/test_blindassist_last10m_struct_search_1.py`.
- Post-format mechanical preflight: `MECHANICAL_PREFLIGHT_PASS`, 24 sealed files
  verified, frozen CLI `codex-cli 0.148.0-alpha.9`.
- Execution manifest validation: `PASS`.
- Formal execution: 36/36 arms `COMPLETED`, 12/12 hidden blocks adjudicated,
  six generation calls per arm, zero hidden-feedback blocks.
- Primary result and immutable tie-break audit:
  `receipts/execution/FINAL_RESULT.json` and `EXECUTION_AUDIT.json`.

## Important commits

- `ed57e1f`: freeze structured temporal searchability experiment.
- `pending`: archive the completed searchability result and decision-invariant
  execution audit.

## Integration notes

Do not integrate without its cumulative SKY-1, DIAG-1, and DIAG-2 parents.
Review the frozen protocol, oracle exclusion boundary, external cohort custody,
and final execution receipts before integration.
