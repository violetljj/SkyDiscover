"""Focused tests for the L10M-ORACLE-3 closed-loop benchmark."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmarks" / "blindassist_last10m_v3"
V1_HIDDEN_PATH = (
    ROOT / "benchmarks" / "blindassist_last10m" / "evaluator" / "scenarios" / "hidden.json"
)
V2_HIDDEN_PATH = (
    ROOT / "benchmarks" / "blindassist_last10m_v2" / "evaluator" / "scenarios" / "hidden.json"
)
V2_SHORTCUT_PATH = (
    ROOT
    / "benchmarks"
    / "blindassist_last10m_v2"
    / "receipts"
    / "2026-08-19_acceptance_preflight"
    / "best_program.py"
)
EVALUATOR_PATH = BENCHMARK / "evaluator" / "evaluator.py"
BASELINE_PATH = BENCHMARK / "initial_program.py"
FROZEN_BASELINE_PATH = BENCHMARK / "evaluator" / "baseline.py"


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
    regression_v1 = evaluator._load_scenarios("regression_v1")
    regression_v2 = evaluator._load_scenarios("regression_v2")
    assert len(dev) == 10
    assert len(hidden) == 4
    assert len(regression_v1) == 4
    assert len(regression_v2) == 4
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


def test_frozen_manifest_and_baseline_match_checked_in_inputs():
    manifest_path = BENCHMARK / "evaluator" / "scenarios" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["benchmark_revision"] == "L10M-ORACLE-3"
    for split in manifest["splits"].values():
        scenario_path = manifest_path.parent / split["file"]
        assert hashlib.sha256(scenario_path.read_bytes()).hexdigest() == split["sha256"]
    assert FROZEN_BASELINE_PATH.read_bytes() == BASELINE_PATH.read_bytes()
    assert (manifest_path.parent / "regression_v1.json").read_bytes() == V1_HIDDEN_PATH.read_bytes()
    assert (manifest_path.parent / "regression_v2.json").read_bytes() == V2_HIDDEN_PATH.read_bytes()


def test_claim_adjudication_is_bound_to_unchanged_acceptance_receipt():
    receipt_dir = BENCHMARK / "receipts" / "2026-08-19_acceptance"
    receipt_path = receipt_dir / "receipt.json"
    adjudication = json.loads((receipt_dir / "claim_adjudication.json").read_text(encoding="utf-8"))
    assert (
        adjudication["source_receipt_sha256"]
        == hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    )
    assert (
        adjudication["canonical_claim"]
        == "SUBSTANTIVE_POLICY_IMPROVEMENT_ESTABLISHED_WITHIN_L10M_ORACLE_3"
    )
    assert adjudication["basis"]["hidden_v3_consumed"] is True
    assert adjudication["discordant_dev_result"]["behavioral_improvement_detected"] is False


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
    assert first["metrics"]["score_delta"] == 0.0
    assert first["metrics"]["behavioral_improvement_detected"] == 0.0
    attribution = json.loads(first["artifacts"]["score_attribution"])
    assert attribution["delta_component_sum"] == 0.0
    assert attribution["delta_total_score"] == 0.0


def test_baseline_hidden_evaluation_is_valid(evaluator):
    result = evaluator.evaluate(str(BASELINE_PATH), "test")
    assert result["metrics"]["validity"] == 1.0
    assert result["metrics"]["task_success"] == 1.0
    assert result["metrics"]["unsafe_forward_count"] == 0.0
    assert result["metrics"]["heldout_improvement_detected"] == 0.0


def test_every_action_label_is_counted_as_an_instruction_event(evaluator):
    scenario = {
        "id": "instruction_event_probe",
        "start": "s0",
        "goal_target_id": "goal",
        "max_steps": 2,
        "optimal_movement_steps": 1,
        "nodes": [
            {
                "id": "s0",
                "target_visible": True,
                "target_bearing": 0,
                "target_distance_class": "medium",
                "target_confidence": 1.0,
                "target_identity_confidence": 1.0,
                "corridor_left": True,
                "corridor_center": True,
                "corridor_right": True,
                "closing_risk": 0.0,
                "safety_confidence": 1.0,
                "heading_error": 0,
                "progress": 0,
                "truth_target_id": "goal",
                "transitions": {"STOP": "goal", "SLOW_DOWN": "goal"},
            },
            {
                "id": "goal",
                "target_visible": True,
                "target_bearing": 0,
                "target_distance_class": "near",
                "target_confidence": 1.0,
                "target_identity_confidence": 1.0,
                "corridor_left": True,
                "corridor_center": True,
                "corridor_right": True,
                "closing_risk": 0.0,
                "safety_confidence": 1.0,
                "heading_error": 0,
                "progress": 1,
                "truth_target_id": "goal",
                "arrival_valid": True,
                "transitions": {},
            },
        ],
    }

    def policy(first_action):
        def decide(observation, memory):
            if observation["target_distance_class"] == "near":
                return "ARRIVED", 1.0, memory
            return first_action, 1.0, memory

        return decide

    assert evaluator.run_episode(policy("STOP"), scenario).instruction_count == 2
    assert evaluator.run_episode(policy("SLOW_DOWN"), scenario).instruction_count == 2


def test_behavioral_gate_rejects_instruction_only_improvement(evaluator):
    baseline = {
        "validity": 1.0,
        "task_success": 1.0,
        "safe_termination": 1.0,
        "unsafe_forward_count": 0.0,
        "premature_arrival_count": 0.0,
        "arrival_quality": 0.9,
        "path_efficiency": 0.9,
        "reacquisition_success": 0.9,
        "wrong_way_steps": 0.0,
        "instruction_flip_rate": 0.0,
        "target_switch_count": 0.0,
        "mean_heading_error": 5.0,
        "final_heading_error": 2.0,
        "instruction_count": 6.0,
    }
    candidate = {**baseline, "instruction_count": 4.0}
    passed, substantive_delta, substantive_share = evaluator._behavioral_gate(
        candidate,
        baseline,
        {"instruction": 0.03, "path": 0.0},
        0.03,
    )
    assert passed is False
    assert substantive_delta == 0.0
    assert substantive_share == 0.0
    candidate["path_efficiency"] = 0.92
    passed, _, substantive_share = evaluator._behavioral_gate(
        candidate,
        baseline,
        {"instruction": 0.01, "path": 0.0032},
        0.0132,
    )
    assert passed is False
    assert substantive_share < 0.5
    passed, _, substantive_share = evaluator._behavioral_gate(
        candidate,
        baseline,
        {"instruction": 0.002, "path": 0.0032},
        0.0052,
    )
    assert passed is True
    assert substantive_share >= 0.5


def test_consumed_v2_shortcut_fails_v3_substantive_gate(evaluator):
    result = evaluator.evaluate(str(V2_SHORTCUT_PATH), "train")
    assert result["metrics"]["score_delta"] > 0.0
    assert result["metrics"]["search_signal_detected"] == 1.0
    assert result["metrics"]["substantive_score_delta"] == 0.0
    assert result["metrics"]["substantive_score_share"] == 0.0
    assert result["metrics"]["behavioral_improvement_detected"] == 0.0


def test_dev_has_achievable_scored_behavioral_headroom(evaluator, tmp_path):
    source = BASELINE_PATH.read_text(encoding="utf-8")
    source = source.replace("bearing < -12.0", "bearing < -8.0")
    source = source.replace("bearing > 12.0", "bearing > 8.0")
    candidate = tmp_path / "lower_alignment_threshold.py"
    candidate.write_text(source, encoding="utf-8")

    result = evaluator.evaluate(str(candidate), "train")

    attribution = json.loads(result["artifacts"]["score_attribution"])
    assert result["metrics"]["path_efficiency"] == 1.0
    assert attribution["delta_path"] > 0.0
    assert result["metrics"]["substantive_score_share"] >= 0.5
    assert result["metrics"]["behavioral_improvement_detected"] == 1.0


def test_syntax_error_emits_structured_failure_receipt(evaluator, tmp_path):
    broken = tmp_path / "broken.py"
    broken.write_text("def decide(observation, memory)\n    pass\n", encoding="utf-8")
    result = evaluator.evaluate(str(broken), "train")
    assert result["status"] == "error"
    assert result["metrics"]["validity"] == 0.0
    artifacts = result["artifacts"]
    assert artifacts["failure_stage"] == "candidate_import"
    assert artifacts["exception_type"] == "SyntaxError"
    assert artifacts["exception_message"]
    assert artifacts["failure_line"] == "1"
    assert artifacts["failure_location"].endswith("broken.py")
    assert artifacts["evaluator_summary"]


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
        if not obs["target_visible"]:
            if obs["lost_steps"] <= 1:
                return "STOP", 1.0, memory
            action = memory.get("scan", "SCAN_LEFT")
            memory["scan"] = "SCAN_RIGHT" if action == "SCAN_LEFT" else "SCAN_LEFT"
            return action, 0.9, memory
        if obs["target_identity_confidence"] < 0.60:
            return "SCAN_RIGHT", 0.9, memory
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
