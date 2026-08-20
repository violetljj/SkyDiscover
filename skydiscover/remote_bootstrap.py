"""Bootstrap and verify a mutable remote execution host for SkyDiscover.

The local checkout remains authoritative.  This tool streams the selected Git
commit to an isolated remote directory, creates a lockfile-backed environment,
and writes matching local and remote manifests.  It deliberately does not start
an experiment or a long-lived evaluation worker.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import textwrap
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

_MANIFEST_PREFIX = "SKYDISCOVER_BOOTSTRAP_MANIFEST="
_VERIFY_PREFIX = "SKYDISCOVER_BOOTSTRAP_VERIFY="
_TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_DEFAULT_UV_VERSION = "0.12.5"


class BootstrapError(RuntimeError):
    """Raised when remote bootstrap cannot complete safely."""


@dataclass(frozen=True)
class RemoteEndpoint:
    """Connection parameters for the currently designated remote host."""

    target: str
    port: int = 22
    strict_host_key_checking: str = "accept-new"

    def __post_init__(self) -> None:
        if not self.target or any(character.isspace() for character in self.target):
            raise ValueError("remote target must be a non-empty user@host value without spaces")
        if self.target.startswith("-"):
            raise ValueError("remote target must not start with '-'")
        if not 1 <= self.port <= 65535:
            raise ValueError("remote port must be between 1 and 65535")
        if self.strict_host_key_checking not in {"yes", "accept-new"}:
            raise ValueError("strict host key checking must be 'yes' or 'accept-new'")


@dataclass(frozen=True)
class BootstrapLayout:
    """Task-owned source paths plus one shared immutable environment."""

    task_root: str
    source_dir: str
    environment_root: str
    venv_dir: str
    environment_manifest_path: str
    tools_dir: str
    uv_cache_dir: str
    build_lock_dir: str
    manifest_path: str


def _run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a local command without a shell and capture its output."""

    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BootstrapError(f"command failed to start or timed out: {command[0]}: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no command output"
        raise BootstrapError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n{detail}"
        )
    return completed


def build_ssh_command(endpoint: RemoteEndpoint, *remote_command: str) -> list[str]:
    """Build a bounded, non-interactive SSH command for one control operation."""

    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        "-o",
        f"StrictHostKeyChecking={endpoint.strict_host_key_checking}",
        "-p",
        str(endpoint.port),
        endpoint.target,
        *remote_command,
    ]


