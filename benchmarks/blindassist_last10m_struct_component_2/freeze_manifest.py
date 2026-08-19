"""Print the COMPONENT-2 execution manifest after mechanical preflight."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PATHS = [
    "benchmarks/blindassist_last10m_struct_component_2/protocol.json",
    "benchmarks/blindassist_last10m_struct_component_2/README.md",
    "benchmarks/blindassist_last10m_struct_component_2/integrity.py",
    "benchmarks/blindassist_last10m_struct_component_2/harness.py",
    "benchmarks/blindassist_last10m_struct_component_2/analysis.py",
    "benchmarks/blindassist_last10m_struct_component_2/progress.py",
    "benchmarks/blindassist_last10m_struct_component_2/execute.py",
    "benchmarks/blindassist_last10m_struct_component_2/preflight.py",
    "benchmarks/blindassist_last10m_struct_component_2/receipts/mechanical_preflight.json",
    "benchmarks/blindassist_last10m_struct_component_1/initial_program.py",
    "benchmarks/blindassist_last10m_struct_component_1/arm_prompts.json",
    "benchmarks/blindassist_last10m_struct_component_1/config.yaml",
    "benchmarks/blindassist_last10m_struct_component_1/candidate_guard.py",
    "benchmarks/blindassist_last10m_struct_component_1/evaluator.py",
    "benchmarks/blindassist_last10m_struct_component_1/harness.py",
    "benchmarks/blindassist_last10m_struct_component_1/analysis.py",
    "benchmarks/blindassist_last10m_comp_2/cohort_manifest.json",
    "benchmarks/blindassist_last10m_v3/evaluator/evaluator.py",
    "skydiscover/execution_budget.py",
    "skydiscover/llm/codex_cli.py",
    "skydiscover/evaluation/evaluator.py",
    "skydiscover/search/incumbent_only/database.py",
    "skydiscover/search/route.py",
    "skydiscover/config.py",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def build() -> dict[str, object]:
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    if protocol["status"] != "EXECUTION_PROTOCOL_FROZEN" or protocol["execution_blockers"]:
        raise RuntimeError("protocol must be execution-frozen without blockers")
    receipt = json.loads((HERE / "receipts/mechanical_preflight.json").read_text(encoding="utf-8"))
    if receipt["status"] != "MECHANICAL_PREFLIGHT_PASS" or receipt["formal_arm_runs"] != 0:
        raise RuntimeError("mechanical preflight is not admissible")
    return {
        "experiment_id": protocol["experiment_id"],
        "status": "EXECUTION_MANIFEST_FROZEN",
        "hash_algorithm": "sha256",
        "text_normalization": "crlf_to_lf",
        "formal_arm_runs_observed_before_freeze": 0,
        "component_1_results_imported": False,
        "files": [{"path": path, "sha256": _sha256(ROOT / path)} for path in PATHS],
    }


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
