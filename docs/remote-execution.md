# Remote execution bootstrap

SkyDiscover treats AutoDL endpoints as mutable execution infrastructure. The
local checkout remains authoritative; the remote host receives a content-addressed
archive of one Git commit plus a lockfile-backed environment.

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

Create or refresh an isolated environment for a task:

```powershell
uv run skydiscover-remote-bootstrap bootstrap --task-id campaign-r4 --extra dev
```

The command:

1. resolves the requested local Git commit;
2. streams that commit once with `git archive` over SSH;
3. locates the remote Python installation, including AutoDL Miniconda;
4. installs `uv` for the remote user when it is absent;
5. runs `uv sync --frozen` in a content-addressed virtual environment; and
6. atomically writes a remote manifest and a matching local manifest under
   `.runs/remote-bootstrap/`.

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
