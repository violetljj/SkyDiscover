#!/usr/bin/env python3
"""Execute preregistered SKY-1 paired blocks with deterministic arm ordering."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import harness

HERE = Path(__file__).resolve().parent


def _blocks() -> list[tuple[int, str, int]]:
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    rows = []
    block_index = 0
    for instance_index in range(1, protocol["instances"]["count"] + 1):
        for seed in protocol["nested_replicates"]["local_seeds"]:
            rows.append((block_index, f"instance_{instance_index:02d}", seed))
            block_index += 1
    return rows


def _arm_order(block_index: int) -> list[str]:
    return ["naked_codex", "sky_search"] if block_index % 2 == 0 else [
        "sky_search",
        "naked_codex",
    ]


async def execute_shard(output_root: Path, shard_index: int, shard_count: int) -> dict:
    completed = []
    for block_index, instance_id, seed in _blocks():
        if block_index % shard_count != shard_index:
            continue
        block_dir = output_root / instance_id / f"seed_{seed}"
        for arm in _arm_order(block_index):
            receipt_path = block_dir / arm / "search_receipt.json"
            if not receipt_path.is_file():
                await harness.run_arm(arm, instance_id, seed, output_root)
        hidden_path = block_dir / "hidden_adjudication.json"
        if not hidden_path.is_file():
            harness.adjudicate_block(instance_id, seed, output_root)
        completed.append({"block_index": block_index, "instance_id": instance_id, "seed": seed})
    return {
        "experiment_id": "L10M-SKY-1",
        "shard_index": shard_index,
        "shard_count": shard_count,
        "completed_blocks": completed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, default=1)
    args = parser.parse_args()
    if not 0 <= args.shard_index < args.shard_count:
        raise ValueError("shard-index must be in [0, shard-count)")
    result = asyncio.run(
        execute_shard(args.output_root.resolve(), args.shard_index, args.shard_count)
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
