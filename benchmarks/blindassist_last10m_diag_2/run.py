"""Run the bounded, post-hoc L10M-DIAG-2 representation audit."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIAG1 = ROOT / "benchmarks" / "blindassist_last10m_diag_1"
EVALUATOR_PATH = ROOT / "benchmarks" / "blindassist_last10m_v3" / "evaluator" / "evaluator.py"
BASELINE = ROOT / "benchmarks" / "blindassist_last10m_v3" / "initial_program.py"
OLD_POLICY = DIAG1 / "policies" / "lower_alignment_threshold.py"
NEW_POLICY = Path(__file__).with_name("policies") / "structured_temporal_policy.py"
MANIFEST = ROOT / "benchmarks" / "blindassist_last10m_sky_1" / "cohort_manifest.json"
PROTOCOL = Path(__file__).with_name("protocol.json")
TARGET_EPISODE = "instance_07_H_08"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _expanded(path: Path) -> list[dict]:
    scenarios = json.loads(path.read_text(encoding="utf-8"))
    for scenario in scenarios:
        defaults = scenario.pop("node_defaults", {})
        defaults.setdefault("rgb_ref", None)
        scenario["nodes"] = [{**defaults, **node} for node in scenario["nodes"]]
    return scenarios


def _trace(evaluator, decide, scenario: dict) -> list[dict]:
    nodes = {str(node["id"]): node for node in scenario["nodes"]}
    current = str(scenario["start"])
    memory = {}
    track_age = 0
    lost_steps = 0
    rows = []
    for step in range(int(scenario["max_steps"])):
        node = nodes[current]
        if node["target_visible"]:
            track_age += 1
            lost_steps = 0
        else:
            track_age = 0
            lost_steps += 1
        observation = evaluator._observation(node, track_age, lost_steps)
        action, confidence, new_memory = decide(dict(observation), dict(memory))
        memory = evaluator._validate_memory(new_memory)
        next_node = evaluator._edge_target(node, action) if action != "ARRIVED" else current
        rows.append(
            {
                "step": step,
                "node": current,
                "progress": observation["progress"],
                "bearing": observation["target_bearing"],
                "action": action,
                "confidence": confidence,
                "next_node": next_node,
                "state": memory.get("state"),
                "stalled": next_node == current and action in evaluator.MOVING_ACTIONS,
            }
        )
        if action == "ARRIVED":
            break
        current = next_node
    return rows


def main() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    evaluator = _load(EVALUATOR_PATH, "l10m_diag_2_evaluator")
    candidates = {"diag_1_policy": OLD_POLICY, "structured_temporal_policy": NEW_POLICY}
    development = {
        name: evaluator.evaluate(str(path), "train") for name, path in candidates.items()
    }
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    consumed = []
    target_scenario = None
    for record in manifest["instances"]:
        hidden_path = ROOT / record["hidden_path"]
        if _sha256(hidden_path) != record["hidden_sha256"]:
            raise RuntimeError(f"consumed hidden hash mismatch: {record['instance_id']}")
        scenarios = _expanded(hidden_path)
        if record["instance_id"] == "instance_07":
            target_scenario = next(item for item in scenarios if item["id"] == TARGET_EPISODE)
        evaluator._load_scenarios = lambda mode, data=scenarios: deepcopy(data)
        consumed.append(
            {
                "instance_id": record["instance_id"],
                "hidden_sha256": record["hidden_sha256"],
                "results": {
                    name: evaluator.evaluate(str(path), "test") for name, path in candidates.items()
                },
            }
        )

    if target_scenario is None:
        raise RuntimeError(f"missing target episode {TARGET_EPISODE}")
    old_decide = evaluator._load_candidate(str(OLD_POLICY))
    new_decide = evaluator._load_candidate(str(NEW_POLICY))
    traces = {
        "diag_1_policy": _trace(evaluator, old_decide, deepcopy(target_scenario)),
        "structured_temporal_policy": _trace(evaluator, new_decide, deepcopy(target_scenario)),
    }
    metrics = [row["results"]["structured_temporal_policy"]["metrics"] for row in consumed]
    behavioral_count = sum(item["behavioral_improvement_detected"] == 1.0 for item in metrics)
    robust_count = sum(
        item["validity"] == item["task_success"] == item["safe_termination"] == 1.0
        for item in metrics
    )
    mean_delta = sum(item["substantive_score_delta"] for item in metrics) / len(metrics)
    rules = protocol["success_rules"]
    success = (
        behavioral_count >= rules["behavioral_pass_instances_min"]
        and mean_delta > rules["mean_substantive_score_delta_gt"]
        and robust_count == rules["robust_safe_instances"]
    )
    receipt = {
        "experiment_id": "L10M-DIAG-2",
        "benchmark_revision": evaluator.BENCHMARK_REVISION,
        "fresh_blind_split_evaluated": False,
        "search_calls": 0,
        "authority_sha256": {
            "protocol": _sha256(PROTOCOL),
            "runner": _sha256(Path(__file__)),
            "evaluator": _sha256(EVALUATOR_PATH),
            "cohort_manifest": _sha256(MANIFEST),
        },
        "candidate_sha256": {name: _sha256(path) for name, path in candidates.items()},
        "development_results": development,
        "consumed_hidden_results": consumed,
        "target_episode_diagnosis": {
            "episode_id": TARGET_EPISODE,
            "cause": "REPEATED_NON_TRANSITIONING_STEERING_WITHOUT_PROGRESS_CONTRACT",
            "traces": traces,
        },
        "summary": {
            "instance_count": len(metrics),
            "behavioral_pass_instances": behavioral_count,
            "robust_safe_instances": robust_count,
            "mean_substantive_score_delta": round(mean_delta, 12),
        },
        "decision": {
            "success_rules_met": success,
            "verdict": (
                "STRUCTURED_REPRESENTATION_ROBUST_REACHABILITY_ESTABLISHED"
                if success
                else "STRUCTURED_REPRESENTATION_ROBUST_REACHABILITY_NOT_ESTABLISHED"
            ),
            "claim_ceiling": protocol["claim_ceiling"],
            "search_restart_authorized": success,
        },
    }
    out = Path(__file__).with_name("receipts") / "development_audit.json"
    out.parent.mkdir(exist_ok=True)
    encoded = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    out.write_text(encoded, encoding="utf-8")
    print(json.dumps({**receipt["summary"], **receipt["decision"]}, sort_keys=True))


if __name__ == "__main__":
    main()
