#!/usr/bin/env python3
"""Frozen fresh-instance analysis for L10M-STRUCT-DIRECT-1."""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from statistics import mean
from typing import Any

HERE = Path(__file__).resolve().parent
PROTOCOL_PATH = HERE / "protocol.json"
COHORT_MANIFEST_PATH = HERE / "cohort_manifest.json"


def exact_sign_flip_greater(effects: list[float], margin: float) -> float:
    """Test a location shift greater than ``margin`` under sign exchangeability."""
    centered = [effect - margin for effect in effects]
    observed = mean(centered)
    if observed <= 0.0:
        return 1.0
    extreme = 0
    total = 0
    for signs in itertools.product((-1.0, 1.0), repeat=len(centered)):
        permuted = mean(sign * value for sign, value in zip(signs, centered))
        extreme += permuted >= observed - 1e-15
        total += 1
    return extreme / total


def _effect_counts(effects: list[float], tie: float) -> dict[str, int]:
    return {
        "wins": sum(effect > tie for effect in effects),
        "ties": sum(-tie <= effect <= tie for effect in effects),
        "losses": sum(effect < -tie for effect in effects),
    }


def _replicate_result(receipt: dict[str, Any], arm: str, replicate_index: int) -> dict[str, Any]:
    result = receipt["arms"][arm]
    return {
        "replicate_index": replicate_index,
        "primary_value": max(
            0.0, float(result.get("best_discovered_substantive_score_delta", 0.0) or 0.0)
        ),
        "robust_safe": bool(result.get("best_discovered_robust_safe", False)),
        "search_status": result["search_status"],
    }


def _select_best(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the preregistered value, safety, then earlier-replicate tie break."""
    return max(
        rows,
        key=lambda row: (
            row["primary_value"],
            row["robust_safe"],
            -row["replicate_index"],
        ),
    )


def analyze(receipt_root: Path) -> dict[str, Any]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    cohort = json.loads(COHORT_MANIFEST_PATH.read_text(encoding="utf-8"))
    seeds = protocol["direct_replicates"]["local_seeds"]
    effects = []
    arm_scores = {arm: [] for arm in protocol["arms"]}
    arm_safe = {arm: [] for arm in protocol["arms"]}
    instance_rows = []
    for item in cohort["instances"]:
        instance_id = item["instance_id"]
        replicate_rows = {arm: [] for arm in protocol["arms"]}
        for replicate_index, seed in enumerate(seeds, start=1):
            path = receipt_root / instance_id / f"seed_{seed}" / "hidden_adjudication.json"
            if not path.is_file():
                raise RuntimeError(f"missing completed ITT block receipt: {path}")
            receipt = json.loads(path.read_text(encoding="utf-8"))
            for arm in protocol["arms"]:
                replicate_rows[arm].append(_replicate_result(receipt, arm, replicate_index))
        selected = {arm: _select_best(rows) for arm, rows in replicate_rows.items()}
        raw = selected["raw_direct"]["primary_value"]
        structured = selected["structured_direct"]["primary_value"]
        effect = structured - raw
        effects.append(effect)
        for arm in protocol["arms"]:
            arm_scores[arm].append(selected[arm]["primary_value"])
            arm_safe[arm].append(selected[arm]["robust_safe"])
        instance_rows.append(
            {
                "instance_id": instance_id,
                "replicates": replicate_rows,
                "selected": selected,
                "instance_effect": effect,
            }
        )

    primary = protocol["primary_endpoint"]
    margin = float(primary["minimum_meaningful_effect"])
    alpha = float(primary["one_sided_alpha"])
    required_safe = int(primary["structured_safety_gate"]["robust_safe_instances_equals"])
    observed = mean(effects)
    p_value = exact_sign_flip_greater(effects, margin)
    safe_count = sum(arm_safe["structured_direct"])
    established = observed > margin and p_value <= alpha and safe_count == required_safe
    if established:
        architecture = "STRUCTURED_DIRECT_INCREMENTAL_VALUE_ESTABLISHED"
    elif safe_count != required_safe:
        architecture = "STRUCTURED_DIRECT_VALUE_NOT_ESTABLISHED_SAFETY_GATE_FAILED"
    else:
        architecture = "STRUCTURED_DIRECT_INCREMENTAL_VALUE_NOT_ESTABLISHED"
    tie = max(abs(value) for value in primary["tie_interval_inclusive"])
    return {
        "experiment_id": protocol["experiment_id"],
        "analysis_unit": "fresh_instance",
        "instance_count": len(instance_rows),
        "estimand": "instance_best_of_six_structured_direct_minus_raw_direct_hidden_substantive_delta",
        "instance_results": instance_rows,
        "arm_summaries": {
            arm: {
                "mean_substantive_score_delta": mean(arm_scores[arm]),
                "robust_safe_instances": sum(arm_safe[arm]),
            }
            for arm in protocol["arms"]
        },
        "STRUCTURED_DIRECT_INCREMENT": {
            "observed_mean": observed,
            "minimum_meaningful_effect": margin,
            "one_sided_exact_p": p_value,
            "structured_safety_gate_passed": safe_count == required_safe,
            "established": established,
            **_effect_counts(effects, tie),
        },
        "architecture_decision": architecture,
        "claim_ceiling": protocol["claim_ceiling"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(args.receipt_root.resolve())
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
