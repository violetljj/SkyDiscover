#!/usr/bin/env python3
"""Persistent, task-owned evaluator data-plane worker for COMPONENT-2."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = ROOT / "benchmarks/blindassist_last10m_struct_component_1"
BASE_EVALUATOR = ROOT / "benchmarks/blindassist_last10m_v3/evaluator/evaluator.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _expanded(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scenarios = copy.deepcopy(raw)
    for scenario in scenarios:
        defaults = scenario.pop("node_defaults", {})
        defaults.setdefault("rgb_ref", None)
        scenario["nodes"] = [{**defaults, **node} for node in scenario["nodes"]]
    return scenarios


def evaluate(request: dict[str, Any]) -> dict[str, Any]:
    request_id = request["request_id"]
    source = request["candidate_source"]
    arm = request["arm"]
    mode = request["mode"]
    raw_scenarios = request["scenarios"]
    with tempfile.TemporaryDirectory(prefix="l10m_component_2_worker_") as temp:
        candidate_path = Path(temp) / "candidate.py"
        candidate_path.write_text(source, encoding="utf-8", newline="\n")
        guard = _load(BASE / "candidate_guard.py", f"component_2_worker_guard_{request_id}")
        guard.validate_path(candidate_path, arm)
        base = _load(BASE_EVALUATOR, f"component_2_worker_evaluator_{request_id}")
        scenarios = _expanded(raw_scenarios)
        base._load_scenarios = lambda requested_mode: copy.deepcopy(scenarios)
        result = base.evaluate(str(candidate_path), mode)
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {
        "request_id": request_id,
        "status": "COMPLETED",
        "result": result,
        "result_sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }


def main() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = evaluate(request)
        except Exception as exc:
            response = {
                "request_id": request.get("request_id") if isinstance(request, dict) else None,
                "status": "ARM_RELATED_EVALUATOR_FAILURE",
                "error": f"{type(exc).__name__}: {exc}",
            }
        print(json.dumps(response, sort_keys=True, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
