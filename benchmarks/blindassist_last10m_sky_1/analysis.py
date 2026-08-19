#!/usr/bin/env python3
"""Frozen instance-level exact analysis for completed L10M-SKY-1 receipts."""

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
    instance_effects = []
    instance_rows = []
    for item in cohort["instances"]:
        instance_id = item["instance_id"]
        replicate_effects = []
        for seed in seeds:
            path = receipt_root / instance_id / f"seed_{seed}" / "hidden_adjudication.json"
            if not path.is_file():
                raise RuntimeError(f"missing completed ITT block receipt: {path}")
            receipt = json.loads(path.read_text(encoding="utf-8"))
            naked = _best_score(receipt, "naked_codex")
            sky = _best_score(receipt, "sky_search")
            replicate_effects.append(sky - naked)
        instance_effect = mean(replicate_effects)
        instance_effects.append(instance_effect)
        instance_rows.append(
            {
                "instance_id": instance_id,
                "replicate_effects": replicate_effects,
                "instance_effect": instance_effect,
            }
        )

    primary = protocol["primary_analysis"]
    alpha = float(primary["one_sided_alpha"])
    margin = float(primary["minimum_meaningful_effect"])
    observed_mean = mean(instance_effects)
    superiority_p = exact_sign_flip_greater(instance_effects, margin)
    superiority = observed_mean > margin and superiority_p <= alpha
    equivalence_lower_p = exact_sign_flip_greater(instance_effects, -margin)
    equivalence_upper_p = exact_sign_flip_greater(
        [-effect for effect in instance_effects], -margin
    )
    equivalence = equivalence_lower_p <= alpha and equivalence_upper_p <= alpha
    harm_p = exact_sign_flip_greater([-effect for effect in instance_effects], margin)
    harm = observed_mean < -margin and harm_p <= alpha

    if superiority:
        decision = "SKY_DIRECT_SEARCH_VALUE_ESTABLISHED"
    elif equivalence:
        decision = "SKY_DIRECT_SEARCH_EQUIVALENT_TO_NAKED_WITHIN_MARGIN"
    elif harm:
        decision = "SKY_DIRECT_SEARCH_MEANINGFULLY_HARMFUL"
    else:
        decision = "SKY_DIRECT_SEARCH_VALUE_NOT_ESTABLISHED"

    tie = max(abs(value) for value in primary["tie_interval_inclusive"])
    return {
        "experiment_id": protocol["experiment_id"],
        "analysis_unit": "fresh_instance",
        "instance_count": len(instance_rows),
        "estimand": "instance_mean_seed_best_hidden_substantive_delta_sky_minus_naked",
        "instance_results": instance_rows,
        "DELTA_SKY": {
            "observed_mean": observed_mean,
            "minimum_meaningful_effect": margin,
            "one_sided_exact_p": superiority_p,
            "superiority_established": superiority,
            "equivalence_lower_p": equivalence_lower_p,
            "equivalence_upper_p": equivalence_upper_p,
            "equivalence_established": equivalence,
            "meaningful_harm_p": harm_p,
            "meaningful_harm_established": harm,
            **_effect_counts(instance_effects, tie),
        },
        "architecture_decision": decision,
        "claim_ceiling": "WITHIN_FROZEN_L10M_SKY_1_GRAPH_FAMILY_ONLY",
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
