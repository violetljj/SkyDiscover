# AGENTS.md

This file applies to the entire repository unless a more specific `AGENTS.md`
exists in a subdirectory.

## Project overview

SkyDiscover is a Python framework for AI-driven scientific and algorithmic
discovery. The installable package lives in `skydiscover/`; tests live in
`tests/`; benchmark definitions and examples live in `benchmarks/`, `examples/`,
and `configs/`; the documentation site lives in `docs/`.

## Environment and commands

- Supported Python versions: 3.10 through 3.13.
- Use `uv` and the committed `uv.lock` for dependency management.
- Install development dependencies with `uv sync --frozen --extra dev`.
- Run a focused test with `uv run pytest path/to/test.py -v`.
- Run the test suite with `uv run pytest tests/ -v` when the change warrants it.
- Check formatting with `uv run black --check skydiscover/`.
- Check imports with `uv run isort --check skydiscover/`.
- Build the package with `uv build` for packaging or release-related changes.

Some benchmarks require optional extras. Install only the relevant extra, as
documented in `README.md` or the benchmark's own README.

## Working conventions

- Keep changes scoped to the requested task and preserve unrelated worktree
  changes, generated outputs, checkpoints, and benchmark artifacts.
- Prefer the smallest implementation that satisfies the requested behavior.
- Follow the existing public APIs, configuration patterns, and type annotations.
- Format Python with Black's configured 100-character line length and keep
  imports compatible with the configured isort Black profile.
- Add or update focused tests for behavior changes. Do not weaken, skip, or
  delete existing tests merely to make a change pass.
- Do not commit credentials, API keys, private benchmark data, model outputs,
  or large generated artifacts.
- Treat evaluators, benchmark inputs, expected results, receipts, and blind-test
  data as evidence boundaries. Do not modify them to improve reported results
  unless the task explicitly requires correcting the evaluation protocol.
- Treat `main` as the stable project integration baseline, not an archive of
  every experiment. Only selectively integrate reusable implementation code,
  tests, and concise experiment summaries after they have been reviewed and
  validated.
- Keep frozen experiment protocols, cohorts, hidden inputs, execution
  manifests, receipts, and detailed result artifacts on their task branches or
  immutable tags. Do not wholesale-merge an experimental branch into `main`
  merely to preserve its evidence; link to the source branch or commit instead.
- When an experiment yields a durable project change, create an isolated
  integration branch from the latest `origin/main`, select only the intended
  paths or commits, validate them, and then merge deliberately. Preserve the
  original experiment branch and evidence boundary.
- Keep claims proportional to the evidence. A smoke test, reused task, or single
  benchmark result does not establish general superiority.

## Validation

Run the narrowest checks that cover the changed surface:

- Treat execution efficiency as a requirement for all work: prefer focused
  checks and avoid full-suite or full-repository tests unless the change's scope,
  risk, or an explicit delivery gate genuinely requires them.

- Documentation/configuration-only changes: validate the affected format,
  schema, links, or configuration loading.
- Isolated Python changes: run the affected tests and relevant format checks.
- Shared APIs or module-level behavior: run the relevant module tests plus the
  package import smoke test.
- Cross-cutting, dependency, build-system, or packaging changes: run the full
  tests, formatting/import checks, and `uv build` as applicable.

If a required check depends on unavailable credentials, services, containers,
hardware, or private data, report that limitation rather than fabricating or
silently substituting evidence.

## Git hygiene

- Inspect `git status` before editing and before delivery.
- Never discard or overwrite unrelated user changes.
- Keep tasks isolated: establish task-owned paths before editing, do not mix
  unrelated changes into the same commit, and use separate branches or
  worktrees for concurrent tasks when their write scopes could overlap.
- Keep task-specific outputs, caches, checkpoints, temporary files, processes,
  ports, and external resources isolated. Clean up only resources owned by the
  current task.
- At the end of every successfully completed task that changes tracked project
  files, automatically stage only task-owned paths, create a focused commit,
  and push the current branch without waiting for a separate request.
- Before pushing, verify the upstream relationship and stop rather than merge,
  rebase, force-push, or include overlapping work when the remote has diverged,
  credentials are unavailable, or task ownership is ambiguous.
- Do not rewrite history, force-push, or open a pull request unless explicitly
  requested.

## Official upstream isolation

SkyDiscover is expected to absorb updates from the official project regularly.
Keep official history, local integration, and task development visibly separate
so upstream synchronization remains safe and auditable.

- Treat `upstream` as the read-only official repository and `origin` as the
  writable project fork. Never push branches, tags, or other refs to `upstream`.
- Treat `upstream/main` as an immutable official baseline. Do not place local
  commits on it, rewrite it, or represent a local integration branch as an
  official branch.
- Keep local project development on focused `codex/<task>` branches created from
  the current project integration branch. Push task branches only to `origin`.
- Keep official-update integration separate from feature work. An upstream-sync
  commit or branch must contain only the official update and necessary conflict
  resolutions; it must not include unrelated local features, experiments,
  generated outputs, or cleanup.
- Before integrating an official update, require a clean or explicitly isolated
  worktree, run `git fetch --prune upstream`, inspect the commit graph and numeric
  divergence, and stop if branch ownership or the intended integration target is
  ambiguous.
- Integrate upstream changes through an isolated synchronization branch or
  worktree, validate the affected surface, and only then update the project
  integration branch. Do not merge upstream directly into an active task branch.
- Keep local feature commits narrowly scoped and independently reviewable so
  they can be rebased, replayed, dropped, or repaired without modifying official
  commits or benchmark evidence.
- Do not reset `origin/main` to `upstream/main`, rename the integration branch,
  change the remote default branch, rebase published project history, or perform
  any other migration without explicit user authorization and a verified
  rollback plan.
- Before every push, verify that the destination remote is `origin`, the target
  branch is intentional, and the remote is not unexpectedly divergent. Stop
  rather than automatically merging, rebasing, or force-pushing.
