#!/usr/bin/env python3
"""Frozen four-arm generation and consumed-validation harness for COMPONENT-1."""

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
from skydiscover.search.default_discovery_controller import DiscoveryControllerInput  # noqa: E402
from skydiscover.search.route import get_discovery_controller  # noqa: E402

HERE = Path(__file__).resolve().parent
PROTOCOL_PATH = HERE / "protocol.json"
EXECUTION_MANIFEST_PATH = HERE / "execution_manifest.json"
SOURCE_COHORT_MANIFEST = ROOT / "benchmarks/blindassist_last10m_comp_2/cohort_manifest.json"
INITIAL_PROGRAM = HERE / "initial_program.py"
CONFIG_PATH = HERE / "config.yaml"
PROMPTS_PATH = HERE / "arm_prompts.json"
DEV_EVALUATOR = HERE / "evaluator.py"
BASE_EVALUATOR = ROOT / "benchmarks/blindassist_last10m_v3/evaluator/evaluator.py"
GUARD_PATH = HERE / "candidate_guard.py"
DEV_SCENARIO_ENV = "L10M_STRUCT_COMPONENT_1_DEV_SCENARIOS"
ARM_ENV = "L10M_STRUCT_COMPONENT_1_ARM"


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
        "DESIGN_FROZEN_PENDING_MECHANICAL_PREFLIGHT",
        "MECHANICAL_PREFLIGHT_PASSED_PENDING_EXECUTION_MANIFEST",
        "EXECUTION_PROTOCOL_FROZEN",
    }
    if protocol.get("status") not in allowed:
        raise RuntimeError(f"unsupported protocol status: {protocol.get('status')}")
    if require_execution_frozen:
        if protocol["status"] != "EXECUTION_PROTOCOL_FROZEN":
            raise RuntimeError("arm execution is blocked until the execution manifest is frozen")
        _validate_execution_manifest()
    return protocol


