#!/usr/bin/env python3
"""Deterministic closed-loop evaluator for L10M-ORACLE-3.

The candidate controls only ``decide``.  This module owns observations,
viewpoint transitions, validation, safety gates, aggregation, and feedback.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ACTIONS = {
    "SCAN_LEFT",
    "SCAN_RIGHT",
    "FORWARD",
    "VEER_LEFT",
    "VEER_RIGHT",
    "SLOW_DOWN",
    "STOP",
    "ARRIVED",
}
MOVING_ACTIONS = {"FORWARD", "VEER_LEFT", "VEER_RIGHT"}
TURN_LEFT = {"SCAN_LEFT", "VEER_LEFT"}
TURN_RIGHT = {"SCAN_RIGHT", "VEER_RIGHT"}
DISTANCE_RANK = {"far": 3, "medium": 2, "near": 1}
MAX_MEMORY_BYTES = 4096
MAX_MEMORY_KEYS = 32
BENCHMARK_REVISION = "L10M-ORACLE-3"
BASELINE_PATH = Path(__file__).with_name("baseline.py")
COMPONENT_WEIGHTS = {
    "success": 0.32,
    "safety": 0.20,
    "arrival": 0.16,
    "path": 0.16,
    "reacquisition": 0.10,
    "wrong_way": 0.04,
    "oscillation": 0.02,
    "instruction": -0.015,
    "target_switch": -0.02,
}


@dataclass
class EpisodeResult:
    scenario_id: str
    validity: float = 1.0
    task_success: float = 0.0
    safe_termination: float = 1.0
    path_efficiency: float = 0.0
    wrong_way_steps: int = 0
    reacquisition_success: float = 0.0
    reacquisition_required: float = 0.0
    target_switch_count: int = 0
    instruction_flip_rate: float = 0.0
    instruction_count: int = 0
    arrival_quality: float = 0.0
    timeout: float = 0.0
    mean_heading_error: float = 0.0
    final_heading_error: float = 180.0
    unsafe_forward_count: int = 0
    premature_arrival_count: int = 0
    diagnostics: list[str] = field(default_factory=list)


def _load_candidate(program_path: str) -> Callable[[dict[str, Any], dict[str, Any]], Any]:
    spec = importlib.util.spec_from_file_location("l10m_candidate", program_path)
    if spec is None or spec.loader is None:
        raise ValueError("candidate module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    decide = getattr(module, "decide", None)
    if not callable(decide):
        raise ValueError("candidate must define callable decide(observation, memory)")
    return decide


def _load_scenarios(mode: str) -> list[dict[str, Any]]:
    scenario_files = {
        "train": "dev.json",
        "test": "hidden.json",
        "regression_v1": "regression_v1.json",
        "regression_v2": "regression_v2.json",
    }
    if mode not in scenario_files:
        raise ValueError("mode must be train, test, regression_v1, or regression_v2")
    name = scenario_files[mode]
    path = Path(__file__).with_name("scenarios") / name
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError(f"scenario set {name} is empty")
    required = {
        "target_visible",
        "target_bearing",
        "target_distance_class",
        "target_confidence",
        "target_identity_confidence",
        "corridor_left",
        "corridor_center",
        "corridor_right",
        "closing_risk",
        "safety_confidence",
        "heading_error",
        "progress",
    }
    for scenario in data:
        defaults = scenario.pop("node_defaults", {})
        defaults.setdefault("rgb_ref", None)
        scenario["nodes"] = [{**defaults, **node} for node in scenario["nodes"]]
        for node in scenario["nodes"]:
            missing = required - node.keys()
            if missing:
                raise ValueError(
                    f"scenario {scenario.get('id')} node {node.get('id')} missing {sorted(missing)}"
                )
    return data


def _observation(node: dict[str, Any], track_age: int, lost_steps: int) -> dict[str, Any]:
    """Expose current oracle perception, never graph topology or future answers."""
    return {
        "target_visible": bool(node["target_visible"]),
        "target_bearing": float(node["target_bearing"]),
        "target_distance_class": str(node["target_distance_class"]),
        "target_confidence": float(node["target_confidence"]),
        "target_identity_confidence": float(node["target_identity_confidence"]),
        "track_age": track_age,
        "lost_steps": lost_steps,
        "corridor_left": bool(node["corridor_left"]),
        "corridor_center": bool(node["corridor_center"]),
        "corridor_right": bool(node["corridor_right"]),
        "closing_risk": float(node["closing_risk"]),
        "safety_confidence": float(node["safety_confidence"]),
        "heading_error": float(node["heading_error"]),
        "progress": float(node["progress"]),
    }


def _validate_memory(memory: Any) -> dict[str, Any]:
    if not isinstance(memory, dict):
        raise ValueError("new_memory must be a dictionary")
    if len(memory) > MAX_MEMORY_KEYS:
        raise ValueError(f"new_memory exceeds {MAX_MEMORY_KEYS} top-level keys")
    try:
        encoded = json.dumps(memory, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("new_memory must be JSON-serializable") from exc
    if len(encoded.encode("utf-8")) > MAX_MEMORY_BYTES:
        raise ValueError(f"new_memory exceeds {MAX_MEMORY_BYTES} bytes")
    return memory


def _edge_target(node: dict[str, Any], action: str) -> str:
    transition = node.get("transitions", {}).get(action)
    if transition is None:
        return str(node["id"])
    return str(transition)


def run_episode(decide: Callable[..., Any], scenario: dict[str, Any]) -> EpisodeResult:
    nodes = {str(node["id"]): node for node in scenario["nodes"]}
    current_id = str(scenario["start"])
    result = EpisodeResult(scenario_id=str(scenario["id"]))
    memory: dict[str, Any] = {}
    track_age = 0
    lost_steps = 0
    consecutive_lost_forward = 0
    movement_steps = 0
    heading_errors: list[float] = []
    turn_actions: list[str] = []
    lost_event = False
    reacquired = False
    previous_truth_id: str | None = None
    stopped_for_hazard = False

    for step in range(int(scenario.get("max_steps", 20))):
        node = nodes[current_id]
        visible = bool(node["target_visible"])
        if visible:
            track_age += 1
            if lost_steps > 0 and node.get("truth_target_id") == scenario["goal_target_id"]:
                reacquired = True
            lost_steps = 0
        else:
            if track_age > 0:
                lost_event = True
            track_age = 0
            lost_steps += 1

        truth_id = node.get("truth_target_id") if visible else None
        if previous_truth_id is not None and truth_id is not None and truth_id != previous_truth_id:
            result.target_switch_count += 1
        if truth_id is not None:
            previous_truth_id = str(truth_id)

        obs = _observation(node, track_age, lost_steps)
        heading_errors.append(abs(float(obs["heading_error"])))
        try:
            response = decide(dict(obs), dict(memory))
            if not isinstance(response, (tuple, list)) or len(response) != 3:
                raise ValueError("decide must return (action, confidence, new_memory)")
            action, confidence, new_memory = response
            if action not in ACTIONS:
                raise ValueError(f"illegal action: {action!r}")
            confidence = float(confidence)
            if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                raise ValueError("confidence must be finite and within [0, 1]")
            memory = _validate_memory(new_memory)
        except Exception as exc:
            result.validity = 0.0
            result.safe_termination = 0.0
            result.diagnostics.append(
                f"step {step}: candidate failure: {type(exc).__name__}: {exc}"
            )
            break

        # Every returned action is an instruction event delivered by the control
        # interface.  STOP and SLOW_DOWN therefore carry the same per-event
        # burden as movement and scan actions; action labels cannot suppress it.
        result.instruction_count += 1
        if action in {"VEER_LEFT", "VEER_RIGHT"}:
            turn_actions.append(action)

        unsafe_now = obs["safety_confidence"] < 0.60 or obs["closing_risk"] >= 0.75
        if action in MOVING_ACTIONS and unsafe_now:
            result.unsafe_forward_count += 1
            result.validity = 0.0
            result.safe_termination = 0.0
            result.diagnostics.append(
                f"step {step}: active motion with low safety confidence or high closing risk"
            )
        if action == "STOP" and (unsafe_now or not visible):
            stopped_for_hazard = True

        if not visible and action == "FORWARD":
            consecutive_lost_forward += 1
            if consecutive_lost_forward >= 2:
                result.validity = 0.0
                result.diagnostics.append(
                    f"step {step}: continued FORWARD for {consecutive_lost_forward} lost-target steps"
                )
        else:
            consecutive_lost_forward = 0

        if action == "ARRIVED":
            correct_target = node.get("truth_target_id") == scenario["goal_target_id"]
            valid_pose = bool(node.get("arrival_valid", False))
            if correct_target and valid_pose:
                result.task_success = 1.0
                heading = abs(float(node["heading_error"]))
                result.arrival_quality = max(0.0, 1.0 - heading / 30.0)
                result.final_heading_error = heading
            else:
                result.premature_arrival_count += 1
                result.validity = 0.0
                reason = "wrong target" if not correct_target else "premature or misaligned arrival"
                result.diagnostics.append(f"step {step}: ARRIVED at {reason}")
            break

        next_id = _edge_target(node, action)
        if next_id not in nodes:
            result.validity = 0.0
            result.diagnostics.append(f"step {step}: evaluator graph has missing node {next_id!r}")
            break
        next_node = nodes[next_id]
        if action in MOVING_ACTIONS:
            movement_steps += 1
            if float(next_node["progress"]) + 1e-9 < float(node["progress"]):
                result.wrong_way_steps += 1
        current_id = next_id
    else:
        result.timeout = 1.0
        result.validity = 0.0
        result.diagnostics.append(
            f"timeout after {scenario.get('max_steps', 20)} steps without valid ARRIVED"
        )

    optimal = max(1, int(scenario.get("optimal_movement_steps", 1)))
    if result.task_success and movement_steps:
        result.path_efficiency = min(1.0, optimal / movement_steps)
    result.reacquisition_required = float(lost_event)
    result.reacquisition_success = float(
        lost_event and reacquired and result.unsafe_forward_count == 0
    )
    flips = 0
    for before, after in zip(turn_actions, turn_actions[1:]):
        if (before in TURN_LEFT and after in TURN_RIGHT) or (
            before in TURN_RIGHT and after in TURN_LEFT
        ):
            flips += 1
    result.instruction_flip_rate = flips / max(1, len(turn_actions) - 1)
    result.mean_heading_error = sum(heading_errors) / max(1, len(heading_errors))
    if not result.task_success:
        result.final_heading_error = abs(float(nodes[current_id]["heading_error"]))
    if result.unsafe_forward_count:
        result.safe_termination = 0.0
    elif lost_event:
        result.safe_termination = float(stopped_for_hazard)
    return result


def _mean(results: list[EpisodeResult], field_name: str) -> float:
    return sum(float(getattr(result, field_name)) for result in results) / len(results)


def _reacquisition_rate(results: list[EpisodeResult]) -> float:
    required = [result for result in results if result.reacquisition_required]
    if not required:
        return 1.0
    return sum(result.reacquisition_success for result in required) / len(required)


def _feedback(results: list[EpisodeResult], mode: str) -> str:
    failed = [r for r in results if not r.task_success or not r.validity]
    lines = [
        f"{BENCHMARK_REVISION} {mode}: "
        f"{len(results) - len(failed)}/{len(results)} episodes valid and successful."
    ]
    for result in failed[:8]:
        lines.append(f"Episode {result.scenario_id}:")
        if result.diagnostics:
            lines.extend(f"- {item}" for item in result.diagnostics[:5])
        lines.append(f"- unsafe forward count: {result.unsafe_forward_count}")
        lines.append(f"- wrong-way steps: {result.wrong_way_steps}")
        lines.append(f"- instruction flip rate: {result.instruction_flip_rate:.3f}")
        if not result.reacquisition_success:
            lines.append("- reacquisition not demonstrated")
    lines.append("No oracle optimal action sequence is included in this feedback.")
    return "\n".join(lines)


def _aggregate(results: list[EpisodeResult]) -> dict[str, float]:
    return {
        "validity": min(r.validity for r in results),
        "task_success": _mean(results, "task_success"),
        "safe_termination": _mean(results, "safe_termination"),
        "path_efficiency": _mean(results, "path_efficiency"),
        "wrong_way_steps": _mean(results, "wrong_way_steps"),
        "reacquisition_success": _reacquisition_rate(results),
        "target_switch_count": _mean(results, "target_switch_count"),
        "instruction_flip_rate": _mean(results, "instruction_flip_rate"),
        "instruction_count": _mean(results, "instruction_count"),
        "arrival_quality": _mean(results, "arrival_quality"),
        "timeout_rate": _mean(results, "timeout"),
        "mean_heading_error": _mean(results, "mean_heading_error"),
        "final_heading_error": _mean(results, "final_heading_error"),
        "unsafe_forward_count": _mean(results, "unsafe_forward_count"),
        "premature_arrival_count": _mean(results, "premature_arrival_count"),
    }


def _score_components(metrics: dict[str, float]) -> dict[str, float]:
    """Return independently attributable terms whose sum is pre-gate utility."""
    return {
        "success": COMPONENT_WEIGHTS["success"] * metrics["task_success"],
        "safety": COMPONENT_WEIGHTS["safety"] * metrics["safe_termination"],
        "arrival": COMPONENT_WEIGHTS["arrival"] * metrics["arrival_quality"],
        "path": COMPONENT_WEIGHTS["path"] * metrics["path_efficiency"],
        "reacquisition": COMPONENT_WEIGHTS["reacquisition"] * metrics["reacquisition_success"],
        "wrong_way": COMPONENT_WEIGHTS["wrong_way"]
        * max(0.0, 1.0 - metrics["wrong_way_steps"] / 3.0),
        "oscillation": COMPONENT_WEIGHTS["oscillation"]
        * max(0.0, 1.0 - metrics["instruction_flip_rate"]),
        "instruction": COMPONENT_WEIGHTS["instruction"] * min(10.0, metrics["instruction_count"]),
        "target_switch": COMPONENT_WEIGHTS["target_switch"]
        * min(3.0, metrics["target_switch_count"]),
    }


def _combined_score(metrics: dict[str, float], components: dict[str, float]) -> float:
    utility = max(0.0, min(1.0, sum(components.values())))
    return round(utility, 6) if metrics["validity"] == 1.0 else 0.0


def _behavioral_gate(
    candidate: dict[str, float],
    baseline: dict[str, float],
    component_deltas: dict[str, float],
    total_delta: float,
) -> tuple[bool, float, float]:
    """Require scored behavior to explain at least half of positive score delta."""
    safety_preserved = (
        candidate["validity"] == 1.0
        and candidate["task_success"] >= baseline["task_success"]
        and candidate["safe_termination"] >= baseline["safe_termination"]
        and candidate["unsafe_forward_count"] <= baseline["unsafe_forward_count"]
        and candidate["premature_arrival_count"] <= baseline["premature_arrival_count"]
    )
    improvements = (
        candidate["arrival_quality"] - baseline["arrival_quality"] >= 0.01,
        candidate["path_efficiency"] - baseline["path_efficiency"] >= 0.01,
        candidate["reacquisition_success"] - baseline["reacquisition_success"] >= 0.01,
        baseline["wrong_way_steps"] - candidate["wrong_way_steps"] >= 0.01,
        baseline["instruction_flip_rate"] - candidate["instruction_flip_rate"] >= 0.01,
        baseline["target_switch_count"] - candidate["target_switch_count"] >= 0.01,
    )
    substantive_delta = sum(
        delta for component, delta in component_deltas.items() if component != "instruction"
    )
    substantive_share = substantive_delta / total_delta if total_delta > 1e-9 else 0.0
    passed = (
        safety_preserved
        and any(improvements)
        and substantive_delta > 1e-9
        and substantive_share >= 0.5
    )
    return passed, substantive_delta, substantive_share


def _failure_artifacts(exc: Exception, stage: str) -> dict[str, str]:
    location = getattr(exc, "filename", None)
    line = getattr(exc, "lineno", None)
    if location is None or line is None:
        frames = traceback.extract_tb(exc.__traceback__)
        if frames:
            location = location or frames[-1].filename
            line = line or frames[-1].lineno
    return {
        "error": f"{type(exc).__name__}: {exc}",
        "failure_stage": stage,
        "exception_type": type(exc).__name__,
        "exception_message": str(exc),
        "failure_location": str(location or "unknown"),
        "failure_line": str(line or "unknown"),
        "validity": "0",
        "evaluator_summary": f"{BENCHMARK_REVISION} evaluation failed during {stage}",
        "traceback": traceback.format_exc(limit=8),
    }


def evaluate(program_path: str, mode: str = "train") -> dict[str, Any]:
    try:
        decide = _load_candidate(program_path)
    except Exception as exc:
        return {
            "status": "error",
            "combined_score": 0.0,
            "metrics": {"combined_score": 0.0, "validity": 0.0},
            "artifacts": _failure_artifacts(exc, "candidate_import"),
        }
    try:
        scenarios = _load_scenarios(mode)
        results = [run_episode(decide, scenario) for scenario in scenarios]
    except Exception as exc:
        return {
            "status": "error",
            "combined_score": 0.0,
            "metrics": {"combined_score": 0.0, "validity": 0.0},
            "artifacts": _failure_artifacts(exc, "episode_evaluation"),
        }

    metrics = _aggregate(results)
    components = _score_components(metrics)
    combined_score = _combined_score(metrics, components)

    baseline_decide = _load_candidate(str(BASELINE_PATH))
    baseline_results = [run_episode(baseline_decide, scenario) for scenario in scenarios]
    baseline_metrics = _aggregate(baseline_results)
    baseline_components = _score_components(baseline_metrics)
    baseline_score = _combined_score(baseline_metrics, baseline_components)
    component_deltas = {key: components[key] - baseline_components[key] for key in components}
    total_delta = combined_score - baseline_score
    search_signal = metrics["validity"] == 1.0 and total_delta > 1e-9
    behavioral_signal, substantive_delta, substantive_share = _behavioral_gate(
        metrics, baseline_metrics, component_deltas, total_delta
    )

    metrics["combined_score"] = combined_score
    metrics["baseline_score"] = baseline_score
    metrics["score_delta"] = total_delta
    metrics["search_signal_detected"] = float(search_signal)
    metrics["behavioral_improvement_detected"] = float(behavioral_signal)
    metrics["substantive_score_delta"] = substantive_delta
    metrics["substantive_score_share"] = substantive_share
    if mode == "test":
        metrics["heldout_improvement_detected"] = float(search_signal)

    attribution = {
        **{f"delta_{key}": round(value, 6) for key, value in component_deltas.items()},
        "delta_component_sum": round(sum(component_deltas.values()), 6),
        "delta_total_score": round(total_delta, 6),
    }
    return {
        "status": "success",
        "combined_score": combined_score,
        "metrics": {key: round(value, 6) for key, value in metrics.items()},
        "artifacts": {
            "feedback": _feedback(results, mode),
            "score_attribution": json.dumps(attribution, sort_keys=True, separators=(",", ":")),
            "evaluator_summary": (
                f"SEARCH_SIGNAL_DETECTED={search_signal}; "
                f"BEHAVIORAL_IMPROVEMENT_DETECTED={behavioral_signal}; "
                f"HELDOUT_IMPROVEMENT_DETECTED={mode == 'test' and search_signal}"
            ),
            "episode_summary": json.dumps(
                [
                    {
                        "episode": r.scenario_id,
                        "valid": bool(r.validity),
                        "success": bool(r.task_success),
                        "unsafe_forward_count": r.unsafe_forward_count,
                        "premature_arrival_count": r.premature_arrival_count,
                        "wrong_way_steps": r.wrong_way_steps,
                        "instruction_flip_rate": round(r.instruction_flip_rate, 3),
                    }
                    for r in results
                ],
                separators=(",", ":"),
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("program_path")
    parser.add_argument(
        "mode",
        choices=("train", "test", "regression_v1", "regression_v2"),
        nargs="?",
        default="train",
    )
    args = parser.parse_args()
    print(json.dumps(evaluate(args.program_path, args.mode), sort_keys=True))


if __name__ == "__main__":
    main()
