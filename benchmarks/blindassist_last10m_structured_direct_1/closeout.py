"""Archive sealed receipts and write a non-authoritative execution audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

HERE = Path(__file__).resolve().parent
ARMS = ("raw_direct", "structured_direct")
SEEDS = (1301, 1302, 1303, 1304, 1305, 1306)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


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
    statuses = Counter()
    token_totals = defaultdict(int)
    in_doubt = []
    hidden_count = 0
    for index in range(1, 13):
        instance = f"instance_{index:02d}"
        for seed in SEEDS:
            block = run_root / instance / f"seed_{seed}"
            hidden_source = block / "hidden_adjudication.json"
            if not hidden_source.is_file():
                raise RuntimeError(f"missing hidden receipt: {hidden_source}")
            hidden = json.loads(hidden_source.read_text(encoding="utf-8"))
            if hidden.get("results_returned_to_generation") is not False:
                raise RuntimeError(f"hidden feedback boundary failed: {hidden_source}")
            archived_block = destination / instance / f"seed_{seed}"
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
            hidden_count += 1
            for arm in ARMS:
                search_source = block / arm / "search_receipt.json"
                manifest_source = block / arm / "candidate_manifest.json"
                search = json.loads(search_source.read_text(encoding="utf-8"))
                statuses[search["status"]] += 1
                token_totals[arm] += int(search["budget"]["usage"]["total_tokens"])
                if search["status"] == "ARM_FAILED_ITT":
                    in_doubt.append(
                        {
                            "instance_id": instance,
                            "seed": seed,
                            "arm": arm,
                            "error": search.get("error"),
                        }
                    )
                if search["budget"]["ceilings"]["generation_calls"] != 1:
                    raise RuntimeError(f"unexpected generation ceiling: {search_source}")
                for source, suffix in (
                    (search_source, "search_receipt.json"),
                    (manifest_source, "candidate_manifest.json"),
                ):
                    target = archived_block / arm / suffix
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    archived.append(
                        {
                            "kind": (
                                "search_receipt"
                                if suffix.startswith("search")
                                else "candidate_manifest"
                            ),
                            "path": target.relative_to(HERE).as_posix(),
                            "sha256": sha256(target),
                        }
                    )
    primary = json.loads(primary_destination.read_text(encoding="utf-8"))
    audit = {
        "experiment_id": "L10M-STRUCT-DIRECT-1",
        "status": "COMPLETE_WITH_LAUNCHER_INCIDENTS",
        "primary_override_authority": False,
        "formal_arm_statuses": dict(statuses),
        "search_receipts": sum(item["kind"] == "search_receipt" for item in archived),
        "candidate_manifests": sum(item["kind"] == "candidate_manifest" for item in archived),
        "hidden_adjudication_receipts": hidden_count,
        "hidden_results_returned_to_generation_blocks": 0,
        "model_outputs_committed": False,
        "total_tokens_by_arm": dict(token_totals),
        "in_doubt_search_units": in_doubt,
        "launcher_incident": {
            "affected_units": len(in_doubt),
            "cause": "initial visible Start-Process launcher was terminated by console control handling before receipts",
            "recovery": "affected units sealed as ARM_FAILED_ITT; no retry; remaining units completed with hidden CreateNoWindow launcher",
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
                "candidate_manifests": audit["candidate_manifests"],
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
