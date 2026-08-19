# `codex/l10m-sky-1`

- Status: `ready_for_review`
- Owner: project work branch
- Base: `main` at `116c8283a61360f804981cb16c12e2ee2ceb2ceb`
- Head reviewed for this record: `16ed351634f35e6b2b81d7f2e3326731d1bedc7b`
- Integration target: `main`
- Integrated commit: `not integrated`

## Purpose

Run the preregistered L10M-SKY-1 direct comparison of SkyDiscover search against
the naked Codex control on a fresh 12-instance graph cohort with two nested
replicates per instance.

## Scope and dependencies

- Owns `benchmarks/blindassist_last10m_sky_1/` and its focused benchmark test.
- Depends on the frozen L10M-ORACLE-3 evaluator family and the project Codex CLI
  provider.
- Excludes general SkyDiscover framework changes and real-world deployment claims.

## Work performed

- Preregistered the paired protocol, generated and froze the fresh cohort, and
  added execution, analysis, closeout, preflight, and focused test tooling.
- Completed 48/48 arm runs and 24/24 paired hidden adjudications.
- Recorded a bounded amendment for a missing score-attribution artifact and
  archived final execution receipts.

## Result and claim ceiling

The final result reports mean `DELTA_SKY = +0.00125`, with 3 wins, 6 ties, and 3
losses. Superiority, equivalence, and meaningful harm were not established. The
frozen architecture decision is `SKY_DIRECT_SEARCH_VALUE_NOT_ESTABLISHED`, only
within the L10M-SKY-1 graph-family claim ceiling.

## Validation and evidence

- Primary evidence: `benchmarks/blindassist_last10m_sky_1/receipts/execution/FINAL_RESULT.json`.
- Execution audit and per-unit receipts are archived beside the final result.
- Focused tests live in `tests/benchmarks/test_blindassist_last10m_sky_1.py`.
- Exact validation command history is not recorded in this ledger backfill.

## Important commits

- `b68b34f`: preregister the direct trial.
- `011532e`: freeze the fresh cohort.
- `11dc5be`: tolerate the missing attribution artifact under a recorded amendment.
- `16ed351`: close the direct trial and archive results.

## Integration notes

Review the complete benchmark and evidence payload before integration. This
branch is the parent dependency for both L10M diagnostic branches. No integration
into `main` is recorded as of this ledger entry.
