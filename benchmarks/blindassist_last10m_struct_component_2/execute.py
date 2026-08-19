#!/usr/bin/env python3
"""Exclusive detached-worktree launcher and recovery path for COMPONENT-2."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROTOCOL_PATH = HERE / "protocol.json"
COHORT_PATH = ROOT / "benchmarks/blindassist_last10m_comp_2/cohort_manifest.json"
HARNESS_PATH = HERE / "harness.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


integrity = _load("l10m_struct_component_2_execute_integrity", HERE / "integrity.py")
analysis_module = _load("l10m_struct_component_2_execute_analysis", HERE / "analysis.py")
progress_module = _load("l10m_struct_component_2_execute_progress", HERE / "progress.py")


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _protocol() -> dict[str, Any]:
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def _blocks() -> list[tuple[str, int]]:
    protocol = _protocol()
    cohort = json.loads(COHORT_PATH.read_text(encoding="utf-8"))
    return [
        (record["instance_id"], seed)
        for seed in protocol["direct_replicates"]["local_seeds"]
        for record in cohort["instances"]
    ]


def init_run(run_root: Path, remote_manifest_path: Path) -> dict[str, Any]:
    protocol = _protocol()
    if protocol["status"] != "EXECUTION_PROTOCOL_FROZEN" or protocol["execution_blockers"]:
        raise RuntimeError("formal launch blocked until protocol and manifest are frozen")
    state = integrity.snapshot()
    if not state["detached"] or not state["tracked_clean"]:
        raise RuntimeError("formal worktree must be detached and tracked-clean")
    run_root = run_root.resolve()
    if run_root.exists() and any(run_root.iterdir()):
        raise FileExistsError(f"formal run root must be new and empty: {run_root}")
    remote_manifest = json.loads(remote_manifest_path.read_text(encoding="utf-8"))
    if remote_manifest.get("source_commit") != state["head"]:
        raise RuntimeError("remote bootstrap source commit does not equal frozen HEAD")
    if remote_manifest.get("status") != "ready":
        raise RuntimeError("remote bootstrap manifest is not ready")
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "units").mkdir()
    (run_root / "logs").mkdir()
    _write_once(run_root / "remote_manifest.json", remote_manifest)
    locked = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "worktree",
            "lock",
            "--reason",
            protocol["experiment_id"],
            str(ROOT),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if locked.returncode != 0 and "already locked" not in (locked.stdout + locked.stderr).lower():
        raise RuntimeError(f"could not lock formal worktree: {locked.stdout}{locked.stderr}")
    lock = {
        "experiment_id": protocol["experiment_id"],
        "created_at_unix": time.time(),
        "worktree": ROOT.resolve().as_posix(),
        "output_root": (run_root / "units").resolve().as_posix(),
        "frozen_head": state["head"],
        "frozen_tracked_tree": state["tracked_tree"],
        "exclusive_owner_token": secrets.token_hex(32),
        "execution_environment": "local_windows",
        "maximum_concurrent_blocks": 2,
        "same_instance_blocks_concurrent": False,
    }
    _write_once(run_root / "execution_lock.json", lock)
    assignments = [
        {"instance_id": instance_id, "seed": seed, "arms": protocol["arms"]}
        for instance_id, seed in _blocks()
    ]
    _write_once(
        run_root / "formal_launch_manifest.json",
        {
            "experiment_id": protocol["experiment_id"],
            "frozen_head": state["head"],
            "frozen_tracked_tree": state["tracked_tree"],
            "component_1_results_imported": False,
            "remote_manifest": str(run_root / "remote_manifest.json"),
            "assignments": assignments,
        },
    )
    integrity.verify(run_root / "execution_lock.json", run_root / "units", "launcher_init")
    return lock


def _block_state(units: Path, instance_id: str, seed: int, arms: list[str]) -> str:
    block = units / instance_id / f"seed_{seed}"
    terminal = sum((block / arm / "search_receipt.json").is_file() for arm in arms)
    started = sum((block / arm / "unit_started.json").is_file() for arm in arms)
    if terminal == len(arms):
        if (block / "consumed_validation.json").is_file():
            return "complete"
        if (block / "validation_started.json").is_file():
            return "validation_in_doubt"
        return "adjudicate"
    if terminal or started:
        return "incomplete_touched"
    return "new"


async def _command(args: list[str], log_path: Path) -> int:
    creationflags = 0x08000000 if os.name == "nt" else 0
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("x", encoding="utf-8", newline="\n") as log:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=log,
            stderr=asyncio.subprocess.STDOUT,
            creationflags=creationflags,
        )
        return await process.wait()


async def _adjudicate(run_root: Path, instance_id: str, seed: int) -> None:
    args = [
        sys.executable,
        str(HARNESS_PATH),
        "adjudicate-block",
        "--instance",
        instance_id,
        "--seed",
        str(seed),
        "--output-root",
        str(run_root / "units"),
        "--execution-lock",
        str(run_root / "execution_lock.json"),
    ]
    code = await _command(args, run_root / "logs" / f"{instance_id}_seed_{seed}_adjudicate.log")
    if code != 0:
        raise RuntimeError(f"adjudication failed for {instance_id}/{seed}; fail closed")


async def _run_block(run_root: Path, instance_id: str, seed: int) -> None:
    protocol = _protocol()
    units = run_root / "units"
    lock = run_root / "execution_lock.json"
    integrity.verify(lock, units, f"block:{instance_id}:{seed}")
    state = _block_state(units, instance_id, seed, protocol["arms"])
    if state == "complete":
        return
    if state == "adjudicate":
        await _adjudicate(run_root, instance_id, seed)
        return
    if state in {"incomplete_touched", "validation_in_doubt"}:
        return
    commands = []
    for arm in protocol["arms"]:
        args = [
            sys.executable,
            str(HARNESS_PATH),
            "run-arm",
            "--arm",
            arm,
            "--instance",
            instance_id,
            "--seed",
            str(seed),
            "--output-root",
            str(units),
            "--execution-lock",
            str(lock),
        ]
        log = run_root / "logs" / f"{instance_id}_seed_{seed}_{arm}.log"
        commands.append(_command(args, log))
    codes = await asyncio.gather(*commands)
    if any(code != 0 for code in codes):
        raise RuntimeError(f"arm process failed for {instance_id}/{seed}; fail closed")
    if _block_state(units, instance_id, seed, protocol["arms"]) != "adjudicate":
        raise RuntimeError(f"four-arm terminal invariant failed for {instance_id}/{seed}")
    await _adjudicate(run_root, instance_id, seed)


async def run_pending(run_root: Path) -> dict[str, Any]:
    run_root = run_root.resolve()
    integrity.verify(run_root / "execution_lock.json", run_root / "units", "harness_start")
    blocks = _blocks()
    for index in range(0, len(blocks), 2):
        batch = blocks[index : index + 2]
        if len({instance_id for instance_id, _ in batch}) != len(batch):
            raise RuntimeError("scheduler attempted same-instance concurrent blocks")
        await asyncio.gather(
            *(_run_block(run_root, instance_id, seed) for instance_id, seed in batch)
        )
    return closeout(run_root)


def closeout(run_root: Path) -> dict[str, Any]:
    run_root = run_root.resolve()
    integrity.verify(run_root / "execution_lock.json", run_root / "units", "closeout_start")
    progress = progress_module.summarize(run_root)
    closeout_path = run_root / "execution_closeout.json"
    if not closeout_path.exists():
        _write_once(
            closeout_path,
            {
                "experiment_id": _protocol()["experiment_id"],
                "status": "GENERATION_AND_ADJUDICATION_TERMINAL",
                "component_1_results_imported": False,
                "progress": progress,
            },
        )
    integrity.verify(run_root / "execution_lock.json", run_root / "units", "analysis_start")
    result = analysis_module.analyze(run_root)
    analysis_path = run_root / "formal_analysis.json"
    if not analysis_path.exists():
        _write_once(analysis_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "run", "closeout"):
        command = sub.add_parser(name)
        command.add_argument("--run-root", type=Path, required=True)
        if name == "init":
            command.add_argument("--remote-manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "init":
        result = init_run(args.run_root, args.remote_manifest)
    elif args.command == "run":
        result = asyncio.run(run_pending(args.run_root))
    else:
        result = closeout(args.run_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
