"""Isolated bridge for using SkyDiscover as another project's auxiliary tool."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

JOB_SCHEMA = "skydiscover-assist-job-v1"
RESULT_SCHEMA = "skydiscover-assist-check-v1"


class AssistError(RuntimeError):
    """An invalid or unavailable consumer bridge configuration."""


@dataclass(frozen=True)
class AssistJob:
    manifest: Path
    consumer: str
    working_directory: Path
    initial_program: Path
    evaluator: Path
    config: Path
    output: Path
    evaluator_command: tuple[str, ...]
    evaluator_timeout_s: float


def _path(base: Path, value: Any, field: str, *, must_exist: bool = True) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise AssistError(f"{field} must be a non-empty path string")
    candidate = Path(os.path.expandvars(value)).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    candidate = candidate.resolve(strict=must_exist)
    return candidate


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def load_job(manifest: Path, evaluator_launcher: Optional[str] = None) -> AssistJob:
    manifest = manifest.resolve(strict=True)
    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssistError(f"cannot read job manifest {manifest}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != JOB_SCHEMA:
        raise AssistError(f"job schema must be {JOB_SCHEMA!r}")
    base = manifest.parent
    consumer = raw.get("consumer")
    if not isinstance(consumer, str) or not consumer.strip():
        raise AssistError("consumer must be a non-empty string")
    working_directory = _path(base, raw.get("working_directory", "."), "working_directory")
    if not working_directory.is_dir():
        raise AssistError("working_directory must be a directory")
    initial_program = _path(base, raw.get("initial_program"), "initial_program")
    evaluator = _path(base, raw.get("evaluator"), "evaluator")
    config = _path(base, raw.get("config"), "config")
    for field, path in (
        ("initial_program", initial_program),
        ("evaluator", evaluator),
        ("config", config),
    ):
        if not path.is_file():
            raise AssistError(f"{field} must be a file: {path}")
    output = _path(base, raw.get("output"), "output", must_exist=False)
    project_root = Path(__file__).resolve().parents[1]
    if _is_within(output, project_root):
        raise AssistError(f"output must be outside the SkyDiscover checkout: {project_root}")

    command_value: Any = (
        [evaluator_launcher] if evaluator_launcher else raw.get("evaluator_command")
    )
    if isinstance(command_value, str):
        command_value = [command_value]
    if not isinstance(command_value, list) or not command_value:
        raise AssistError("evaluator_command must be a non-empty string list")
    command: list[str] = []
    for index, part in enumerate(command_value):
        if not isinstance(part, str) or not part.strip():
            raise AssistError("evaluator_command entries must be non-empty strings")
        expanded = os.path.expandvars(part)
        if index == 0 and ("/" in expanded or "\\" in expanded):
            expanded = str(_path(base, expanded, "evaluator_command[0]"))
        command.append(expanded)
    timeout_value = raw.get("evaluator_timeout_s", 300)
    if not isinstance(timeout_value, (int, float)) or timeout_value <= 0:
        raise AssistError("evaluator_timeout_s must be positive")
    return AssistJob(
        manifest=manifest,
        consumer=consumer.strip(),
        working_directory=working_directory,
        initial_program=initial_program,
        evaluator=evaluator,
        config=config,
        output=output,
        evaluator_command=tuple(command),
        evaluator_timeout_s=float(timeout_value),
    )


def _worker_path() -> Path:
    return Path(__file__).resolve().parent / "optimize" / "evaluation" / "subprocess_worker.py"


def _probe(job: AssistJob) -> dict[str, Any]:
    process = subprocess.run(
        list(job.evaluator_command)
        + [str(_worker_path()), "probe", "--evaluator", str(job.evaluator)],
        cwd=job.working_directory,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=job.evaluator_timeout_s,
        check=False,
    )
    if process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip()
        raise AssistError(f"evaluator transport probe failed: {detail[-4000:]}")
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise AssistError("evaluator transport probe returned invalid JSON") from exc
    if payload.get("status") != "ok":
        raise AssistError(f"evaluator transport probe failed: {payload}")
    return payload


def _summary(job: AssistJob) -> dict[str, Any]:
    return {
        "schema": RESULT_SCHEMA,
        "status": "ok",
        "consumer": job.consumer,
        "manifest": str(job.manifest),
        "working_directory": str(job.working_directory),
        "initial_program": str(job.initial_program),
        "evaluator": str(job.evaluator),
        "config": str(job.config),
        "output": str(job.output),
        "evaluator_command": list(job.evaluator_command),
        "environment_boundary": "subprocess-json",
    }


def _run(job: AssistJob, extra_args: Sequence[str]) -> int:
    job.output.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(
        {
            "SKYDISCOVER_ASSIST_EVALUATOR_COMMAND": json.dumps(job.evaluator_command),
            "SKYDISCOVER_ASSIST_EVALUATOR": str(job.evaluator),
            "SKYDISCOVER_ASSIST_WORKER": str(_worker_path()),
            "SKYDISCOVER_ASSIST_WORKING_DIRECTORY": str(job.working_directory),
            "SKYDISCOVER_ASSIST_EVALUATOR_TIMEOUT_S": str(job.evaluator_timeout_s),
        }
    )
    proxy = Path(__file__).resolve().parent / "optimize" / "evaluation" / "subprocess_proxy.py"
    command = [
        sys.executable,
        "-m",
        "skydiscover.optimize.cli",
        str(job.initial_program),
        str(proxy),
        "--config",
        str(job.config),
        "--output",
        str(job.output),
        *extra_args,
    ]
    return subprocess.run(
        command,
        cwd=job.working_directory,
        env=environment,
        check=False,
    ).returncode


def _validate_forwarded_args(extra_args: Sequence[str]) -> None:
    protected = {"--config", "-c", "--output", "-o"}
    for part in extra_args:
        option = part.split("=", 1)[0]
        if option in protected:
            raise AssistError(f"{option} is owned by the assist manifest and cannot be forwarded")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run SkyDiscover as an isolated auxiliary tool for another project"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "run"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("manifest")
        subparser.add_argument(
            "--evaluator-launcher",
            help="Override the manifest's evaluator command with one launcher path",
        )
        if name == "run":
            subparser.add_argument(
                "args",
                nargs=argparse.REMAINDER,
                help="Arguments after -- are forwarded to skydiscover-run",
            )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        job = load_job(Path(args.manifest), args.evaluator_launcher)
        _probe(job)
        print(json.dumps(_summary(job), indent=2, sort_keys=True))
        if args.command == "check":
            return 0
        extra_args = list(args.args)
        if extra_args and extra_args[0] == "--":
            extra_args = extra_args[1:]
        _validate_forwarded_args(extra_args)
        return _run(job, extra_args)
    except (AssistError, OSError, subprocess.SubprocessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
