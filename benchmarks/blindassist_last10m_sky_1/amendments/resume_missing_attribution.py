#!/usr/bin/env python3
"""Resume SKY-1 after a hidden candidate omitted a diagnostic attribution artifact."""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
BENCHMARK = HERE.parent
if str(BENCHMARK) not in sys.path:
    sys.path.insert(0, str(BENCHMARK))

import execute
import harness


def _evaluate_hidden_with_optional_attribution(evaluator: Any, solution: str) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", encoding="utf-8", delete=False
    ) as handle:
        handle.write(solution)
        candidate_path = Path(handle.name)
    try:
        result = evaluator.evaluate(str(candidate_path), "test")
    finally:
        candidate_path.unlink(missing_ok=True)
    artifacts = result.get("artifacts") or {}
    raw_attribution = artifacts.get("score_attribution")
    if isinstance(raw_attribution, str):
        try:
            attribution = json.loads(raw_attribution)
        except json.JSONDecodeError:
            attribution = {}
    elif isinstance(raw_attribution, dict):
        attribution = copy.deepcopy(raw_attribution)
    else:
        attribution = {}
    return {
        "status": result["status"],
        "combined_score": result["combined_score"],
        "metrics": result["metrics"],
        "score_attribution": attribution,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, default=4)
    args = parser.parse_args()
    harness._evaluate_hidden = _evaluate_hidden_with_optional_attribution
    result = asyncio.run(
        execute.execute_shard(
            args.output_root.resolve(), args.shard_index, args.shard_count
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
