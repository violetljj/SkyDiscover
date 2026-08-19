"""Receipt-only mechanism autopsy for L10M-STRUCT-DIRECT-1.

This module never calls a model and never evaluates a candidate.  It reads the
sealed hidden adjudications and candidate manifests, selects the same frozen
best-of-six rows as the formal analyzer, and reports descriptive associations
between changed contract bodies and paired outcomes.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

HERE = Path(__file__).resolve().parent


def _functions(source: str) -> dict[str, str]:
    tree = ast.parse(source)
    return {
        node.name: ast.unparse(node)
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _candidate(manifest: Path, candidate_id: str) -> str:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    for item in payload.get("candidates", []):
        if item.get("id") == candidate_id:
            return str(item.get("solution", ""))
    raise RuntimeError(f"candidate {candidate_id} missing from {manifest}")


def _selected(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return max(rows, key=lambda row: (row["value"], row["safe"], -row["replicate"]))


def _tags(source: str, baseline: dict[str, str]) -> list[str]:
    current = _functions(source)
    names = (
        "safety_contract",
        "tracking_contract",
        "propose_moves",
        "progress_contract",
        "termination_contract",
    )
    return [name for name in names if current.get(name) != baseline.get(name)]


def _features(source: str) -> list[str]:
    """Extract conservative implementation features from selected source text."""
    functions = _functions(source)
    progress = functions.get("progress_contract", "")
    tracking = functions.get("tracking_contract", "")
    safety = functions.get("safety_contract", "")
    termination = functions.get("termination_contract", "")
    features = []
    if any(
        token in progress
        for token in ("last_action", "action_age", "stagn", "failed", "no_progress")
    ):
        features.append("progress_memory")
    if any(token in tracking for token in ("lost_steps", "scan_direction", "REACQUIRE")):
        features.append("tracking_memory")
    if any(token in safety for token in ("closing_risk", "safety_confidence", "STOP")):
        features.append("safety_guard")
    if "STOP" in termination and "return" in termination:
        features.append("termination_fallback")
    if "propose_moves" in functions and "candidates" in functions["propose_moves"]:
        features.append("move_proposals")
    return features


def analyze(receipt_root: Path, initial_program: Path) -> dict[str, Any]:
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    cohort = json.loads((HERE / "cohort_manifest.json").read_text(encoding="utf-8"))
    baseline = _functions(initial_program.read_text(encoding="utf-8"))
    seeds = protocol["direct_replicates"]["local_seeds"]
    rows = []
    for item in cohort["instances"]:
        instance = item["instance_id"]
        arms: dict[str, list[dict[str, Any]]] = {arm: [] for arm in protocol["arms"]}
        for replicate, seed in enumerate(seeds, 1):
            receipt_path = receipt_root / instance / f"seed_{seed}" / "hidden_adjudication.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            for arm in protocol["arms"]:
                result = receipt["arms"][arm]
                attempt = (result.get("hidden_attempts") or [{}])[0]
                candidate_id = attempt.get("candidate_id")
                manifest = (
                    receipt_root / instance / f"seed_{seed}" / arm / "candidate_manifest.json"
                )
                arms[arm].append(
                    {
                        "replicate": replicate,
                        "seed": seed,
                        "value": max(
                            0.0,
                            float(
                                result.get("best_discovered_substantive_score_delta", 0.0) or 0.0
                            ),
                        ),
                        "safe": bool(result.get("best_discovered_robust_safe", False)),
                        "candidate_id": candidate_id,
                        "source": _candidate(manifest, candidate_id) if candidate_id else "",
                    }
                )
        selected = {arm: _selected(values) for arm, values in arms.items()}
        structured = selected["structured_direct"]
        raw = selected["raw_direct"]
        rows.append(
            {
                "instance_id": instance,
                "structured_value": structured["value"],
                "raw_value": raw["value"],
                "effect": structured["value"] - raw["value"],
                "structured_safe": structured["safe"],
                "structured_candidate_id": structured["candidate_id"],
                "changed_contracts": _tags(structured["source"], baseline),
                "features": _features(structured["source"]),
            }
        )
    tie = max(abs(x) for x in protocol["primary_endpoint"]["tie_interval_inclusive"])
    component_rows: dict[str, list[dict[str, Any]]] = {
        name: []
        for name in (
            "safety_contract",
            "tracking_contract",
            "propose_moves",
            "progress_contract",
            "termination_contract",
        )
    }
    feature_rows: dict[str, list[dict[str, Any]]] = {
        name: []
        for name in (
            "progress_memory",
            "tracking_memory",
            "safety_guard",
            "termination_fallback",
            "move_proposals",
        )
    }
    for row in rows:
        for name in component_rows:
            if name in row["changed_contracts"]:
                component_rows[name].append(row)
        for name in feature_rows:
            if name in row["features"]:
                feature_rows[name].append(row)

    def summarize(values: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "selected_instances": len(values),
            "mean_effect": mean(r["effect"] for r in values) if values else 0.0,
            "wins": sum(r["effect"] > tie for r in values),
            "losses": sum(r["effect"] < -tie for r in values),
            "instances": [r["instance_id"] for r in values],
        }

    return {
        "experiment_id": "L10M-STRUCT-AUTOPSY-1",
        "source_experiment": protocol["experiment_id"],
        "fresh_tasks": 0,
        "model_calls": 0,
        "receipt_only": True,
        "instance_count": len(rows),
        "paired_summary": {
            "mean_effect_structured_minus_raw": mean(r["effect"] for r in rows),
            "wins": sum(r["effect"] > tie for r in rows),
            "ties": sum(-tie <= r["effect"] <= tie for r in rows),
            "losses": sum(r["effect"] < -tie for r in rows),
            "structured_robust_safe": sum(r["structured_safe"] for r in rows),
        },
        "component_associations": {
            name: summarize(values) for name, values in component_rows.items()
        },
        "feature_associations": {name: summarize(values) for name, values in feature_rows.items()},
        "instances": rows,
        "claim_ceiling": "descriptive, post-hoc association only; no component-level causal claim",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt-root", type=Path, required=True)
    parser.add_argument(
        "--initial-program", type=Path, default=HERE / "structured_initial_program.py"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(args.receipt_root.resolve(), args.initial_program.resolve())
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
