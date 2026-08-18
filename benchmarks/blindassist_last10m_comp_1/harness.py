#!/usr/bin/env python3
"""Budgeted search and sealed adjudication harness for L10M-COMP-1."""

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
import time
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skydiscover.config import load_config  # noqa: E402
from skydiscover.execution_budget import (  # noqa: E402
    BudgetCeilings,
    BudgetLedger,
)
from skydiscover.runner import Runner  # noqa: E402
from skydiscover.search.default_discovery_controller import (  # noqa: E402
    DiscoveryControllerInput,
)
from skydiscover.search.route import get_discovery_controller  # noqa: E402

HERE = Path(__file__).resolve().parent
PROTOCOL_PATH = HERE / "protocol.json"
EXECUTION_MANIFEST_PATH = HERE / "execution_manifest.json"
ORACLE3 = ROOT / "benchmarks" / "blindassist_last10m_v3"
INITIAL_PROGRAM = ORACLE3 / "initial_program.py"
EVALUATOR = ORACLE3 / "evaluator" / "evaluator.py"
ARM_CONFIGS = {
    "skydiscover_best_of_n_3": HERE / "configs" / "skydiscover.yaml",
    "naked_codex_incumbent_only": HERE / "configs" / "naked_codex.yaml",
    "evox": HERE / "configs" / "evox.yaml",
}


