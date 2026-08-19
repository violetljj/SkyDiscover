"""Archive receipts and audit the frozen result without primary-claim authority."""

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
ARMS = ("naked_structured", "evox_structured", "sky_evox_structured")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def safe_tie_exists(arm: dict[str, Any]) -> bool:
    best = max(float(row["primary_substantive_value"]) for row in arm["hidden_attempts"])
    return any(
        bool(row["robust_safe"]) and abs(float(row["primary_substantive_value"]) - best) < 1e-12
        for row in arm["hidden_attempts"]
    )


def closeout(run_root: Path, primary_source: Path) -> dict[str, Any]:
    destination = HERE / "receipts/execution"
    if destination.exists():
        raise FileExistsError(f"refusing to replace execution archive: {destination}")
    destination.mkdir(parents=True)
    primary_destination = destination / "FINAL_RESULT.json"
    shutil.copyfile(primary_source, primary_destination)
    archived = [
        {
            "kind": "frozen_primary_result",
            "path": primary_destination.relative_to(HERE).as_posix(),
            "sha256": sha256(primary_destination),
        }
    ]
    statuses = defaultdict(int)
    token_totals = defaultdict(int)
    intended_safe = defaultdict(int)
    recorded_safe = defaultdict(int)
    mismatches = []
    for index in range(1, 13):
        instance = f"instance_{index:02d}"
        block = run_root / instance / "seed_947"
        hidden_source = block / "hidden_adjudication.json"
        hidden = json.loads(hidden_source.read_text(encoding="utf-8"))
        if hidden["results_returned_to_search"] is not False:
            raise RuntimeError(f"hidden feedback boundary failed: {hidden_source}")
        archived_block = destination / instance / "seed_947"
        archived_block.mkdir(parents=True)
        hidden_destination = archived_block / "hidden_adjudication.json"
        shutil.copyfile(hidden_source, hidden_destination)
        archived.append(
            {
                "kind": "hidden_adjudication",
                "path": hidden_destination.relative_to(HERE).as_posix(),
                "sha256": sha256(hidden_destination),
            }
        )
        for arm_name in ARMS:
            search_source = block / arm_name / "search_receipt.json"
            search = json.loads(search_source.read_text(encoding="utf-8"))
            statuses[search["status"]] += 1
            token_totals[arm_name] += int(search["budget"]["usage"]["total_tokens"])
            if search["budget"]["usage"]["generation_calls"] != 6:
                raise RuntimeError(f"unexpected generation count: {search_source}")
            search_destination = archived_block / f"{arm_name}.search_receipt.json"
            shutil.copyfile(search_source, search_destination)
            archived.append(
                {
                    "kind": "search_receipt",
                    "path": search_destination.relative_to(HERE).as_posix(),
                    "sha256": sha256(search_destination),
                }
            )
            arm = hidden["arms"][arm_name]
            intended = safe_tie_exists(arm)
            recorded = bool(arm["best_discovered_robust_safe"])
            intended_safe[arm_name] += intended
            recorded_safe[arm_name] += recorded
            if intended != recorded:
                mismatches.append(
                    {
                        "instance_id": instance,
                        "arm": arm_name,
                        "recorded": recorded,
                        "safe_equal_primary_value_candidate_exists": intended,
                    }
                )
    primary = json.loads(primary_destination.read_text(encoding="utf-8"))
    audit = {
        "experiment_id": "L10M-STRUCT-SEARCH-1",
        "status": "COMPLETE_WITH_DECISION_INVARIANT_TIE_BREAK_DEFECT",
        "primary_override_authority": False,
        "formal_arm_statuses": dict(statuses),
        "search_receipts": sum(item["kind"] == "search_receipt" for item in archived),
        "hidden_adjudication_receipts": sum(
            item["kind"] == "hidden_adjudication" for item in archived
        ),
        "model_outputs_committed": False,
        "hidden_results_returned_to_search_blocks": 0,
        "total_tokens_by_arm": dict(token_totals),
        "mean_tokens_per_arm_unit": {
            arm: mean(
                json.loads(
                    (
                        destination / f"instance_{index:02d}/seed_947/{arm}.search_receipt.json"
                    ).read_text(encoding="utf-8")
                )["budget"]["usage"]["total_tokens"]
                for index in range(1, 13)
            )
            for arm in ARMS
        },
        "tie_break_defect": {
            "cause": "max_primary_value_used_generation_order_for_zero_value_safe_unsafe_ties",
            "recorded_robust_safe_counts": dict(recorded_safe),
            "intended_safe_tie_counts": dict(intended_safe),
            "mismatches": mismatches,
            "decision_invariant": True,
            "reason": (
                "EvoX remains below the strict +0.005 mean gate; Sky+EvoX equals rather "
                "than exceeds +0.005 and remains below 12/12 robust-safe."
            ),
        },
        "primary_architecture_decision": primary["architecture_decision"],
        "primary_result_sha256": sha256(primary_destination),
        "archived_receipts": archived,
    }
    write_once(destination / "EXECUTION_AUDIT.json", audit)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--primary-result", type=Path, required=True)
    args = parser.parse_args()
    audit = closeout(args.run_root.resolve(), args.primary_result.resolve())
    print(
        json.dumps(
            {
                "status": audit["status"],
                "search_receipts": audit["search_receipts"],
                "hidden_adjudication_receipts": audit["hidden_adjudication_receipts"],
                "primary_architecture_decision": audit["primary_architecture_decision"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
