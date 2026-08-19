#!/usr/bin/env python3
"""Development-only guarded adapter for L10M-STRUCT-COMPONENT-1."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASE_EVALUATOR = ROOT / "benchmarks" / "blindassist_last10m_v3" / "evaluator" / "evaluator.py"
SCENARIO_ENV = "L10M_STRUCT_COMPONENT_1_DEV_SCENARIOS"
ARM_ENV = "L10M_STRUCT_COMPONENT_1_ARM"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def expanded_scenarios(path: Path) -> list[dict[str, Any]]:
    scenarios = copy.deepcopy(json.loads(path.read_text(encoding="utf-8")))
    for scenario in scenarios:
        defaults = scenario.pop("node_defaults", {})
        defaults.setdefault("rgb_ref", None)
        scenario["nodes"] = [{**defaults, **node} for node in scenario["nodes"]]
    return scenarios


def evaluate(program_path: str, mode: str = "train") -> dict[str, Any]:
    if mode != "train":
        raise ValueError("COMPONENT-1 generation adapter accepts train mode only")
    selected = os.environ.get(SCENARIO_ENV)
    arm = os.environ.get(ARM_ENV)
    if not selected or arm is None:
        raise RuntimeError("scenario and arm must be assigned by the frozen harness")
    scenario_path = Path(selected).resolve()
    if scenario_path.name != "dev.json" or not scenario_path.is_file():
        raise RuntimeError("development scenario path is invalid")
    guard = _load_module(HERE / "candidate_guard.py", "l10m_struct_component_1_guard")
    guard.validate_path(Path(program_path), arm)
    base = _load_module(BASE_EVALUATOR, "l10m_struct_component_1_base_evaluator")
    scenarios = expanded_scenarios(scenario_path)
    base._load_scenarios = lambda requested_mode: copy.deepcopy(scenarios)
    return base.evaluate(program_path, "train")