def _validate_execution_manifest() -> None:
    if not EXECUTION_MANIFEST_PATH.is_file():
        raise RuntimeError("execution manifest is missing")
    manifest = json.loads(EXECUTION_MANIFEST_PATH.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = ROOT / item["path"]
        if not path.is_file() or _sha256(path) != item["sha256"]:
            raise RuntimeError(f"execution manifest mismatch: {item['path']}")


def _cohort() -> dict[str, Any]:
    protocol = _load_protocol(require_execution_frozen=False)
    if _sha256(SOURCE_COHORT_MANIFEST) != protocol["consumed_cohort"]["manifest_sha256"]:
        raise RuntimeError("consumed cohort manifest mismatch")
    return json.loads(SOURCE_COHORT_MANIFEST.read_text(encoding="utf-8"))


def _instance_record(instance_id: str) -> dict[str, Any]:
    records = {item["instance_id"]: item for item in _cohort()["instances"]}
    if instance_id not in records:
        raise ValueError(f"unknown consumed instance: {instance_id}")
    return records[instance_id]


def _scenario_path(record: dict[str, Any], split: str) -> Path:
    path = (ROOT / record[f"{split}_path"]).resolve()
    path.relative_to(ROOT)
    if not path.is_file() or _sha256(path) != record[f"{split}_sha256"]:
        raise RuntimeError(f"consumed {split} scenario mismatch for {record['instance_id']}")
    return path


def _arm_prompt(arm: str) -> str:
    prompts = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
    if arm not in prompts:
        raise ValueError(f"unknown arm: {arm}")
    return prompts[arm]


def synthetic_preflight() -> dict[str, Any]:
    protocol = _load_protocol(require_execution_frozen=False)
    config = load_config(CONFIG_PATH)
    ceilings = protocol["generation_ceilings_per_arm_instance_replicate"]
    receipts = {}
    for arm in protocol["arms"]:
        ledger = BudgetLedger(
            BudgetCeilings(
                generation_calls=ceilings["generation_calls"],
                evaluator_attempts=ceilings["dev_evaluator_attempts"],
                total_tokens=ceilings["total_tokens_input_plus_output"],
            )
        )
        event = ledger.start_generation(provider="synthetic", model=protocol["model"], attempt=1)
        ledger.finish_generation(
            event, metadata={"codex_usage": {"input_tokens": 20000, "output_tokens": 1000}}
        )
        ledger.start_evaluation(program_id=f"synthetic-{arm}", mode="train")
        receipts[arm] = ledger.to_receipt()
    return {
        "experiment_id": protocol["experiment_id"],
        "preflight": "PASS",
        "arms": protocol["arms"],
        "common_config_sha256": _sha256(CONFIG_PATH),
        "config_model": config.llm.models[0].name,
        "arm_budget_receipts": receipts,
    }


def _unit_state(run_dir: Path) -> str:
    if (run_dir / "search_receipt.json").is_file():
        return "terminal"
    if (run_dir / "unit_started.json").is_file():
        return "in_doubt"
    if run_dir.exists():
        return "occupied"
    return "new"


async def run_arm(arm: str, instance_id: str, seed: int, output_root: Path) -> dict[str, Any]:
    protocol = _load_protocol(require_execution_frozen=True)
    if arm not in protocol["arms"]:
        raise ValueError(f"unknown arm: {arm}")
    if seed not in protocol["direct_replicates"]["local_seeds"]:
        raise ValueError(f"unregistered replicate seed: {seed}")
    record = _instance_record(instance_id)
    dev_path = _scenario_path(record, "dev")
    run_dir = output_root.resolve() / instance_id / f"seed_{seed}" / arm
    state = _unit_state(run_dir)
    if state != "new":
        raise FileExistsError(f"refusing {state} unit reuse: {run_dir}")
    run_dir.mkdir(parents=True)
    prompt = _arm_prompt(arm)
    _write_create_once(
        run_dir / "unit_started.json",
        {
            "experiment_id": protocol["experiment_id"],
            "status": "GENERATION_CALL_ASSIGNED",
            "arm": arm,
            "instance_id": instance_id,
            "seed": seed,
            "started_at_unix": time.time(),
            "in_doubt_if_no_terminal_receipt": True,
        },
    )

    config = load_config(CONFIG_PATH)
    config.random_seed = seed
    config.context_builder.system_message = f"{config.context_builder.system_message}\n\n{prompt}"
    random.seed(seed)
    runner = None
    controller = None
    ledger = None
    started = time.time()
    old_dev = os.environ.get(DEV_SCENARIO_ENV)
    old_arm = os.environ.get(ARM_ENV)
    os.environ[DEV_SCENARIO_ENV] = str(dev_path)
    os.environ[ARM_ENV] = arm
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
        ceilings = protocol["generation_ceilings_per_arm_instance_replicate"]
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
        candidates = sorted(
            (p for p in runner.database.programs.values() if p.iteration_found > 0),
            key=lambda p: (p.iteration_found, p.timestamp, p.id),
        )
        rows = [
            {
                "id": candidate.id,
                "solution_sha256": hashlib.sha256(candidate.solution.encode("utf-8")).hexdigest(),
                "solution": candidate.solution,
            }
            for candidate in candidates
        ]
        status = "COMPLETED"
        error = None
    except Exception as exc:  # ITT preserves the assigned failed arm.
        rows = []
        status = "ARM_FAILED_ITT"
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if controller is not None:
            controller.close()
        if old_dev is None:
            os.environ.pop(DEV_SCENARIO_ENV, None)
        else:
            os.environ[DEV_SCENARIO_ENV] = old_dev
        if old_arm is None:
            os.environ.pop(ARM_ENV, None)
        else:
            os.environ[ARM_ENV] = old_arm

    _write_create_once(run_dir / "candidate_manifest.json", {"candidates": rows})
    receipt = {
        "experiment_id": protocol["experiment_id"],
        "status": status,
        "error": error,
        "arm": arm,
        "instance_id": instance_id,
        "seed": seed,
        "common_config_sha256": _sha256(CONFIG_PATH),
        "arm_prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "dev_sha256": record["dev_sha256"],
        "initial_program_sha256": _sha256(INITIAL_PROGRAM),
        "evaluator_sha256": _sha256(DEV_EVALUATOR),
        "consumed_validation_evaluations": 0,
        "candidate_count": len(rows),
        "elapsed_seconds": round(time.time() - started, 6),
        "budget": ledger.to_receipt() if ledger is not None else None,
    }
    _write_create_once(run_dir / "search_receipt.json", receipt)
    return receipt


def _load_validation_evaluator(path: Path):
    spec = importlib.util.spec_from_file_location(
        f"l10m_struct_component_1_validation_{time.time_ns()}", BASE_EVALUATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load frozen base evaluator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    from evaluator import expanded_scenarios

    scenarios = expanded_scenarios(path)
    module._load_scenarios = lambda mode: copy.deepcopy(scenarios)
    return module


def _evaluate_validation(evaluator: Any, solution: str, arm: str) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", encoding="utf-8", delete=False
    ) as handle:
        handle.write(solution)
        candidate_path = Path(handle.name)
    try:
        spec = importlib.util.spec_from_file_location(
            f"l10m_struct_component_1_guard_{time.time_ns()}", GUARD_PATH
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("could not load candidate guard")
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        guard.validate_path(candidate_path, arm)
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
    return all(
        float(metrics.get(key, 0.0)) == 1.0
        for key in ("validity", "task_success", "safe_termination")
    )


def adjudicate_block(instance_id: str, seed: int, output_root: Path) -> dict[str, Any]:
    protocol = _load_protocol(require_execution_frozen=True)
    if seed not in protocol["direct_replicates"]["local_seeds"]:
        raise ValueError(f"unregistered replicate seed: {seed}")
    record = _instance_record(instance_id)
    validation_path = _scenario_path(record, "hidden")
    block_dir = output_root.resolve() / instance_id / f"seed_{seed}"
    receipt_path = block_dir / "consumed_validation.json"
    if receipt_path.exists():
        raise FileExistsError(f"refusing repeated consumed validation: {receipt_path}")
    inputs = {}
    for arm in protocol["arms"]:
        arm_dir = block_dir / arm
        search_path = arm_dir / "search_receipt.json"
        manifest_path = arm_dir / "candidate_manifest.json"
        if not search_path.is_file() or not manifest_path.is_file():
            raise RuntimeError(f"four-arm block is incomplete: {instance_id}/{seed}/{arm}")
        inputs[arm] = (
            json.loads(search_path.read_text(encoding="utf-8")),
            json.loads(manifest_path.read_text(encoding="utf-8")),
        )
    evaluator = _load_validation_evaluator(validation_path)
    arm_results = {}
    for arm in protocol["arms"]:
        search, manifest = inputs[arm]
        candidates = manifest["candidates"][:1]
        if search["status"] == "COMPLETED" and candidates:
            candidate = candidates[0]
            result = _evaluate_validation(evaluator, candidate["solution"], arm)
            robust_safe = _robust_safe(result["metrics"])
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
            }
        else:
            row = {
                "candidate_id": None,
                "status": "itt_zero_invalid_missing_or_arm_failure",
                "combined_score": 0.0,
                "metrics": {"substantive_score_delta": 0.0},
                "score_attribution": {},
                "robust_safe": False,
                "primary_substantive_value": 0.0,
            }
        arm_results[arm] = {"search_status": search["status"], "validation": row}
    receipt = {
        "experiment_id": protocol["experiment_id"],
        "evidence_role": "CONSUMED_DEVELOPMENT_VALIDATION_NOT_BLIND",
        "instance_id": instance_id,
        "seed": seed,
        "validation_sha256": record["hidden_sha256"],
        "results_returned_to_generation": False,
        "arms": arm_results,
    }
    _write_create_once(receipt_path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight")
    arm_parser = subparsers.add_parser("run-arm")
    arm_parser.add_argument("--arm", required=True)
    arm_parser.add_argument("--instance", required=True)
    arm_parser.add_argument("--seed", type=int, required=True)
    arm_parser.add_argument("--output-root", type=Path, required=True)
    validation_parser = subparsers.add_parser("adjudicate-block")
    validation_parser.add_argument("--instance", required=True)
    validation_parser.add_argument("--seed", type=int, required=True)
    validation_parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "preflight":
        print(json.dumps(synthetic_preflight(), indent=2, sort_keys=True))
        return 0
    if args.command == "run-arm":
        result = asyncio.run(run_arm(args.arm, args.instance, args.seed, args.output_root))
    else:
        result = adjudicate_block(args.instance, args.seed, args.output_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
