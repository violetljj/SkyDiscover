"""Zero-model bundle/config/evaluator transport canary for GC2-B."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from skydiscover.config import load_config

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True


def run(bundle: Path) -> dict[str, object]:
    harness_spec = importlib.util.spec_from_file_location("gc2b_harness", HERE / "harness.py")
    assert harness_spec and harness_spec.loader
    harness = importlib.util.module_from_spec(harness_spec)
    harness_spec.loader.exec_module(harness)
    manifest = harness.verify_bundle(bundle)
    config = load_config(HERE / "config.yaml")
    evaluator_spec = importlib.util.spec_from_file_location(
        "gc2b_bundle_evaluator", bundle / "evaluator.py"
    )
    assert evaluator_spec and evaluator_spec.loader
    evaluator = importlib.util.module_from_spec(evaluator_spec)
    evaluator_spec.loader.exec_module(evaluator)
    metrics = evaluator.evaluate(str(bundle / "initial_policy.py"))
    passed = (
        manifest["protocol_id"] == "GOAL-COPILOT-2B"
        and config.max_iterations == 16
        and config.search.database.best_of_n == 4
        and metrics["clean_completion_count"] == 12
        and metrics["combined_moderate_completion_count"] == 0
        and metrics["unsafe_guidance_total"] == 0
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "model_calls": 0,
        "bundle_digest": manifest["bundle_digest"],
        "baseline_calibration": {
            "clean_completion_count": metrics["clean_completion_count"],
            "combined_moderate_completion_count": metrics["combined_moderate_completion_count"],
            "premature_completion_total": metrics["premature_completion_total"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.bundle.resolve())
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("xb") as stream:
        stream.write((json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode())
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
