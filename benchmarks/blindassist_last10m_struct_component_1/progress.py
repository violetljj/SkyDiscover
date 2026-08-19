#!/usr/bin/env python3
"""Read-only progress summary for a COMPONENT-1 execution root."""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def summarize(run_root: Path) -> dict[str, object]:
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    cohort = json.loads(
        (ROOT / "benchmarks/blindassist_last10m_comp_2/cohort_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    counts: Counter[str] = Counter()
    active = []
    failures: Counter[str] = Counter()
    latest_mtime = 0.0
    total = (
        len(cohort["instances"])
        * len(protocol["direct_replicates"]["local_seeds"])
        * len(protocol["arms"])
    )
    for record in cohort["instances"]:
        for seed in protocol["direct_replicates"]["local_seeds"]:
            for arm in protocol["arms"]:
                unit = run_root / record["instance_id"] / f"seed_{seed}" / arm
                receipt = unit / "search_receipt.json"
                started = unit / "unit_started.json"
                if receipt.is_file():
                    data = json.loads(receipt.read_text(encoding="utf-8"))
                    status = "completed" if data["status"] == "COMPLETED" else "failed"
                    counts[status] += 1
                    if status == "failed":
                        failures[str(data.get("error") or "unknown").split(":", 1)[0]] += 1
                    latest_mtime = max(latest_mtime, receipt.stat().st_mtime)
                elif started.is_file():
                    counts["in_doubt_or_active"] += 1
                    active.append(f"{record['instance_id']}/seed_{seed}/{arm}")
                    latest_mtime = max(latest_mtime, started.stat().st_mtime)
                else:
                    counts["pending"] += 1
    terminal = counts["completed"] + counts["failed"]
    return {
        "experiment_id": protocol["experiment_id"],
        "read_only": True,
        "units": {
            "terminal": terminal,
            "total": total,
            "percent": round(100.0 * terminal / total, 2),
        },
        "status_counts": dict(counts),
        "active_or_in_doubt_units": active,
        "failure_classes": dict(failures),
        "last_activity_unix": latest_mtime or None,
        "last_activity_age_seconds": round(time.time() - latest_mtime, 1) if latest_mtime else None,
        "eta": "unknown",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(summarize(args.run_root.resolve()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