def _run_remote(
    endpoint: RemoteEndpoint,
    script: str,
    *,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    command = build_ssh_command(endpoint, "bash", "-s")
    # Text-mode pipes on Windows translate LF to CRLF. Send bytes explicitly so
    # Linux bash never receives stray carriage returns.
    payload = script.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    try:
        raw = subprocess.run(
            command,
            input=payload,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BootstrapError(f"remote command failed to start or timed out: {exc}") from exc
    completed = subprocess.CompletedProcess(
        raw.args,
        raw.returncode,
        raw.stdout.decode("utf-8", errors="replace"),
        raw.stderr.decode("utf-8", errors="replace"),
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no command output"
        raise BootstrapError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n{detail}"
        )
    return completed


def _validate_remote_root(remote_root: str) -> str:
    path = PurePosixPath(remote_root)
    if (
        not path.is_absolute()
        or ".." in path.parts
        or remote_root == "/"
        or any(ord(character) < 32 for character in remote_root)
    ):
        raise ValueError("remote root must be an absolute, non-root POSIX path without '..'")
    return str(path)


def _validate_task_id(task_id: str) -> str:
    if not _TASK_ID_PATTERN.fullmatch(task_id):
        raise ValueError(
            "task id must start with an alphanumeric character and contain only "
            "letters, numbers, '.', '_', or '-'"
        )
    return task_id


def _git_commit(repo: Path, revision: str) -> str:
    completed = _run(["git", "rev-parse", f"{revision}^{{commit}}"], cwd=repo, timeout=30)
    return completed.stdout.strip()


def _git_file_sha256(repo: Path, commit: str, path: str) -> str:
    """Hash a file exactly as stored in the selected commit."""

    try:
        completed = subprocess.run(
            ["git", "show", f"{commit}:{path}"],
            cwd=repo,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BootstrapError(f"failed to read {path} from commit {commit}: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode(errors="replace").strip() or "no command output"
        raise BootstrapError(f"failed to read {path} from commit {commit}: {detail}")
    return hashlib.sha256(completed.stdout).hexdigest()


def _environment_key(
    pyproject_sha256: str,
    lock_sha256: str,
    extras: Sequence[str],
    *,
    runtime: Mapping[str, Any] | None = None,
    uv_version: str = _DEFAULT_UV_VERSION,
) -> str:
    payload = json.dumps(
        {
            "extras": sorted(set(extras)),
            "pyproject_sha256": pyproject_sha256,
            "runtime": dict(sorted((runtime or {}).items())),
            "uv_version": uv_version,
            "uv_lock_sha256": lock_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _layout(
    remote_root: str,
    task_id: str,
    commit: str,
    environment_key: str,
    *,
    uv_version: str = _DEFAULT_UV_VERSION,
) -> BootstrapLayout:
    task_root = posixpath.join(remote_root, task_id)
    environment_root = posixpath.join(remote_root, "_environments", environment_key)
    return BootstrapLayout(
        task_root=task_root,
        source_dir=posixpath.join(task_root, "source", commit),
        environment_root=environment_root,
        venv_dir=posixpath.join(environment_root, "venv"),
        environment_manifest_path=posixpath.join(environment_root, "verified.json"),
        tools_dir=posixpath.join(remote_root, "_tools", environment_key, f"uv-{uv_version}"),
        uv_cache_dir=posixpath.join(remote_root, "_uv-cache", environment_key),
        build_lock_dir=posixpath.join(remote_root, "_environment-locks", environment_key),
        manifest_path=posixpath.join(task_root, "manifests", f"{commit}-{environment_key}.json"),
    )


def _extract_prefixed_json(output: str, prefix: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        if line.startswith(prefix):
            try:
                value = json.loads(line[len(prefix) :])
            except json.JSONDecodeError as exc:
                raise BootstrapError(f"remote returned invalid JSON after {prefix}") from exc
            if not isinstance(value, dict):
                raise BootstrapError(f"remote returned a non-object JSON value after {prefix}")
            return value
    raise BootstrapError(f"remote output did not contain the expected {prefix} record")


def _python_locator_shell() -> str:
    return textwrap.dedent("""
        PYTHON_BIN=""
        for candidate in python3 python /root/miniconda3/bin/python; do
          if command -v "$candidate" >/dev/null 2>&1; then
            PYTHON_BIN=$(command -v "$candidate")
            break
          fi
          if [ -x "$candidate" ]; then
            PYTHON_BIN="$candidate"
            break
          fi
        done
        if [ -z "$PYTHON_BIN" ]; then
          echo "No Python interpreter found (tried python3, python, and AutoDL Miniconda)." >&2
          exit 20
        fi
        export PYTHON_BIN
        """).strip()


def preflight(
    endpoint: RemoteEndpoint,
    remote_root: str,
    *,
    timeout: int = 60,
) -> dict[str, Any]:
    """Run a read-only capability and workload inspection on the remote host."""

    remote_root = _validate_remote_root(remote_root)
    script = (
        f"""
set -eu
{_python_locator_shell()}
export SKYDISCOVER_REMOTE_ROOT={shlex.quote(remote_root)}
"$PYTHON_BIN" - <<'PY'
"""
        + r"""
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def command_output(command):
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def cpuset_count(value):
    if not value:
        return None
    count = 0
    try:
        for section in value.split(","):
            bounds = [int(part) for part in section.split("-", 1)]
            count += 1 if len(bounds) == 1 else bounds[1] - bounds[0] + 1
    except (TypeError, ValueError):
        return None
    return count


def quota_count(value):
    if not value or value.startswith("max "):
        return None
    try:
        quota, period = (int(part) for part in value.split())
    except (TypeError, ValueError):
        return None
    return max(1, quota // period) if period > 0 else None


root = Path(os.environ["SKYDISCOVER_REMOTE_ROOT"])
probe = root
while not probe.exists() and probe != probe.parent:
    probe = probe.parent
usage = shutil.disk_usage(probe)
process_output = command_output(["ps", "-eo", "pid=,etimes=,%cpu=,%mem=,args="]) or ""
relevant_processes = [
    line.strip()
    for line in process_output.splitlines()
    if "skydiscover" in line.lower() or str(root) in line
][:50]
locks = []
manifests = []
if root.exists():
    locks = [
        str(path)
        for path in root.glob("**/*.lock")
        if path.name != "uv.lock"
    ][:50]
    manifests = [str(path) for path in root.glob("**/manifests/*.json")][:50]
blocking_locks = [
    path
    for path in locks
    if not any(
        marker in path
        for marker in (
            "/venvs/",
            "/uv-cache/",
            "/bootstrap-tools/",
            "/_environments/",
            "/_tools/",
            "/_uv-cache/",
        )
    )
]
cpu_max = read_text("/sys/fs/cgroup/cpu.max")
cpuset = read_text("/sys/fs/cgroup/cpuset.cpus.effective")
cpu_limits = [value for value in (os.cpu_count(), cpuset_count(cpuset), quota_count(cpu_max)) if value]
payload = {
    "schema_version": 1,
    "status": "reachable",
    "hostname": platform.node(),
    "platform": platform.platform(),
    "platform_machine": platform.machine(),
    "platform_system": platform.system(),
    "python": platform.python_version(),
    "python_cache_tag": sys.implementation.cache_tag,
    "python_implementation": platform.python_implementation(),
    "python_executable": os.environ["PYTHON_BIN"],
    "cpu_count_host": os.cpu_count(),
    "cpu_count_visible": min(cpu_limits) if cpu_limits else None,
    "cpu_max": cpu_max,
    "cpuset": cpuset,
    "memory_current_bytes": read_text("/sys/fs/cgroup/memory.current"),
    "memory_limit_bytes": read_text("/sys/fs/cgroup/memory.max"),
    "disk_probe": str(probe),
    "disk_total_bytes": usage.total,
    "disk_free_bytes": usage.free,
    "remote_root": str(root),
    "remote_root_exists": root.exists(),
    "locks": locks,
    "blocking_locks": blocking_locks,
    "manifests": manifests,
    "relevant_processes": relevant_processes,
    "container_runtimes": [
        name
        for name in ("docker", "podman", "nerdctl", "apptainer", "singularity")
        if shutil.which(name)
    ],
}
print(json.dumps(payload, sort_keys=True))
"""
        + "\nPY\n"
    )
    completed = _run_remote(endpoint, script, timeout=timeout)
    try:
        payload = json.loads(completed.stdout.strip())
    except json.JSONDecodeError as exc:
        raise BootstrapError("remote preflight did not return valid JSON") from exc
    if not isinstance(payload, dict):
        raise BootstrapError("remote preflight returned a non-object JSON value")
    payload["endpoint"] = endpoint.target
    payload["port"] = endpoint.port
    return payload


def _git_archive_command(commit: str) -> list[str]:
    """Build a Git archive command that preserves committed LF bytes on Windows."""

    return ["git", "-c", "core.autocrlf=false", "archive", "--format=tar", commit]


def _stream_git_archive(
    endpoint: RemoteEndpoint,
    repo: Path,
    commit: str,
    source_dir: str,
    *,
    timeout: int,
) -> None:
    prepare_script = f"""
set -eu
mkdir -p {shlex.quote(source_dir)}
"""
    archive_command = _git_archive_command(commit)
    _run_remote(endpoint, prepare_script, timeout=min(timeout, 60))

    archive: subprocess.Popen[bytes] | None = None
    try:
        archive = subprocess.Popen(
            archive_command,
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        extract_command = build_ssh_command(endpoint, f"tar -xf - -C {shlex.quote(source_dir)}")
        assert archive.stdout is not None
        extracted = subprocess.run(
            extract_command,
            stdin=archive.stdout,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        archive.stdout.close()
        archive.wait(timeout=30)
        archive_stderr = archive.stderr.read() if archive.stderr else b""
    except (OSError, subprocess.TimeoutExpired) as exc:
        if archive is not None:
            archive.kill()
            archive.wait()
        raise BootstrapError(f"Git archive transfer failed or timed out: {exc}") from exc
    assert archive is not None
    if archive.returncode != 0:
        raise BootstrapError(
            f"git archive failed ({archive.returncode}): {archive_stderr.decode(errors='replace')}"
        )
    if extracted.returncode != 0:
        raise BootstrapError(
            "remote archive extraction failed "
            f"({extracted.returncode}): {extracted.stderr.decode(errors='replace')}"
        )


def _install_script(
    *,
    endpoint: RemoteEndpoint,
    layout: BootstrapLayout,
    task_id: str,
    commit: str,
    pyproject_sha256: str,
    lock_sha256: str,
    environment_key: str,
    runtime: Mapping[str, Any],
    bundle_hydrated: bool,
    extras: Sequence[str],
    uv_version: str | None,
) -> str:
    resolved_uv_version = uv_version or _DEFAULT_UV_VERSION
    uv_requirement = f"uv=={resolved_uv_version}"
    uv_extra_args = " ".join(f"--extra {shlex.quote(extra)}" for extra in extras)
    environment_seed = {
        "schema_version": 1,
        "status": "verified",
        "environment_key": environment_key,
        "pyproject_sha256": pyproject_sha256,
        "uv_lock_sha256": lock_sha256,
        "extras": sorted(set(extras)),
        "runtime": dict(sorted(runtime.items())),
        "uv_version": resolved_uv_version,
        "venv_dir": layout.venv_dir,
    }
    manifest_seed = {
        "schema_version": 1,
        "status": "ready",
        "endpoint": endpoint.target,
        "port": endpoint.port,
        "task_id": task_id,
        "source_commit": commit,
        "pyproject_sha256": pyproject_sha256,
        "uv_lock_sha256": lock_sha256,
        "extras": sorted(set(extras)),
        "task_root": layout.task_root,
        "source_dir": layout.source_dir,
        "environment_key": environment_key,
        "environment_runtime": dict(sorted(runtime.items())),
        "environment_uv_version": resolved_uv_version,
        "environment_root": layout.environment_root,
        "environment_manifest_path": layout.environment_manifest_path,
        "environment_bundle_hydrated": bundle_hydrated,
        "venv_dir": layout.venv_dir,
        "tools_dir": layout.tools_dir,
        "uv_cache_dir": layout.uv_cache_dir,
        "manifest_path": layout.manifest_path,
    }
    shell_header = f"""
set -eu
{_python_locator_shell()}
mkdir -p {shlex.quote(posixpath.dirname(layout.manifest_path))}
TASK_TOOLS_DIR={shlex.quote(layout.tools_dir)}
export UV_CACHE_DIR={shlex.quote(layout.uv_cache_dir)}
ENVIRONMENT_ROOT={shlex.quote(layout.environment_root)}
ENVIRONMENT_MANIFEST={shlex.quote(layout.environment_manifest_path)}
ENVIRONMENT_BUILD_LOCK={shlex.quote(layout.build_lock_dir)}
VENV_DIR={shlex.quote(layout.venv_dir)}
mkdir -p "$UV_CACHE_DIR" "$(dirname "$TASK_TOOLS_DIR")" "$(dirname "$ENVIRONMENT_ROOT")" "$(dirname "$ENVIRONMENT_BUILD_LOCK")"
if [ ! -x "$TASK_TOOLS_DIR/bin/uv" ]; then
  if ! mkdir "$TASK_TOOLS_DIR.build-lock" 2>/dev/null; then
    echo "uv tool installation is already active: $TASK_TOOLS_DIR.build-lock" >&2
    exit 26
  fi
  trap 'rm -rf -- "$TASK_TOOLS_DIR"; rmdir "$TASK_TOOLS_DIR.build-lock" 2>/dev/null || true' EXIT HUP INT TERM
  "$PYTHON_BIN" -m venv "$TASK_TOOLS_DIR"
  "$TASK_TOOLS_DIR/bin/python" -m pip install --disable-pip-version-check {shlex.quote(uv_requirement)}
  trap - EXIT HUP INT TERM
  rmdir "$TASK_TOOLS_DIR.build-lock"
fi
UV_BIN="$TASK_TOOLS_DIR/bin/uv"
if [ ! -x "$UV_BIN" ]; then
  echo "shared uv installation did not produce an executable at $UV_BIN" >&2
  exit 21
fi
export SKYDISCOVER_ENVIRONMENT_SEED={shlex.quote(json.dumps(environment_seed, sort_keys=True))}
export SKYDISCOVER_ENVIRONMENT_MANIFEST="$ENVIRONMENT_MANIFEST"
ENVIRONMENT_REUSED=0
if [ -f "$ENVIRONMENT_MANIFEST" ]; then
  "$PYTHON_BIN" - <<'PY'
import json
import os
import sys
from pathlib import Path

expected = json.loads(os.environ["SKYDISCOVER_ENVIRONMENT_SEED"])
path = Path(os.environ["SKYDISCOVER_ENVIRONMENT_MANIFEST"])
try:
    actual = json.loads(path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(1)
for key, value in expected.items():
    if actual.get(key) != value:
        raise SystemExit(1)
if not (Path(expected["venv_dir"]) / "bin" / "python").is_file():
    raise SystemExit(1)
PY
  ENVIRONMENT_REUSED=1
else
  if ! mkdir "$ENVIRONMENT_BUILD_LOCK" 2>/dev/null; then
    echo "environment build is already active: $ENVIRONMENT_BUILD_LOCK" >&2
    exit 25
  fi
  cleanup_environment_build() {{
    status=$?
    trap - EXIT HUP INT TERM
    if [ "$status" -ne 0 ]; then
      rm -rf -- "$VENV_DIR"
    fi
    rmdir "$ENVIRONMENT_BUILD_LOCK" 2>/dev/null || true
    exit "$status"
  }}
  trap cleanup_environment_build EXIT HUP INT TERM
  rm -rf -- "$VENV_DIR"
  export UV_PROJECT_ENVIRONMENT="$VENV_DIR"
  "$UV_BIN" sync --frozen --quiet --no-install-project --python "$PYTHON_BIN" --project {shlex.quote(layout.source_dir)} {uv_extra_args}
  export SKYDISCOVER_UV_BIN="$UV_BIN"
  "$PYTHON_BIN" - <<'PY'
import datetime
import json
import os
import subprocess
from pathlib import Path

manifest = json.loads(os.environ["SKYDISCOVER_ENVIRONMENT_SEED"])
manifest["completed_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
manifest["uv"] = subprocess.run(
    [os.environ["SKYDISCOVER_UV_BIN"], "--version"],
    text=True,
    capture_output=True,
    check=True,
).stdout.strip()
path = Path(os.environ["SKYDISCOVER_ENVIRONMENT_MANIFEST"])
path.parent.mkdir(parents=True, exist_ok=True)
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.replace(temporary, path)
PY
  trap - EXIT HUP INT TERM
  rmdir "$ENVIRONMENT_BUILD_LOCK"
fi
export SKYDISCOVER_MANIFEST_SEED={shlex.quote(json.dumps(manifest_seed, sort_keys=True))}
export SKYDISCOVER_UV_BIN="$UV_BIN"
export SKYDISCOVER_ENVIRONMENT_REUSED="$ENVIRONMENT_REUSED"
export SKYDISCOVER_MANIFEST_PREFIX={shlex.quote(_MANIFEST_PREFIX)}
"$PYTHON_BIN" - <<'PY'
"""
    remote_python = r"""
import datetime
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def cpuset_count(value):
    if not value:
        return None
    count = 0
    try:
        for section in value.split(","):
            bounds = [int(part) for part in section.split("-", 1)]
            count += 1 if len(bounds) == 1 else bounds[1] - bounds[0] + 1
    except (TypeError, ValueError):
        return None
    return count


def quota_count(value):
    if not value or value.startswith("max "):
        return None
    try:
        quota, period = (int(part) for part in value.split())
    except (TypeError, ValueError):
        return None
    return max(1, quota // period) if period > 0 else None


manifest = json.loads(os.environ["SKYDISCOVER_MANIFEST_SEED"])
venv_python = Path(manifest["venv_dir"]) / "bin" / "python"
cpu_max = read_text("/sys/fs/cgroup/cpu.max")
cpuset = read_text("/sys/fs/cgroup/cpuset.cpus.effective")
cpu_limits = [value for value in (os.cpu_count(), cpuset_count(cpuset), quota_count(cpu_max)) if value]
manifest.update(
    {
        "completed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "hostname": platform.node(),
        "platform": platform.platform(),
        "bootstrap_python": platform.python_version(),
        "environment_python": subprocess.run(
            [str(venv_python), "--version"], text=True, capture_output=True, check=True
        ).stdout.strip(),
        "environment_reused": os.environ["SKYDISCOVER_ENVIRONMENT_REUSED"] == "1",
        "uv": subprocess.run(
            [os.environ["SKYDISCOVER_UV_BIN"], "--version"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip(),
        "cpu_count_host": os.cpu_count(),
        "cpu_count_visible": min(cpu_limits) if cpu_limits else None,
        "cpu_max": cpu_max,
        "cpuset": cpuset,
        "memory_limit_bytes": read_text("/sys/fs/cgroup/memory.max"),
        "source_free_bytes": shutil.disk_usage(manifest["source_dir"]).free,
    }
)
path = Path(manifest["manifest_path"])
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.replace(temporary, path)
print(os.environ["SKYDISCOVER_MANIFEST_PREFIX"] + json.dumps(manifest, sort_keys=True))
"""
    return shell_header + remote_python + "\nPY\n"


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bundle_paths(bundle_cache: Path, environment_key: str) -> tuple[Path, Path]:
    return (
        bundle_cache / f"{environment_key}.tar.gz",
        bundle_cache / f"{environment_key}.json",
    )


def _validate_bundle_archive(bundle_path: Path, environment_key: str) -> None:
    allowed = {
        f"_environments/{environment_key}",
        f"_tools/{environment_key}",
    }
    try:
        with tarfile.open(bundle_path, "r:gz") as archive:
            members = archive.getmembers()
    except (OSError, tarfile.TarError) as exc:
        raise BootstrapError(f"environment bundle is invalid: {bundle_path}: {exc}") from exc
    if not members:
        raise BootstrapError(f"environment bundle is empty: {bundle_path}")
    for member in members:
        normalized = member.name.removeprefix("./").rstrip("/")
        if not any(normalized == root or normalized.startswith(f"{root}/") for root in allowed):
            raise BootstrapError(f"environment bundle has an unsafe member: {member.name}")
        if member.issym() or member.islnk():
            target = member.linkname
            safe_runtime_link = target.startswith("/root/miniconda3/bin/python")
            if (target.startswith("/") and not safe_runtime_link) or ".." in PurePosixPath(
                target
            ).parts:
                raise BootstrapError(
                    f"environment bundle has an unsafe link target: {member.name} -> {target}"
                )


def _remote_file_exists(
    endpoint: RemoteEndpoint,
    path: str,
    *,
    timeout: int,
) -> bool:
    command = build_ssh_command(endpoint, f"test -f {shlex.quote(path)}")
    try:
        completed = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BootstrapError(f"remote existence check failed: {exc}") from exc
    if completed.returncode not in {0, 1}:
        detail = completed.stderr.decode(errors="replace").strip() or "no command output"
        raise BootstrapError(f"remote existence check failed ({completed.returncode}): {detail}")
    return completed.returncode == 0


def _hydrate_environment_bundle(
    endpoint: RemoteEndpoint,
    remote_root: str,
    layout: BootstrapLayout,
    bundle_cache: Path,
    environment_key: str,
    runtime: Mapping[str, Any],
    uv_version: str,
    *,
    timeout: int,
) -> bool:
    if _remote_file_exists(
        endpoint,
        layout.environment_manifest_path,
        timeout=min(timeout, 60),
    ):
        return False
    bundle_path, metadata_path = _bundle_paths(bundle_cache, environment_key)
    if not bundle_path.is_file() or not metadata_path.is_file():
        return False
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BootstrapError(f"environment bundle metadata is invalid: {metadata_path}") from exc
    expected = {
        "environment_key": environment_key,
        "remote_root": remote_root,
        "runtime": dict(sorted(runtime.items())),
        "uv_version": uv_version,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise BootstrapError(f"environment bundle metadata mismatch: {key}")
    if metadata.get("bundle_sha256") != _file_sha256(bundle_path):
        raise BootstrapError("environment bundle hash mismatch")
    _validate_bundle_archive(bundle_path, environment_key)
    prepare = f"mkdir -p {shlex.quote(remote_root)} && tar -xzf - -C {shlex.quote(remote_root)}"
    command = build_ssh_command(endpoint, prepare)
    try:
        with bundle_path.open("rb") as bundle:
            completed = subprocess.run(
                command,
                stdin=bundle,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BootstrapError(f"environment bundle upload failed or timed out: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode(errors="replace").strip() or "no command output"
        raise BootstrapError(f"environment bundle upload failed ({completed.returncode}): {detail}")
    return True


def _capture_environment_bundle(
    endpoint: RemoteEndpoint,
    remote_root: str,
    layout: BootstrapLayout,
    bundle_cache: Path,
    environment_key: str,
    runtime: Mapping[str, Any],
    uv_version: str,
    *,
    timeout: int,
) -> tuple[Path, str]:
    bundle_path, metadata_path = _bundle_paths(bundle_cache, environment_key)
    if bundle_path.is_file() and metadata_path.is_file():
        return bundle_path, _file_sha256(bundle_path)
    bundle_cache.mkdir(parents=True, exist_ok=True)
    temporary = bundle_path.with_suffix(bundle_path.suffix + ".tmp")
    environment_relative = posixpath.relpath(layout.environment_root, remote_root)
    tools_relative = posixpath.relpath(posixpath.dirname(layout.tools_dir), remote_root)
    if any(".." in PurePosixPath(path).parts for path in (environment_relative, tools_relative)):
        raise BootstrapError("environment bundle paths escaped the remote registry root")
    command = build_ssh_command(
        endpoint,
        "tar -czf - "
        f"-C {shlex.quote(remote_root)} "
        f"{shlex.quote(environment_relative)} {shlex.quote(tools_relative)}",
    )
    try:
        with temporary.open("wb") as output:
            completed = subprocess.run(
                command,
                stdout=output,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        temporary.unlink(missing_ok=True)
        raise BootstrapError(f"environment bundle capture failed or timed out: {exc}") from exc
    if completed.returncode != 0:
        temporary.unlink(missing_ok=True)
        detail = completed.stderr.decode(errors="replace").strip() or "no command output"
        raise BootstrapError(
            f"environment bundle capture failed ({completed.returncode}): {detail}"
        )
    os.replace(temporary, bundle_path)
    _validate_bundle_archive(bundle_path, environment_key)
    bundle_sha256 = _file_sha256(bundle_path)
    _write_json_atomic(
        metadata_path,
        {
            "schema_version": 1,
            "environment_key": environment_key,
            "remote_root": remote_root,
            "runtime": dict(sorted(runtime.items())),
            "uv_version": uv_version,
            "bundle_sha256": bundle_sha256,
            "bundle_size_bytes": bundle_path.stat().st_size,
        },
    )
    return bundle_path, bundle_sha256


def bootstrap(
    endpoint: RemoteEndpoint,
    repo: Path,
    remote_root: str,
    task_id: str,
    *,
    revision: str = "HEAD",
    extras: Sequence[str] = ("dev",),
    uv_version: str | None = None,
    bundle_cache: Path | None = None,
    manifest_out: Path | None = None,
    timeout: int = 1800,
) -> dict[str, Any]:
    """Stage one commit and create a reproducible remote project environment."""

    repo = repo.resolve()
    remote_root = _validate_remote_root(remote_root)
    task_id = _validate_task_id(task_id)
    pyproject_path = repo / "pyproject.toml"
    lock_path = repo / "uv.lock"
    if not pyproject_path.is_file() or not lock_path.is_file():
        raise BootstrapError(f"repository must contain pyproject.toml and uv.lock: {repo}")
    commit = _git_commit(repo, revision)
    pyproject_sha256 = _git_file_sha256(repo, commit, "pyproject.toml")
    lock_sha256 = _git_file_sha256(repo, commit, "uv.lock")
    resolved_uv_version = uv_version or _DEFAULT_UV_VERSION
    host_inspection = preflight(endpoint, remote_root, timeout=min(timeout, 60))
    runtime = {
        key: host_inspection.get(key)
        for key in (
            "platform_machine",
            "platform_system",
            "python",
            "python_cache_tag",
            "python_implementation",
        )
    }
    if any(value in (None, "") for value in runtime.values()):
        raise BootstrapError("remote preflight did not return a complete runtime fingerprint")
    environment_key = _environment_key(
        pyproject_sha256,
        lock_sha256,
        extras,
        runtime=runtime,
        uv_version=resolved_uv_version,
    )
    layout = _layout(
        remote_root,
        task_id,
        commit,
        environment_key,
        uv_version=resolved_uv_version,
    )

    inspection = preflight(endpoint, layout.task_root, timeout=min(timeout, 60))
    if inspection.get("blocking_locks") or inspection.get("relevant_processes"):
        raise BootstrapError(
            "remote task root has active processes or locks; choose a new task id or wait "
            "for the existing task to reach a terminal state"
        )

    resolved_bundle_cache = (
        bundle_cache.resolve()
        if bundle_cache is not None
        else (repo / ".runs" / "remote-environments").resolve()
    )
    bundle_hydrated = _hydrate_environment_bundle(
        endpoint,
        remote_root,
        layout,
        resolved_bundle_cache,
        environment_key,
        runtime,
        resolved_uv_version,
        timeout=timeout,
    )

    # This is intentionally a one-time streamed deployment, not a per-evaluation
    # SSH/SCP workflow.
    _stream_git_archive(endpoint, repo, commit, layout.source_dir, timeout=timeout)
    completed = _run_remote(
        endpoint,
        _install_script(
            endpoint=endpoint,
            layout=layout,
            task_id=task_id,
            commit=commit,
            pyproject_sha256=pyproject_sha256,
            lock_sha256=lock_sha256,
            environment_key=environment_key,
            runtime=runtime,
            bundle_hydrated=bundle_hydrated,
            extras=extras,
            uv_version=resolved_uv_version,
        ),
        timeout=timeout,
    )
    manifest = _extract_prefixed_json(completed.stdout, _MANIFEST_PREFIX)
    if manifest.get("hostname") != inspection.get("hostname"):
        raise BootstrapError("remote host identity changed between preflight and bootstrap")
    bundle_path, bundle_sha256 = _capture_environment_bundle(
        endpoint,
        remote_root,
        layout,
        resolved_bundle_cache,
        environment_key,
        runtime,
        resolved_uv_version,
        timeout=timeout,
    )
    manifest["environment_bundle_path"] = str(bundle_path.resolve())
    manifest["environment_bundle_sha256"] = bundle_sha256
    destination = manifest_out or (
        repo / ".runs" / "remote-bootstrap" / f"{task_id}-{commit[:12]}.json"
    )
    _write_json_atomic(destination, manifest)
    manifest["local_manifest_path"] = str(destination.resolve())
    return manifest


def verify(
    endpoint: RemoteEndpoint,
    repo: Path,
    remote_root: str,
    task_id: str,
    *,
    revision: str = "HEAD",
    extras: Sequence[str] = ("dev",),
    uv_version: str | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    """Verify a bootstrapped environment without mutating it."""

    repo = repo.resolve()
    remote_root = _validate_remote_root(remote_root)
    task_id = _validate_task_id(task_id)
    commit = _git_commit(repo, revision)
    pyproject_sha256 = _git_file_sha256(repo, commit, "pyproject.toml")
    lock_sha256 = _git_file_sha256(repo, commit, "uv.lock")
    resolved_uv_version = uv_version or _DEFAULT_UV_VERSION
    host_inspection = preflight(endpoint, remote_root, timeout=min(timeout, 60))
    runtime = {
        key: host_inspection.get(key)
        for key in (
            "platform_machine",
            "platform_system",
            "python",
            "python_cache_tag",
            "python_implementation",
        )
    }
    if any(value in (None, "") for value in runtime.values()):
        raise BootstrapError("remote preflight did not return a complete runtime fingerprint")
    layout = _layout(
        remote_root,
        task_id,
        commit,
        _environment_key(
            pyproject_sha256,
            lock_sha256,
            extras,
            runtime=runtime,
            uv_version=resolved_uv_version,
        ),
        uv_version=resolved_uv_version,
    )
    expected = {
        "endpoint": endpoint.target,
        "port": endpoint.port,
        "task_id": task_id,
        "source_commit": commit,
        "pyproject_sha256": pyproject_sha256,
        "uv_lock_sha256": lock_sha256,
        "extras": sorted(set(extras)),
        "source_dir": layout.source_dir,
        "environment_key": posixpath.basename(layout.environment_root),
        "environment_runtime": dict(sorted(runtime.items())),
        "environment_uv_version": resolved_uv_version,
        "environment_manifest_path": layout.environment_manifest_path,
        "venv_dir": layout.venv_dir,
        "manifest_path": layout.manifest_path,
    }
    shell_header = f"""
set -eu
{_python_locator_shell()}
export SKYDISCOVER_MANIFEST_PATH={shlex.quote(layout.manifest_path)}
export SKYDISCOVER_EXPECTED={shlex.quote(json.dumps(expected, sort_keys=True))}
export SKYDISCOVER_VERIFY_PREFIX={shlex.quote(_VERIFY_PREFIX)}
"$PYTHON_BIN" - <<'PY'
"""
    remote_python = r"""
import hashlib
import json
import os
import subprocess
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


path = Path(os.environ["SKYDISCOVER_MANIFEST_PATH"])
expected = json.loads(os.environ["SKYDISCOVER_EXPECTED"])
issues = []
manifest = None
if not path.is_file():
    issues.append("manifest_missing")
else:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        issues.append("manifest_invalid")
if isinstance(manifest, dict):
    for key, value in expected.items():
        if manifest.get(key) != value:
            issues.append(f"manifest_mismatch:{key}")
environment_path = Path(expected["environment_manifest_path"])
environment = None
if not environment_path.is_file():
    issues.append("environment_manifest_missing")
else:
    try:
        environment = json.loads(environment_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        issues.append("environment_manifest_invalid")
if isinstance(environment, dict):
    environment_expected = {
        "status": "verified",
        "environment_key": expected["environment_key"],
        "pyproject_sha256": expected["pyproject_sha256"],
        "uv_lock_sha256": expected["uv_lock_sha256"],
        "extras": expected["extras"],
        "runtime": expected["environment_runtime"],
        "uv_version": expected["environment_uv_version"],
        "venv_dir": expected["venv_dir"],
    }
    for key, value in environment_expected.items():
        if environment.get(key) != value:
            issues.append(f"environment_manifest_mismatch:{key}")
source = Path(expected["source_dir"])
if not source.is_dir():
    issues.append("source_missing")
else:
    for name, key in (("pyproject.toml", "pyproject_sha256"), ("uv.lock", "uv_lock_sha256")):
        candidate = source / name
        if not candidate.is_file() or sha256(candidate) != expected[key]:
            issues.append(f"source_hash_mismatch:{name}")
venv_python = Path(expected["venv_dir"]) / "bin" / "python"
if not venv_python.is_file():
    issues.append("venv_python_missing")
else:
    result = subprocess.run(
        [str(venv_python), "-c", "import skydiscover"],
        cwd=source,
        env={**os.environ, "PYTHONPATH": str(source), "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        issues.append("skydiscover_import_failed")
payload = {
    "schema_version": 1,
    "status": "verified" if not issues else "invalid",
    "ok": not issues,
    "issues": issues,
    "manifest_path": str(path),
    "source_commit": expected["source_commit"],
}
print(os.environ["SKYDISCOVER_VERIFY_PREFIX"] + json.dumps(payload, sort_keys=True))
"""
    script = shell_header + remote_python + "\nPY\n"
    completed = _run_remote(endpoint, script, timeout=timeout)
    result = _extract_prefixed_json(completed.stdout, _VERIFY_PREFIX)
    result["endpoint"] = endpoint.target
    result["port"] = endpoint.port
    return result


def _add_endpoint_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--target",
        help="Mutable SSH target (user@host); defaults to SKYDISCOVER_REMOTE_TARGET",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="SSH port; defaults to SKYDISCOVER_REMOTE_PORT or 22",
    )
    parser.add_argument(
        "--strict-host-key-checking",
        choices=("yes", "accept-new"),
        default="accept-new",
        help="OpenSSH host-key policy (default: accept-new)",
    )
    parser.add_argument(
        "--remote-root",
        default=os.environ.get("SKYDISCOVER_REMOTE_ROOT", "/root/autodl-tmp/skydiscover"),
        help="Task-owned remote root",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skydiscover-remote-bootstrap",
        description="Preflight, bootstrap, and verify a mutable SkyDiscover execution host.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight_parser = subparsers.add_parser("preflight", help="Read-only host inspection")
    _add_endpoint_arguments(preflight_parser)
    preflight_parser.add_argument("--timeout", type=int, default=60)

    bootstrap_parser = subparsers.add_parser(
        "bootstrap", help="Stage the current commit and synchronize its environment"
    )
    _add_endpoint_arguments(bootstrap_parser)
    bootstrap_parser.add_argument("--repo", type=Path, default=Path.cwd())
    bootstrap_parser.add_argument("--task-id", default="skydiscover")
    bootstrap_parser.add_argument("--revision", default="HEAD")
    bootstrap_parser.add_argument("--extra", action="append", dest="extras")
    bootstrap_parser.add_argument("--uv-version")
    bootstrap_parser.add_argument("--bundle-cache", type=Path)
    bootstrap_parser.add_argument("--manifest-out", type=Path)
    bootstrap_parser.add_argument("--timeout", type=int, default=1800)

    verify_parser = subparsers.add_parser("verify", help="Read-only environment verification")
    _add_endpoint_arguments(verify_parser)
    verify_parser.add_argument("--repo", type=Path, default=Path.cwd())
    verify_parser.add_argument("--task-id", default="skydiscover")
    verify_parser.add_argument("--revision", default="HEAD")
    verify_parser.add_argument("--extra", action="append", dest="extras")
    verify_parser.add_argument("--uv-version")
    verify_parser.add_argument("--timeout", type=int, default=60)
    return parser


def _endpoint_from_args(args: argparse.Namespace) -> RemoteEndpoint:
    target = args.target or os.environ.get("SKYDISCOVER_REMOTE_TARGET")
    if not target:
        raise ValueError("pass --target or set SKYDISCOVER_REMOTE_TARGET")
    port_value = args.port
    if port_value is None:
        raw_port = os.environ.get("SKYDISCOVER_REMOTE_PORT", "22")
        try:
            port_value = int(raw_port)
        except ValueError as exc:
            raise ValueError("SKYDISCOVER_REMOTE_PORT must be an integer") from exc
    return RemoteEndpoint(
        target=target,
        port=port_value,
        strict_host_key_checking=args.strict_host_key_checking,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Console entry point."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        endpoint = _endpoint_from_args(args)
        if args.command == "preflight":
            result = preflight(endpoint, args.remote_root, timeout=args.timeout)
        elif args.command == "bootstrap":
            result = bootstrap(
                endpoint,
                args.repo,
                args.remote_root,
                args.task_id,
                revision=args.revision,
                extras=args.extras or ("dev",),
                uv_version=args.uv_version,
                bundle_cache=args.bundle_cache,
                manifest_out=args.manifest_out,
                timeout=args.timeout,
            )
        else:
            result = verify(
                endpoint,
                args.repo,
                args.remote_root,
                args.task_id,
                revision=args.revision,
                extras=args.extras or ("dev",),
                uv_version=args.uv_version,
                timeout=args.timeout,
            )
    except (BootstrapError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.command == "verify" and not result.get("ok", False):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
