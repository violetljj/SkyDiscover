#!/usr/bin/env python3
"""Preregistered complete-block factorial analysis for COMPONENT-2."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROTOCOL_PATH = HERE / "protocol.json"
COHORT_PATH = ROOT / "benchmarks/blindassist_last10m_comp_2/cohort_manifest.json"


def _load_helpers():
    path = ROOT / "benchmarks/blindassist_last10m_struct_component_1/analysis.py"
    spec = importlib.util.spec_from_file_location("l10m_struct_component_2_analysis_helpers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


helpers = _load_helpers()
exact_sign_flip_greater = helpers.exact_sign_flip_greater


def _block_state(units: Path, instance_id: str, seed: int, arms: list[str]) -> dict[str, Any]:
    block = units / instance_id / f"seed_{seed}"
    terminal = [arm for arm in arms if (block / arm / "search_receipt.json").is_file()]
    started = [arm for arm in arms if (block / arm / "unit_started.json").is_file()]
    validation = block / "consumed_validation.json"
    if len(terminal) == len(arms):
        if not validation.is_file():
            return {"status": "SYSTEMIC_INTEGRITY_FAILURE", "reason": "missing_validation_receipt"}
        return {"status": "COMPLETE", "receipt": validation}
    return {
        "status": "INFRASTRUCTURE_INCOMPLETE",
        "terminal_arms": terminal,
        "in_doubt_arms": sorted(set(started) - set(terminal)),
        "never_started_arms": sorted(set(arms) - set(started)),
    }


def _not_evaluable(protocol: dict[str, Any], blocks: list[dict[str, Any]], reason: str):
    return {
        "experiment_id": protocol["experiment_id"],
        "status": "NOT_EVALUABLE",
        "reason": reason,
        "block_accounting": blocks,
        "factorial_estimands": None,
        "fresh_admission_contrasts": None,
        "fresh_execution_authorized": False,
        "claim_ceiling": "NO_FACTORIAL_OR_FRESH_ADMISSION_CLAIM",
    }


def analyze(run_root: Path) -> dict[str, Any]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    cohort = json.loads(COHORT_PATH.read_text(encoding="utf-8"))
    if (run_root / "component_1_receipts").exists():
        raise RuntimeError("forbidden COMPONENT-1 receipt input detected")
    units = run_root / "units"
    seeds = protocol["direct_replicates"]["local_seeds"]
    arms = protocol["arms"]
    block_rows = []
    complete_by_instance: dict[str, list[int]] = {}
    systemic = []
    for record in cohort["instances"]:
        instance_id = record["instance_id"]
        complete_by_instance[instance_id] = []
        for seed in seeds:
            state = _block_state(units, instance_id, seed, arms)
            row = {"instance_id": instance_id, "seed": seed, **state}
            block_rows.append(row)
            if state["status"] == "COMPLETE":
                complete_by_instance[instance_id].append(seed)
            elif state["status"] == "SYSTEMIC_INTEGRITY_FAILURE":
                systemic.append(row)
    if systemic:
        return _not_evaluable(
            protocol, block_rows, "SYSTEMIC_EVALUATOR_OR_RECEIPT_INTEGRITY_FAILURE"
        )
    complete_count = sum(len(value) for value in complete_by_instance.values())
    gate = protocol["complete_block_rule"]
    deficient = {
        instance_id: len(value)
        for instance_id, value in complete_by_instance.items()
        if len(value) < gate["minimum_complete_seeds_per_instance"]
    }
    if complete_count < gate["minimum_complete_blocks"] or deficient:
        return _not_evaluable(
            protocol,
            block_rows,
            f"COMPLETENESS_GATE_FAILED complete={complete_count} deficient_instances={deficient}",
        )

    selected_values = {arm: [] for arm in arms}
    selected_safe = {arm: [] for arm in arms}
    factorial = {"progress_main": [], "moves_main": [], "interaction": []}
    contrasts = {arm: [] for arm in arms if arm != "raw_control"}
    instance_rows = []
    for record in cohort["instances"]:
        instance_id = record["instance_id"]
        common_seeds = complete_by_instance[instance_id]
        candidates = {arm: [] for arm in arms}
        for seed in common_seeds:
            receipt = json.loads(
                (units / instance_id / f"seed_{seed}" / "consumed_validation.json").read_text(
                    encoding="utf-8"
                )
            )
            for arm in arms:
                row = receipt["arms"][arm]["validation"]
                candidates[arm].append(
                    {
                        "replicate_index": seeds.index(seed) + 1,
                        "seed": seed,
                        "primary_value": max(0.0, float(row["primary_substantive_value"])),
                        "robust_safe": bool(row["robust_safe"]),
                    }
                )
        selected = {arm: helpers._select_best(rows) for arm, rows in candidates.items()}
        values = {arm: selected[arm]["primary_value"] for arm in arms}
        for arm in arms:
            selected_values[arm].append(values[arm])
            selected_safe[arm].append(selected[arm]["robust_safe"])
        effects = {
            "progress_main": 0.5
            * (
                values["progress_only"]
                - values["raw_control"]
                + values["progress_moves"]
                - values["moves_only"]
            ),
            "moves_main": 0.5
            * (
                values["moves_only"]
                - values["raw_control"]
                + values["progress_moves"]
                - values["progress_only"]
            ),
            "interaction": values["progress_moves"]
            - values["progress_only"]
            - values["moves_only"]
            + values["raw_control"],
        }
        for name, value in effects.items():
            factorial[name].append(value)
        for arm in contrasts:
            contrasts[arm].append(values[arm] - values["raw_control"])
        instance_rows.append(
            {
                "instance_id": instance_id,
                "complete_seeds": common_seeds,
                "selected": selected,
                "factorial_effects": effects,
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
            **helpers._effect_counts(effects, tie),
        }
        for name, effects in factorial.items()
    }
    contrast_results = {}
    admission_alpha = float(analysis["fresh_admission_familywise_alpha"])
    for arm, effects in contrasts.items():
        observed = mean(effects)
        p_value = exact_sign_flip_greater(effects, margin)
        safe_count = sum(selected_safe[arm])
        leave_one_out = helpers._leave_one_out_positive(effects)
        contrast_results[arm] = {
            "observed_mean": observed,
            "minimum_meaningful_effect": margin,
            "one_sided_exact_p": p_value,
            "familywise_alpha": admission_alpha,
            "robust_safe_instances": safe_count,
            "all_leave_one_out_means_positive": leave_one_out,
            "fresh_preregistration_admitted": (
                observed > margin
                and p_value <= admission_alpha
                and safe_count == len(instance_rows)
                and leave_one_out
            ),
            **helpers._effect_counts(effects, tie),
        }
    admitted = [
        arm for arm, result in contrast_results.items() if result["fresh_preregistration_admitted"]
    ]
    return {
        "experiment_id": protocol["experiment_id"],
        "status": "EVALUABLE",
        "evidence_role": protocol["evidence_role"],
        "complete_blocks": complete_count,
        "total_planned_blocks": gate["total_planned_blocks"],
        "complete_seeds_by_instance": {
            key: len(value) for key, value in complete_by_instance.items()
        },
        "excluded_infrastructure_blocks": [
            row for row in block_rows if row["status"] == "INFRASTRUCTURE_INCOMPLETE"
        ],
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
        "fresh_preregistration_admitted_arms": admitted,
        "fresh_execution_authorized": False,
        "claim_ceiling": protocol["claim_ceiling"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(args.run_root.resolve())
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
