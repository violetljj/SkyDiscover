"""Focused tests for the L10M-ORACLE-1 closed-loop benchmark."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmarks" / "blindassist_last10m"
EVALUATOR_PATH = BENCHMARK / "evaluator" / "evaluator.py"
BASELINE_PATH = BENCHMARK / "initial_program.py"


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def evaluator():
    return _module(EVALUATOR_PATH, "l10m_evaluator_test")


def test_scenario_split_and_required_coverage(evaluator):
    dev = evaluator._load_scenarios("train")
    hidden = evaluator._load_scenarios("test")
    assert len(dev) == 8
    assert len(hidden) == 4
    assert {scenario["id"] for scenario in dev}.isdisjoint(scenario["id"] for scenario in hidden)
    assert sum(len(scenario["nodes"]) for scenario in dev + hidden) >= 40
    for scenario in dev + hidden:
        nodes = {node["id"] for node in scenario["nodes"]}
        assert scenario["start"] in nodes
        assert all(node["rgb_ref"] is None for node in scenario["nodes"])
        assert all(
            destination in nodes
            for node in scenario["nodes"]
            for destination in node.get("transitions", {}).values()
        )


def test_viewpoint_action_changes_future_observation(evaluator):
    scenario = evaluator._load_scenarios("train")[1]
    nodes = {node["id"]: node for node in scenario["nodes"]}
    start = nodes[scenario["start"]]
    next_id = evaluator._edge_target(start, "VEER_LEFT")
    held_id = evaluator._edge_target(start, "STOP")
    assert next_id != held_id
    assert nodes[next_id]["progress"] > nodes[held_id]["progress"]


def test_baseline_replay_is_deterministic_and_valid(evaluator):
    first = evaluator.evaluate(str(BASELINE_PATH), "train")
    second = evaluator.evaluate(str(BASELINE_PATH), "train")
    assert first == second
    assert first["status"] == "success"
    assert first["metrics"]["validity"] == 1.0
    assert first["metrics"]["task_success"] == 1.0
    assert first["combined_score"] > 0.80


def test_baseline_hidden_evaluation_is_valid(evaluator):
    result = evaluator.evaluate(str(BASELINE_PATH), "test")
    assert result["metrics"]["validity"] == 1.0
    assert result["metrics"]["task_success"] == 1.0
    assert result["metrics"]["unsafe_forward_count"] == 0.0


def test_always_stop_cannot_get_safety_only_score(evaluator, tmp_path):
    policy = tmp_path / "always_stop.py"
    policy.write_text(
        "def decide(observation, memory):\n    return 'STOP', 1.0, memory\n",
        encoding="utf-8",
    )
    result = evaluator.evaluate(str(policy), "train")
    assert result["metrics"]["timeout_rate"] == 1.0
    assert result["metrics"]["validity"] == 0.0
    assert result["combined_score"] == 0.0


def test_unsafe_policy_trips_hard_gate(evaluator, tmp_path):
    policy = tmp_path / "unsafe.py"
    policy.write_text(
        "def decide(observation, memory):\n    return 'FORWARD', 1.0, memory\n",
        encoding="utf-8",
    )
    result = evaluator.evaluate(str(policy), "train")
    assert result["metrics"]["unsafe_forward_count"] > 0.0
    assert result["metrics"]["validity"] == 0.0
    assert result["combined_score"] == 0.0
    assert "low safety confidence or high closing risk" in result["artifacts"]["feedback"]
    assert "continued FORWARD" in result["artifacts"]["feedback"]


def test_wrong_target_arrival_is_invalid(evaluator):
    scenario = evaluator._load_scenarios("train")[3]

    def decoy_policy(observation, memory):
        if not observation["target_visible"]:
            return "SCAN_LEFT", 1.0, memory
        return "ARRIVED", 1.0, memory

    result = evaluator.run_episode(decoy_policy, scenario)
    assert result.validity == 0.0
    assert result.premature_arrival_count == 1
    assert any("wrong target" in message for message in result.diagnostics)


def test_illegal_action_and_bad_memory_are_invalid(evaluator, tmp_path):
    illegal = tmp_path / "illegal.py"
    illegal.write_text(
        "def decide(observation, memory):\n    return 'TELEPORT', 1.0, memory\n",
        encoding="utf-8",
    )
    bad_memory = tmp_path / "bad_memory.py"
    bad_memory.write_text(
        "def decide(observation, memory):\n    return 'STOP', 1.0, {'x': object()}\n",
        encoding="utf-8",
    )
    crashing = tmp_path / "crashing.py"
    crashing.write_text(
        "def decide(observation, memory):\n    raise RuntimeError('boom')\n",
        encoding="utf-8",
    )
    for path in (illegal, bad_memory, crashing):
        result = evaluator.evaluate(str(path), "train")
        assert result["metrics"]["validity"] == 0.0
        assert result["combined_score"] == 0.0


def test_oracle_like_sanity_policy_scores_high_without_being_search_input(evaluator):
    # Evaluator-only upper sanity check: uses observation fields, never graph IDs.
    def oracle_like(obs, memory):
        memory = dict(memory)
        if obs["safety_confidence"] < 0.60 or obs["closing_risk"] >= 0.75:
            return "STOP", 1.0, memory
        if not obs["target_visible"] or obs["target_identity_confidence"] < 0.60:
            if obs["lost_steps"] <= 1:
                return "STOP", 1.0, memory
            action = memory.get("scan", "SCAN_LEFT")
            memory["scan"] = "SCAN_RIGHT" if action == "SCAN_LEFT" else "SCAN_LEFT"
            return action, 0.9, memory
        if obs["track_age"] < 2:
            return "SLOW_DOWN", 0.9, memory
        if obs["target_distance_class"] == "near":
            if abs(obs["heading_error"]) <= 15:
                return "ARRIVED", 1.0, memory
            return ("VEER_LEFT" if obs["target_bearing"] < 0 else "VEER_RIGHT"), 0.9, memory
        if obs["target_bearing"] < -12 and obs["corridor_left"]:
            return "VEER_LEFT", 0.9, memory
        if obs["target_bearing"] > 12 and obs["corridor_right"]:
            return "VEER_RIGHT", 0.9, memory
        if obs["corridor_center"]:
            return "FORWARD", 0.9, memory
        if obs["corridor_left"]:
            return "VEER_LEFT", 0.8, memory
        if obs["corridor_right"]:
            return "VEER_RIGHT", 0.8, memory
        return "STOP", 1.0, memory

    results = [
        evaluator.run_episode(oracle_like, scenario)
        for scenario in evaluator._load_scenarios("test")
    ]
    assert all(result.validity for result in results)
    assert all(result.task_success for result in results)


def test_cli_emits_single_json_document():
    # The container protocol requires stdout to be exactly one JSON object.
    import subprocess

    completed = subprocess.run(
        [sys.executable, str(EVALUATOR_PATH), str(BASELINE_PATH), "train"],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    payload = json.loads(completed.stdout)
    assert payload["status"] == "success"
    assert completed.stderr == ""
