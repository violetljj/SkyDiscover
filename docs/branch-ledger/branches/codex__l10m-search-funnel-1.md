# `codex/l10m-search-funnel-1`

- Status: `complete_ready_for_review`
- Owner: project work branch
- Base: `codex/l10m-struct-component-2` at `401688b`
- Integration target: `main`, after review of the cumulative L10M dependency chain
- Integrated commit: `not integrated`

## Purpose

Start the post-Structured mechanism phase with a zero-call search-funnel audit
that distinguishes candidate scarcity from selection/retention loss.

## Task-owned scope

- `benchmarks/blindassist_last10m_search_funnel_1/`
- `tests/benchmarks/test_blindassist_last10m_search_funnel_1.py`
- this branch record

## Dependencies and evidence boundary

- Depends on the sealed `L10M-SKY-1` repository evidence and its task-owned
  local run archive at `E:/SkyDiscover/.runs/l10m_sky_1_20260819`.
- Reads consumed development metrics, lineage, retained-program state, and
  hidden adjudications without invoking a model or evaluator.
- Does not modify or rerun sealed units and cannot establish fresh/blind value.

## Work performed

- Froze selection-loss and candidate-scarcity diagnostic gates before running
  the audit.
- Added identity and source-hash joins across manifests, checkpoints, retained
  best state, search receipts, and hidden adjudications.
- Added focused tests for the hard-safety predicate and funnel aggregation.
- Completed the audit over 48 arm-blocks and 476 produced candidates while
  preserving four missing opportunities as frozen ITT zeros.

## Current status and claim ceiling

The audit bound and verified 742 input files. For Sky search, 13/24 blocks had
a robust-safe positive candidate, but the mean oracle-minus-retained hidden gap
was only `0.0008333` and positive in 2/24 blocks. Selection/retention loss did
not pass its frozen gate. Absolute candidate scarcity also did not pass, so the
formal decision is `MIXED_OR_UNRESOLVED`.

Sky retained mean hidden value was `0.0070833` versus Naked Codex `0.0058333`,
reproducing the prior `+0.00125` incremental gap. The evidence supports moving
development attention toward incremental candidate quality, but does not prove
a single causal mechanism or admit fresh execution. The maximum claim remains
mechanism localization on the consumed L10M-SKY-1 cohort.

## Validation

- `uv run pytest tests/benchmarks/test_blindassist_last10m_search_funnel_1.py -v`
  (`3 passed`).
- Black and isort checks passed for the benchmark and focused test.
- The receipt-only audit completed with zero model/evaluator calls and zero
  hidden reruns; input identity SHA-256 is
  `09d06b73fae0d336dcd48002cacf7aae98916860b74d64e5fdf5e1403d1a95ef`.

## Important commits

- `77d195d`: implement, validate, and archive the receipt-only search-funnel audit.

## Readiness and disposition

Ready for review as a diagnostic dependency. Do not use it to reopen the
Structured route or to claim selection failure, candidate scarcity, fresh
search value, or general superiority. The next experiment must remain on
consumed development data until a candidate-quality mechanism shows a clear,
robust-safe retained gain.
