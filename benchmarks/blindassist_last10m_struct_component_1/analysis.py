#!/usr/bin/env python3
"""Preregistered consumed-instance factorial analysis for COMPONENT-1."""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from statistics import mean
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROTOCOL_PATH = HERE / "protocol.json"
COHORT_PATH = ROOT / "benchmarks/blindassist_last10m_comp_2/cohort_manifest.json"


def exact_sign_flip_greater(effects: list[float], margin: float) -> float:
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


def _select_best(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        rows,
        key=lambda row: (row["primary_value"], row["robust_safe"], -row["replicate_index"]),
    )


def _leave_one_out_positive(effects: list[float]) -> bool:
    return all(mean(effects[:index] + effects[index + 1 :]) > 0.0 for index in range(len(effects)))


def analyze(receipt_root: Path) -> dict[str, Any]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    cohort = json.loads(COHORT_PATH.read_text(encoding="utf-8"))
    seeds = protocol["direct_replicates"]["local_seeds"]
    arms = protocol["arms"]
    instance_rows = []
    selected_values = {arm: [] for arm in arms}
    selected_safe = {arm: [] for arm in arms}
    factorial = {"progress_main": [], "moves_main": [], "interaction": []}
    contrasts = {arm: [] for arm in arms if arm != "raw_control"}
    for record in cohort["instances"]:
        instance_id = record["instance_id"]
        replicate_rows = {arm: [] for arm in arms}
        for replicate_index, seed in enumerate(seeds, start=1):
            receipt_path = receipt_root / instance_id / f"seed_{seed}" / "consumed_validation.json"
            if not receipt_path.is_file():
                raise RuntimeError(f"missing completed four-arm block: {receipt_path}")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            for arm in arms:
                row = receipt["arms"][arm]["validation"]
                replicate_rows[arm].append(
                    {
                        "replicate_index": replicate_index,
                        "seed": seed,
                        "primary_value": max(0.0, float(row["primary_substantive_value"])),
                        "robust_safe": bool(row["robust_safe"]),
                    }
                )
        selected = {arm: _select_best(rows) for arm, rows in replicate_rows.items()}
        values = {arm: selected[arm]["primary_value"] for arm in arms}
        for arm in arms:
            selected_values[arm].append(values[arm])
            selected_safe[arm].append(selected[arm]["robust_safe"])
        progress_main = 0.5 * (
            values["progress_only"]
            - values["raw_control"]
            + values["progress_moves"]
            - values["moves_only"]
        )
        moves_main = 0.5 * (
            values["moves_only"]
            - values["raw_control"]
            + values["progress_moves"]
            - values["progress_only"]
        )
        interaction = (
            values["progress_moves"]
            - values["progress_only"]
            - values["moves_only"]
            + values["raw_control"]
        )
        factorial["progress_main"].append(progress_main)
        factorial["moves_main"].append(moves_main)
        factorial["interaction"].append(interaction)
        for arm in contrasts:
            contrasts[arm].append(values[arm] - values["raw_control"])
        instance_rows.append(
            {
                "instance_id": instance_id,
                "selected": selected,
                "factorial_effects": {
                    "progress_main": progress_main,
                    "moves_main": moves_main,
                    "interaction": interaction,
                },
                "simple_arm_contrasts": {
                    arm: values[arm] - values["raw_control"] for arm in contrasts
                },
            }
        )
    analysis = protocol["analysis"]
    margin = float(analysis["minimum_meaningful_effect"])
    tie = max(abs(value) for value in analysis["tie_interval_inclusive"])
    factorial_results = {
        name: {
            "observed_mean": mean(effects),
            "minimum_meaningful_effect": margin,
            "one_sided_exact_p": exact_sign_flip_greater(effects, margin),
            **_effect_counts(effects, tie),
        }
        for name, effects in factorial.items()
    }
    admission_alpha = float(analysis["fresh_admission_familywise_alpha"])
    contrast_results = {}
    for arm, effects in contrasts.items():
        observed = mean(effects)
        p_value = exact_sign_flip_greater(effects, margin)
        safe_count = sum(selected_safe[arm])
        leave_one_out = _leave_one_out_positive(effects)
        admitted = (
            observed > margin
            and p_value <= admission_alpha
            and safe_count == len(instance_rows)
            and leave_one_out
        )
        contrast_results[arm] = {
            "observed_mean": observed,
            "minimum_meaningful_effect": margin,
            "one_sided_exact_p": p_value,
            "familywise_alpha": admission_alpha,
            "robust_safe_instances": safe_count,
            "all_leave_one_out_means_positive": leave_one_out,
            "fresh_preregistration_admitted": admitted,
            **_effect_counts(effects, tie),
        }
    admitted_arms = [
        arm for arm, result in contrast_results.items() if result["fresh_preregistration_admitted"]
    ]
    return {
        "experiment_id": protocol["experiment_id"],
        "evidence_role": protocol["evidence_role"],
        "analysis_unit": "consumed_instance",
        "instance_count": len(instance_rows),
        "instance_results": instance_rows,
        "arm_summaries": {
            arm: {
                "mean_selected_substantive_value": mean(selected_values[arm]),
                "robust_safe_instances": sum(selected_safe[arm]),
            }
            for arm in arms
        },
        "factorial_estimands": factorial_results,
        "fresh_admission_contrasts": contrast_results,
        "fresh_preregistration_admitted_arms": admitted_arms,
        "fresh_execution_authorized": False,
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
