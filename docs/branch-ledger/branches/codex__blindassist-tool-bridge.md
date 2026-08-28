# `codex/blindassist-tool-bridge`

- Status: `active`
- Owner: project work branch
- Base: `main` at `c475ed4009071159b4d5b777715f1af9202cebba`
- Integration target: `main`
- Integrated commit: `not integrated`

## Purpose

Let BlindAssist temporarily use SkyDiscover as an auxiliary discovery tool
without installing BlindAssist dependencies into SkyDiscover or SkyDiscover
into BlindAssist.

## Scope and dependencies

- Owns the generic assist CLI, subprocess evaluator transport, focused tests,
  user documentation, project script registration, and this ledger.
- Depends on a consumer-owned evaluator, launcher, configuration, initial
  program, working directory, and output root.
- Excludes BlindAssist algorithm/evaluator changes, generated search results,
  model calls, remote execution, and changes to normal SkyDiscover execution.

## Work performed

- In progress.

## Result and claim ceiling

Not yet validated. The intended result is local dependency and output isolation,
not scientific performance or production sandboxing against malicious code.

## Validation and evidence

- Not run.

## Important commits

- None yet.

## Integration notes

Review the transport seam and focused tests before integration. A zero-model-call
consumer transport probe is required before any formal consumer run.

## Final disposition

Active.
