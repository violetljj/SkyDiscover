#!/usr/bin/env python3
"""Frozen two-replicate-compatible Sky proposal harness for the BA Pilot."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skydiscover.config import load_config
from skydiscover.execution_budget import BudgetCeilings, BudgetLedger
from skydiscover.runner import Runner
from skydiscover.search.default_discovery_controller import DiscoveryControllerInput
from skydiscover.search.route import get_discovery_controller

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "config.yaml"
PROTOCOL_ID = "GOAL-COPILOT-1-SKY-PILOT"


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_once(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _canonical(value)
    with path.open("xb") as stream:
        stream.write(data)


def _git_head() -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def verify_bundle(bundle: Path) -> dict[str, Any]:
    manifest = json.loads((bundle / "manifest.json").read_text())
    checksums = json.loads((bundle / "checksums.json").read_text())
    actual = {name: _sha256(bundle / name) for name in sorted(manifest["payload_files"])}
    if checksums != actual:
        raise RuntimeError("BUNDLE_CORRUPTION: payload checksums differ")
    digest = hashlib.sha256(_canonical(checksums)).hexdigest()
    if manifest.get("bundle_digest") != digest or bundle.name != digest:
        raise RuntimeError("BUNDLE_CORRUPTION: identity differs")
    if manifest.get("fresh_material_exported") is not False:
        raise RuntimeError("FRESH_LEAKAGE")
    if any("fresh" in path.name.lower() for path in bundle.rglob("*")):
        raise RuntimeError("FRESH_LEAKAGE")
    return manifest


def verify_seal(seal_path: Path, bundle_manifest: dict[str, Any], replicate_id: str, seed: int) -> dict[str, Any]:
    seal = json.loads(seal_path.read_text())
    if seal.get("status") != "GOAL_COPILOT_1_SKY_PILOT_MODEL_CALLS_AUTHORIZED_NOT_STARTED":
        raise RuntimeError("formal seal does not authorize model calls")
    if seal.get("protocol_id") != PROTOCOL_ID:
        raise RuntimeError("protocol identity mismatch")
    if seal["source_commits"]["skydiscover"] != _git_head():
        raise RuntimeError("SkyDiscover commit drift")
    if seal["search_task_bundle_digest"] != bundle_manifest["bundle_digest"]:
        raise RuntimeError("SearchTaskBundle drift")
    registered = {item["id"]: item["seed"] for item in seal["replicates"]}
    if registered.get(replicate_id) != seed:
        raise RuntimeError("replicate identity is not preregistered")
    if seal["search_budget"]["generation_attempts_per_replicate"] != 16:
        raise RuntimeError("generation budget drift")
    return seal


async def run_replicate(bundle: Path, seal_path: Path, replicate_id: str, seed: int, output_dir: Path) -> dict[str, Any]:
    manifest = verify_bundle(bundle)
    seal = verify_seal(seal_path, manifest, replicate_id, seed)
    if output_dir.exists():
        raise FileExistsError(f"refusing to reuse formal replicate root: {output_dir}")
    output_dir.mkdir(parents=True)
    _write_once(output_dir / "run_started.json", {
        "protocol_id": PROTOCOL_ID, "replicate_id": replicate_id, "seed": seed,
        "status": "FORMAL_RUN_STARTED", "started_unix": time.time(),
    })

    config = load_config(CONFIG)
    config.context_builder.system_message = (
        (bundle / "search_prompt.md").read_text(encoding="utf-8")
        + "\n\n"
        + config.context_builder.system_message
    )
    config.llm.update_model_params(
        {"system_message": config.context_builder.system_message}, overwrite=True
    )
    config.search.database.random_seed = seed
    random.seed(seed)
    initial = bundle / "initial_policy.py"
    evaluator = bundle / "evaluator.py"
    runner = Runner(
        evaluation_file=str(evaluator), initial_program_path=str(initial),
        config=config, output_dir=str(output_dir / "sky_runtime"),
    )
    controller_input = DiscoveryControllerInput(
        config=config, evaluation_file=str(evaluator), database=runner.database,
        file_suffix=runner.file_extension, output_dir=str(output_dir / "sky_runtime"),
    )
    controller = get_discovery_controller(controller_input)
    runner.discovery_controller = controller
    started = time.time()
    ledger = BudgetLedger(
        BudgetCeilings(
            generation_calls=16, evaluator_attempts=16,
            total_tokens=seal["search_budget"]["total_token_ceiling_per_replicate"],
            require_token_usage=True,
        ),
        journal_path=str(output_dir / "generation_journal.jsonl"),
    )
    try:
        # Frozen baseline is not a candidate-generation opportunity.
        await runner._add_initial_program(0)
        with ledger.activate():
            await controller.run_discovery(
                start_iteration=1, max_iterations=16,
                checkpoint_callback=None, retry_times=1,
            )
        runner._sync_database()
        candidates_dir = output_dir / "candidates"
        candidates_dir.mkdir()
        entries = []
        for program in sorted(
            (item for item in runner.database.programs.values() if item.iteration_found > 0),
            key=lambda item: (item.iteration_found, item.id),
        ):
            digest = hashlib.sha256(program.solution.encode()).hexdigest()
            target = candidates_dir / digest
            target.mkdir(exist_ok=True)
            policy = target / "policy.py"
            if not policy.exists():
                policy.write_text(program.solution, encoding="utf-8", newline="\n")
            actual_digest = _sha256(policy)
            bundle_digest = hashlib.sha256(_canonical({
                "candidate_digest": actual_digest,
                "replicate_id": replicate_id,
                "iteration": program.iteration_found,
                "source_search_task_bundle_digest": manifest["bundle_digest"],
            })).hexdigest()
            entries.append({
                "candidate_digest": actual_digest,
                "candidate_bundle_digest": bundle_digest,
                "iteration": program.iteration_found,
                "program_id": program.id,
                "parent_id": program.parent_id,
                "solution_file": policy.relative_to(output_dir).as_posix(),
                "sky_dev_metrics_provenance_only": program.metrics,
            })
        candidate_manifest = {
            "protocol_id": PROTOCOL_ID,
            "replicate_id": replicate_id,
            "seed": seed,
            "generation_attempts": ledger.generation_calls,
            "source_search_task_bundle_digest": manifest["bundle_digest"],
            "candidates": entries,
        }
        _write_once(output_dir / "candidate_manifest.json", candidate_manifest)
        receipt = {
            "protocol_id": PROTOCOL_ID,
            "replicate_id": replicate_id,
            "seed": seed,
            "skydiscover_commit": _git_head(),
            "config_sha256": _sha256(CONFIG),
            "bundle_digest": manifest["bundle_digest"],
            "candidate_count": len(entries),
            "unique_candidate_count": len({item["candidate_digest"] for item in entries}),
            "budget": ledger.to_receipt(),
            "fresh_evaluations": 0,
            "elapsed_seconds": round(time.time() - started, 6),
            "status": "COMPLETE" if ledger.generation_calls == 16 else "INCOMPLETE_FORMAL_RUN",
        }
        _write_once(output_dir / "search_receipt.json", receipt)
        return receipt
    finally:
        controller.close()
        runner.discovery_controller = None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--seal", type=Path, required=True)
    parser.add_argument("--replicate-id", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = asyncio.run(run_replicate(
        args.bundle.resolve(), args.seal.resolve(), args.replicate_id,
        args.seed, args.output.resolve(),
    ))
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
