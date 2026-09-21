"""SkyDiscover-side proxy for an evaluator owned by another project."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from skydiscover.optimize.evaluation import EvaluationResult

SCHEMA = "skydiscover-assist-evaluation-v1"
_COMMAND_ENV = "SKYDISCOVER_ASSIST_EVALUATOR_COMMAND"
_EVALUATOR_ENV = "SKYDISCOVER_ASSIST_EVALUATOR"
_WORKER_ENV = "SKYDISCOVER_ASSIST_WORKER"
_WORKDIR_ENV = "SKYDISCOVER_ASSIST_WORKING_DIRECTORY"
_TIMEOUT_ENV = "SKYDISCOVER_ASSIST_EVALUATOR_TIMEOUT_S"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing assist bridge environment variable: {name}")
    return value


def _decode_payload(process: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    if process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip()
        raise RuntimeError(f"consumer evaluator exited {process.returncode}: {detail[-4000:]}")
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("consumer evaluator did not return one JSON document") from exc
    if payload.get("schema") != SCHEMA or payload.get("status") != "ok":
        raise RuntimeError(f"consumer evaluator protocol failure: {payload.get('error', payload)}")
    return payload


def evaluate(program_path: str) -> EvaluationResult:
    command = json.loads(_required(_COMMAND_ENV))
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part for part in command)
    ):
        raise RuntimeError("consumer evaluator command must be a non-empty JSON string list")
    worker = str(Path(_required(_WORKER_ENV)).resolve(strict=True))
    evaluator = str(Path(_required(_EVALUATOR_ENV)).resolve(strict=True))
    working_directory = str(Path(_required(_WORKDIR_ENV)).resolve(strict=True))
    timeout_s = float(_required(_TIMEOUT_ENV))
    try:
        process = subprocess.run(
            command + [worker, "evaluate", "--evaluator", evaluator, "--program", program_path],
            cwd=working_directory,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"consumer evaluator timed out after {timeout_s:g}s") from exc
    payload = _decode_payload(process)
    return EvaluationResult(
        metrics={str(key): float(value) for key, value in payload["metrics"].items()},
        artifacts={
            str(key): json.dumps(value) if not isinstance(value, str) else value
            for key, value in payload.get("artifacts", {}).items()
        },
    )
