#!/usr/bin/env python3
"""COMPONENT-2 wrapper over the byte-identical COMPONENT-1 mechanism harness."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE_DIR = ROOT / "benchmarks/blindassist_last10m_struct_component_1"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


base = _load("l10m_struct_component_2_base_harness", BASE_DIR / "harness.py")
integrity = _load("l10m_struct_component_2_integrity", HERE / "integrity.py")
base.PROTOCOL_PATH = HERE / "protocol.json"
base.EXECUTION_MANIFEST_PATH = HERE / "execution_manifest.json"
base.DEV_SCENARIO_ENV = "L10M_STRUCT_COMPONENT_2_DEV_SCENARIOS"
base.ARM_ENV = "L10M_STRUCT_COMPONENT_2_ARM"


def synthetic_preflight() -> dict[str, Any]:
    return base.synthetic_preflight()


async def run_arm(
    arm: str, instance_id: str, seed: int, output_root: Path, lock_path: Path
) -> dict[str, Any]:
    integrity.verify(lock_path, output_root, f"arm:{instance_id}:{seed}:{arm}")
    return await base.run_arm(arm, instance_id, seed, output_root)


def _zero_row(status: str, error: str | None) -> dict[str, Any]:
    return {
        "candidate_id": None,
        "status": status,
        "error": error,
        "combined_score": 0.0,
        "metrics": {"substantive_score_delta": 0.0},
        "score_attribution": {},
        "robust_safe": False,
        "primary_substantive_value": 0.0,
        "failure_semantics": "TERMINAL_ARM_FAILURE_ITT_ZERO_NOT_MISSING",
    }


def adjudicate_block(
    instance_id: str, seed: int, output_root: Path, lock_path: Path
) -> dict[str, Any]:
    integrity.verify(lock_path, output_root, f"adjudication:{instance_id}:{seed}")
    protocol = base._load_protocol(require_execution_frozen=True)
    if seed not in protocol["direct_replicates"]["local_seeds"]:
        raise ValueError(f"unregistered replicate seed: {seed}")
    record = base._instance_record(instance_id)
    validation_path = base._scenario_path(record, "hidden")
    block_dir = output_root.resolve() / instance_id / f"seed_{seed}"
    receipt_path = block_dir / "consumed_validation.json"
    if receipt_path.exists():
        raise FileExistsError(f"refusing repeated consumed validation: {receipt_path}")
    inputs = {}
    for arm in protocol["arms"]:
        search_path = block_dir / arm / "search_receipt.json"
        manifest_path = block_dir / arm / "candidate_manifest.json"
        if not search_path.is_file() or not manifest_path.is_file():
            raise RuntimeError(f"four-arm block is infrastructure-incomplete: {instance_id}/{seed}")
        inputs[arm] = (
            json.loads(search_path.read_text(encoding="utf-8")),
            json.loads(manifest_path.read_text(encoding="utf-8")),
        )
    base._write_create_once(
        block_dir / "validation_started.json",
        {
            "experiment_id": protocol["experiment_id"],
            "instance_id": instance_id,
            "seed": seed,
            "started_at_unix": time.time(),
            "in_doubt_if_no_terminal_receipt": True,
            "rerun_if_in_doubt": False,
        },
    )
    try:
        evaluator = base._load_validation_evaluator(validation_path)
    except Exception as exc:
        raise RuntimeError(
            f"systemic evaluator integrity failure: {type(exc).__name__}: {exc}"
        ) from exc
    arm_results = {}
    for arm in protocol["arms"]:
        search, manifest = inputs[arm]
        candidates = manifest["candidates"][:1]
        if search["status"] != "COMPLETED" or not candidates:
            row = _zero_row("itt_zero_terminal_generation_failure", search.get("error"))
        else:
            candidate = candidates[0]
            try:
                result = base._evaluate_validation(evaluator, candidate["solution"], arm)
                robust_safe = base._robust_safe(result["metrics"])
                value = (
                    max(0.0, float(result["metrics"].get("substantive_score_delta", 0.0) or 0.0))
                    if robust_safe
                    else 0.0
                )
                row = {
                    "candidate_id": candidate["id"],
                    "solution_sha256": candidate["solution_sha256"],
                    **result,
                    "robust_safe": robust_safe,
                    "primary_substantive_value": value,
                    "failure_semantics": None if robust_safe else "TERMINAL_UNSAFE_ITT_ZERO",
                }
            except Exception as exc:
                row = _zero_row(
                    "itt_zero_candidate_guard_or_arm_related_evaluator_failure",
                    f"{type(exc).__name__}: {exc}",
                )
        arm_results[arm] = {"search_status": search["status"], "validation": row}
    receipt = {
        "experiment_id": protocol["experiment_id"],
        "evidence_role": "CONSUMED_DEVELOPMENT_VALIDATION_NOT_BLIND",
        "instance_id": instance_id,
        "seed": seed,
        "validation_sha256": record["hidden_sha256"],
        "results_returned_to_generation": False,
        "complete_four_arm_block": True,
        "arms": arm_results,
    }
    base._write_create_once(receipt_path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight")
    arm_parser = subparsers.add_parser("run-arm")
    for subparser in (arm_parser,):
        subparser.add_argument("--arm", required=True)
    arm_parser.add_argument("--instance", required=True)
    arm_parser.add_argument("--seed", type=int, required=True)
    arm_parser.add_argument("--output-root", type=Path, required=True)
    arm_parser.add_argument("--execution-lock", type=Path, required=True)
    validation_parser = subparsers.add_parser("adjudicate-block")
    validation_parser.add_argument("--instance", required=True)
    validation_parser.add_argument("--seed", type=int, required=True)
    validation_parser.add_argument("--output-root", type=Path, required=True)
    validation_parser.add_argument("--execution-lock", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "preflight":
        print(json.dumps(synthetic_preflight(), indent=2, sort_keys=True))
        return 0
    if args.command == "run-arm":
        result = asyncio.run(
            run_arm(args.arm, args.instance, args.seed, args.output_root, args.execution_lock)
        )
    else:
        result = adjudicate_block(args.instance, args.seed, args.output_root, args.execution_lock)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
