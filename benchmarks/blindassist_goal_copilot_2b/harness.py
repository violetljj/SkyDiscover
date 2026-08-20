#!/usr/bin/env python3
"""Formal GC2-B harness built on the frozen GC1 Pilot budget mechanics."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PILOT = ROOT / "benchmarks" / "blindassist_goal_copilot_pilot" / "harness.py"
SPEC = importlib.util.spec_from_file_location("goal_copilot_pilot_harness", PILOT)
assert SPEC and SPEC.loader
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)

PROTOCOL_ID = "GOAL-COPILOT-2B"
CONFIG = HERE / "config.yaml"
pilot.PROTOCOL_ID = PROTOCOL_ID
pilot.CONFIG = CONFIG
sys.dont_write_bytecode = True


def verify_seal(
    seal_path: Path, bundle_manifest: dict[str, Any], replicate_id: str, seed: int
) -> dict[str, Any]:
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    if seal.get("status") != "GOAL_COPILOT_2B_MODEL_CALLS_AUTHORIZED_NOT_STARTED":
        raise RuntimeError("formal seal does not authorize GC2-B model calls")
    if seal.get("protocol_id") != PROTOCOL_ID:
        raise RuntimeError("protocol identity mismatch")
    if seal["source_commits"]["skydiscover"] != pilot._git_head():
        raise RuntimeError("SkyDiscover commit drift")
    if seal["search_task_bundle_digest"] != bundle_manifest["bundle_digest"]:
        raise RuntimeError("SearchTaskBundle drift")
    registered = {item["id"]: item["seed"] for item in seal["replicates"]}
    if registered.get(replicate_id) != seed:
        raise RuntimeError("replicate identity is not preregistered")
    budget = seal["search_budget"]
    if (
        budget["generation_attempts_per_replicate"] != 16
        or budget["generation_attempts_total"] != 32
        or budget["generation_retries"] != 0
        or budget["evaluator_retries"] != 0
    ):
        raise RuntimeError("search budget drift")
    if seal["heldout_plaintext_present_during_search"] is not False:
        raise RuntimeError("held-out leakage")
    return seal


pilot.verify_seal = verify_seal
run_replicate = pilot.run_replicate
verify_bundle = pilot.verify_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--seal", type=Path, required=True)
    parser.add_argument("--replicate-id", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = asyncio.run(
        run_replicate(
            args.bundle.resolve(),
            args.seal.resolve(),
            args.replicate_id,
            args.seed,
            args.output.resolve(),
        )
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
