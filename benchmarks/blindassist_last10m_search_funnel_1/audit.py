#!/usr/bin/env python3
"""Receipt-only search-funnel audit for the consumed L10M-SKY-1 cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROTOCOL_PATH = HERE / "protocol.json"
SOURCE_ROOT = ROOT / "benchmarks" / "blindassist_last10m_sky_1"
COHORT_PATH = SOURCE_ROOT / "cohort_manifest.json"
ARCHIVE_ROOT = SOURCE_ROOT / "receipts" / "execution"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"missing required sealed input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_digest(rows: list[dict[str, str]]) -> str:
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _inner_metrics(program: dict[str, Any]) -> dict[str, Any]:
    metrics = program.get("metrics", {})
    if not isinstance(metrics, dict) or not isinstance(metrics.get("metrics"), dict):
        raise RuntimeError(f"program {program.get('id')} has no frozen development metrics")
    return metrics["metrics"]


def _hidden_value(row: dict[str, Any]) -> float:
    return max(0.0, float(row.get("metrics", {}).get("substantive_score_delta", 0.0) or 0.0))


def _robust_safe(row: dict[str, Any]) -> bool:
    metrics = row.get("metrics", {})
    return (
        float(metrics.get("validity", 0.0) or 0.0) == 1.0
        and float(metrics.get("task_success", 0.0) or 0.0) == 1.0
        and float(metrics.get("safe_termination", 0.0) or 0.0) == 1.0
        and float(metrics.get("unsafe_forward_count", 0.0) or 0.0) == 0.0
        and float(metrics.get("premature_arrival_count", 0.0) or 0.0) == 0.0
    )


def _programs(checkpoint: Path, input_hashes: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    result = {}
    for path in sorted((checkpoint / "programs").glob("*.json")):
        input_hashes.append({"path": str(path), "sha256": _sha256(path)})
        program = _load(path)
        program_id = str(program["id"])
        if program_id in result:
            raise RuntimeError(f"duplicate checkpoint program id: {program_id}")
        result[program_id] = program
    return result


def _audit_arm(
    run_root: Path,
    instance_id: str,
    seed: int,
    arm: str,
    hidden_arm: dict[str, Any],
    expected_candidates: int,
    input_hashes: list[dict[str, str]],
) -> dict[str, Any]:
    arm_root = run_root / instance_id / f"seed_{seed}" / arm
    manifest_path = arm_root / "candidate_manifest.json"
    search_path = arm_root / "search_receipt.json"
    best_path = arm_root / "best" / "best_program_info.json"
    checkpoint = arm_root / "checkpoints" / "checkpoint_10"
    checkpoint_best_path = checkpoint / "best_program_info.json"
    for path in (manifest_path, search_path, best_path, checkpoint_best_path):
        input_hashes.append({"path": str(path), "sha256": _sha256(path)})

    manifest = _load(manifest_path)
    search = _load(search_path)
    best = _load(best_path)
    checkpoint_best = _load(checkpoint_best_path)
    candidates = manifest.get("candidates", [])
    if (
        search.get("status") != "COMPLETED"
        or len(candidates) > expected_candidates
        or int(search.get("candidate_count", -1)) != len(candidates)
    ):
        raise RuntimeError(f"incomplete arm evidence: {instance_id}/{seed}/{arm}")
    if best.get("id") != search.get("best_program_id") or checkpoint_best.get("id") != best.get(
        "id"
    ):
        raise RuntimeError(f"retained best identity mismatch: {instance_id}/{seed}/{arm}")

    programs = _programs(checkpoint, input_hashes)
    best_id = str(best["id"])
    if best_id not in programs:
        raise RuntimeError(f"retained best missing from checkpoint: {instance_id}/{seed}/{arm}")
    hidden_rows = hidden_arm.get("hidden_attempts", [])
    if len(hidden_rows) != expected_candidates:
        raise RuntimeError(f"hidden attempt count mismatch: {instance_id}/{seed}/{arm}")
    for index, hidden in enumerate(hidden_rows[len(candidates) :], start=len(candidates) + 1):
        if hidden.get("candidate_id") is not None or not str(hidden.get("status", "")).startswith(
            "itt_zero_"
        ):
            raise RuntimeError(
                f"missing candidate is not a frozen ITT zero: {instance_id}/{seed}/{arm}/{index}"
            )

    joined = []
    candidate_ids = []
    for index, (candidate, hidden) in enumerate(zip(candidates, hidden_rows), start=1):
        candidate_id = str(candidate["id"])
        candidate_ids.append(candidate_id)
        if hidden.get("candidate_id") != candidate_id or int(hidden.get("attempt", -1)) != index:
            raise RuntimeError(
                f"candidate/hidden order mismatch: {instance_id}/{seed}/{arm}/{index}"
            )
        solution_hash = hashlib.sha256(candidate["solution"].encode("utf-8")).hexdigest()
        if (
            candidate.get("solution_sha256") != solution_hash
            or hidden.get("solution_sha256") != solution_hash
        ):
            raise RuntimeError(
                f"candidate source hash mismatch: {instance_id}/{seed}/{arm}/{index}"
            )
        if candidate_id not in programs:
            raise RuntimeError(
                f"candidate missing from checkpoint: {instance_id}/{seed}/{arm}/{index}"
            )
        program = programs[candidate_id]
        if hashlib.sha256(program["solution"].encode("utf-8")).hexdigest() != solution_hash:
            raise RuntimeError(f"checkpoint source mismatch: {instance_id}/{seed}/{arm}/{index}")
        dev = _inner_metrics(program)
        parent_id = program.get("parent_id")
        parent_dev = None
        if parent_id is not None:
            if parent_id not in programs:
                raise RuntimeError(
                    f"missing parent {parent_id}: {instance_id}/{seed}/{arm}/{index}"
                )
            parent_dev = float(
                _inner_metrics(programs[parent_id]).get("combined_score", 0.0) or 0.0
            )
        dev_score = float(dev.get("combined_score", 0.0) or 0.0)
        joined.append(
            {
                "attempt": index,
                "candidate_id": candidate_id,
                "parent_id": parent_id,
                "dev_combined_score": dev_score,
                "dev_valid": float(dev.get("validity", 0.0) or 0.0) == 1.0,
                "dev_improves_parent": parent_dev is not None and dev_score > parent_dev + 1e-12,
                "hidden_value": _hidden_value(hidden),
                "hidden_robust_safe": _robust_safe(hidden),
                "hidden_behavioral_pass": float(
                    hidden.get("metrics", {}).get("behavioral_improvement_detected", 0.0) or 0.0
                )
                == 1.0,
            }
        )

    retained_generated = best_id in candidate_ids
    if retained_generated:
        retained_row = joined[candidate_ids.index(best_id)]
        retained_hidden_value = retained_row["hidden_value"]
        retained_hidden_safe = retained_row["hidden_robust_safe"]
    else:
        if int(best.get("iteration", -1)) != 0:
            raise RuntimeError(
                f"non-generated retained best is not initial: {instance_id}/{seed}/{arm}"
            )
        retained_hidden_value = 0.0
        retained_hidden_safe = True

    oracle_row = max(
        joined, key=lambda row: (row["hidden_value"], row["hidden_robust_safe"], -row["attempt"])
    )
    safe_positive = [
        row for row in joined if row["hidden_robust_safe"] and row["hidden_value"] > 0.0
    ]
    dev_improvers = [row for row in joined if row["dev_improves_parent"]]
    return {
        "arm": arm,
        "instance_id": instance_id,
        "seed": seed,
        "generated_candidates": len(joined),
        "missing_candidate_opportunities": expected_candidates - len(joined),
        "unique_solution_hashes": len({candidate["solution_sha256"] for candidate in candidates}),
        "retained_program_id": best_id,
        "retained_is_generated": retained_generated,
        "retained_dev_combined_score": float(_inner_metrics(programs[best_id])["combined_score"]),
        "retained_hidden_value": retained_hidden_value,
        "retained_hidden_robust_safe": retained_hidden_safe,
        "oracle_generated_hidden_value": oracle_row["hidden_value"],
        "oracle_generated_candidate_id": oracle_row["candidate_id"],
        "oracle_generated_robust_safe": oracle_row["hidden_robust_safe"],
        "oracle_minus_retained_hidden_value": oracle_row["hidden_value"] - retained_hidden_value,
        "robust_safe_positive_candidates": len(safe_positive),
        "has_robust_safe_positive_candidate": bool(safe_positive),
        "dev_improving_children": len(dev_improvers),
        "dev_improving_children_with_hidden_gain": sum(
            row["hidden_value"] > 0.0 for row in dev_improvers
        ),
        "generated_children_with_hidden_gain": sum(row["hidden_value"] > 0.0 for row in joined),
        "candidate_rows": joined,
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    gaps = [float(row["oracle_minus_retained_hidden_value"]) for row in rows]
    dev_improvers = sum(int(row["dev_improving_children"]) for row in rows)
    converted = sum(int(row["dev_improving_children_with_hidden_gain"]) for row in rows)
    return {
        "blocks": len(rows),
        "generated_candidates": sum(int(row["generated_candidates"]) for row in rows),
        "missing_candidate_opportunities": sum(
            int(row["missing_candidate_opportunities"]) for row in rows
        ),
        "unique_solution_rate": sum(int(row["unique_solution_hashes"]) for row in rows)
        / sum(int(row["generated_candidates"]) for row in rows),
        "retained_generated_blocks": sum(bool(row["retained_is_generated"]) for row in rows),
        "blocks_with_robust_safe_positive_candidate": sum(
            bool(row["has_robust_safe_positive_candidate"]) for row in rows
        ),
        "mean_oracle_generated_hidden_value": mean(
            float(row["oracle_generated_hidden_value"]) for row in rows
        ),
        "mean_retained_hidden_value": mean(float(row["retained_hidden_value"]) for row in rows),
        "mean_oracle_minus_retained_hidden_value": mean(gaps),
        "positive_selection_gap_blocks": sum(gap > 1e-12 for gap in gaps),
        "dev_improving_children": dev_improvers,
        "dev_improving_children_with_hidden_gain": converted,
        "dev_improving_child_hidden_conversion_rate": (
            converted / dev_improvers if dev_improvers else 0.0
        ),
    }


def audit(run_root: Path) -> dict[str, Any]:
    protocol = _load(PROTOCOL_PATH)
    cohort = _load(COHORT_PATH)
    instances = {str(row["instance_id"]): row for row in cohort["instances"]}
    if len(instances) != int(protocol["expected_instances"]):
        raise RuntimeError("source cohort instance count does not match the frozen audit protocol")

    input_hashes = [
        {"path": str(PROTOCOL_PATH), "sha256": _sha256(PROTOCOL_PATH)},
        {"path": str(COHORT_PATH), "sha256": _sha256(COHORT_PATH)},
    ]
    rows = []
    for instance_id in sorted(instances):
        for seed in protocol["expected_seeds"]:
            hidden_path = ARCHIVE_ROOT / instance_id / f"seed_{seed}" / "hidden_adjudication.json"
            input_hashes.append({"path": str(hidden_path), "sha256": _sha256(hidden_path)})
            hidden = _load(hidden_path)
            if hidden.get("instance_id") != instance_id or int(hidden.get("seed", -1)) != seed:
                raise RuntimeError(f"hidden block identity mismatch: {instance_id}/{seed}")
            for arm in protocol["arms"]:
                rows.append(
                    _audit_arm(
                        run_root,
                        instance_id,
                        seed,
                        arm,
                        hidden["arms"][arm],
                        int(protocol["expected_candidates_per_arm_block"]),
                        input_hashes,
                    )
                )

    summaries = {
        arm: _summarize([row for row in rows if row["arm"] == arm]) for arm in protocol["arms"]
    }
    primary = summaries[protocol["primary_mechanism_arm"]]
    selection_gate = protocol["selection_loss_signal"]
    selection_signal = (
        primary["mean_oracle_minus_retained_hidden_value"]
        >= float(selection_gate["minimum_mean_oracle_minus_retained_hidden_value"])
        and primary["positive_selection_gap_blocks"]
        >= int(selection_gate["minimum_positive_gap_blocks"])
        and primary["blocks_with_robust_safe_positive_candidate"] > 0
    )
    scarcity_signal = primary["blocks_with_robust_safe_positive_candidate"] <= int(
        protocol["candidate_scarcity_signal"][
            "maximum_blocks_with_any_robust_safe_positive_candidate"
        ]
    )
    if selection_signal:
        decision = "SELECTION_RETENTION_SIGNAL"
    elif scarcity_signal:
        decision = "CANDIDATE_QUALITY_SCARCITY_SIGNAL"
    else:
        decision = "MIXED_OR_UNRESOLVED"

    normalized_hashes = sorted(input_hashes, key=lambda row: row["path"])
    return {
        "experiment_id": protocol["experiment_id"],
        "status": "COMPLETE",
        "source_experiment": protocol["source_experiment"],
        "model_calls": 0,
        "evaluator_calls": 0,
        "hidden_reruns": 0,
        "blocks": rows,
        "arm_summaries": summaries,
        "mechanism_decision": decision,
        "selection_signal_passed": selection_signal,
        "candidate_scarcity_signal_passed": scarcity_signal,
        "input_file_count": len(normalized_hashes),
        "input_identity_sha256": _canonical_digest(normalized_hashes),
        "claim_ceiling": protocol["claim_ceiling"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.run_root.resolve())
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
