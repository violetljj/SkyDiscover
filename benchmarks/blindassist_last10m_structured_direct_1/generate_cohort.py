#!/usr/bin/env python3
"""Materialize the fresh STRUCT-DIRECT-1 cohort into an external sealed root."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import random
import secrets
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROTOCOL_PATH = HERE / "protocol.json"
BASE_GENERATOR = ROOT / "benchmarks" / "blindassist_last10m_comp_1" / "generate_hidden_v4.py"
BASE_EVALUATOR = ROOT / "benchmarks" / "blindassist_last10m_v3" / "evaluator" / "evaluator.py"
INITIAL_PROGRAM = ROOT / "benchmarks" / "blindassist_last10m_v3" / "initial_program.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _swap_lr(value: str) -> str:
    swaps = {
        "SCAN_LEFT": "SCAN_RIGHT",
        "SCAN_RIGHT": "SCAN_LEFT",
        "VEER_LEFT": "VEER_RIGHT",
        "VEER_RIGHT": "VEER_LEFT",
    }
    return swaps.get(value, value)


def _transform_scenarios(seed: int, prefix: str) -> list[dict[str, Any]]:
    """Create a candidate-independent parameterization of the frozen graph family."""
    generator = _load_module(f"l10m_comp2_generator_{seed}", BASE_GENERATOR)
    scenarios = copy.deepcopy(generator.build_hidden_v4())
    rng = random.Random(seed)
    for index, scenario in enumerate(scenarios, start=1):
        mirror = bool(rng.getrandbits(1))
        scenario["id"] = f"{prefix}_{index:02d}"
        records = [scenario.get("node_defaults", {})] + list(scenario["nodes"])
        for record in records:
            if mirror:
                left = record.get("corridor_left")
                right = record.get("corridor_right")
                if left is not None or right is not None:
                    record["corridor_left"], record["corridor_right"] = right, left
            for field in ("target_bearing", "heading_error"):
                value = record.get(field)
                if isinstance(value, (int, float)) and value:
                    sign = -1.0 if float(value) < 0 else 1.0
                    magnitude = max(1.0, abs(float(value)) + rng.choice([-2, -1, 0, 1, 2]))
                    record[field] = round((-sign if mirror else sign) * magnitude, 3)
            transitions = record.get("transitions")
            if mirror and isinstance(transitions, dict):
                record["transitions"] = {
                    _swap_lr(action): target for action, target in transitions.items()
                }
        scenario["max_steps"] = int(scenario.get("max_steps", 20)) + rng.choice([0, 1, 2])
    rng.shuffle(scenarios)
    return scenarios


def _expand(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scenarios = copy.deepcopy(raw)
    for scenario in scenarios:
        defaults = scenario.pop("node_defaults", {})
        defaults.setdefault("rgb_ref", None)
        scenario["nodes"] = [{**defaults, **node} for node in scenario["nodes"]]
    return scenarios


def _baseline_result(raw: list[dict[str, Any]]) -> dict[str, float]:
    evaluator = _load_module(f"l10m_comp2_eval_{random.getrandbits(64)}", BASE_EVALUATOR)
    scenarios = _expand(raw)
    evaluator._load_scenarios = lambda mode: copy.deepcopy(scenarios)
    result = evaluator.evaluate(str(INITIAL_PROGRAM), "train")
    metrics = result["metrics"]
    return {
        "combined_score": float(result["combined_score"]),
        "validity": float(metrics["validity"]),
        "task_success": float(metrics["task_success"]),
        "safe_termination": float(metrics["safe_termination"]),
    }


def _eligible(result: dict[str, float], ceiling: float) -> bool:
    return (
        result["validity"] == 1.0
        and result["task_success"] == 1.0
        and result["safe_termination"] == 1.0
        and result["combined_score"] < ceiling
    )


def build_cohort(master_seed: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    if protocol["status"] != "DESIGN_FROZEN_PENDING_FRESH_COHORT":
        raise RuntimeError("unsupported protocol state for deterministic cohort reproduction")
    spec = protocol["instances"]
    headroom = spec["headroom_rule"]
    if protocol["instances"]["generator_seed"] != "sealed_private_create_once":
        raise RuntimeError("public protocol must not disclose the cohort seed")
    rng = random.Random(master_seed)
    accepted: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    for candidate_index in range(1, spec["candidate_pool_limit"] + 1):
        instance_seed = rng.randrange(1, 2**31)
        instance_rng = random.Random(instance_seed)
        dev_seed = instance_rng.randrange(1, 2**31)
        hidden_seed = instance_rng.randrange(1, 2**31)
        instance_id = f"instance_{len(accepted) + 1:02d}"
        dev = _transform_scenarios(dev_seed, f"{instance_id}_D")
        hidden = _transform_scenarios(hidden_seed, f"{instance_id}_H")
        dev_result = _baseline_result(dev)
        hidden_result = _baseline_result(hidden)
        admitted = _eligible(
            dev_result, headroom["development_initial_score_strictly_below"]
        ) and _eligible(hidden_result, headroom["hidden_initial_score_strictly_below"])
        audit.append(
            {
                "candidate_index": candidate_index,
                "instance_seed": instance_seed,
                "dev_seed": dev_seed,
                "hidden_seed": hidden_seed,
                "dev_initial": dev_result,
                "hidden_initial": hidden_result,
                "admitted": admitted,
            }
        )
        if admitted:
            accepted.append(
                {
                    "instance_id": instance_id,
                    "instance_seed": instance_seed,
                    "dev_seed": dev_seed,
                    "hidden_seed": hidden_seed,
                    "dev": dev,
                    "hidden": hidden,
                    "dev_initial": dev_result,
                    "hidden_initial": hidden_result,
                }
            )
            if len(accepted) == spec["count"]:
                break
    if len(accepted) != spec["count"]:
        raise RuntimeError(f"only {len(accepted)} eligible instances were found")
    return accepted, {"candidate_audit": audit}


def materialize(output_root: Path) -> dict[str, Any]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    if protocol["status"] != "DESIGN_FROZEN_PENDING_FRESH_COHORT":
        raise RuntimeError("new cohort materialization requires the design-frozen protocol state")
    if output_root.exists():
        raise FileExistsError(f"refusing to replace cohort root: {output_root}")
    try:
        output_root.relative_to(ROOT)
    except ValueError:
        pass
    else:
        raise ValueError("sealed cohort root must be outside the Git worktree")
    master_seed = secrets.randbits(128)
    cohort, audit = build_cohort(master_seed)
    output_root.mkdir(parents=True)
    records = []
    for instance in cohort:
        instance_dir = output_root / instance["instance_id"]
        instance_dir.mkdir()
        dev_path = instance_dir / "dev.json"
        hidden_path = instance_dir / "hidden.json"
        dev_path.write_text(
            json.dumps(instance.pop("dev"), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        hidden_path.write_text(
            json.dumps(instance.pop("hidden"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        records.append(
            {
                "instance_id": instance["instance_id"],
                "dev_path": dev_path.relative_to(output_root).as_posix(),
                "dev_sha256": _sha256(dev_path),
                "hidden_path": hidden_path.relative_to(output_root).as_posix(),
                "hidden_sha256": _sha256(hidden_path),
            }
        )
    manifest = {
        "experiment_id": "L10M-STRUCT-DIRECT-1",
        "status": "FRESH_COHORT_MATERIALIZED_PRE_TREATMENT",
        "treatment_runs_observed": 0,
        "protocol_sha256": _sha256(PROTOCOL_PATH),
        "private_seed_disclosed": False,
        "private_paths_are_relative_to_sealed_root": True,
        "instances": records,
    }
    private_receipt = {
        "experiment_id": "L10M-STRUCT-DIRECT-1",
        "status": "PRIVATE_CREATE_ONCE_GENERATION_RECEIPT",
        "master_seed": str(master_seed),
        "protocol_sha256": _sha256(PROTOCOL_PATH),
        "candidate_audit": audit["candidate_audit"],
        "public_manifest": manifest,
    }
    with (output_root / "generation_receipt.private.json").open(
        "x", encoding="utf-8", newline="\n"
    ) as handle:
        json.dump(private_receipt, handle, indent=2, sort_keys=True)
        handle.write("\n")
    manifest_path = HERE / "cohort_manifest.json"
    with manifest_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = materialize(args.output_root.resolve())
    print(
        json.dumps(
            {
                "experiment_id": result["experiment_id"],
                "status": result["status"],
                "instance_count": len(result["instances"]),
                "private_seed_disclosed": result["private_seed_disclosed"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
