#!/usr/bin/env python3
"""Archive SKY-1 receipts and compute descriptive secondary endpoints.

This post-treatment closeout utility has no primary-claim authority. The
execution-manifest-bound ``analysis.py`` alone decides the primary contrast.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

HERE = Path(__file__).resolve().parent
PROTOCOL_PATH = HERE / "protocol.json"
FINAL_RESULT_PATH = HERE / "receipts" / "execution" / "FINAL_RESULT.json"
TOKEN_GRID = [0, 50000, 100000, 150000, 200000, 250000, 300000]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _candidate_token_map(budget: dict[str, Any]) -> dict[str, int]:
    cumulative = 0
    result = {}
    for event in budget["events"]:
        if event["kind"] == "generation":
            cumulative += int(event.get("input_tokens", 0)) + int(event.get("output_tokens", 0))
        elif event["kind"] == "evaluation" and event.get("program_id"):
            result[str(event["program_id"])] = cumulative
    return result


def closeout(source_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    if not FINAL_RESULT_PATH.is_file():
        raise RuntimeError("frozen primary analysis must run before descriptive closeout")
    destination = HERE / "receipts" / "execution"
    archive_rows = []
    arm_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for instance_index in range(1, protocol["instances"]["count"] + 1):
        instance_id = f"instance_{instance_index:02d}"
        for seed in protocol["nested_replicates"]["local_seeds"]:
            source_block = source_root / instance_id / f"seed_{seed}"
            hidden_source = source_block / "hidden_adjudication.json"
            if not hidden_source.is_file():
                raise RuntimeError(f"missing hidden receipt: {hidden_source}")
            hidden = json.loads(hidden_source.read_text(encoding="utf-8"))
            if hidden["results_returned_to_search"] is not False:
                raise RuntimeError(f"hidden feedback boundary failed: {hidden_source}")

            archived_block = destination / instance_id / f"seed_{seed}"
            archived_block.mkdir(parents=True, exist_ok=True)
            hidden_dest = archived_block / "hidden_adjudication.json"
            if hidden_dest.exists():
                raise FileExistsError(hidden_dest)
            shutil.copyfile(hidden_source, hidden_dest)
            archive_rows.append(
                {
                    "kind": "hidden_adjudication",
                    "path": hidden_dest.relative_to(HERE).as_posix(),
                    "sha256": _sha256(hidden_dest),
                }
            )

            for arm in protocol["arms"]:
                search_source = source_block / arm / "search_receipt.json"
                if not search_source.is_file():
                    raise RuntimeError(f"missing search receipt: {search_source}")
                search = json.loads(search_source.read_text(encoding="utf-8"))
                if search["status"] != "COMPLETED":
                    raise RuntimeError(f"non-completed assigned arm: {search_source}")
                search_dest = archived_block / f"{arm}.search_receipt.json"
                if search_dest.exists():
                    raise FileExistsError(search_dest)
                shutil.copyfile(search_source, search_dest)
                archive_rows.append(
                    {
                        "kind": "search_receipt",
                        "path": search_dest.relative_to(HERE).as_posix(),
                        "sha256": _sha256(search_dest),
                    }
                )

                result = hidden["arms"][arm]
                budget = result["search_budget"]
                token_map = _candidate_token_map(budget)
                real_attempts = [
                    attempt for attempt in result["hidden_attempts"] if attempt["candidate_id"]
                ]
                first_pass_tokens = None
                for attempt in real_attempts:
                    if attempt["metrics"].get("behavioral_improvement_detected") == 1.0:
                        first_pass_tokens = token_map.get(str(attempt["candidate_id"]))
                        break
                cost_curve = {}
                for threshold in TOKEN_GRID:
                    eligible = [
                        float(attempt["metrics"].get("substantive_score_delta", 0.0) or 0.0)
                        for attempt in real_attempts
                        if token_map.get(str(attempt["candidate_id"]), threshold + 1) <= threshold
                    ]
                    cost_curve[str(threshold)] = max([0.0, *eligible])
                arm_rows[arm].append(
                    {
                        "primary_behavioral_discovery": bool(
                            result["primary_behavioral_discovery"]
                        ),
                        "best_substantive_delta": float(
                            result["best_discovered_substantive_score_delta"] or 0.0
                        ),
                        "anytime_auc": float(result["behavioral_anytime_auc"]),
                        "tokens": int(budget["usage"]["total_tokens"]),
                        "generation_calls": int(budget["usage"]["generation_calls"]),
                        "evaluator_attempts": int(budget["usage"]["evaluator_attempts"]),
                        "first_pass_tokens": first_pass_tokens,
                        "real_hidden_candidates": len(real_attempts),
                        "valid_hidden_candidates": sum(
                            attempt["metrics"].get("validity") == 1.0 for attempt in real_attempts
                        ),
                        "mean_task_success": mean(
                            [
                                float(attempt["metrics"].get("task_success", 0.0))
                                for attempt in real_attempts
                            ]
                            or [0.0]
                        ),
                        "mean_safe_termination": mean(
                            [
                                float(attempt["metrics"].get("safe_termination", 0.0))
                                for attempt in real_attempts
                            ]
                            or [0.0]
                        ),
                        "cost_curve": cost_curve,
                    }
                )

    secondary_arms = {}
    for arm, rows in arm_rows.items():
        total_real = sum(row["real_hidden_candidates"] for row in rows)
        total_valid = sum(row["valid_hidden_candidates"] for row in rows)
        first_pass = [row["first_pass_tokens"] for row in rows if row["first_pass_tokens"]]
        secondary_arms[arm] = {
            "blocks": len(rows),
            "primary_behavioral_discoveries": sum(
                row["primary_behavioral_discovery"] for row in rows
            ),
            "mean_best_substantive_delta": mean(row["best_substantive_delta"] for row in rows),
            "mean_behavioral_anytime_auc": mean(row["anytime_auc"] for row in rows),
            "total_tokens": sum(row["tokens"] for row in rows),
            "mean_tokens": mean(row["tokens"] for row in rows),
            "mean_generation_calls": mean(row["generation_calls"] for row in rows),
            "mean_evaluator_attempts": mean(row["evaluator_attempts"] for row in rows),
            "mean_tokens_to_first_behavioral_pass_when_reached": (
                mean(first_pass) if first_pass else None
            ),
            "real_hidden_candidates": total_real,
            "valid_hidden_candidate_rate": total_valid / total_real if total_real else 0.0,
            "mean_candidate_task_success": mean(row["mean_task_success"] for row in rows),
            "mean_candidate_safe_termination": mean(row["mean_safe_termination"] for row in rows),
            "mean_cost_effectiveness_curve": {
                str(threshold): mean(row["cost_curve"][str(threshold)] for row in rows)
                for threshold in TOKEN_GRID
            },
        }

    audit = {
        "experiment_id": protocol["experiment_id"],
        "status": "COMPLETE",
        "search_receipts": sum(row["kind"] == "search_receipt" for row in archive_rows),
        "hidden_adjudication_receipts": sum(
            row["kind"] == "hidden_adjudication" for row in archive_rows
        ),
        "candidate_manifests_local_only": (
            protocol["instances"]["count"]
            * len(protocol["nested_replicates"]["local_seeds"])
            * len(protocol["arms"])
        ),
        "model_outputs_committed": False,
        "arm_level_failures": 0,
        "hidden_results_returned_to_search_blocks": 0,
        "max_generation_calls": max(
            row["generation_calls"] for rows in arm_rows.values() for row in rows
        ),
        "max_evaluator_attempts": max(
            row["evaluator_attempts"] for rows in arm_rows.values() for row in rows
        ),
        "max_total_tokens": max(row["tokens"] for rows in arm_rows.values() for row in rows),
        "primary_result_sha256": _sha256(FINAL_RESULT_PATH),
        "orchestration_events": [],
        "archived_receipts": archive_rows,
    }
    secondary = {
        "experiment_id": protocol["experiment_id"],
        "status": "DESCRIPTIVE_SECONDARY_ONLY",
        "primary_gate_override_authority": False,
        "token_grid": TOKEN_GRID,
        "arms": secondary_arms,
    }
    return audit, secondary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    audit, secondary = closeout(args.source_root.resolve())
    destination = HERE / "receipts" / "execution"
    _write_once(destination / "EXECUTION_AUDIT.json", audit)
    _write_once(destination / "SECONDARY_RESULTS.json", secondary)
    print(json.dumps({"audit": audit, "secondary": secondary}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
