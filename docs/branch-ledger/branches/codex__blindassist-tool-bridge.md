# `codex/blindassist-tool-bridge`

- Status: `ready_for_review`
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

- Added a manifest-driven `skydiscover-assist` CLI that fixes consumer inputs,
  output, working directory, launcher, and evaluator timeout before launch.
- Added a standard-library worker and SkyDiscover-side proxy so a consumer
  evaluator runs in its own interpreter and returns one JSON result document.
- Added path ownership checks, a zero-model-call evaluator import probe, focused
  tests, packaging entrypoint, and user documentation.

## Result and claim ceiling

The bridge imported the real BlindAssist C29 evaluator through BlindAssist's GPU
launcher without installing SkyDiscover in that environment. This establishes
the dependency and output boundary for cooperative evaluators; it is not a
security sandbox for malicious code and makes no scientific-performance claim.

## Validation and evidence

- `uv run pytest tests/test_assist.py tests/test_cli_positional_paths.py -q`:
  10 passed.
- Focused Black and isort checks passed.
- `uv run skydiscover-assist --help` passed.
- `uv build` produced both wheel and source distribution.
- Real BlindAssist C29 `check` transport probe passed with no model call.

## Important commits

- `8392124`: add isolated consumer assist bridge.

## Integration notes

Ready to integrate into `main`. A zero-model-call consumer transport probe is
required before any formal consumer run.

## Final disposition

Ready for review and integration.
