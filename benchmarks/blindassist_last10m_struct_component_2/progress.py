#!/usr/bin/env python3
"""Read-only unit and complete-block progress for COMPONENT-2."""

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
    units = run_root / "units"
    counts: Counter[str] = Counter()
    blocks: Counter[str] = Counter()
    active = []
    latest = 0.0
    for record in cohort["instances"]:
        for seed in protocol["direct_replicates"]["local_seeds"]:
            terminal = 0
            in_doubt = 0
            for arm in protocol["arms"]:
                unit = units / record["instance_id"] / f"seed_{seed}" / arm
                receipt = unit / "search_receipt.json"
                started = unit / "unit_started.json"
                if receipt.is_file():
                    data = json.loads(receipt.read_text(encoding="utf-8"))
                    counts["completed" if data["status"] == "COMPLETED" else "failed_itt"] += 1
                    terminal += 1
                    latest = max(latest, receipt.stat().st_mtime)
                elif started.is_file():
                    counts["in_doubt_or_active"] += 1
                    in_doubt += 1
                    active.append(f"{record['instance_id']}/seed_{seed}/{arm}")
                    latest = max(latest, started.stat().st_mtime)
                else:
                    counts["pending"] += 1
            validation = units / record["instance_id"] / f"seed_{seed}" / "consumed_validation.json"
            if terminal == 4 and validation.is_file():
                blocks["complete_adjudicated"] += 1
            elif terminal == 4:
                blocks["terminal_pending_adjudication"] += 1
            elif in_doubt:
                blocks["incomplete_in_doubt"] += 1
            else:
                blocks["pending"] += 1
    terminal_units = counts["completed"] + counts["failed_itt"]
    return {
        "experiment_id": protocol["experiment_id"],
        "read_only": True,
        "units": {
            "terminal": terminal_units,
            "total": 288,
            "percent": round(100.0 * terminal_units / 288, 2),
        },
        "blocks": {"counts": dict(blocks), "complete": blocks["complete_adjudicated"], "total": 72},
        "status_counts": dict(counts),
        "active_or_in_doubt_units": active,
        "last_activity_unix": latest or None,
        "last_activity_age_seconds": round(time.time() - latest, 1) if latest else None,
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
