#!/usr/bin/env python3
"""COMPONENT-2 evaluator adapter: local controller dispatches to AutoDL."""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from transport import RemoteEvaluationClient  # noqa: E402

_CLIENTS: dict[str, RemoteEvaluationClient] = {}


def expanded_scenarios(path: Path) -> list[dict[str, Any]]:
    scenarios = copy.deepcopy(json.loads(path.read_text(encoding="utf-8")))
    for scenario in scenarios:
        defaults = scenario.pop("node_defaults", {})
        defaults.setdefault("rgb_ref", None)
        scenario["nodes"] = [{**defaults, **node} for node in scenario["nodes"]]
    return scenarios


def _client() -> RemoteEvaluationClient:
    manifest = Path(os.environ["L10M_STRUCT_COMPONENT_2_REMOTE_MANIFEST"]).resolve()
    worker_id = os.environ["L10M_STRUCT_COMPONENT_2_REMOTE_WORKER_ID"]
    key = f"{manifest}:{worker_id}"
    if key not in _CLIENTS:
        journal = Path(os.environ["L10M_STRUCT_COMPONENT_2_REMOTE_JOURNAL_ROOT"])
        _CLIENTS[key] = RemoteEvaluationClient(manifest, journal, worker_id)
    return _CLIENTS[key]


def evaluate(program_path: str, mode: str = "train") -> dict[str, Any]:
    if mode not in {"train", "test"}:
        raise ValueError("COMPONENT-2 remote adapter accepts train or test mode only")
    scenario_env = (
        "L10M_STRUCT_COMPONENT_2_DEV_SCENARIOS"
        if mode == "train"
        else "L10M_STRUCT_COMPONENT_2_HIDDEN_SCENARIOS"
    )
    selected = os.environ.get(scenario_env)
    arm = os.environ.get("L10M_STRUCT_COMPONENT_2_ARM")
    if not selected or arm is None:
        raise RuntimeError("scenario and arm must be assigned by the frozen harness")
    path = Path(selected).resolve()
    if not path.is_file() or path.name not in {"dev.json", "hidden.json"}:
        raise RuntimeError("scenario path is invalid")
    source = Path(program_path).read_text(encoding="utf-8")
    return _client().evaluate(
        candidate_source=source,
        scenarios=json.loads(path.read_text(encoding="utf-8")),
        arm=arm,
        mode=mode,
        request_id=None,
    )


def close_clients() -> None:
    for client in _CLIENTS.values():
        client.close()
    _CLIENTS.clear()
