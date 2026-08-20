# `codex/remote-env-registry`

- Status: `validated_ready_for_integration`
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
- Added archive/member, metadata, runtime, libc, Python executable, size, and
  SHA-256 checks before accepting or reusing a portable bundle.
- Moved the documented AutoDL default to the persistent
  `/root/autodl-tmp/skydiscover` data volume.

## Evidence and claim ceiling

- Focused local tests: `26 passed`; Black, isort, focused mypy, and diff checks
  passed.
- On the designated 32-vCPU AutoDL host, building the final environment from an
  already populated package cache and capturing its 66 MB bundle completed in
  about 34 seconds. The first canary correctly failed before a verified marker
  when it exposed a generated-script newline escaping defect; the defect was
  fixed and covered by a regression assertion.
- After moving the exact environment, tools, and cache out of the registry to
  simulate a compatible new host, local bundle hydration completed in about 42
  seconds and read-only verify returned `ok: true` with no issues.
- A subsequent isolated task reused the verified environment; verify plus the
  hot bootstrap completed in about 17 seconds, with the bootstrap itself about
  12 seconds.
- Final environment key: `c203087905460e0b`; bundle SHA-256:
  `3502797d70b42ff5589ccb75fba0764ecc79877f421cfb9e5282334f914c2acc`.
- Claim ceiling: remote environment preparation efficiency only; no experiment
  or scientific performance claim.

## Readiness and disposition

Live build, empty-registry hydration, hot reuse, and read-only verification all
passed. Ready for integration after exact engineering backup cleanup and final
pre-push parity checks.
