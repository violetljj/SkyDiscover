# `codex/remote-bootstrap`

- Status: `ready_for_review`
- Owner: project work branch
- Base: `main` at `1b34d32543ab2060d7abf8be7e6dbcb2c3375678`
- Head reviewed for this record: `a1d3b91` (local-control/remote-evaluation boundary)
- Integration target: `main`
- Integrated commit: `not integrated`

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

Integrate the focused implementation and documentation into `main` after review.
Keep remote validation directories, manifests, and caches outside the repository;
they are task-owned execution evidence, not source changes. A future evaluator
transport should land as a separate focused component and pass a zero-model-call
transport canary before formal use.
