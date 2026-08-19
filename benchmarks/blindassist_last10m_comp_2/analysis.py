#!/usr/bin/env python3
"""Frozen instance-level exact analysis for completed L10M-COMP-2 receipts."""

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
    """Test a location shift greater than margin under sign exchangeability."""
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


def _best_score(receipt: dict[str, Any], arm: str) -> float:
    result = receipt["arms"][arm]
    return max(
        0.0,
        float(result.get("best_discovered_substantive_score_delta", 0.0) or 0.0),
    )


def _effect_counts(effects: list[float], tie: float) -> dict[str, int]:
    return {
        "wins": sum(effect > tie for effect in effects),
        "ties": sum(-tie <= effect <= tie for effect in effects),
        "losses": sum(effect < -tie for effect in effects),
    }


def analyze(receipt_root: Path) -> dict[str, Any]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    cohort = json.loads(COHORT_MANIFEST_PATH.read_text(encoding="utf-8"))
    seeds = protocol["nested_replicates"]["local_seeds"]
    instance_effects_e = []
    instance_effects_h = []
    instance_rows = []
    for item in cohort["instances"]:
        instance_id = item["instance_id"]
        replicate_e = []
        replicate_h = []
        for seed in seeds:
            path = receipt_root / instance_id / f"seed_{seed}" / "hidden_adjudication.json"
            if not path.is_file():
                raise RuntimeError(f"missing completed ITT block receipt: {path}")
            receipt = json.loads(path.read_text(encoding="utf-8"))
            naked = _best_score(receipt, "naked_codex")
            evox = _best_score(receipt, "evox")
            sky_evox = _best_score(receipt, "sky_evox")
            replicate_e.append(evox - naked)
            replicate_h.append(sky_evox - evox)
        effect_e = mean(replicate_e)
        effect_h = mean(replicate_h)
        instance_effects_e.append(effect_e)
        instance_effects_h.append(effect_h)
        instance_rows.append(
            {
                "instance_id": instance_id,
                "replicate_effects_e": replicate_e,
                "replicate_effects_h": replicate_h,
                "instance_effect_e": effect_e,
                "instance_effect_h": effect_h,
            }
        )

    primary = protocol["primary_analysis"]
    alpha = float(primary["one_sided_alpha"])
    delta_e = float(primary["delta_e_minimum_meaningful_effect"])
    delta_h = float(primary["delta_h_minimum_meaningful_effect"])
    p_g1 = exact_sign_flip_greater(instance_effects_e, delta_e)
    g1 = mean(instance_effects_e) > delta_e and p_g1 <= alpha
    p_g2 = exact_sign_flip_greater(instance_effects_h, delta_h) if g1 else None
    g2 = bool(g1 and mean(instance_effects_h) > delta_h and p_g2 <= alpha)
    equivalence_lower = exact_sign_flip_greater(instance_effects_h, -delta_h) if g1 else None
    equivalence_upper = (
        exact_sign_flip_greater([-effect for effect in instance_effects_h], -delta_h)
        if g1
        else None
    )
    equivalent = bool(g1 and equivalence_lower <= alpha and equivalence_upper <= alpha)
    harm_p = (
        exact_sign_flip_greater([-effect for effect in instance_effects_h], delta_h) if g1 else None
    )
    harm = bool(g1 and mean(instance_effects_h) < -delta_h and harm_p <= alpha)
    if not g1:
        architecture = "EVOX_INCREMENTAL_VALUE_NOT_ESTABLISHED_G2_NOT_TESTED"
    elif g2:
        architecture = "ADOPT_SKY_EVOX_COMPOSED_SEARCH"
    elif equivalent:
        architecture = "ADOPT_EVOX_KEEP_SKY_AS_NEUTRAL_INFRASTRUCTURE"
    elif harm:
        architecture = "ADOPT_EVOX_REJECT_SKY_SEARCH_LAYER"
    else:
        architecture = "ADOPT_EVOX_SKY_SEARCH_LAYER_INCONCLUSIVE"

    tie = max(abs(value) for value in primary["tie_interval_inclusive"])
    return {
        "experiment_id": protocol["experiment_id"],
        "analysis_unit": "fresh_instance",
        "instance_count": len(instance_rows),
        "instance_results": instance_rows,
        "G1_DELTA_E": {
            "observed_mean": mean(instance_effects_e),
            "minimum_meaningful_effect": delta_e,
            "one_sided_exact_p": p_g1,
            "established": g1,
            **_effect_counts(instance_effects_e, tie),
        },
        "G2_DELTA_H": {
            "tested": g1,
            "observed_mean": mean(instance_effects_h),
            "minimum_meaningful_effect": delta_h,
            "one_sided_exact_p": p_g2,
            "superiority_established": g2,
            "equivalence_lower_p": equivalence_lower,
            "equivalence_upper_p": equivalence_upper,
            "equivalence_established": equivalent,
            "meaningful_harm_p": harm_p,
            "meaningful_harm_established": harm,
            **_effect_counts(instance_effects_h, tie),
        },
        "architecture_decision": architecture,
        "claim_ceiling": "WITHIN_FROZEN_L10M_COMP_2_GRAPH_FAMILY_ONLY",
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
