"""Focused frozen-contract tests for L10M-STRUCT-SEARCH-1."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmarks/blindassist_last10m_struct_search_1"
sys.path.insert(0, str(BENCHMARK))

import analysis  # noqa: E402
import candidate_guard  # noqa: E402
import harness  # noqa: E402

from skydiscover.config import load_config  # noqa: E402


def test_protocol_freezes_fresh_instance_searchability_endpoint():
    protocol = json.loads((BENCHMARK / "protocol.json").read_text(encoding="utf-8"))
    assert protocol["experiment_id"] == "L10M-STRUCT-SEARCH-1"
    assert protocol["status"] == "EXECUTION_PROTOCOL_FROZEN"
    assert protocol["instances"]["count"] == 12
    assert protocol["instances"]["generator_seed"] == "sealed_private_create_once"
    assert protocol["nested_replicates"]["count_per_instance"] == 1
    assert protocol["primary_endpoint"]["absolute_candidate_gate"] == {
        "mean_substantive_score_delta_strictly_greater_than": 0.005,
        "robust_safe_instances_equals": 12,
    }


def test_seed_language_exposes_contracts_without_diag_2_repair():
    source = (BENCHMARK / "initial_program.py").read_text(encoding="utf-8")
    candidate_guard.validate_source(source)
    for marker in candidate_guard.FORBIDDEN_LITERALS:
        assert marker not in source
    assert "return candidates[0] if candidates else None" in source


def test_candidate_guard_blocks_oracle_and_file_capabilities():
    source = (BENCHMARK / "initial_program.py").read_text(encoding="utf-8")
    with pytest.raises(candidate_guard.CandidateRejected):
        candidate_guard.validate_source(source + "\nimport os\n")
    with pytest.raises(candidate_guard.CandidateRejected):
        candidate_guard.validate_source(source + "\nopen('hidden.json')\n")
    with pytest.raises(candidate_guard.CandidateRejected):
        candidate_guard.validate_source(source.replace("candidates[0]", "failed_moves[0]"))


def test_arm_configs_have_equal_model_budget_and_iteration_count():
    configs = [
        load_config(BENCHMARK / "configs/naked_codex.yaml"),
        load_config(BENCHMARK / "configs/evox.yaml"),
        load_config(BENCHMARK / "configs/sky_evox.yaml"),
    ]
    assert {config.max_iterations for config in configs} == {6}
    assert {config.checkpoint_interval for config in configs} == {1}
    assert {config.llm.models[0].name for config in configs} == {"codex-cli/gpt-5.6-sol"}
    assert len({config.llm.models[0].codex_executable for config in configs}) == 1


def test_synthetic_preflight_applies_equal_ceilings():
    receipt = harness.synthetic_preflight()
    assert receipt["preflight"] == "PASS"
    assert receipt["arms"] == [
        "evox_structured",
        "naked_structured",
        "sky_evox_structured",
    ]
    for arm in receipt["arm_budget_receipts"].values():
        assert arm["usage"]["generation_calls"] == 6
        assert arm["usage"]["evaluator_attempts"] == 6
        assert arm["usage"]["total_tokens"] < 180000


def test_exact_sign_flip_uses_twelve_instances():
    assert analysis.exact_sign_flip_greater([0.01] * 12, 0.005) == 1 / 4096


def test_public_manifest_contains_hashes_but_no_seed_or_absolute_paths():
    manifest = json.loads((BENCHMARK / "cohort_manifest.json").read_text(encoding="utf-8"))
    assert manifest["private_seed_disclosed"] is False
    assert len(manifest["instances"]) == 12
    for record in manifest["instances"]:
        assert "seed" not in " ".join(record)
        assert not Path(record["dev_path"]).is_absolute()
        assert not Path(record["hidden_path"]).is_absolute()


def test_mechanical_preflight_passed_before_execution_manifest_freeze():
    receipt = json.loads(
        (BENCHMARK / "receipts/mechanical_preflight_v2.json").read_text(encoding="utf-8")
    )
    assert receipt["status"] == "MECHANICAL_PREFLIGHT_PASS"
    assert receipt["sealed_files_verified"] == 24
    assert receipt["initial_program_sha256"] != receipt["diag_2_oracle_sha256"]
