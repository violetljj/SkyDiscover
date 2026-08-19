"""Frozen-contract tests for L10M-STRUCT-COMPONENT-1."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmarks/blindassist_last10m_struct_component_1"


def _load_component_module(alias: str, filename: str):
    spec = importlib.util.spec_from_file_location(alias, BENCHMARK / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


candidate_guard = _load_component_module(
    "l10m_struct_component_1_candidate_guard", "candidate_guard.py"
)
harness = _load_component_module("l10m_struct_component_1_harness", "harness.py")
analysis = _load_component_module("l10m_struct_component_1_analysis", "analysis.py")
progress = _load_component_module("l10m_struct_component_1_progress", "progress.py")
# preflight is a script-compatible module that imports its siblings by their
# short names. Resolve those names only during its isolated import, then remove
# them so the frozen two-arm tests can import their own modules without cache
# collisions.
sys.modules["candidate_guard"] = candidate_guard
sys.modules["harness"] = harness
preflight = _load_component_module("l10m_struct_component_1_preflight", "preflight.py")
for _name, _module in (("candidate_guard", candidate_guard), ("harness", harness)):
    if sys.modules.get(_name) is _module:
        del sys.modules[_name]

from skydiscover.config import load_config  # noqa: E402


def test_protocol_freezes_factor_matrix_estimands_and_fresh_gate():
    protocol = json.loads((BENCHMARK / "protocol.json").read_text(encoding="utf-8"))
    assert protocol["experiment_id"] == "L10M-STRUCT-COMPONENT-1"
    assert protocol["evidence_role"] == "CONSUMED_DEVELOPMENT_MECHANISM_SCREEN_ONLY"
    assert protocol["consumed_cohort"]["fresh_or_blind_claim_authority"] is False
    assert protocol["factor_matrix"] == {
        "raw_control": {"progress_memory": False, "move_proposals": False},
        "progress_only": {"progress_memory": True, "move_proposals": False},
        "moves_only": {"progress_memory": False, "move_proposals": True},
        "progress_moves": {"progress_memory": True, "move_proposals": True},
    }
    assert set(protocol["estimands"]) == {
        "progress_main",
        "moves_main",
        "interaction",
        "simple_arm_contrasts_for_fresh_admission",
    }
    assert protocol["fresh_admission_gate"]["effect"] == (
        "authorizes_separate_fresh_preregistration_only"
    )
    assert protocol["status"] == "EXECUTION_PROTOCOL_FROZEN"
    assert protocol["execution_blockers"] == []


def test_all_arms_share_one_initial_program_and_one_config():
    protocol = json.loads((BENCHMARK / "protocol.json").read_text(encoding="utf-8"))
    assert protocol["common_invariants"]["initial_program"] == ("BYTE_IDENTICAL_COMMON_SCAFFOLD")
    assert protocol["common_invariants"]["single_common_config_file"] is True
    config = load_config(BENCHMARK / "config.yaml")
    assert config.max_iterations == config.checkpoint_interval == 1
    assert config.search.type == "incumbent_only"
    assert config.search.num_context_programs == 0
    assert config.llm.models[0].name == protocol["model"]
    assert config.llm.retries == 0


def test_guard_admits_only_assigned_component_bodies():
    sources = {
        "raw_control": preflight.example_source(progress=False, moves=False),
        "progress_only": preflight.example_source(progress=True, moves=False),
        "moves_only": preflight.example_source(progress=False, moves=True),
        "progress_moves": preflight.example_source(progress=True, moves=True),
    }
    for arm, source in sources.items():
        candidate_guard.validate_source(source, arm)
    with pytest.raises(candidate_guard.CandidateRejected):
        candidate_guard.validate_source(sources["progress_moves"], "progress_only")
    with pytest.raises(candidate_guard.CandidateRejected):
        candidate_guard.validate_source(sources["progress_moves"], "moves_only")
    unsafe = sources["progress_moves"].replace(
        'observation["closing_risk"] >= 0.75', 'observation["closing_risk"] >= 0.95'
    )
    with pytest.raises(candidate_guard.CandidateRejected):
        candidate_guard.validate_source(unsafe, "progress_moves")


def test_progress_component_cannot_manufacture_moves_or_use_unbounded_memory():
    action_literal = preflight.PROGRESS_BODY.replace(
        "return action", 'return "FORWARD" if action is None else action'
    )
    source = preflight.replace_function(
        preflight.example_source(progress=False, moves=False),
        "progress_contract",
        action_literal,
    )
    with pytest.raises(candidate_guard.CandidateRejected):
        candidate_guard.validate_source(source, "progress_only")
    leaked_safety = preflight.PROGRESS_BODY.replace(
        'progress = float(observation["progress"])',
        'progress = float(observation["progress"]) + float(observation["closing_risk"])',
    )
    source = preflight.replace_function(
        preflight.example_source(progress=False, moves=False),
        "progress_contract",
        leaked_safety,
    )
    with pytest.raises(candidate_guard.CandidateRejected):
        candidate_guard.validate_source(source, "progress_only")
    bad_memory = preflight.PROGRESS_BODY.replace(
        'memory["last_move"] = action', 'memory["arbitrary_state"] = action'
    )
    source = preflight.replace_function(
        preflight.example_source(progress=False, moves=False),
        "progress_contract",
        bad_memory,
    )
    with pytest.raises(candidate_guard.CandidateRejected):
        candidate_guard.validate_source(source, "progress_only")


def test_synthetic_preflight_applies_identical_ceilings_to_four_arms():
    receipt = harness.synthetic_preflight()
    assert receipt["preflight"] == "PASS"
    assert receipt["arms"] == ["raw_control", "progress_only", "moves_only", "progress_moves"]
    assert len(receipt["arm_budget_receipts"]) == 4
    for arm_receipt in receipt["arm_budget_receipts"].values():
        assert arm_receipt["usage"]["generation_calls"] == 1
        assert arm_receipt["usage"]["evaluator_attempts"] == 1


def test_execution_manifest_binds_final_protocol_before_any_arm():
    harness._validate_execution_manifest()
    manifest = json.loads((BENCHMARK / "execution_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "EXECUTION_MANIFEST_FROZEN"
    assert manifest["formal_arm_runs_observed_before_freeze"] == 0
    receipt = json.loads(
        (BENCHMARK / "receipts/mechanical_preflight.json").read_text(encoding="utf-8")
    )
    assert receipt["status"] == "MECHANICAL_PREFLIGHT_PASS"
    assert receipt["formal_arm_runs"] == 0


def test_factorial_formulas_and_admission_are_instance_level():
    assert analysis.exact_sign_flip_greater([0.01] * 12, 0.005) == 1 / 4096
    assert analysis.exact_sign_flip_greater([0.005] * 12, 0.005) == 1.0
    assert analysis._leave_one_out_positive([0.01] * 12) is True
    assert analysis._leave_one_out_positive([0.0] * 12) is False


def test_progress_summary_is_read_only_and_counts_full_execution_graph(tmp_path: Path):
    result = progress.summarize(tmp_path)
    assert result["read_only"] is True
    assert result["units"] == {"terminal": 0, "total": 288, "percent": 0.0}
    assert result["status_counts"] == {"pending": 288}
