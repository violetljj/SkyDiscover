#!/usr/bin/env python3
"""Create the immutable execution manifest after all zero-call gates pass."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PATHS = [
    "benchmarks/blindassist_last10m_long_horizon_1/protocol.json",
    "benchmarks/blindassist_last10m_long_horizon_1/README.md",
    "benchmarks/blindassist_last10m_long_horizon_1/configs/naked.yaml",
    "benchmarks/blindassist_last10m_long_horizon_1/configs/adaevolve.yaml",
    "benchmarks/blindassist_last10m_long_horizon_1/configs/evox.yaml",
    "benchmarks/blindassist_last10m_long_horizon_1/evaluator.py",
    "benchmarks/blindassist_last10m_long_horizon_1/harness.py",
    "benchmarks/blindassist_last10m_long_horizon_1/launcher.py",
    "benchmarks/blindassist_last10m_long_horizon_1/progress.py",
    "benchmarks/blindassist_last10m_long_horizon_1/remote_worker.py",
    "benchmarks/blindassist_last10m_long_horizon_1/transport.py",
    "benchmarks/blindassist_last10m_long_horizon_1/receipts/mechanical_preflight.json",
    "benchmarks/blindassist_last10m_comp_2/cohort_manifest.json",
    "benchmarks/blindassist_last10m_v3/initial_program.py",
    "benchmarks/blindassist_last10m_v3/evaluator/evaluator.py",
    "skydiscover/evaluation/evaluator.py",
    "skydiscover/execution_budget.py",
    "skydiscover/runner.py",
    "skydiscover/search/adaevolve/controller.py",
    "skydiscover/search/evox/controller.py",
    "skydiscover/search/evox/utils/search_scorer.py",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    preflight = json.loads(
        (HERE / "receipts/mechanical_preflight.json").read_text(encoding="utf-8")
    )
    if protocol["status"] != "EXECUTION_PROTOCOL_FROZEN":
        raise RuntimeError("protocol is not execution-frozen")
    if preflight["status"] != "MECHANICAL_PREFLIGHT_PASS":
        raise RuntimeError("mechanical preflight did not pass")
    payload = {
        "experiment_id": protocol["experiment_id"],
        "status": "EXECUTION_MANIFEST_FROZEN",
        "hash_algorithm": "sha256",
        "text_normalization": "crlf_to_lf",
        "formal_trajectories_observed_before_freeze": 0,
        "files": [{"path": path, "sha256": sha256(ROOT / path)} for path in PATHS],
    }
    path = HERE / "execution_manifest.json"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"status": payload["status"], "files": len(PATHS)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
