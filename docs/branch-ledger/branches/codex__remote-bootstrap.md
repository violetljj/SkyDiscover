# `codex/remote-bootstrap`

- Status: `integrated`
- Owner: project work branch
- Base: `main` at `1b34d32543ab2060d7abf8be7e6dbcb2c3375678`
- Head reviewed for this record: `92c22cc` (completed remote workflow policy)
- Integration target: `main`
- Integrated commit: `92c22cc` (fast-forwarded into `main`)

## Purpose

Provide a repeatable bootstrap and verification tool for mutable, shared remote
execution hosts without moving Codex control or evidence authority off the local
machine.

## Scope and dependencies

- Owns `skydiscover/remote_bootstrap.py`, its focused tests, the remote execution
  documentation, the README entry, and the project script registration.
- Depends on local `uv`, Git, and the user's current SSH endpoint.
- The remote host is execution-only; Codex CLI, model calls, Git, control, and
  evidence aggregation remain local.

## Work performed

- Added `preflight`, `bootstrap`, and `verify` CLI commands with mutable endpoint
  selection, content-addressed source/venv paths, task-local uv tools/cache,
  manifests, and shared-host resource checks.
- Added Windows-safe LF transport and committed-byte archive hashing.
- Added guidance for persistent evaluation channels and Docker as an optional
  backend only when the remote runtime is actually available.
- Clarified that the intended next layer is a local-control/remote-evaluation
  transport; this branch does not implement or claim that channel.
- Recorded the target follow-up design: immutable content-addressed environments
  reused read-only across experiments, with task-owned execution roots; the
  current implementation remains task-local.
- Added the operating requirement that remote jobs remain under read-only,
  evidence-backed supervision through a verified terminal receipt or explicit
  handoff; monitoring and durable evaluator transport remain follow-up work.

## Result and claim ceiling

The tool completed a real bootstrap and verification on the currently designated
AutoDL host with Python 3.12.3, uv 0.12.5, 32 effective CPUs, and a 60 GiB memory
limit. This demonstrates environment preparation and verification for that host;
it does not establish remote experiment reliability or scientific performance.

## Validation and evidence

- Focused tests: `uv run pytest tests/test_remote_bootstrap.py -q` (22 passed).
- Formatting/import checks: Black, isort, and focused mypy passed.
- Packaging: `uv build` passed.
- Remote smoke: bootstrap and verify returned `ok: true` on the designated host.

## Important commits

- `b786016`: add remote environment bootstrap tool.
- `a74d2c2`: classify task cache locks as nonblocking.

## Integration notes

Fast-forwarded the focused implementation and documentation into `main` after
review and repeated the targeted validation on the integrated tree. Keep remote
validation directories, manifests, and caches outside the repository; they are
task-owned execution evidence, not source changes. A future evaluator transport
should land as a separate focused component and pass a zero-model-call transport
canary before formal use.

## Final disposition

Integrated into `main` at `92c22cc`. The source branch is retained as historical
delivery context; no active experiment should switch commits until its own safe
checkpoint or next run.
