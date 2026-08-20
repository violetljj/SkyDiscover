#!/usr/bin/env python3
"""Read-only progress and ETA summary for L10M-LONG-HORIZON-1."""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROTOCOL = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
COHORT = json.loads(
    (HERE.parents[1] / "benchmarks/blindassist_last10m_comp_2/cohort_manifest.json").read_text(
        encoding="utf-8"
    )
)


def summarize(root: Path) -> dict[str, object]:
    total = len(COHORT["instances"]) * len(PROTOCOL["replicates"]["seeds"]) * len(PROTOCOL["arms"])
    counts: Counter[str] = Counter()
    active = []
    completed_iterations = 0
    latest = 0.0
    earliest = time.time()
    for record in COHORT["instances"]:
        for seed in PROTOCOL["replicates"]["seeds"]:
            for arm in PROTOCOL["arms"]:
                unit = root / record["instance_id"] / f"seed_{seed}" / arm
                receipt = unit / "trajectory_receipt.json"
                if receipt.is_file():
                    data = json.loads(receipt.read_text(encoding="utf-8"))
                    counts[str(data["status"])] += 1
                    iteration = max(
                        (row["iteration"] for row in data.get("prefix_observations", [])),
                        default=0,
                    )
                    completed_iterations += iteration
                    latest = max(latest, receipt.stat().st_mtime)
                    continue
                checkpoints = []
                for path in (unit / "checkpoints").glob("checkpoint_*"):
                    try:
                        checkpoints.append(int(path.name.split("_", 1)[1]))
                    except ValueError:
                        pass
                iteration = max(checkpoints, default=0)
                completed_iterations += iteration
                started = unit / "launcher_started.json"
                if started.is_file():
                    counts["ACTIVE_OR_RECOVERABLE"] += 1
                    active.append(
                        {
                            "unit": f"{record['instance_id']}/seed_{seed}/{arm}",
                            "iteration": iteration,
                        }
                    )
                    latest = max(latest, started.stat().st_mtime)
                    earliest = min(earliest, started.stat().st_mtime)
                else:
                    counts["PENDING"] += 1
    target_iterations = total * PROTOCOL["horizon"]["solution_candidate_generations"]
    elapsed = max(0.0, time.time() - earliest)
    rate = completed_iterations / elapsed if completed_iterations and elapsed else 0.0
    eta = (target_iterations - completed_iterations) / rate if rate else None
    return {
        "experiment_id": PROTOCOL["experiment_id"],
        "read_only": True,
        "trajectories": {"total": total, "status_counts": dict(counts)},
        "iterations": {
            "completed": completed_iterations,
            "total": target_iterations,
            "percent": round(100.0 * completed_iterations / target_iterations, 2),
        },
        "active": active,
        "last_activity_age_seconds": round(time.time() - latest, 1) if latest else None,
        "eta_seconds": round(eta, 1) if eta is not None else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.run_root.resolve()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
