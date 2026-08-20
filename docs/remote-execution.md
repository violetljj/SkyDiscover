# Remote execution bootstrap

SkyDiscover treats AutoDL endpoints as mutable execution infrastructure. The
local checkout remains authoritative; the remote host receives a content-addressed
archive of one Git commit and resolves its dependencies from a shared
content-addressed environment registry.

## Configure the current endpoint

Supply the endpoint at runtime rather than editing source code. In PowerShell:

```powershell
$env:SKYDISCOVER_REMOTE_TARGET = "root@connect.westb.seetacloud.com"
$env:SKYDISCOVER_REMOTE_PORT = "24564"
```

When the rented host changes, replace these values with the endpoint most
recently supplied by the user. The tool has no permanent AutoDL hostname or port
default.

## Preflight

Run the read-only inspection before dispatching work:

```powershell
uv run skydiscover-remote-bootstrap preflight
```

The report includes the actual endpoint, host identity, process-visible CPU and
memory limits, disk availability, existing task manifests and locks, and
SkyDiscover processes under the task-owned root. It also reports any available
container runtime.

## Bootstrap

Stage a task and resolve its dependency environment:

```powershell
uv run skydiscover-remote-bootstrap bootstrap --task-id campaign-r4 --extra dev
```

The command:

1. resolves the requested local Git commit;
2. streams that commit once with `git archive` over SSH;
3. locates the remote Python installation, including AutoDL Miniconda;
4. resolves a shared `uv` tool pinned by version;
5. fingerprints dependency-relevant `pyproject.toml` fields, `uv.lock`, extras,
   Python executable/ABI, libc, platform, and `uv` version; unrelated project
   metadata and entry-point edits do not force a dependency rebuild;
6. reuses the verified environment for that fingerprint, or runs one guarded
   cold `uv sync --no-install-project` when it is absent; and
7. atomically writes a remote manifest and a matching local manifest under
   `.runs/remote-bootstrap/`.

Use the default `/root/autodl-tmp/skydiscover` root on AutoDL so the registry is
stored on the persistent XFS data volume rather than the small overlay system
disk. Reusable dependencies and mutable task state are separated:

```text
/root/autodl-tmp/skydiscover/
  _environments/<fingerprint>/venv
  _environments/<fingerprint>/verified.json
  _environment-locks/<fingerprint>
  _tools/<fingerprint>/uv-<version>
  _uv-cache/<fingerprint>
  <task-id>/source/<commit>
  <task-id>/manifests/<commit>-<fingerprint>.json
```

The shared environment contains dependencies only. SkyDiscover itself is loaded
from each task's staged frozen source, so reuse cannot silently substitute code
from an earlier task. A hit is recorded as `environment_reused: true` in the
task manifest.

After the first compatible cold build, bootstrap also saves a validated portable
bundle under `.runs/remote-environments/<fingerprint>.tar.gz`. On a later AutoDL
instance with an empty data volume, the tool verifies the bundle hash and member
paths, streams that single archive, and hydrates the same registry path before
running verification. This avoids another PyPI resolution and per-package cold
sync. Use `--bundle-cache <path>` to place these machine-owned bundles outside
the repository's default `.runs/` location.

Use repeated `--extra` arguments for additional project extras. Use
`--uv-version` when a protocol requires a specifically frozen `uv` release.
Bootstrap is infrastructure preparation only: it does not start an experiment,
consume a scientific evaluation, or create a persistent evaluation worker.

## Docker and other container runtimes

A container image can reduce dependency setup when a future remote host exposes
Docker, Podman, or Apptainer. It does not replace SSH endpoint discovery,
resource preflight, persistent job transport, manifests, receipts, or reconnect
semantics. AutoDL instances are commonly containers themselves and may not
expose a nested container runtime, so the bootstrap tool uses `uv` and an
isolated virtual environment as the portable baseline. Select a containerized
execution backend only after `preflight` reports that the runtime is actually
available; do not attempt to install or start a host-level container daemon from
inside a rented worker.

## Verify

Before launching work, verify the staged commit, lockfiles, environment, and
package import without modifying the remote host:

```powershell
uv run skydiscover-remote-bootstrap verify --task-id campaign-r4 --extra dev
```

Exit code `0` means the environment matches. Exit code `2` means verification
completed but found a mismatch. Transport or configuration failures return exit
code `1`.

For high-frequency evaluation, start a persistent worker after bootstrap and
reuse its channel. Do not invoke this bootstrap command for every candidate.
