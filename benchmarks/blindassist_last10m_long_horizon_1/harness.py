#!/usr/bin/env python3
"""One recoverable consumed-only trajectory for L10M-LONG-HORIZON-1."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skydiscover.config import load_config  # noqa: E402
from skydiscover.execution_budget import BudgetCeilings, BudgetLedger  # noqa: E402
from skydiscover.runner import Runner  # noqa: E402

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "protocol.json"
EXECUTION_MANIFEST = HERE / "execution_manifest.json"
COHORT = ROOT / "benchmarks/blindassist_last10m_comp_2/cohort_manifest.json"
INITIAL = ROOT / "benchmarks/blindassist_last10m_v3/initial_program.py"
EVALUATOR = HERE / "evaluator.py"
CONFIGS = {arm: HERE / "configs" / f"{arm}.yaml" for arm in ("naked", "adaevolve", "evox")}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _load_frozen() -> tuple[dict[str, Any], dict[str, Any]]:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    if protocol["status"] != "EXECUTION_PROTOCOL_FROZEN":
        raise RuntimeError("formal execution is blocked until the execution protocol is frozen")
    manifest = json.loads(EXECUTION_MANIFEST.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = ROOT / item["path"]
        if not path.is_file() or _sha256(path) != item["sha256"]:
            raise RuntimeError(f"execution manifest mismatch: {item['path']}")
    return protocol, json.loads(COHORT.read_text(encoding="utf-8"))


def _record(cohort: dict[str, Any], instance_id: str) -> dict[str, Any]:
    records = {row["instance_id"]: row for row in cohort["instances"]}
    if instance_id not in records:
        raise ValueError(f"unknown consumed instance: {instance_id}")
    return records[instance_id]


def _latest_checkpoint(run_dir: Path) -> tuple[Path | None, int]:
    found: list[tuple[int, Path]] = []
    for path in (run_dir / "checkpoints").glob("checkpoint_*"):
        try:
            iteration = int(path.name.split("_", 1)[1])
        except ValueError:
            continue
        info = path / "best_program_info.json"
        if (
            info.is_file()
            and json.loads(info.read_text(encoding="utf-8"))["current_iteration"] == iteration
        ):
            found.append((iteration, path))
    return (
        max(found, default=(0, None), key=lambda item: item[0])[1],
        max([x[0] for x in found], default=0),
    )


def _prefixes(run_dir: Path, observations: list[int]) -> list[dict[str, Any]]:
    rows = []
    for iteration in observations:
        info = run_dir / "checkpoints" / f"checkpoint_{iteration}" / "best_program_info.json"
        if not info.is_file():
            continue
        data = json.loads(info.read_text(encoding="utf-8"))
        metrics = data.get("metrics", {})
        safe = all(
            float(metrics.get(key, 0.0)) == 1.0
            for key in ("validity", "task_success", "safe_termination")
        )
        rows.append(
            {
                "iteration": iteration,
                "robust_safe": safe,
                "robust_safe_best_so_far": (
                    float(metrics.get("combined_score", 0.0)) if safe else 0.0
                ),
                "program_id": data.get("id"),
            }
        )
    return rows


async def run_trajectory(args: argparse.Namespace) -> dict[str, Any]:
    protocol, cohort = _load_frozen()
    if args.arm not in protocol["arms"] or args.seed not in protocol["replicates"]["seeds"]:
        raise ValueError("arm or seed is outside the frozen assignment")
    record = _record(cohort, args.instance)
    scenario = ROOT / record["dev_path"]
    if _sha256(scenario) != record["dev_sha256"]:
        raise RuntimeError("consumed DEV scenario hash mismatch")

    run_dir = args.output_root.resolve() / args.instance / f"seed_{args.seed}" / args.arm
    terminal = run_dir / "trajectory_receipt.json"
    if terminal.exists():
        return json.loads(terminal.read_text(encoding="utf-8"))
    run_dir.mkdir(parents=True, exist_ok=True)
    budget_path = run_dir / "budget_journal.json"
    checkpoint, completed = _latest_checkpoint(run_dir)
    ceilings = protocol["budget_per_trajectory"]
    if budget_path.exists():
        ledger = BudgetLedger.from_journal(budget_path)
        if any(event.get("status") == "in_doubt" for event in ledger.events):
            receipt = {
                "experiment_id": protocol["experiment_id"],
                "status": "TRAJECTORY_IN_DOUBT",
                "instance_id": args.instance,
                "seed": args.seed,
                "arm": args.arm,
                "completed_iteration": completed,
                "budget": ledger.to_receipt(),
            }
            _write_once(terminal, receipt)
            return receipt
    else:
        ledger = BudgetLedger(
            BudgetCeilings(
                generation_calls=ceilings["generation_call_ceiling"][args.arm],
                evaluator_attempts=ceilings["evaluator_attempt_ceiling"],
                total_tokens=ceilings["total_token_ceiling"],
            ),
            journal_path=budget_path,
        )

    config = load_config(CONFIGS[args.arm])
    config.random_seed = args.seed
    random.seed(args.seed)
    worker_id = f"{args.instance}-seed-{args.seed}-{args.arm}"
    env_vars = {
        "L10M_LONG_REMOTE_MANIFEST": str(args.remote_manifest.resolve()),
        "L10M_LONG_DISPATCH_JOURNAL": str((run_dir / "dispatch_journal").resolve()),
        "L10M_LONG_WORKER_ID": worker_id,
        "L10M_LONG_DEV_SCENARIOS": str(scenario.resolve()),
        "L10M_LONG_ARM": args.arm,
        **protocol["parallelism"]["thread_env"],
    }
    started = time.time()
    status = "COMPLETED"
    error = None
    try:
        runner = Runner(
            evaluation_file=str(EVALUATOR),
            initial_program_path=str(INITIAL),
            config=config,
            output_dir=str(run_dir),
            evaluator_env_vars=env_vars,
        )
        remaining = protocol["horizon"]["solution_candidate_generations"] - completed
        if remaining > 0:
            with ledger.activate():
                await runner.run(
                    iterations=remaining, checkpoint_path=str(checkpoint) if checkpoint else None
                )
    except BaseException as exc:
        status = "TRAJECTORY_FAILED"
        error = f"{type(exc).__name__}: {exc}"
    receipt = {
        "experiment_id": protocol["experiment_id"],
        "status": status,
        "error": error,
        "instance_id": args.instance,
        "seed": args.seed,
        "arm": args.arm,
        "elapsed_seconds": round(time.time() - started, 6),
        "prefix_observations": _prefixes(run_dir, protocol["horizon"]["prefix_observations"]),
        "budget": ledger.to_receipt(),
        "remote_manifest_sha256": _sha256(args.remote_manifest),
    }
    _write_once(terminal, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", required=True, choices=sorted(CONFIGS))
    parser.add_argument("--instance", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--remote-manifest", required=True, type=Path)
    args = parser.parse_args()
    result = asyncio.run(run_trajectory(args))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
