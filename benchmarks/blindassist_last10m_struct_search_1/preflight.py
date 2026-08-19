"""Mechanical preflight for the frozen structured-search experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import candidate_guard  # noqa: E402

from skydiscover.config import load_config  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def run(cohort_root: Path) -> dict[str, object]:
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    manifest = json.loads((HERE / "cohort_manifest.json").read_text(encoding="utf-8"))
    assert protocol["status"] == "EXECUTION_PROTOCOL_FROZEN"
    assert manifest["treatment_runs_observed"] == 0
    assert manifest["private_seed_disclosed"] is False
    assert len(manifest["instances"]) == protocol["instances"]["count"] == 12
    candidate_guard.validate_path(HERE / "initial_program.py")
    oracle = ROOT / "benchmarks/blindassist_last10m_diag_2/policies/structured_temporal_policy.py"
    assert sha256(HERE / "initial_program.py") != sha256(oracle)
    visible_paths = [HERE / "initial_program.py", *(HERE / "configs").glob("*.yaml")]
    visible = "\n".join(path.read_text(encoding="utf-8") for path in visible_paths)
    for literal in candidate_guard.FORBIDDEN_LITERALS:
        assert literal not in visible
    malicious = (HERE / "initial_program.py").read_text(encoding="utf-8") + "\nimport os\n"
    try:
        candidate_guard.validate_source(malicious)
    except candidate_guard.CandidateRejected:
        pass
    else:
        raise AssertionError("candidate guard admitted an import")
    for record in manifest["instances"]:
        for split in ("dev", "hidden"):
            relative = Path(record[f"{split}_path"])
            assert not relative.is_absolute() and ".." not in relative.parts
            path = cohort_root / relative
            assert path.is_file() and sha256(path) == record[f"{split}_sha256"]
    configs = {
        "naked": load_config(HERE / "configs/naked_codex.yaml"),
        "evox": load_config(HERE / "configs/evox.yaml"),
        "sky": load_config(HERE / "configs/sky_evox.yaml"),
    }
    for config in configs.values():
        assert config.max_iterations == 6
        assert config.checkpoint_interval == 1
        assert config.llm.models[0].name == protocol["model"]
    assert configs["evox"].search.type == configs["sky"].search.type == "evox"
    executable = Path(protocol["provider_executable"]["path"])
    version = subprocess.run(
        [str(executable), "--version"], check=True, capture_output=True, text=True, timeout=30
    ).stdout.strip()
    if not version or "unknown" in version.lower():
        raise RuntimeError(f"unusable Codex CLI version: {version!r}")
    assert version == protocol["provider_executable"]["required_version"]
    return {
        "experiment_id": protocol["experiment_id"],
        "status": "MECHANICAL_PREFLIGHT_PASS",
        "instance_count": len(manifest["instances"]),
        "sealed_files_verified": len(manifest["instances"]) * 2,
        "candidate_guard": "PASS",
        "oracle_seed_excluded": True,
        "equal_generation_call_ceiling": protocol["search_ceilings_per_arm_instance_replicate"][
            "generation_calls"
        ],
        "checkpoint_interval_iterations": 1,
        "codex_cli_version": version,
        "codex_cli_sha256": sha256(executable),
        "protocol_sha256": sha256(HERE / "protocol.json"),
        "cohort_manifest_sha256": sha256(HERE / "cohort_manifest.json"),
        "initial_program_sha256": sha256(HERE / "initial_program.py"),
        "diag_2_oracle_sha256": sha256(oracle),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.cohort_root.resolve())
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
