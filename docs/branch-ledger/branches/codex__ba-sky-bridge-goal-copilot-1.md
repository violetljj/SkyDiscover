# `codex/ba-sky-bridge-goal-copilot-1`

- Status: `mechanics_ready_pending_committed_replay`
- Owner: Codex task branch
- Base: `main` at `f1c5dbfb1da760f983077cf5a5b9aee3f0b2e3da`
- Head reviewed for this record: `not committed`
- Integration target: `main`
- Integrated commit: `not integrated`

## Purpose

Add the optimizer-side half of the BlindAssist-owned SearchTaskBundle to
CandidateBundle bridge and prove the boundary with a zero-model dry-run.

## Scope and dependencies

- Owns `benchmarks/blindassist_goal_copilot/`, its focused test, and this ledger.
- Depends on the matching BlindAssist `GOAL-COPILOT-1` bundle schema.
- Does not modify the existing L10M evaluators, consumed runs, or `.runs/` state.

## Work performed

Implemented a read-only task-bundle verifier and deterministic mock candidate emitter.
The adapter contains no evaluator or hidden truth and records proposal-only provenance.

## Result and claim ceiling

Focused tests and a pre-commit cross-repository mock roundtrip pass. The maximum possible
claim is bridge mechanics only; no model call or scientific comparison is authorized.

## Validation and evidence

- Focused test: `uv run pytest tests/benchmarks/test_blindassist_goal_copilot.py -v`.
- Cross-repository pre-commit dry-run: `ACCEPT`; committed-source replay pending.

## Important commits

- Pending.

## Integration notes

Ready for `main` only after the matching BlindAssist exporter/importer contract is
delivered and the end-to-end zero-model replay passes.
