"""Run the bounded, development-only L10M-DIAG-1 audit."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = Path(__file__).with_name("protocol.json")
EVALUATOR_PATH = ROOT / "benchmarks" / "blindassist_last10m_v3" / "evaluator" / "evaluator.py"
BASELINE = ROOT / "benchmarks" / "blindassist_last10m_v3" / "initial_program.py"
INSTRUCTION_ONLY = (
    ROOT
    / "benchmarks"
    / "blindassist_last10m_v2"
    / "receipts"
    / "2026-08-19_acceptance_preflight"
    / "best_program.py"
)
REACHABLE = Path(__file__).with_name("policies") / "lower_alignment_threshold.py"
SKY1_MANIFEST = ROOT / "benchmarks" / "blindassist_last10m_sky_1" / "cohort_manifest.json"
MINIMUM_MEANINGFUL_EFFECT = 0.005


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(f"diag_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _expanded_scenarios(path: Path) -> list[dict]:
    scenarios = json.loads(path.read_text(encoding="utf-8"))
    for scenario in scenarios:
        defaults = scenario.pop("node_defaults", {})
        defaults.setdefault("rgb_ref", None)
        scenario["nodes"] = [{**defaults, **node} for node in scenario["nodes"]]
    return scenarios


def _consumed_hidden_results(candidates: dict[str, Path]) -> list[dict]:
    manifest = json.loads(SKY1_MANIFEST.read_text(encoding="utf-8"))
    rows = []
    for record in manifest["instances"]:
        hidden_path = ROOT / record["hidden_path"]
        if _sha256(hidden_path) != record["hidden_sha256"]:
            raise RuntimeError(f"consumed hidden hash mismatch: {record['instance_id']}")
        evaluator = _load(EVALUATOR_PATH)
        scenarios = _expanded_scenarios(hidden_path)
        evaluator._load_scenarios = lambda mode, data=scenarios: deepcopy(data)
        instance_results = {
            name: evaluator.evaluate(str(path), "test") for name, path in candidates.items()
        }
        rows.append(
            {
                "instance_id": record["instance_id"],
                "hidden_sha256": record["hidden_sha256"],
                "results": instance_results,
            }
        )
    return rows


def main() -> None:
    evaluator = _load(EVALUATOR_PATH)
    candidates = {
        "baseline": BASELINE,
        "instruction_only_counterfactual": INSTRUCTION_ONLY,
        "reachable_path_counterfactual": REACHABLE,
    }
    results = {name: evaluator.evaluate(str(path), "train") for name, path in candidates.items()}
    consumed_hidden = _consumed_hidden_results(candidates)
    instruction = results["instruction_only_counterfactual"]["metrics"]
    reachable = results["reachable_path_counterfactual"]["metrics"]
    hidden_reachable = [
        row["results"]["reachable_path_counterfactual"]["metrics"] for row in consumed_hidden
    ]
    hidden_mean_substantive_delta = sum(
        metrics["substantive_score_delta"] for metrics in hidden_reachable
    ) / len(hidden_reachable)
    hidden_behavioral_pass_rate = sum(
        metrics["behavioral_improvement_detected"] for metrics in hidden_reachable
    ) / len(hidden_reachable)
    hidden_robust_safe_rate = sum(
        metrics["validity"] == 1.0
        and metrics["task_success"] == 1.0
        and metrics["safe_termination"] == 1.0
        for metrics in hidden_reachable
    ) / len(hidden_reachable)
    receipt = {
        "experiment_id": "L10M-DIAG-1",
        "benchmark_revision": evaluator.BENCHMARK_REVISION,
        "splits": ["train", "consumed_l10m_sky_1_hidden"],
        "fresh_blind_split_evaluated": False,
        "search_calls": 0,
        "authority_sha256": {
            "protocol": _sha256(PROTOCOL),
            "runner": _sha256(Path(__file__)),
            "evaluator": _sha256(EVALUATOR_PATH),
            "sky_1_cohort_manifest": _sha256(SKY1_MANIFEST),
        },
        "candidate_sha256": {name: _sha256(path) for name, path in candidates.items()},
        "results": results,
        "consumed_hidden_results": consumed_hidden,
        "consumed_hidden_summary": {
            "instance_count": len(hidden_reachable),
            "reachable_mean_substantive_score_delta": round(hidden_mean_substantive_delta, 12),
            "reachable_behavioral_pass_rate": round(hidden_behavioral_pass_rate, 12),
            "reachable_robust_safe_rate": round(hidden_robust_safe_rate, 12),
        },
        "decision": {
            "objective_signal": bool(
                instruction["score_delta"] > 0
                and instruction["substantive_score_delta"] == 0
                and instruction["behavioral_improvement_detected"] == 0
            ),
            "reachable_effect_signal": bool(
                reachable["validity"] == 1.0
                and reachable["behavioral_improvement_detected"] == 1.0
                and reachable["substantive_score_share"] >= 0.5
                and hidden_mean_substantive_delta > MINIMUM_MEANINGFUL_EFFECT
                and hidden_behavioral_pass_rate >= 0.5
            ),
            "robust_safe_reachability": hidden_robust_safe_rate == 1.0,
            "verdict": "OBJECTIVE_SIGNAL_PRESENT_ROBUST_REACHABILITY_NOT_ESTABLISHED",
            "claim_ceiling": "POST_HOC_CONSUMED_L10M_ORACLE_3_AND_SKY_1_COHORT_ONLY",
        },
    }
    out = Path(__file__).with_name("receipts") / "development_audit.json"
    out.parent.mkdir(exist_ok=True)
    encoded = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if out.exists() and out.read_text(encoding="utf-8") != encoded:
        raise RuntimeError(f"refusing to overwrite non-matching receipt: {out}")
    if not out.exists():
        out.write_text(encoded, encoding="utf-8")
    print(json.dumps(receipt["decision"], sort_keys=True))


if __name__ == "__main__":
    main()
