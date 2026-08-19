# `codex/l10m-structured-direct-1`

- Status: `complete_ready_for_review`
- Owner: project work branch
- Base: `codex/l10m-struct-search-1` at `cbf609ab505abba720f6109358fd64d76cbf4f99`
- Integration target: `main`, after review of the cumulative experiment chain
- Integrated commit: `not integrated`

## Purpose

Formally test the incremental value of SkyDiscover's structured generation
package against a raw direct-generation control on a fresh L10M graph-family
cohort, without temporal search between candidates.

## Scope and dependencies

- Owns `benchmarks/blindassist_last10m_structured_direct_1/` and its focused test.
- Depends on the cumulative SKY-1, DIAG-1, DIAG-2, and STRUCT-SEARCH-1 heads.
- Uses a private external create-once cohort and native authenticated Codex CLI.
- Excludes claims about individual contracts, temporal search, other benchmarks,
  or real-world safety.

## Work performed

- Frozen a two-arm contrast: raw direct versus structured direct.
- Used six fresh-start one-call candidates per arm and instance, with no prior
  candidate, score, evaluator feedback, or temporal search exposed between them.
- Added interface-specific static guards, deterministic hidden tie-breaking, and
  a corrected analyzer that prefers robust-safe candidates at equal primary value.
- Materialized a fresh 12-instance cohort and completed 144 search receipts and
  72 hidden adjudications.
- Six initial visible-launcher units were terminated before receipt creation;
  they were sealed as in-doubt `ARM_FAILED_ITT` units and never retried. The
  remaining 138 units completed, and the rest of adjudication completed through
  a hidden `CreateNoWindow` launcher.

## Result and claim ceiling

Structured Direct mean hidden substantive delta was `0.006667`, raw Direct was
`0.005000`, and the paired instance mean effect was `+0.001667`. The exact
one-sided sign-flip p-value for a `+0.005` meaningful effect was `1.0`.
Structured robust-safe coverage was `10/12`, so the conjunctive safety gate
also failed. The frozen decision is
`STRUCTURED_DIRECT_VALUE_NOT_ESTABLISHED_SAFETY_GATE_FAILED`.

The claim ceiling is limited to the Sky structured-generation package, fresh
start best-of-six candidates, and one frozen L10M graph family. This does not
establish that structured generation has no value generally, nor does it test
individual contract ablations.

## Validation and evidence

- Focused tests: `9 passed`.
- Black and isort checks passed for the changed benchmark and test files.
- Mechanical preflight passed with authenticated `codex-cli 0.148.0` and the
  frozen native executable hash.
- Execution manifest was frozen before treatment.
- Primary evidence: `receipts/execution/FINAL_RESULT.json`.
- Audit evidence: `receipts/execution/EXECUTION_AUDIT.json`.
- Formal receipts: 144 search receipts, 144 candidate manifests, 72 hidden
  adjudications; 138 completed and 6 in-doubt ITT failures.

## Important commits

- `pending`: implement, execute, and archive the formal direct comparison.

## Integration notes

Review the protocol, execution manifest, external cohort custody, launcher
incident, and primary result together. Do not alter or rerun sealed receipts.
