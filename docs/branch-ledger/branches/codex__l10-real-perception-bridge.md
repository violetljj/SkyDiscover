# `codex/l10-real-perception-bridge`

- Status: `active`
- Owner: project work branch
- Base: `origin/main` at `c475ed4009071159b4d5b777715f1af9202cebba`
- Integration target: `main`
- Integrated commit: `not integrated`

## Purpose

Create a clean SkyDiscover search boundary for the BlindAssist last-ten-metre
active-observation policy using exported perception and temporal-belief states,
without carrying forward the obsolete oracle benchmark contract.

## Scope and dependencies

- Owns `benchmarks/blindassist_last10m_perception_1/`.
- Depends on BlindAssist producing frozen real-perception episode exports.
- May later use the generic assist subprocess bridge from its separately owned
  branch; this branch does not duplicate or modify that concurrent work.
- Excludes model/threshold search, old benchmark migration, product claims, and
  active-view causality claims from unposed ordered images.

## Current result

The evaluator, policy interface, hard false-commit/arrival gates, and explicit
AdaEvolve Pareto objectives are implemented. The first real perception prefix
is also recorded: a scale-consistency gate removes one observed false commit,
but portal truth remains absent from both candidate sets. Scientific search is
therefore not authorized; the proposal representation must change first.

## Validation

- Focused deterministic train and hidden replays of the baseline policy.
- Python compilation and configuration loading before delivery.

## Integration notes

Integrate only after the BlindAssist exporter supplies at least one frozen
`BLINDASSIST_REAL_PERCEPTION` episode with source/model/protocol/backend hashes.
