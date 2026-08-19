#!/usr/bin/env python3
"""Create the L10M-SKY-1 execution manifest after protocol/cohort freeze."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUTPUT = HERE / "execution_manifest.json"

FILES = [
    "benchmarks/blindassist_last10m_sky_1/protocol.json",
    "benchmarks/blindassist_last10m_sky_1/cohort_manifest.json",
    "benchmarks/blindassist_last10m_sky_1/generate_cohort.py",
    "benchmarks/blindassist_last10m_sky_1/evaluator.py",
    "benchmarks/blindassist_last10m_sky_1/harness.py",
    "benchmarks/blindassist_last10m_sky_1/execute.py",
    "benchmarks/blindassist_last10m_sky_1/analysis.py",
    "benchmarks/blindassist_last10m_sky_1/configs/naked_codex.yaml",
    "benchmarks/blindassist_last10m_sky_1/configs/sky_search.yaml",
    "benchmarks/blindassist_last10m_v3/initial_program.py",
    "benchmarks/blindassist_last10m_v3/evaluator/evaluator.py",
    "skydiscover/execution_budget.py",
    "skydiscover/llm/codex_cli.py",
    "skydiscover/evaluation/evaluator.py",
    "skydiscover/search/incumbent_only/database.py",
    "skydiscover/search/best_of_n/database.py",
    "skydiscover/search/default_discovery_controller.py",
    "skydiscover/search/route.py",
    "skydiscover/config.py"
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to replace {OUTPUT}")
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    if protocol["status"] != "EXECUTION_PROTOCOL_FROZEN":
        raise RuntimeError("protocol must be execution-frozen before manifest creation")
    cohort = json.loads((HERE / "cohort_manifest.json").read_text(encoding="utf-8"))
    if cohort["treatment_runs_observed"] != 0:
        raise RuntimeError("cohort is not pre-treatment")
    payload = {
        "experiment_id": "L10M-SKY-1",
        "frozen_at": "2026-08-19",
        "hash_algorithm": "sha256",
        "text_normalization": "crlf_to_lf",
        "cohort_files_bound_transitively_by": "cohort_manifest.json",
        "files": [
            {"path": relative, "sha256": _sha256(ROOT / relative)} for relative in FILES
        ],
    }
    with OUTPUT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
