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

## Preferred remote execution

- Prefer the AutoDL host most recently designated by the user as the primary
  execution worker for suitable SkyDiscover tasks. The remote endpoint is
  mutable infrastructure, not a permanent project constant. The currently
  designated endpoint is
  `ssh -p 24564 root@connect.westb.seetacloud.com`; a later endpoint supplied by
  the user supersedes it. Do not assume a historical host or port is still
  current, and do not bake it into code as a permanent default. Record the
  resolved endpoint in task manifests and receipts for provenance. If the
  current remote is unavailable, unhealthy, or incompatible with the task,
  continue on the local machine instead of letting remote setup block useful
  work.
- Before dispatch, perform a read-only preflight of SSH access, active jobs and
  locks, CPU and memory pressure, disk space, and required runtimes. Do not
  disturb work already running on the host.
- Use the project tool `uv run skydiscover-remote-bootstrap preflight` for that
  inspection. After a new endpoint, Python/OS image, or task environment is
  selected, run `bootstrap` once for the exact commit and requested extras, then
  run `verify` before launching work. Do not hand-copy a virtual environment or
  repeat bootstrap for every candidate iteration.
- Treat `bootstrap` as environment preparation only; it must not be used as the
  experiment or evaluation transport. Start a persistent worker/channel only
  after verification, and keep its task IDs, receipts, and reconnect semantics
  separate. Use Docker or another container backend only when preflight confirms
  that runtime is available; the portable baseline is the detected Python plus
  lockfile-backed uv environment.
- Treat the remote host as an execution-only worker. Codex Desktop/CLI, model
  provider calls, source editing, Git operations, experiment control, evidence
  aggregation, and final adjudication remain local. Do not install, invoke, or
  route the project's Codex CLI through the remote host; remote processes may
  execute only the already-staged project code and explicitly scoped evaluators.
- The intended architecture is a local control plane and a remote evaluation
  data plane: the local frozen controller/protocol, Codex generation, candidate
  store, dispatch journal, evidence ledger, analysis, and closeout remain local;
  only CPU-heavy evaluator workers run remotely. A remote worker may receive
  candidate source, scenario/arm, seed, and idempotency key, and may return
  metrics, artifact hashes, and a receipt, but the local controller validates the
  response and remains the authority that creates terminal receipts.
- A persistent evaluator channel is a separate engineering component from
  bootstrap. The current `remote-bootstrap` tool only prepares and verifies an
  environment; it does not implement this transport and must not be presented
  as if it does. Before a formal experiment uses remote evaluation, implement
  the worker/dispatch protocol and pass a zero-model-call transport canary.
  Preserve sealed failed generation units and do not resume them merely because
  the transport later becomes available.
- Treat dependency setup as an environment lifecycle, not an experiment step.
  The target design is an immutable, content-addressed environment registry
  keyed by the committed dependency lock, extras, Python/runtime and platform;
  build and verify each fingerprint once, then reuse it read-only across
  experiments. Keep each experiment's evaluator workers, logs, checkpoints,
  receipts, locks, and process groups in its own task root. The current
  task-local bootstrap is the safe baseline until that shared immutable registry
  is implemented; do not claim cross-experiment reuse before then.
- Use the remote host's available capacity aggressively when it improves
  turnaround time: dynamically size parallelism to the process-visible CPU and
  memory limits, keep useful workers busy, and avoid nested BLAS, OpenMP, or
  subprocess oversubscription. Preserve enough headroom for supervision,
  checkpoints, and reliable completion.
- Isolate each task by project, commit, job ID, working directory, environment,
  output root, logs, locks, caches, process group, and resource limits. Keep the
  local workspace authoritative for source control and evidence; bring back and
  verify required outputs, checkpoints, receipts, and provenance before treating
  remote execution as complete.
- Assume the remote host is shared with other projects. Never install packages
  into global Python/Conda environments, mutate global shell startup files, or
  share writable pip/uv caches, temporary roots, ports, locks, or process groups.
  Use the bootstrap tool's task-owned tool environment and cache, and remove or
  terminate only exact resources created by the current task; never perform
  broad cleanup or kill processes belonging to another project.
- For iterative or high-frequency evaluation, do not use a fresh SSH/SCP session
  for every operation or repeatedly transfer the repository or Git bundle. Stage
  the frozen code, protocol, and environment once, then use a persistent SSH
  channel or long-lived remote worker per evaluation slot. Send only the minimal
  per-iteration payload, such as the candidate hash and code, seed, and request
  identifier, and use keepalives plus bounded reconnection to recover the same
  remote job.
- Journal each external dispatch before sending it and after completion, assign
  an idempotency key, and create evaluation receipts atomically. After a channel
  loss, query the existing remote job and receipt before taking further action.
  If dispatch may have occurred but consumption cannot be proved either way,
  classify the attempt as `in_doubt`, count it conservatively against the frozen
  budget, and do not rerun it automatically.
- A series of successful SSH probes establishes only momentary reachability, not
  the reliability of a high-frequency short-connection design. Routine work may
  fall back to local execution after remote failure, but an active frozen or
  evidence-critical experiment must not silently change execution environments;
  stop or resume it only under its preregistered recovery rules.
- Do not leave the rented host idle after its work reaches a terminal state;
  remind the user to shut it down in the AutoDL console.

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
- Keep claims proportional to the evidence. A smoke test, reused task, or single
  benchmark result does not establish general superiority.

