"""Zero-model-call mechanical preflight for COMPONENT-2."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = ROOT / "benchmarks/blindassist_last10m_struct_component_1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


harness = _load("l10m_struct_component_2_preflight_harness", HERE / "harness.py")


def run() -> dict[str, object]:
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    assert protocol["status"] in {
        "DESIGN_FROZEN_PENDING_MECHANICAL_PREFLIGHT",
        "EXECUTION_PROTOCOL_FROZEN",
    }
    assert protocol["arms"] == ["raw_control", "progress_only", "moves_only", "progress_moves"]
    assert set(protocol["direct_replicates"]["local_seeds"]).isdisjoint(
        {1701, 1702, 1703, 1704, 1705, 1706}
    )
    assert protocol["complete_block_rule"]["minimum_complete_blocks"] == 70
    assert protocol["complete_block_rule"]["minimum_complete_seeds_per_instance"] == 5
    source_manifest = json.loads((BASE / "execution_manifest.json").read_text(encoding="utf-8"))
    source_hashes = {row["path"]: row["sha256"] for row in source_manifest["files"]}
    reused = {}
    for filename in protocol["unchanged_component_implementation"]["files"]:
        path = BASE / filename
        key = f"benchmarks/blindassist_last10m_struct_component_1/{filename}"
        assert _sha256(path) == source_hashes[key]
        reused[filename] = _sha256(path)
    cohort = ROOT / protocol["consumed_cohort"]["manifest_path"]
    assert _sha256(cohort) == protocol["consumed_cohort"]["manifest_sha256"]
    assert harness.synthetic_preflight()["arms"] == protocol["arms"]
    executable = Path(protocol["provider_executable"]["path"])
    version = subprocess.run(
        [str(executable), "--version"], check=True, capture_output=True, text=True, timeout=30
    ).stdout.strip()
    if not version or "unknown" in version.lower():
        raise RuntimeError(f"unusable Codex CLI version: {version!r}")
    assert version == protocol["provider_executable"]["required_version"]
    login = subprocess.run(
        [str(executable), "login", "status"], check=True, capture_output=True, text=True, timeout=30
    )
    assert "Logged in using ChatGPT" in (login.stdout + login.stderr)
    assert (
        hashlib.sha256(executable.read_bytes()).hexdigest()
        == protocol["provider_executable"]["sha256"]
    )
    return {
        "experiment_id": protocol["experiment_id"],
        "status": "MECHANICAL_PREFLIGHT_PASS",
        "model_calls": 0,
        "formal_arm_runs": 0,
        "component_1_results_imported": False,
        "reused_component_file_hashes": reused,
        "new_seeds_disjoint": True,
        "complete_block_gate": "70_OF_72_AND_5_OF_6_PER_INSTANCE",
        "synthetic_budget_preflight": "PASS",
        "codex_cli_version": version,
        "codex_cli_login": "CHATGPT_AUTHENTICATED",
        "codex_cli_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "protocol_sha256": _sha256(HERE / "protocol.json"),
    }


def main() -> int:
    print(json.dumps(run(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