def _sha256(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def _write_create_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _load_protocol(*, require_execution_frozen: bool) -> dict[str, Any]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    allowed = {
        "MECHANICAL_PROTOCOL_FROZEN_PENDING_HIDDEN_V4",
        "EXECUTION_PROTOCOL_FROZEN",
    }
    if protocol.get("status") not in allowed:
        raise RuntimeError(f"unsupported protocol status: {protocol.get('status')}")
    if require_execution_frozen and protocol.get("status") != "EXECUTION_PROTOCOL_FROZEN":
        raise RuntimeError("arm execution is blocked until hidden-v4 and all hashes are frozen")
    if require_execution_frozen:
        _validate_execution_manifest()
    return protocol


def _validate_execution_manifest() -> None:
    if not EXECUTION_MANIFEST_PATH.exists():
        raise RuntimeError("execution manifest is missing")
    manifest = json.loads(EXECUTION_MANIFEST_PATH.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = ROOT / item["path"]
        if not path.is_file() or _sha256(path) != item["sha256"]:
            raise RuntimeError(f"execution manifest mismatch: {item['path']}")


def _validate_arm(protocol: dict[str, Any], arm: str, seed: int) -> Path:
    if arm not in protocol["arms"] or arm not in ARM_CONFIGS:
        raise ValueError(f"unknown arm: {arm}")
    if seed not in protocol["replicates"]["local_seeds"]:
        raise ValueError(f"seed {seed} is not preregistered")
    return ARM_CONFIGS[arm]


def synthetic_preflight() -> dict[str, Any]:
    """Exercise the frozen accounting rules without model or hidden data."""
    protocol = _load_protocol(require_execution_frozen=False)
    ceiling_data = protocol["search_ceilings_per_arm_replicate"]
    receipts: dict[str, Any] = {}
    schedules = {
        "skydiscover_best_of_n_3": (10, 10),
        "naked_codex_incumbent_only": (10, 10),
        "evox": (10, 7),
    }
    for arm, (generation_calls, evaluator_attempts) in schedules.items():
        ledger = BudgetLedger(
            BudgetCeilings(
                generation_calls=ceiling_data["generation_calls"],
                evaluator_attempts=ceiling_data["dev_evaluator_attempts"],
                total_tokens=ceiling_data["total_tokens_input_plus_output"],
            )
        )
        for call in range(generation_calls):
            event = ledger.start_generation(
                provider="synthetic", model=protocol["model"], attempt=1
            )
            ledger.finish_generation(
                event,
                metadata={
                    "codex_usage": {
                        "input_tokens": 20000 + call,
                        "output_tokens": 1000,
                    }
                },
            )
        for attempt in range(evaluator_attempts):
            ledger.start_evaluation(program_id=f"synthetic-{attempt}", mode="train")
        receipts[arm] = ledger.to_receipt()

    return {
        "experiment_id": protocol["experiment_id"],
        "preflight": "PASS",
        "hidden_materialized": protocol["hidden_adjudication"]["materialized"],
        "arm_receipts": receipts,
    }


async def run_arm(arm: str, seed: int, output_root: Path) -> dict[str, Any]:
    """Run one isolated arm without any automatic hidden evaluation."""
    protocol = _load_protocol(require_execution_frozen=True)
    config_path = _validate_arm(protocol, arm, seed)
    config = load_config(config_path)
    config.random_seed = seed
    random.seed(seed)

    run_dir = output_root.resolve() / f"seed_{seed}" / arm
    if run_dir.exists():
        raise FileExistsError(f"refusing to reuse arm output: {run_dir}")
    run_dir.mkdir(parents=True)

    runner = Runner(
        evaluation_file=str(EVALUATOR),
        initial_program_path=str(INITIAL_PROGRAM),
        config=config,
        output_dir=str(run_dir),
    )
    controller_input = DiscoveryControllerInput(
        config=config,
        evaluation_file=str(EVALUATOR),
        database=runner.database,
        file_suffix=runner.file_extension,
        output_dir=str(run_dir),
    )
    controller = get_discovery_controller(controller_input)
    runner.discovery_controller = controller

    started = time.time()
    try:
        # Common frozen baseline evaluation is outside the candidate opportunity budget.
        await runner._add_initial_program(0)
        ceilings = protocol["search_ceilings_per_arm_replicate"]
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
        candidate_manifest = [
            {
                "id": candidate.id,
                "iteration_found": candidate.iteration_found,
                "solution_sha256": hashlib.sha256(candidate.solution.encode("utf-8")).hexdigest(),
                "solution": candidate.solution,
            }
            for candidate in candidates
        ]
        _write_create_once(run_dir / "candidate_manifest.json", {"candidates": candidate_manifest})
        receipt = {
            "experiment_id": protocol["experiment_id"],
            "arm": arm,
            "seed": seed,
            "config_sha256": _sha256(config_path),
            "initial_program_sha256": _sha256(INITIAL_PROGRAM),
            "evaluator_sha256": _sha256(EVALUATOR),
            "hidden_evaluations": 0,
            "candidate_count": len(candidate_manifest),
            "best_program_id": best.id if best else None,
            "elapsed_seconds": round(time.time() - started, 6),
            "budget": ledger.to_receipt(),
        }
        _write_create_once(run_dir / "search_receipt.json", receipt)
        return receipt
    finally:
        controller.close()
        runner.discovery_controller = None


def _load_oracle3_with_hidden_v4():
    evaluator_path = ORACLE3 / "evaluator" / "evaluator.py"
    spec = importlib.util.spec_from_file_location("l10m_comp_1_oracle3", evaluator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load frozen ORACLE-3 evaluator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    raw_hidden = json.loads(
        (HERE / "evaluator" / "scenarios" / "hidden_v4.json").read_text(encoding="utf-8")
    )

    def load_scenarios(mode: str) -> list[dict[str, Any]]:
        if mode != "test":
            raise ValueError("sealed adjudicator accepts test mode only")
        data = copy.deepcopy(raw_hidden)
        required = {
            "target_visible",
            "target_bearing",
            "target_distance_class",
            "target_confidence",
            "target_identity_confidence",
            "corridor_left",
            "corridor_center",
            "corridor_right",
            "closing_risk",
            "safety_confidence",
            "heading_error",
            "progress",
        }
        for scenario in data:
            defaults = scenario.pop("node_defaults", {})
            defaults.setdefault("rgb_ref", None)
            scenario["nodes"] = [{**defaults, **node} for node in scenario["nodes"]]
            for node in scenario["nodes"]:
                missing = required - node.keys()
                if missing:
                    raise ValueError(
                        f"scenario {scenario.get('id')} node {node.get('id')} "
                        f"missing {sorted(missing)}"
                    )
        return data

    module._load_scenarios = load_scenarios
    return module


def _evaluate_hidden_candidate(evaluator: Any, solution: str) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", encoding="utf-8", delete=False
    ) as handle:
        handle.write(solution)
        candidate_path = Path(handle.name)
    try:
        result = evaluator.evaluate(str(candidate_path), "test")
    finally:
        candidate_path.unlink(missing_ok=True)
    metrics = result["metrics"]
    return {
        "status": result["status"],
        "combined_score": result["combined_score"],
        "metrics": metrics,
        "score_attribution": json.loads(result["artifacts"]["score_attribution"]),
    }


def adjudicate_block(seed: int, output_root: Path) -> dict[str, Any]:
    """Evaluate a completed paired block once, without returning hidden feedback."""
    protocol = _load_protocol(require_execution_frozen=True)
    if seed not in protocol["replicates"]["local_seeds"]:
        raise ValueError(f"seed {seed} is not preregistered")
    block_dir = output_root.resolve() / f"seed_{seed}"
    receipt_path = block_dir / "hidden_adjudication_receipt.json"
    if receipt_path.exists():
        raise FileExistsError(f"refusing to repeat hidden adjudication: {receipt_path}")

    inputs: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for arm in protocol["arms"]:
        arm_dir = block_dir / arm
        search_receipt_path = arm_dir / "search_receipt.json"
        candidate_manifest_path = arm_dir / "candidate_manifest.json"
        if not search_receipt_path.is_file() or not candidate_manifest_path.is_file():
            raise RuntimeError(f"paired block is incomplete: {arm}")
        inputs[arm] = (
            json.loads(search_receipt_path.read_text(encoding="utf-8")),
            json.loads(candidate_manifest_path.read_text(encoding="utf-8")),
        )

    evaluator = _load_oracle3_with_hidden_v4()
    attempts = protocol["hidden_adjudication"]["attempts_per_arm_replicate"]
    arm_results: dict[str, Any] = {}
    for arm in protocol["arms"]:
        search_receipt, candidate_manifest = inputs[arm]
        candidates = candidate_manifest["candidates"][:attempts]
        results = []
        best_so_far = 0.0
        curve = []
        for index in range(attempts):
            if index < len(candidates):
                candidate = candidates[index]
                hidden = _evaluate_hidden_candidate(evaluator, candidate["solution"])
                result = {
                    "attempt": index + 1,
                    "candidate_id": candidate["id"],
                    "solution_sha256": candidate["solution_sha256"],
                    **hidden,
                }
                substantive_delta = max(
                    0.0, float(hidden["metrics"].get("substantive_score_delta", 0.0))
                )
            else:
                result = {
                    "attempt": index + 1,
                    "candidate_id": None,
                    "status": "missing_or_dev_inadmissible",
                    "combined_score": 0.0,
                    "metrics": {"behavioral_improvement_detected": 0.0},
                    "score_attribution": {},
                }
                substantive_delta = 0.0
            best_so_far = max(best_so_far, substantive_delta)
            curve.append(round(best_so_far, 12))
            results.append(result)

        passes = [
            result
            for result in results
            if result["metrics"].get("behavioral_improvement_detected") == 1.0
        ]
        best_result = max(
            results,
            key=lambda result: float(result["metrics"].get("substantive_score_delta", 0.0)),
        )
        arm_results[arm] = {
            "search_receipt_sha256": _sha256(block_dir / arm / "search_receipt.json"),
            "candidate_manifest_sha256": _sha256(block_dir / arm / "candidate_manifest.json"),
            "primary_behavioral_discovery": bool(passes),
            "first_behavioral_pass_attempt": passes[0]["attempt"] if passes else None,
            "behavioral_anytime_curve": curve,
            "behavioral_anytime_auc": round(sum(curve) / attempts, 12),
            "best_discovered_candidate_id": best_result["candidate_id"],
            "best_discovered_substantive_score_delta": best_result["metrics"].get(
                "substantive_score_delta", 0.0
            ),
            "search_budget": search_receipt["budget"]["usage"],
            "hidden_attempts": results,
        }

    receipt = {
        "experiment_id": protocol["experiment_id"],
        "seed": seed,
        "hidden_v4_sha256": protocol["hidden_adjudication"]["sha256"],
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
    arm_parser.add_argument("--seed", type=int, required=True)
    arm_parser.add_argument("--output-root", type=Path, required=True)
    adjudicate_parser = subparsers.add_parser("adjudicate-block")
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
        receipt = asyncio.run(run_arm(args.arm, args.seed, args.output_root))
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    if args.command == "adjudicate-block":
        receipt = adjudicate_block(args.seed, args.output_root)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