## Blind-run monitoring

- Blind discipline prohibits feeding hidden outcomes back into the run or using
  interim results to change code, budgets, samples, stopping rules, retries, or
  rerun decisions. It does not prohibit read-only inspection of sealed scores.
- For long-running evaluated work, monitor both execution health and scoring
  health. Read-only inspection of sealed interim scores can detect failures such
  as all-zero or constant output, missing fields, arm collapse, evaluator wiring
  errors, or implausible score distributions before the entire run is spent.
- Clearly label partial score summaries as interim and keep the preregistered
  complete-cohort analysis authoritative. Continue the frozen run unless its
  protocol already defines an applicable stopping condition or an actual
  integrity failure makes continuation invalid.
- Apply evidence safeguards according to the risk they control. Do not withhold
  useful diagnostics merely to preserve a stronger form of operator blindness
  that the frozen protocol did not require.

## Windows task launcher constraints

- Long-running or concurrent benchmark launchers must not create visible
  PowerShell or Windows Terminal windows. Use hidden, non-interactive child
  processes with redirected stdout/stderr (for PowerShell, include
  `-WindowStyle Hidden`; for `ProcessStartInfo`, set `UseShellExecute = $false`
  and `CreateNoWindow = $true`).
- Use one persistent hidden launcher to supervise workers; do not open one
  foreground terminal per unit or per arm. Record each worker's command, PID,
  log paths, exit code, and receipt outcome in the task log.
- Stopping a run must use a controlled cancellation path that drains and
  records workers before releasing locks. Users must not need to close terminal
  windows to stop a run; closing a console is treated as an interruption and
  may yield `STATUS_CONTROL_C_EXIT` without a receipt.
- Before resuming after interruption, inspect authoritative output roots,
  receipts, locks, and worker state. Skip sealed receipts, classify units with
  no receipt as unconsumed/failed according to the frozen protocol, and never
  overwrite or silently rerun a sealed unit.

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
- Every project-owned work branch must have a durable record under
  `docs/branch-ledger/branches/`, using the branch name with `/` replaced by
  `__` as the filename. Create it with the branch's first meaningful commit;
  update it only at material scope/status changes and before handoff, integration,
  abandonment, or deletion. Do not create empty placeholder records.
- Each branch record must state its purpose, base branch and base commit,
  task-owned scope, dependencies, work performed, current status, evidence-backed
  result and claim ceiling, validation, important commits, integration target and
  readiness/blockers, and final disposition. Use `unknown` or `not run` rather
  than inventing missing historical facts.
- Keep one file per branch so concurrent branches do not edit a shared status
  table. Review the branch record together with its diff before integration;
  integration is incomplete until the record reflects the integrated commit or
  exact blocker. Preserve completed records after branch deletion as project
  history.
- Use `codex/<task>` branches for ordinary code, feature, and experiment work.
  Small clean documentation, configuration, or governance changes may use the
  intended integration branch directly. Use a separate worktree when active WIP,
  processes, concurrent work, or rollback risk requires physical isolation.
- Keep task-specific outputs, caches, checkpoints, temporary files, processes,
  ports, and external resources isolated. Clean up only resources owned by the
  current task.
- At the end of a meaningful completed change, stage only task-owned paths,
  create a focused commit, and push to `origin` without waiting for a separate
  request. Consecutive clarifications to one governance change may share a
  single delivery; intermediate edits do not each require a commit.
- Use one pre-push check: verify staged scope, destination remote and branch,
  upstream relationship, credentials, and numeric divergence. Stop rather than
  merge, rebase, force-push, or absorb unrelated work when any result is unsafe
  or ambiguous.
- Do not rewrite history, force-push, or open a pull request unless explicitly
  requested.

## Official upstream isolation

SkyDiscover is expected to absorb updates from the official project regularly.
Keep official history, local integration, and task development visibly separate
so upstream synchronization remains safe and auditable.

- Treat `upstream` as the read-only official repository, `upstream/main` as the
  immutable official baseline, and `origin` as the writable project fork. Never
  push branches, tags, or other refs to `upstream`.
- Keep official-update integration separate from feature work. An upstream-sync
  commit or branch must contain only the official update and necessary conflict
  resolutions; it must not include unrelated local features, experiments,
  generated outputs, or cleanup.
- Before integration, run `git fetch --prune upstream`, inspect the graph and
  numeric divergence, and validate the affected surface. A clean inactive
  `main` may integrate directly; use an isolated branch or worktree when WIP,
  active processes, conflicts, concurrent work, or ownership uncertainty exists.
- Treat an official synchronization as incomplete if the validated result exists
  only in temporary state. If conflicts are resolved, relevant validation passes,
  evidence boundaries remain intact, ownership is clear, and `origin/main` has
  not diverged unexpectedly, immediately update and push `origin/main` without a
  second user request, then verify numeric parity. Otherwise leave `main`
  unchanged and report the exact blocker.
- Do not inject the new `main` into an already running experiment or iterative
  campaign. Keep the active run on its frozen commit; make the updated official
  functionality available to new work immediately, and update existing task
  branches only at a safe checkpoint or before their next run.
- Do not reset `origin/main` to `upstream/main`, rename the integration branch,
  change the remote default branch, rebase published project history, or perform
  any other migration without explicit user authorization and a verified
  rollback plan.
