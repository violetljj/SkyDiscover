"""Local evaluator facade that dispatches consumed DEV work to a remote worker."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from transport import RemoteEvaluationClient

_CLIENT: RemoteEvaluationClient | None = None
_SCENARIOS: list[dict[str, Any]] | None = None


def _client() -> RemoteEvaluationClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = RemoteEvaluationClient(
            Path(os.environ["L10M_LONG_REMOTE_MANIFEST"]),
            Path(os.environ["L10M_LONG_DISPATCH_JOURNAL"]),
            os.environ["L10M_LONG_WORKER_ID"],
        )
    return _CLIENT


def _scenarios() -> list[dict[str, Any]]:
    global _SCENARIOS
    if _SCENARIOS is None:
        _SCENARIOS = json.loads(
            Path(os.environ["L10M_LONG_DEV_SCENARIOS"]).read_text(encoding="utf-8")
        )
    return _SCENARIOS


def evaluate(program_path: str) -> dict[str, Any]:
    source = Path(program_path).read_text(encoding="utf-8")
    return _client().evaluate(
        candidate_source=source,
        scenarios=_scenarios(),
        arm=os.environ["L10M_LONG_ARM"],
        mode="train",
    )


def close() -> None:
    global _CLIENT
    if _CLIENT is not None:
        _CLIENT.close()
        _CLIENT = None
