"""Create the immutable execution manifest after preflight passes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PATHS = [
    "benchmarks/blindassist_last10m_structured_direct_1/protocol.json",
    "benchmarks/blindassist_last10m_structured_direct_1/cohort_manifest.json",
    "benchmarks/blindassist_last10m_structured_direct_1/structured_initial_program.py",
    "benchmarks/blindassist_last10m_structured_direct_1/candidate_guard.py",
    "benchmarks/blindassist_last10m_structured_direct_1/evaluator.py",
    "benchmarks/blindassist_last10m_structured_direct_1/generate_cohort.py",
    "benchmarks/blindassist_last10m_structured_direct_1/harness.py",
    "benchmarks/blindassist_last10m_structured_direct_1/analysis.py",
    "benchmarks/blindassist_last10m_structured_direct_1/preflight.py",
    "benchmarks/blindassist_last10m_structured_direct_1/receipts/mechanical_preflight.json",
    "benchmarks/blindassist_last10m_structured_direct_1/configs/raw_direct.yaml",
    "benchmarks/blindassist_last10m_structured_direct_1/configs/structured_direct.yaml",
    "benchmarks/blindassist_last10m_v3/initial_program.py",
    "benchmarks/blindassist_last10m_v3/evaluator/evaluator.py",
    "skydiscover/execution_budget.py",
    "skydiscover/llm/codex_cli.py",
    "skydiscover/evaluation/evaluator.py",
    "skydiscover/search/incumbent_only/database.py",
    "skydiscover/search/evox/controller.py",
    "skydiscover/search/evox/database/initial_search_strategy.py",
    "skydiscover/search/evox/database/search_strategy_evaluator.py",
    "skydiscover/search/route.py",
    "skydiscover/search/registry.py",
    "skydiscover/config.py",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    receipt = json.loads((HERE / "receipts/mechanical_preflight.json").read_text(encoding="utf-8"))
    if receipt["status"] != "MECHANICAL_PREFLIGHT_PASS":
        raise RuntimeError("mechanical preflight did not pass")
    result = {
        "experiment_id": "L10M-STRUCT-DIRECT-1",
        "status": "EXECUTION_MANIFEST_FROZEN",
        "hash_algorithm": "sha256",
        "text_normalization": "crlf_to_lf",
        "external_cohort_files_bound_transitively_by": "cohort_manifest.json",
        "files": [{"path": item, "sha256": sha256(ROOT / item)} for item in PATHS],
    }
    path = HERE / "execution_manifest.json"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"status": result["status"], "files": len(PATHS)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
