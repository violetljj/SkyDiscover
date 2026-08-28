#!/usr/bin/env python3
"""Policy evaluator over exported BlindAssist perception episodes."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ACTIONS = {
    "SWEEP",
    "CENTER_AND_APPROACH",
    "HOLD",
    "TRACK",
    "SCAN_LAST_BEARING",
    "ARRIVED",
}
MAX_MEMORY_BYTES = 4096
MAX_MEMORY_KEYS = 32
PUBLIC_FIELDS = {
    "perception_state",
    "candidates",
    "selected_track_id",
    "last_bearing",
    "consecutive_hits",
    "lost_steps",
    "scale_change",
    "safe_to_approach",
    "handoff_ready",
}


@dataclass
class EpisodeResult:
    episode_id: str
    validity: float = 1.0
    task_success: float = 0.0
    correct_track_steps: int = 0
    track_steps: int = 0
    truth_retained_steps: int = 0
    truth_visible_steps: int = 0
    reacquisition_required: bool = False
    reacquisition_success: float = 0.0
    information_actions: int = 0
    instruction_count: int = 0
    false_commit_count: int = 0
    premature_arrival_count: int = 0
    diagnostics: list[str] = field(default_factory=list)


def _load_candidate(path: str) -> Callable[[dict[str, Any], dict[str, Any]], Any]:
    spec = importlib.util.spec_from_file_location("l10_perception_candidate", path)
    if spec is None or spec.loader is None:
        raise ValueError("candidate module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    decide = getattr(module, "decide", None)
    if not callable(decide):
        raise ValueError("candidate must define decide(observation, memory)")
    return decide


def _validate_episode(episode: dict[str, Any]) -> None:
    if episode.get("observation_authority") not in {
        "MECHANICS_FIXTURE",
        "BLINDASSIST_REAL_PERCEPTION",
    }:
        raise ValueError(f"episode {episode.get('id')} has unknown observation authority")
    nodes = episode.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError(f"episode {episode.get('id')} has no nodes")
    ids = {str(node.get("id")) for node in nodes}
    if str(episode.get("start")) not in ids:
        raise ValueError(f"episode {episode.get('id')} start node is missing")
    for node in nodes:
        missing = PUBLIC_FIELDS - node.keys()
        if missing:
            raise ValueError(f"node {node.get('id')} missing {sorted(missing)}")
        if node["perception_state"] not in {"SEARCH", "SET_VALUED", "COMMIT", "REACQUIRE"}:
            raise ValueError(f"node {node.get('id')} has invalid perception_state")
        for action, target in node.get("transitions", {}).items():
            if action not in ACTIONS or str(target) not in ids:
                raise ValueError(f"node {node.get('id')} has invalid transition")


def _load_episodes(mode: str) -> list[dict[str, Any]]:
    name = "dev.json" if mode == "train" else "hidden.json"
    payload = json.loads((Path(__file__).with_name("episodes") / name).read_text("utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"{name} must contain episodes")
    for episode in payload:
        _validate_episode(episode)
    return payload


def _public_observation(node: dict[str, Any]) -> dict[str, Any]:
    return {key: node[key] for key in PUBLIC_FIELDS}


def _validate_memory(memory: Any) -> dict[str, Any]:
    if not isinstance(memory, dict) or len(memory) > MAX_MEMORY_KEYS:
        raise ValueError("new_memory must be a small dictionary")
    encoded = json.dumps(memory, sort_keys=True, allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_MEMORY_BYTES:
        raise ValueError("new_memory exceeds 4096 bytes")
    return memory


def run_episode(decide: Callable[..., Any], episode: dict[str, Any]) -> EpisodeResult:
    nodes = {str(node["id"]): node for node in episode["nodes"]}
    current = str(episode["start"])
    memory: dict[str, Any] = {}
    result = EpisodeResult(str(episode["id"]))
    lost_seen = False

    for step in range(int(episode.get("max_steps", 12))):
        node = nodes[current]
        if node.get("truth_visible", False):
            result.truth_visible_steps += 1
            if node.get("truth_in_candidate_set", False):
                result.truth_retained_steps += 1
        if node["perception_state"] == "REACQUIRE":
            lost_seen = True
            result.reacquisition_required = True

        try:
            response = decide(dict(_public_observation(node)), dict(memory))
            if not isinstance(response, (tuple, list)) or len(response) != 3:
                raise ValueError("decide must return (action, confidence, new_memory)")
            action, confidence, memory = response
            if action not in ACTIONS:
                raise ValueError(f"illegal action {action!r}")
            confidence = float(confidence)
            if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                raise ValueError("confidence must be within [0, 1]")
            memory = _validate_memory(memory)
        except Exception as exc:
            result.validity = 0.0
            result.diagnostics.append(f"step {step}: candidate failure: {type(exc).__name__}: {exc}")
            break

        result.instruction_count += int(action != "HOLD")
        result.information_actions += int(action in {"SWEEP", "CENTER_AND_APPROACH", "SCAN_LAST_BEARING"})

        if action == "CENTER_AND_APPROACH" and not node["safe_to_approach"]:
            result.validity = 0.0
            result.diagnostics.append(f"step {step}: approached while safety veto was active")
            break
        if action == "TRACK":
            result.track_steps += 1
            if node.get("selected_track_is_truth", False):
                result.correct_track_steps += 1
            else:
                result.false_commit_count += 1
                result.validity = 0.0
                result.diagnostics.append(f"step {step}: tracked an ungrounded or wrong portal")
                break
        if action == "ARRIVED":
            if node.get("arrival_truth", False) and node["handoff_ready"]:
                result.task_success = 1.0
            else:
                result.premature_arrival_count += 1
                result.validity = 0.0
                result.diagnostics.append(f"step {step}: premature or wrong-portal arrival")
            break

        next_id = str(node.get("transitions", {}).get(action, current))
        current = next_id
        next_node = nodes[current]
        if lost_seen and next_node["perception_state"] == "COMMIT" and next_node.get(
            "selected_track_is_truth", False
        ):
            result.reacquisition_success = 1.0
    else:
        result.validity = 0.0
        result.diagnostics.append("timeout without valid arrival")
    return result


def _mean(results: list[EpisodeResult], field: str) -> float:
    return sum(float(getattr(row, field)) for row in results) / len(results)


def evaluate(program_path: str, mode: str = "train") -> dict[str, Any]:
    try:
        decide = _load_candidate(program_path)
        episodes = _load_episodes(mode)
        results = [run_episode(decide, episode) for episode in episodes]
    except Exception as exc:
        return {
            "status": "error",
            "combined_score": 0.0,
            "metrics": {"combined_score": 0.0, "validity": 0.0},
            "artifacts": {"feedback": f"setup failed: {type(exc).__name__}: {exc}", "traceback": traceback.format_exc(limit=8)},
        }

    truth_visible = sum(row.truth_visible_steps for row in results)
    track_steps = sum(row.track_steps for row in results)
    reacquire = [row for row in results if row.reacquisition_required]
    metrics = {
        "validity": min(row.validity for row in results),
        "task_success": _mean(results, "task_success"),
        "commit_precision": sum(row.correct_track_steps for row in results) / max(track_steps, 1),
        "truth_retention": sum(row.truth_retained_steps for row in results) / max(truth_visible, 1),
        "reacquisition_success": (
            sum(row.reacquisition_success for row in reacquire) / len(reacquire)
            if reacquire
            else 1.0
        ),
        "false_commit_count": _mean(results, "false_commit_count"),
        "premature_arrival_count": _mean(results, "premature_arrival_count"),
        "information_actions": _mean(results, "information_actions"),
        "instruction_count": _mean(results, "instruction_count"),
    }
    utility = (
        0.34 * metrics["task_success"]
        + 0.22 * metrics["commit_precision"]
        + 0.18 * metrics["truth_retention"]
        + 0.16 * metrics["reacquisition_success"]
        + 0.10 * max(0.0, 1.0 - metrics["instruction_count"] / 12.0)
    )
    score = round(max(0.0, min(1.0, utility)), 6) if metrics["validity"] == 1.0 else 0.0
    metrics["combined_score"] = score
    failures = [row for row in results if not row.task_success or not row.validity]
    feedback = [f"{mode}: {len(results) - len(failures)}/{len(results)} episodes succeeded."]
    for row in failures:
        feedback.append(f"{row.episode_id}: {'; '.join(row.diagnostics) or 'no valid arrival'}")
    feedback.append("Artifacts expose failure classes, never truth labels or an oracle action sequence.")
    return {
        "status": "success",
        "combined_score": score,
        "metrics": {key: round(value, 6) for key, value in metrics.items()},
        "artifacts": {"feedback": "\n".join(feedback)},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("program_path")
    parser.add_argument("mode", choices=("train", "test"), nargs="?", default="train")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.program_path, args.mode), sort_keys=True))


if __name__ == "__main__":
    main()
