"""Focused frozen-contract tests for L10M-STRUCT-DIRECT-1."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmarks/blindassist_last10m_structured_direct_1"
sys.path.insert(0, str(BENCHMARK))

import analysis  # noqa: E402
import candidate_guard  # noqa: E402
import harness  # noqa: E402

from skydiscover.config import load_config  # noqa: E402


def test_protocol_freezes_two_arm_fresh_start_contrast():
    protocol = json.loads((BENCHMARK / "protocol.json").read_text(encoding="utf-8"))
    assert protocol["experiment_id"] == "L10M-STRUCT-DIRECT-1"
    assert protocol["status"] == "EXECUTION_PROTOCOL_FROZEN"
    assert protocol["arms"] == ["raw_direct", "structured_direct"]
    assert protocol["instances"]["count"] == 12
    assert protocol["direct_replicates"]["count_per_arm_instance"] == 6
    assert protocol["generation_ceilings_per_arm_instance_replicate"]["generation_calls"] == 1


def test_both_interfaces_are_guarded_and_oracle_markers_rejected():
    raw = ROOT / "benchmarks/blindassist_last10m_v3/initial_program.py"
    structured = BENCHMARK / "structured_initial_program.py"
    candidate_guard.validate_path(raw, "raw_direct")
    candidate_guard.validate_path(structured, "structured_direct")
    with pytest.raises(candidate_guard.CandidateRejected):
        candidate_guard.validate_source(
            raw.read_text(encoding="utf-8") + "\nimport os\n", "raw_direct"
        )
    with pytest.raises(candidate_guard.CandidateRejected):
        candidate_guard.validate_source(
            structured.read_text(encoding="utf-8") + "\nopen('hidden.json')\n", "structured_direct"
        )


def test_arm_configs_are_equal_fresh_start_one_call_configs():
    configs = [
        load_config(BENCHMARK / "configs" / f"{arm}.yaml")
        for arm in ("raw_direct", "structured_direct")
    ]
    assert {config.max_iterations for config in configs} == {1}
    assert {config.checkpoint_interval for config in configs} == {1}
    assert {config.search.type for config in configs} == {"incumbent_only"}
    assert {config.search.num_context_programs for config in configs} == {0}
    assert {config.llm.models[0].name for config in configs} == {"codex-cli/gpt-5.6-sol"}
    assert {config.llm.retries for config in configs} == {0}


def test_synthetic_preflight_applies_one_call_ceilings():
    receipt = harness.synthetic_preflight()
    assert receipt["preflight"] == "PASS"
    assert receipt["arms"] == ["raw_direct", "structured_direct"]
    for arm in receipt["arm_budget_receipts"].values():
        assert arm["usage"]["generation_calls"] == 1
        assert arm["usage"]["evaluator_attempts"] == 1


def test_exact_sign_flip_uses_twelve_instances():
    assert analysis.exact_sign_flip_greater([0.01] * 12, 0.005) == 1 / 4096


def test_public_manifest_has_only_relative_paths_and_no_private_seed():
    manifest = json.loads((BENCHMARK / "cohort_manifest.json").read_text(encoding="utf-8"))
    assert manifest["private_seed_disclosed"] is False
    assert len(manifest["instances"]) == 12
    for record in manifest["instances"]:
        assert not Path(record["dev_path"]).is_absolute()
        assert not Path(record["hidden_path"]).is_absolute()


def test_mechanical_preflight_passed_before_execution_freeze():
    receipt = json.loads(
        (BENCHMARK / "receipts/mechanical_preflight.json").read_text(encoding="utf-8")
    )
    assert receipt["status"] == "MECHANICAL_PREFLIGHT_PASS"
    assert receipt["sealed_files_verified"] == 24
    assert receipt["codex_cli_login"] == "CHATGPT_AUTHENTICATED"


def test_formal_result_does_not_establish_structured_increment():
    result = json.loads(
        (BENCHMARK / "receipts/execution/FINAL_RESULT.json").read_text(encoding="utf-8")
    )
    assert result["STRUCTURED_DIRECT_INCREMENT"]["established"] is False
    assert result["STRUCTURED_DIRECT_INCREMENT"]["observed_mean"] == pytest.approx(1 / 600)
    assert result["STRUCTURED_DIRECT_INCREMENT"]["one_sided_exact_p"] == 1.0
    assert (
        result["architecture_decision"]
        == "STRUCTURED_DIRECT_VALUE_NOT_ESTABLISHED_SAFETY_GATE_FAILED"
    )


def test_execution_audit_preserves_launcher_incident_without_override():
    audit = json.loads(
        (BENCHMARK / "receipts/execution/EXECUTION_AUDIT.json").read_text(encoding="utf-8")
    )
    assert audit["formal_arm_statuses"] == {"ARM_FAILED_ITT": 6, "COMPLETED": 138}
    assert audit["search_receipts"] == 144
    assert audit["candidate_manifests"] == 144
    assert audit["hidden_adjudication_receipts"] == 72
    assert audit["primary_override_authority"] is False
    assert audit["launcher_incident"]["affected_units"] == 6
