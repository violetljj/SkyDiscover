#!/usr/bin/env python3
"""Bounded hidden-process launcher for independent long-horizon trajectories."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROTOCOL = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
COHORT = json.loads(
    (HERE.parents[1] / "benchmarks/blindassist_last10m_comp_2/cohort_manifest.json").read_text(
        encoding="utf-8"
    )
)


def _assignments() -> list[tuple[str, int, str]]:
    arms = PROTOCOL["arms"]
    rows = []
    for instance_index, record in enumerate(COHORT["instances"]):
        for seed_index, seed in enumerate(PROTOCOL["replicates"]["seeds"]):
            offset = (instance_index + seed_index) % len(arms)
            for arm in arms[offset:] + arms[:offset]:
                rows.append((record["instance_id"], seed, arm))
    return rows


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")


async def _run_one(
    semaphore: asyncio.Semaphore,
    output_root: Path,
    remote_manifest: Path,
    assignment: tuple[str, int, str],
) -> None:
    instance, seed, arm = assignment
    unit = output_root / instance / f"seed_{seed}" / arm
    if (unit / "trajectory_receipt.json").is_file():
        return
    async with semaphore:
        started = unit / "launcher_started.json"
        if not started.exists():
            _write_once(
                started,
                {
                    "instance_id": instance,
                    "seed": seed,
                    "arm": arm,
                    "pid": os.getpid(),
                    "started_at_unix": time.time(),
                },
            )
        unit.mkdir(parents=True, exist_ok=True)
        stdout = (unit / "trajectory.stdout.log").open("ab")
        stderr = (unit / "trajectory.stderr.log").open("ab")
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(HERE / "harness.py"),
                "--instance",
                instance,
                "--seed",
                str(seed),
                "--arm",
                arm,
                "--output-root",
                str(output_root),
                "--remote-manifest",
                str(remote_manifest),
                stdout=stdout,
                stderr=stderr,
                creationflags=creationflags,
            )
            await process.wait()
        finally:
            stdout.close()
            stderr.close()


async def launch(args: argparse.Namespace) -> None:
    args.output_root.mkdir(parents=True, exist_ok=True)
    lock = args.output_root / "launcher.lock.json"
    _write_once(
        lock,
        {
            "experiment_id": PROTOCOL["experiment_id"],
            "pid": os.getpid(),
            "max_trajectories": args.max_trajectories,
            "started_at_unix": time.time(),
        },
    )
    try:
        semaphore = asyncio.Semaphore(args.max_trajectories)
        await asyncio.gather(
            *(
                _run_one(semaphore, args.output_root, args.remote_manifest, assignment)
                for assignment in _assignments()
            )
        )
    finally:
        lock.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--remote-manifest", required=True, type=Path)
    parser.add_argument(
        "--max-trajectories",
        type=int,
        default=PROTOCOL["parallelism"]["local_llm_call_ceiling"],
    )
    args = parser.parse_args()
    ceiling = PROTOCOL["parallelism"]["local_llm_call_ceiling"]
    if not 1 <= args.max_trajectories <= ceiling:
        parser.error(f"max-trajectories must be between 1 and {ceiling}")
    asyncio.run(launch(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
