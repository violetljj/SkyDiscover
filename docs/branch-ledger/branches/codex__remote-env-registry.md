# `codex/remote-env-registry`

- Status: `implementation_validation_in_progress`
- Owner: project work branch
- Base: `origin/main` at `4817547`
- Integration target: `main`
- Integrated commit: `not integrated`

## Purpose

Make new AutoDL task environments start quickly by building each dependency
fingerprint once on the persistent data volume and reusing it across isolated
tasks.

## Task-owned scope

- `skydiscover/remote_bootstrap.py`
- `tests/test_remote_bootstrap.py`
- `docs/remote-execution.md`
- `AGENTS.md`
- this branch record

## Work performed

- Split task-owned source and manifests from the shared dependency registry.
- Bound environment fingerprints to dependency semantics, lockfiles, extras,
  the Python executable/ABI, libc, platform, and a pinned uv version without
  invalidating reusable dependencies for unrelated project metadata edits.
- Installed dependencies with `--no-install-project` so a shared environment
  never points to another task's source checkout.
- Added atomic environment build locks, verified markers, and cache-hit
  provenance.
- Added a local content-addressed tar bundle for hydrating an empty compatible
  AutoDL registry without repeating a cold dependency sync.
- Moved the documented AutoDL default to the persistent
  `/root/autodl-tmp/skydiscover` data volume.

## Evidence and claim ceiling

- Focused local tests: `23 passed` before live remote validation.
- Real cold-build and cache-hit timing: pending.
- Claim ceiling: remote environment preparation efficiency only; no experiment
  or scientific performance claim.

## Readiness and disposition

Pending live cold-build, second-task cache-hit, verify, cleanup, and integration
review.
