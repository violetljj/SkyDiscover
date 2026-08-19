# `codex/l10m-struct-autopsy-1`

- Status: `sealed_complete`
- Owner: project work branch
- Base: `codex/l10m-structured-direct-1` at `ff58271`
- Integration target: `main`, after review of the structured-direct evidence chain
- Integrated commit: `not integrated`

## Purpose

Perform `L10M-STRUCT-AUTOPSY-1`: a receipt-only mechanism analysis of the
sealed Structured Direct versus Raw Direct cohort, with zero fresh tasks and
zero model calls.

## Scope and dependencies

- Owns the autopsy analyzer, report, and focused test only.
- Depends on the frozen `L10M-STRUCT-DIRECT-1` protocol, receipts, and candidate
  manifests; no receipt or evaluator input is modified.
- Does not claim causal value for any individual contract.

## Work performed

- Replayed the formal best-of-six selection from hidden adjudications.
- Parsed selected candidate source from immutable manifests and extracted
  conservative contract-diff and mechanism-feature tags.
- Recorded package-level wins, ties, loss, safety failures, and feature-level
  descriptive associations.

## Result and claim ceiling

The package-level result remains `+0.001667`, `2/9/1` wins/ties/losses, and
`10/12` robust-safe. All five named contract bodies changed in all selected
candidates, while semantic feature coverage was nearly universal. This is
descriptive post-hoc association only; component-level causal value is not
established. The mechanism presence counts (`11/12` progress memory and `10/12`
move proposals) rule out simple non-adoption as a sufficient explanation, but
they do not identify benefit, harm, or interaction effects.

## Validation and evidence

- Focused autopsy test: expected to cover receipt-only invariants and frozen
  summary counts.
- Evidence source: `benchmarks/blindassist_last10m_structured_direct_1/receipts/execution/`.
- No fresh execution, model call, evaluator run, retry, or receipt mutation.

## Important commits

- `9df7a87`: add receipt-only autopsy and report.

## Integration notes

Keep the structured-direct cohort sealed. Any future fresh run should test a
pre-registered minimal mechanism contrast rather than another full package.
The next development step is `L10M-STRUCT-COMPONENT-1`: a consumed/development
2x2 screen with Raw, Progress-only, Moves-only, and Progress-plus-Moves arms.
Safety, tracking, termination, generation budget, model, candidate count,
selection, and evaluator remain fixed; only the two mechanism toggles may
differ. Fresh-task confirmation is admissible only after a clear, stable,
robust-safe gain appears in at least one treatment arm.
