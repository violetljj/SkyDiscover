"""Create the immutable COMPONENT-1 execution manifest after preflight."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PATHS = [
    "benchmarks/blindassist_last10m_struct_component_1/protocol.json",
    "benchmarks/blindassist_last10m_struct_component_1/README.md",
    "benchmarks/blindassist_last10m_struct_component_1/initial_program.py",
    "benchmarks/blindassist_last10m_struct_component_1/arm_prompts.json",
    "benchmarks/blindassist_last10m_struct_component_1/config.yaml",
    "benchmarks/blindassist_last10m_struct_component_1/candidate_guard.py",
    "benchmarks/blindassist_last10m_struct_component_1/evaluator.py",
    "benchmarks/blindassist_last10m_struct_component_1/harness.py",
    "benchmarks/blindassist_last10m_struct_component_1/analysis.py",
    "benchmarks/blindassist_last10m_struct_component_1/progress.py",
    "benchmarks/blindassist_last10m_struct_component_1/preflight.py",
    "benchmarks/blindassist_last10m_struct_component_1/receipts/mechanical_preflight.json",
    "benchmarks/blindassist_last10m_comp_2/cohort_manifest.json",
    "benchmarks/blindassist_last10m_v3/evaluator/evaluator.py",
    "skydiscover/execution_budget.py",
    "skydiscover/llm/codex_cli.py",
    "skydiscover/evaluation/evaluator.py",
    "skydiscover/search/incumbent_only/database.py",
    "skydiscover/search/route.py",
    "skydiscover/config.py",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def build() -> dict[str, object]:
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    if protocol["status"] != "EXECUTION_PROTOCOL_FROZEN":
        raise RuntimeError("protocol must be marked execution-frozen before manifest creation")
    if protocol["execution_blockers"]:
        raise RuntimeError("protocol still contains execution blockers")
    receipt = json.loads((HERE / "receipts/mechanical_preflight.json").read_text(encoding="utf-8"))
    if receipt["status"] != "MECHANICAL_PREFLIGHT_PASS":
        raise RuntimeError("mechanical preflight did not pass")
    return {
        "experiment_id": protocol["experiment_id"],
        "status": "EXECUTION_MANIFEST_FROZEN",
        "hash_algorithm": "sha256",
        "text_normalization": "crlf_to_lf",
        "formal_arm_runs_observed_before_freeze": 0,
        "files": [{"path": path, "sha256": sha256(ROOT / path)} for path in PATHS],
    }


def main() -> int:
    result = build()
    path = HERE / "execution_manifest.json"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"status": result["status"], "files": len(PATHS)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
