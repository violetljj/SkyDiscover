"""Mechanical preflight for L10M-STRUCT-COMPONENT-1; performs no model call."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import candidate_guard  # noqa: E402
import harness  # noqa: E402

from skydiscover.config import load_config  # noqa: E402

PROGRESS_BODY = '''def progress_contract(observation, memory, candidates):
    """Use bounded progress memory to reject a repeated non-progressing candidate."""
    progress = float(observation["progress"])
    previous_progress = memory.get("last_move_progress")
    failed = list(memory.get("failed_moves", []))
    previous_move = memory.get("last_move")
    if previous_progress is None or progress > float(previous_progress) + 1e-9:
        failed = []
    elif previous_move is not None and previous_move not in failed:
        failed.append(previous_move)
    action = next((candidate for candidate in candidates if candidate not in failed), None)
    memory["last_move_progress"] = progress
    memory["failed_moves"] = failed
    memory["last_move"] = action
    return action
'''

MOVES_BODY = '''def propose_moves(observation):
    """Generate ordered, duplicate-free moves from current observable geometry."""
    bearing = float(observation["target_bearing"])
    candidates = []
    if bearing < -12.0 and observation["corridor_left"]:
        candidates.append("VEER_LEFT")
    if bearing > 12.0 and observation["corridor_right"]:
        candidates.append("VEER_RIGHT")
    if observation["corridor_center"]:
        candidates.append("FORWARD")
    if observation["corridor_left"]:
        candidates.append("VEER_LEFT")
    if observation["corridor_right"]:
        candidates.append("VEER_RIGHT")
    return list(dict.fromkeys(candidates))
'''


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def replace_function(source: str, name: str, replacement: str) -> str:
    tree = ast.parse(source)
    function = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name
    )
    lines = source.splitlines(keepends=True)
    return (
        "".join(lines[: function.lineno - 1]) + replacement + "".join(lines[function.end_lineno :])
    )


def example_source(*, progress: bool, moves: bool) -> str:
    source = (HERE / "initial_program.py").read_text(encoding="utf-8").replace("\r\n", "\n")
    source = source.replace("# CANDIDATE-TAG: initial", "# CANDIDATE-TAG: generated", 1)
    if progress:
        source = replace_function(source, "progress_contract", PROGRESS_BODY)
    if moves:
        source = replace_function(source, "propose_moves", MOVES_BODY)
    return source


def run() -> dict[str, object]:
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    assert protocol["status"] in {
        "DESIGN_FROZEN_PENDING_MECHANICAL_PREFLIGHT",
        "MECHANICAL_PREFLIGHT_PASSED_PENDING_EXECUTION_MANIFEST",
        "EXECUTION_PROTOCOL_FROZEN",
    }
    cohort_path = ROOT / protocol["consumed_cohort"]["manifest_path"]
    assert sha256(cohort_path) == protocol["consumed_cohort"]["manifest_sha256"]
    cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
    assert len(cohort["instances"]) == protocol["consumed_cohort"]["instance_count"] == 12
    verified = 0
    for record in cohort["instances"]:
        for split in ("dev", "hidden"):
            scenario_path = ROOT / record[f"{split}_path"]
            assert scenario_path.is_file() and sha256(scenario_path) == record[f"{split}_sha256"]
            verified += 1

    examples = {
        "raw_control": example_source(progress=False, moves=False),
        "progress_only": example_source(progress=True, moves=False),
        "moves_only": example_source(progress=False, moves=True),
        "progress_moves": example_source(progress=True, moves=True),
    }
    for arm, source in examples.items():
        candidate_guard.validate_source(source, arm)
    malicious = examples["progress_moves"].replace(
        'observation["safety_confidence"] < 0.60',
        'observation["safety_confidence"] < 0.10',
    )
    try:
        candidate_guard.validate_source(malicious, "progress_moves")
    except candidate_guard.CandidateRejected:
        pass
    else:
        raise AssertionError("candidate guard admitted a safety-contract mutation")

    config = load_config(HERE / "config.yaml")
    assert config.max_iterations == config.checkpoint_interval == 1
    assert config.search.type == "incumbent_only"
    assert config.search.num_context_programs == 0
    assert config.evaluator.inject_evaluator_context is False
    assert config.llm.models[0].name == protocol["model"]
    assert config.llm.retries == 0
    synthetic = harness.synthetic_preflight()
    assert synthetic["arms"] == protocol["arms"]

    executable = Path(protocol["provider_executable"]["path"])
    version = subprocess.run(
        [str(executable), "--version"], check=True, capture_output=True, text=True, timeout=30
    ).stdout.strip()
    if not version or "unknown" in version.lower():
        raise RuntimeError(f"unusable Codex CLI version: {version!r}")
    assert version == protocol["provider_executable"]["required_version"]
    login = subprocess.run(
        [str(executable), "login", "status"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert "Logged in using ChatGPT" in (login.stdout + login.stderr)
    executable_sha256 = hashlib.sha256(executable.read_bytes()).hexdigest()
    assert executable_sha256 == protocol["provider_executable"]["sha256"]
    return {
        "experiment_id": protocol["experiment_id"],
        "status": "MECHANICAL_PREFLIGHT_PASS",
        "model_calls": 0,
        "formal_arm_runs": 0,
        "consumed_scenario_files_verified": verified,
        "four_arm_guard_examples": "PASS",
        "locked_safety_mutation_rejected": True,
        "synthetic_budget_preflight": "PASS",
        "codex_cli_version": version,
        "codex_cli_login": "CHATGPT_AUTHENTICATED",
        "codex_cli_sha256": executable_sha256,
        "protocol_sha256": sha256(HERE / "protocol.json"),
        "cohort_manifest_sha256": sha256(cohort_path),
        "initial_program_sha256": sha256(HERE / "initial_program.py"),
    }


def main() -> int:
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
