#!/usr/bin/env python3
"""Budgeted structured search and sealed adjudication harness."""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import importlib.util
import json
import os
import random
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skydiscover.config import load_config  # noqa: E402
from skydiscover.execution_budget import BudgetCeilings, BudgetLedger  # noqa: E402
from skydiscover.runner import Runner  # noqa: E402
from skydiscover.search.default_discovery_controller import (  # noqa: E402
    DiscoveryControllerInput,
)
from skydiscover.search.route import get_discovery_controller  # noqa: E402

HERE = Path(__file__).resolve().parent
PROTOCOL_PATH = HERE / "protocol.json"
COHORT_MANIFEST_PATH = HERE / "cohort_manifest.json"
EXECUTION_MANIFEST_PATH = HERE / "execution_manifest.json"
INITIAL_PROGRAM = HERE / "initial_program.py"
BASE_EVALUATOR = ROOT / "benchmarks" / "blindassist_last10m_v3" / "evaluator" / "evaluator.py"
GUARD_PATH = HERE / "candidate_guard.py"
DEV_EVALUATOR = HERE / "evaluator.py"
DEV_SCENARIO_ENV = "L10M_STRUCT_SEARCH_1_DEV_SCENARIOS"
COHORT_ROOT_ENV = "L10M_STRUCT_SEARCH_1_COHORT_ROOT"
ARM_CONFIGS = {
    "naked_structured": HERE / "configs" / "naked_codex.yaml",
    "evox_structured": HERE / "configs" / "evox.yaml",
    "sky_evox_structured": HERE / "configs" / "sky_evox.yaml",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _write_create_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _load_protocol(*, require_execution_frozen: bool) -> dict[str, Any]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    allowed = {
        "DESIGN_FROZEN_PENDING_FRESH_COHORT",
        "FRESH_COHORT_FROZEN_PENDING_EXECUTION_MANIFEST",
        "EXECUTION_PROTOCOL_FROZEN",
    }
    if protocol.get("status") not in allowed:
        raise RuntimeError(f"unsupported protocol status: {protocol.get('status')}")
    if require_execution_frozen:
        if protocol["status"] != "EXECUTION_PROTOCOL_FROZEN":
            raise RuntimeError("treatment execution is blocked until every manifest is frozen")
        _validate_execution_manifest()
    return protocol


def _load_cohort() -> dict[str, Any]:
    if not COHORT_MANIFEST_PATH.is_file():
        raise RuntimeError("fresh cohort manifest is missing")
    cohort = json.loads(COHORT_MANIFEST_PATH.read_text(encoding="utf-8"))
    if cohort.get("treatment_runs_observed") != 0:
        raise RuntimeError("cohort was not materialized pre-treatment")
    return cohort


def _validate_execution_manifest() -> None:
    if not EXECUTION_MANIFEST_PATH.is_file():
        raise RuntimeError("execution manifest is missing")
    manifest = json.loads(EXECUTION_MANIFEST_PATH.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = ROOT / item["path"]
        if not path.is_file() or _sha256(path) != item["sha256"]:
            raise RuntimeError(f"execution manifest mismatch: {item['path']}")


def _instance_record(instance_id: str) -> dict[str, Any]:
    cohort = _load_cohort()
    records = {item["instance_id"]: item for item in cohort["instances"]}
    if instance_id not in records:
        raise ValueError(f"unknown fresh instance: {instance_id}")
    return records[instance_id]


def _scenario_path(record: dict[str, Any], split: str) -> Path:
    selected_root = os.environ.get(COHORT_ROOT_ENV)
    if not selected_root:
        raise RuntimeError(f"{COHORT_ROOT_ENV} must name the external sealed cohort root")
    cohort_root = Path(selected_root).resolve()
    path = (cohort_root / record[f"{split}_path"]).resolve()
    try:
        path.relative_to(cohort_root)
    except ValueError as exc:
        raise RuntimeError("cohort manifest path escapes the sealed root") from exc
    if not path.is_file() or _sha256(path) != record[f"{split}_sha256"]:
        raise RuntimeError(f"frozen {split} scenario mismatch for {record['instance_id']}")
    return path


def synthetic_preflight() -> dict[str, Any]:
    protocol = _load_protocol(require_execution_frozen=False)
    ceilings = protocol["search_ceilings_per_arm_instance_replicate"]
    configs = {arm: load_config(path) for arm, path in ARM_CONFIGS.items()}
    receipts = {}
    for arm in protocol["arms"]:
        ledger = BudgetLedger(
            BudgetCeilings(
                generation_calls=ceilings["generation_calls"],
                evaluator_attempts=ceilings["dev_evaluator_attempts"],
                total_tokens=ceilings["total_tokens_input_plus_output"],
            )
        )
        for call in range(ceilings["generation_calls"]):
            event = ledger.start_generation(
                provider="synthetic", model=protocol["model"], attempt=1
            )
            ledger.finish_generation(
                event,
                metadata={"codex_usage": {"input_tokens": 20000 + call, "output_tokens": 1000}},
            )
        for attempt in range(ceilings["dev_evaluator_attempts"]):
            ledger.start_evaluation(program_id=f"synthetic-{attempt}", mode="train")
        receipts[arm] = ledger.to_receipt()
    return {
        "experiment_id": protocol["experiment_id"],
        "preflight": "PASS",
        "arms": sorted(configs),
        "arm_budget_receipts": receipts,
    }


async def run_arm(arm: str, instance_id: str, seed: int, output_root: Path) -> dict[str, Any]:
    protocol = _load_protocol(require_execution_frozen=True)
    if arm not in protocol["arms"] or arm not in ARM_CONFIGS:
        raise ValueError(f"unknown arm: {arm}")
    if seed not in protocol["nested_replicates"]["local_seeds"]:
        raise ValueError(f"unregistered nested replicate seed: {seed}")
    record = _instance_record(instance_id)
    dev_path = _scenario_path(record, "dev")
    run_dir = output_root.resolve() / instance_id / f"seed_{seed}" / arm
    if run_dir.exists():
        raise FileExistsError(f"refusing to reuse arm output: {run_dir}")
    run_dir.mkdir(parents=True)

    config_path = ARM_CONFIGS[arm]
    config = load_config(config_path)
    config.random_seed = seed
    random.seed(seed)
    runner = None
    controller = None
    ledger = None
    started = time.time()
    old_dev_path = os.environ.get(DEV_SCENARIO_ENV)
    os.environ[DEV_SCENARIO_ENV] = str(dev_path)
    try:
        runner = Runner(
            evaluation_file=str(DEV_EVALUATOR),
            initial_program_path=str(INITIAL_PROGRAM),
            config=config,
            output_dir=str(run_dir),
        )
        controller_input = DiscoveryControllerInput(
            config=config,
            evaluation_file=str(DEV_EVALUATOR),
            database=runner.database,
            file_suffix=runner.file_extension,
            output_dir=str(run_dir),
        )
        controller = get_discovery_controller(controller_input)
        runner.discovery_controller = controller
        await runner._add_initial_program(0)
        ceilings = protocol["search_ceilings_per_arm_instance_replicate"]
        ledger = BudgetLedger(
            BudgetCeilings(
                generation_calls=ceilings["generation_calls"],
                evaluator_attempts=ceilings["dev_evaluator_attempts"],
                total_tokens=ceilings["total_tokens_input_plus_output"],
            )
        )

        def checkpoint(iteration: int) -> None:
            runner._sync_database()
            runner._save_checkpoint(iteration)

        with ledger.activate():
            await controller.run_discovery(
                start_iteration=1,
                max_iterations=config.max_iterations,
                checkpoint_callback=checkpoint,
            )
        runner._sync_database()
        runner._save_checkpoint(config.max_iterations)
        best = runner._get_best_program()
        if best is not None:
            runner._save_best_program(best)
        candidates = sorted(
            (
                program
                for program in runner.database.programs.values()
                if program.iteration_found > 0
            ),
            key=lambda program: (program.iteration_found, program.timestamp, program.id),
        )
        candidate_rows = [
            {
                "id": candidate.id,
                "iteration_found": candidate.iteration_found,
                "solution_sha256": hashlib.sha256(candidate.solution.encode("utf-8")).hexdigest(),
                "solution": candidate.solution,
            }
            for candidate in candidates
        ]
        status = "COMPLETED"
        error = None
        best_id = best.id if best else None
    except Exception as exc:  # ITT keeps the failed assigned arm in the analysis.
        candidate_rows = []
        status = "ARM_FAILED_ITT"
        error = f"{type(exc).__name__}: {exc}"
        best_id = None
    finally:
        if controller is not None:
            controller.close()
        if old_dev_path is None:
            os.environ.pop(DEV_SCENARIO_ENV, None)
        else:
            os.environ[DEV_SCENARIO_ENV] = old_dev_path

    _write_create_once(run_dir / "candidate_manifest.json", {"candidates": candidate_rows})
    receipt = {
        "experiment_id": protocol["experiment_id"],
        "status": status,
        "error": error,
        "arm": arm,
        "instance_id": instance_id,
        "seed": seed,
        "config_sha256": _sha256(config_path),
        "dev_sha256": record["dev_sha256"],
        "initial_program_sha256": _sha256(INITIAL_PROGRAM),
        "evaluator_sha256": _sha256(DEV_EVALUATOR),
        "hidden_evaluations": 0,
        "candidate_count": len(candidate_rows),
        "best_program_id": best_id,
        "elapsed_seconds": round(time.time() - started, 6),
        "budget": ledger.to_receipt() if ledger is not None else None,
    }
    _write_create_once(run_dir / "search_receipt.json", receipt)
    return receipt


def _load_hidden_evaluator(hidden_path: Path):
    spec = importlib.util.spec_from_file_location(
        f"l10m_struct_search_1_hidden_{time.time_ns()}", BASE_EVALUATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load frozen base evaluator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    raw = json.loads(hidden_path.read_text(encoding="utf-8"))
    scenarios = copy.deepcopy(raw)
    for scenario in scenarios:
        defaults = scenario.pop("node_defaults", {})
        defaults.setdefault("rgb_ref", None)
        scenario["nodes"] = [{**defaults, **node} for node in scenario["nodes"]]
    module._load_scenarios = lambda mode: copy.deepcopy(scenarios)
    return module


def _evaluate_hidden(evaluator: Any, solution: str) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", encoding="utf-8", delete=False
    ) as handle:
        handle.write(solution)
        candidate_path = Path(handle.name)
    try:
        guard_spec = importlib.util.spec_from_file_location(
            f"l10m_struct_search_1_guard_{time.time_ns()}", GUARD_PATH
        )
        if guard_spec is None or guard_spec.loader is None:
            raise RuntimeError("could not load frozen candidate guard")
        guard = importlib.util.module_from_spec(guard_spec)
        guard_spec.loader.exec_module(guard)
        guard.validate_path(candidate_path)
        result = evaluator.evaluate(str(candidate_path), "test")
    finally:
        candidate_path.unlink(missing_ok=True)
    return {
        "status": result["status"],
        "combined_score": result["combined_score"],
        "metrics": result["metrics"],
        "score_attribution": json.loads(result["artifacts"]["score_attribution"]),
    }


def _robust_safe(metrics: dict[str, Any]) -> bool:
    return (
        float(metrics.get("validity", 0.0)) == 1.0
        and float(metrics.get("task_success", 0.0)) == 1.0
        and float(metrics.get("safe_termination", 0.0)) == 1.0
    )


def adjudicate_block(instance_id: str, seed: int, output_root: Path) -> dict[str, Any]:
    protocol = _load_protocol(require_execution_frozen=True)
    if seed not in protocol["nested_replicates"]["local_seeds"]:
        raise ValueError(f"unregistered nested replicate seed: {seed}")
    record = _instance_record(instance_id)
    hidden_path = _scenario_path(record, "hidden")
    block_dir = output_root.resolve() / instance_id / f"seed_{seed}"
    receipt_path = block_dir / "hidden_adjudication.json"
    if receipt_path.exists():
        raise FileExistsError(f"refusing repeated hidden adjudication: {receipt_path}")

    inputs = {}
    for arm in protocol["arms"]:
        arm_dir = block_dir / arm
        search_path = arm_dir / "search_receipt.json"
        candidates_path = arm_dir / "candidate_manifest.json"
        if not search_path.is_file() or not candidates_path.is_file():
            raise RuntimeError(f"paired ITT block is incomplete: {instance_id}/{seed}/{arm}")
        inputs[arm] = (
            json.loads(search_path.read_text(encoding="utf-8")),
            json.loads(candidates_path.read_text(encoding="utf-8")),
        )

    evaluator = _load_hidden_evaluator(hidden_path)
    attempts = protocol["hidden_adjudication"]["attempts_per_arm_instance_replicate"]
    arm_results = {}
    for arm in protocol["arms"]:
        search_receipt, manifest = inputs[arm]
        candidates = manifest["candidates"][:attempts]
        hidden_rows = []
        curve = []
        best_so_far = 0.0
        for index in range(attempts):
            if index < len(candidates) and search_receipt["status"] == "COMPLETED":
                candidate = candidates[index]
                hidden = _evaluate_hidden(evaluator, candidate["solution"])
                row = {
                    "attempt": index + 1,
                    "candidate_id": candidate["id"],
                    "solution_sha256": candidate["solution_sha256"],
                    **hidden,
                }
                row["robust_safe"] = _robust_safe(hidden["metrics"])
                substantive = (
                    max(
                        0.0,
                        float(hidden["metrics"].get("substantive_score_delta", 0.0) or 0.0),
                    )
                    if row["robust_safe"]
                    else 0.0
                )
                row["primary_substantive_value"] = substantive
            else:
                row = {
                    "attempt": index + 1,
                    "candidate_id": None,
                    "status": "itt_zero_invalid_missing_or_arm_failure",
                    "combined_score": 0.0,
                    "metrics": {
                        "behavioral_improvement_detected": 0.0,
                        "substantive_score_delta": 0.0,
                    },
                    "score_attribution": {},
                    "robust_safe": False,
                    "primary_substantive_value": 0.0,
                }
                substantive = 0.0
            best_so_far = max(best_so_far, substantive)
            curve.append(round(best_so_far, 12))
            hidden_rows.append(row)
        best_row = max(hidden_rows, key=lambda row: float(row["primary_substantive_value"]))
        passes = [
            row
            for row in hidden_rows
            if row["metrics"].get("behavioral_improvement_detected") == 1.0
        ]
        arm_results[arm] = {
            "search_status": search_receipt["status"],
            "primary_behavioral_discovery": bool(passes),
            "first_behavioral_pass_attempt": passes[0]["attempt"] if passes else None,
            "behavioral_anytime_curve": curve,
            "behavioral_anytime_auc": round(sum(curve) / attempts, 12),
            "best_discovered_substantive_score_delta": best_row["primary_substantive_value"],
            "best_discovered_robust_safe": bool(best_row["robust_safe"]),
            "search_budget": search_receipt["budget"],
            "hidden_attempts": hidden_rows,
        }
    receipt = {
        "experiment_id": protocol["experiment_id"],
        "instance_id": instance_id,
        "seed": seed,
        "hidden_sha256": record["hidden_sha256"],
        "results_returned_to_search": False,
        "arms": arm_results,
    }
    _write_create_once(receipt_path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--receipt", type=Path)
    arm_parser = subparsers.add_parser("run-arm")
    arm_parser.add_argument("--arm", choices=sorted(ARM_CONFIGS), required=True)
    arm_parser.add_argument("--instance", required=True)
    arm_parser.add_argument("--seed", type=int, required=True)
    arm_parser.add_argument("--output-root", type=Path, required=True)
    adjudicate_parser = subparsers.add_parser("adjudicate-block")
    adjudicate_parser.add_argument("--instance", required=True)
    adjudicate_parser.add_argument("--seed", type=int, required=True)
    adjudicate_parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "preflight":
        receipt = synthetic_preflight()
        if args.receipt:
            _write_create_once(args.receipt, receipt)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    if args.command == "run-arm":
        receipt = asyncio.run(run_arm(args.arm, args.instance, args.seed, args.output_root))
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    if args.command == "adjudicate-block":
        receipt = adjudicate_block(args.instance, args.seed, args.output_root)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
