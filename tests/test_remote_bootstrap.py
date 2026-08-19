"""Focused tests for the remote bootstrap controller."""

import json
import subprocess
from pathlib import Path

import pytest

import skydiscover.remote_bootstrap as remote_bootstrap
from skydiscover.remote_bootstrap import (
    BootstrapError,
    RemoteEndpoint,
    _endpoint_from_args,
    _environment_key,
    _extract_prefixed_json,
    _layout,
    _validate_remote_root,
    _validate_task_id,
    _write_json_atomic,
    build_parser,
    build_ssh_command,
)


def test_build_ssh_command_is_noninteractive_and_kept_alive() -> None:
    endpoint = RemoteEndpoint("root@example.test", 24564)

    command = build_ssh_command(endpoint, "bash", "-s")

    assert command[0] == "ssh"
    assert "BatchMode=yes" in command
    assert "ServerAliveInterval=15" in command
    assert "ServerAliveCountMax=3" in command
    assert command[-3:] == ["root@example.test", "bash", "-s"]
    assert command[command.index("-p") + 1] == "24564"


def test_run_remote_sends_lf_bytes_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_input = b""

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal captured_input
        captured_input = kwargs["input"]  # type: ignore[assignment]
        return subprocess.CompletedProcess(command, 0, stdout=b"ok", stderr=b"")

    monkeypatch.setattr(remote_bootstrap.subprocess, "run", fake_run)

    result = remote_bootstrap._run_remote(
        RemoteEndpoint("root@example.test"), "set -eu\r\nprintf ok\r\n", timeout=10
    )

    assert captured_input == b"set -eu\nprintf ok\n"
    assert result.stdout == "ok"


@pytest.mark.parametrize("port", [0, 65536])
def test_endpoint_rejects_invalid_port(port: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 65535"):
        RemoteEndpoint("root@example.test", port)


@pytest.mark.parametrize("root", ["relative/path", "/", "/root/../tmp"])
def test_remote_root_must_be_bounded(root: str) -> None:
    with pytest.raises(ValueError, match="absolute, non-root"):
        _validate_remote_root(root)


@pytest.mark.parametrize("task_id", ["", "../task", "task/name", "-task"])
def test_task_id_rejects_path_traversal_and_option_like_values(task_id: str) -> None:
    with pytest.raises(ValueError, match="task id"):
        _validate_task_id(task_id)


def test_layout_is_content_addressed() -> None:
    layout = _layout(
        "/root/autodl-tmp/skydiscover",
        "trial-01",
        "a" * 40,
        "env123",
    )

    assert layout.source_dir.endswith(f"/trial-01/source/{'a' * 40}")
    assert layout.venv_dir.endswith("/trial-01/venvs/env123")
    assert layout.manifest_path.endswith(f"/trial-01/manifests/{'a' * 40}-env123.json")


def test_environment_key_is_order_independent_and_extra_sensitive() -> None:
    first = _environment_key("project", "lock", ["dev", "math"])
    reordered = _environment_key("project", "lock", ["math", "dev", "dev"])
    different = _environment_key("project", "lock", ["dev"])

    assert first == reordered
    assert first != different


def test_extract_prefixed_json_uses_last_matching_record() -> None:
    output = 'noise\nRESULT={"attempt": 1}\nmore\nRESULT={"attempt": 2}\n'

    assert _extract_prefixed_json(output, "RESULT=") == {"attempt": 2}


def test_extract_prefixed_json_rejects_missing_record() -> None:
    with pytest.raises(BootstrapError, match="expected"):
        _extract_prefixed_json("noise only", "RESULT=")


def test_preflight_builds_remote_python_without_formatting_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_script = ""

    def fake_run_remote(
        endpoint: RemoteEndpoint, script: str, *, timeout: int
    ) -> subprocess.CompletedProcess[str]:
        nonlocal captured_script
        captured_script = script
        return subprocess.CompletedProcess([], 0, stdout='{"status": "reachable"}', stderr="")

    monkeypatch.setattr(remote_bootstrap, "_run_remote", fake_run_remote)

    result = remote_bootstrap.preflight(
        RemoteEndpoint("root@example.test", 24564),
        "/root/autodl-tmp/skydiscover",
    )

    assert "payload = {" in captured_script
    assert '"cpu_count_visible": min(cpu_limits)' in captured_script
    assert result["endpoint"] == "root@example.test"


def test_install_script_preserves_remote_python_dict_literals() -> None:
    layout = _layout("/root/autodl-tmp/skydiscover", "trial", "a" * 40, "env123")

    script = remote_bootstrap._install_script(
        endpoint=RemoteEndpoint("root@example.test", 24564),
        layout=layout,
        task_id="trial",
        commit="a" * 40,
        pyproject_sha256="project",
        lock_sha256="lock",
        extras=("dev",),
        uv_version=None,
    )

    assert "manifest.update(" in script
    assert '"completed_at_utc":' in script
    assert "SKYDISCOVER_BOOTSTRAP_MANIFEST=" in script


def test_bootstrap_stops_before_transfer_when_task_root_is_active(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    monkeypatch.setattr(remote_bootstrap, "_git_commit", lambda repo, revision: "a" * 40)
    monkeypatch.setattr(
        remote_bootstrap, "_git_file_sha256", lambda repo, commit, path: f"hash-{path}"
    )
    monkeypatch.setattr(
        remote_bootstrap,
        "preflight",
        lambda endpoint, remote_root, timeout: {
            "hostname": "worker",
            "locks": [f"{remote_root}/active.lock"],
            "relevant_processes": [],
        },
    )

    def unexpected_transfer(*args: object, **kwargs: object) -> None:
        raise AssertionError("archive transfer must not start while a task lock exists")

    monkeypatch.setattr(remote_bootstrap, "_stream_git_archive", unexpected_transfer)

    with pytest.raises(BootstrapError, match="active processes or locks"):
        remote_bootstrap.bootstrap(
            RemoteEndpoint("root@example.test"),
            tmp_path,
            "/root/autodl-tmp/skydiscover",
            "active-task",
        )


def test_endpoint_comes_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKYDISCOVER_REMOTE_TARGET", "root@new-host.example")
    monkeypatch.setenv("SKYDISCOVER_REMOTE_PORT", "32100")
    args = build_parser().parse_args(["preflight"])

    endpoint = _endpoint_from_args(args)

    assert endpoint.target == "root@new-host.example"
    assert endpoint.port == 32100


def test_explicit_endpoint_supersedes_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKYDISCOVER_REMOTE_TARGET", "root@old-host.example")
    monkeypatch.setenv("SKYDISCOVER_REMOTE_PORT", "2200")
    args = build_parser().parse_args(
        ["preflight", "--target", "root@current-host.example", "--port", "24564"]
    )

    endpoint = _endpoint_from_args(args)

    assert endpoint.target == "root@current-host.example"
    assert endpoint.port == 24564


def test_atomic_manifest_write(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "manifest.json"

    _write_json_atomic(destination, {"status": "ready"})

    assert json.loads(destination.read_text(encoding="utf-8")) == {"status": "ready"}
    assert not destination.with_suffix(".json.tmp").exists()
