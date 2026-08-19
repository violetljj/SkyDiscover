"""Protocol-hardening tests for L10M-STRUCT-COMPONENT-2."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmarks/blindassist_last10m_struct_component_2"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, BENCHMARK / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


analysis = _load("l10m_struct_component_2_test_analysis", "analysis.py")
execute = _load("l10m_struct_component_2_test_execute", "execute.py")
progress = _load("l10m_struct_component_2_test_progress", "progress.py")
harness = _load("l10m_struct_component_2_test_harness", "harness.py")


def _write_block(run_root: Path, instance: str, seed: int, failed_arm: str | None = None):
    arms = ["raw_control", "progress_only", "moves_only", "progress_moves"]
    block = run_root / "units" / instance / f"seed_{seed}"
    rows = {}
    for arm in arms:
        unit = block / arm
        unit.mkdir(parents=True, exist_ok=True)
        status = "ARM_FAILED_ITT" if arm == failed_arm else "COMPLETED"
        (unit / "unit_started.json").write_text("{}", encoding="utf-8")
        (unit / "search_receipt.json").write_text(json.dumps({"status": status}), encoding="utf-8")
        value = (
            0.0
            if arm == failed_arm
            else {
                "raw_control": 0.01,
                "progress_only": 0.02,
                "moves_only": 0.03,
                "progress_moves": 0.05,
            }[arm]
        )
        rows[arm] = {
            "search_status": status,
            "validation": {
                "primary_substantive_value": value,
                "robust_safe": arm != failed_arm,
            },
        }
    (block / "consumed_validation.json").write_text(json.dumps({"arms": rows}), encoding="utf-8")


def _full_run(tmp_path: Path) -> Path:
    protocol = json.loads((BENCHMARK / "protocol.json").read_text(encoding="utf-8"))
    cohort = json.loads(
        (ROOT / "benchmarks/blindassist_last10m_comp_2/cohort_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    for record in cohort["instances"]:
        for seed in protocol["direct_replicates"]["local_seeds"]:
            _write_block(tmp_path, record["instance_id"], seed)
    return tmp_path


def test_protocol_keeps_exact_four_arms_and_original_three_factorial_questions():
    protocol = json.loads((BENCHMARK / "protocol.json").read_text(encoding="utf-8"))
    assert protocol["experiment_id"] == "L10M-STRUCT-COMPONENT-2"
    assert protocol["arms"] == ["raw_control", "progress_only", "moves_only", "progress_moves"]
    assert set(protocol["estimands"]) == {
        "progress_main",
        "moves_main",
        "interaction",
        "simple_arm_contrasts_for_fresh_admission",
    }
    assert protocol["component_1_outcomes_in_formal_estimand"] is False
    assert set(protocol["direct_replicates"]["local_seeds"]).isdisjoint(range(1701, 1707))


def test_execution_manifest_binds_new_engineering_and_unchanged_mechanism_files():
    harness.base._validate_execution_manifest()
    manifest = json.loads((BENCHMARK / "execution_manifest.json").read_text(encoding="utf-8"))
    assert manifest["formal_arm_runs_observed_before_freeze"] == 0
    assert manifest["component_1_results_imported"] is False


def test_two_infrastructure_blocks_across_instances_are_complete_case_evaluable(tmp_path: Path):
    run_root = _full_run(tmp_path)
    for instance, seed in (("instance_01", 1801), ("instance_02", 1801)):
        block = run_root / "units" / instance / f"seed_{seed}"
        for path in block.rglob("*"):
            if path.is_file():
                path.unlink()
        for path in sorted(block.rglob("*"), reverse=True):
            if path.is_dir():
                path.rmdir()
        block.rmdir()
    result = analysis.analyze(run_root)
    assert result["status"] == "EVALUABLE"
    assert result["complete_blocks"] == 70
    assert result["complete_seeds_by_instance"]["instance_01"] == 5
    assert result["complete_seeds_by_instance"]["instance_02"] == 5
    assert len(result["excluded_infrastructure_blocks"]) == 2


def test_two_missing_blocks_in_one_instance_fail_five_of_six_gate(tmp_path: Path):
    run_root = _full_run(tmp_path)
    for seed in (1801, 1802):
        block = run_root / "units" / "instance_01" / f"seed_{seed}"
        for file in block.rglob("*"):
            if file.is_file():
                file.unlink()
    result = analysis.analyze(run_root)
    assert result["status"] == "NOT_EVALUABLE"
    assert "instance_01" in result["reason"]
    assert result["factorial_estimands"] is None


def test_terminal_arm_failure_is_retained_as_zero_not_deleted(tmp_path: Path):
    run_root = _full_run(tmp_path)
    _write_block(run_root, "instance_01", 1801, failed_arm="progress_only")
    result = analysis.analyze(run_root)
    assert result["status"] == "EVALUABLE"
    assert result["complete_blocks"] == 72
    assert result["instance_results"][0]["selected"]["progress_only"]["primary_value"] == 0.02


def test_scheduler_pairs_never_share_an_instance():
    blocks = execute._blocks()
    assert len(blocks) == 72
    for index in range(0, len(blocks), 2):
        assert len({instance for instance, _ in blocks[index : index + 2]}) == len(
            blocks[index : index + 2]
        )


def test_started_validation_without_receipt_is_never_retried(tmp_path: Path):
    _write_block(tmp_path, "instance_01", 1801)
    block = tmp_path / "units" / "instance_01" / "seed_1801"
    (block / "consumed_validation.json").unlink()
    (block / "validation_started.json").write_text("{}", encoding="utf-8")
    assert (
        execute._block_state(
            tmp_path / "units",
            "instance_01",
            1801,
            ["raw_control", "progress_only", "moves_only", "progress_moves"],
        )
        == "validation_in_doubt"
    )


def test_progress_reports_blocks_and_units_without_mutation(tmp_path: Path):
    before = list(tmp_path.rglob("*"))
    result = progress.summarize(tmp_path)
    after = list(tmp_path.rglob("*"))
    assert before == after
    assert result["units"] == {"terminal": 0, "total": 288, "percent": 0.0}
    assert result["blocks"]["total"] == 72
