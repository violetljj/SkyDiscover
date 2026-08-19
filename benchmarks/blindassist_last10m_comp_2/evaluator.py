#!/usr/bin/env python3
"""Development-only adapter for one frozen L10M-COMP-2 instance."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BASE_EVALUATOR = ROOT / "benchmarks" / "blindassist_last10m_v3" / "evaluator" / "evaluator.py"
SCENARIO_ENV = "L10M_COMP2_DEV_SCENARIOS"


def _load_base():
    spec = importlib.util.spec_from_file_location("l10m_comp_2_base_evaluator", BASE_EVALUATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load frozen L10M-ORACLE-3 evaluator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _expanded_scenarios(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    scenarios = copy.deepcopy(raw)
    for scenario in scenarios:
        defaults = scenario.pop("node_defaults", {})
        defaults.setdefault("rgb_ref", None)
        scenario["nodes"] = [{**defaults, **node} for node in scenario["nodes"]]
    return scenarios


def evaluate(program_path: str, mode: str = "train") -> dict[str, Any]:
    """Evaluate against only the development split selected by the harness."""
    if mode != "train":
        raise ValueError("COMP-2 search adapter accepts train mode only")
    selected = os.environ.get(SCENARIO_ENV)
    if not selected:
        raise RuntimeError(f"{SCENARIO_ENV} must be set by the COMP-2 harness")
    scenario_path = Path(selected).resolve()
    if scenario_path.name != "dev.json" or not scenario_path.is_file():
        raise RuntimeError("COMP-2 development scenario path is invalid")
    base = _load_base()
    scenarios = _expanded_scenarios(scenario_path)
    base._load_scenarios = lambda requested_mode: copy.deepcopy(scenarios)
    return base.evaluate(program_path, "train")
