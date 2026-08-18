"""Contract checks for the L10M-COMP-1 preregistration."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = ROOT / "benchmarks" / "blindassist_last10m_comp_1" / "protocol.json"
BUDGET_BASIS_PATH = ROOT / "benchmarks" / "blindassist_last10m_comp_1" / "budget_basis.json"


def test_comparison_protocol_freezes_equal_three_arm_budgets():
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    assert protocol["experiment_id"] == "L10M-COMP-1"
    assert protocol["status"] == "MECHANICAL_PROTOCOL_FROZEN_PENDING_HIDDEN_V4"
    assert protocol["evaluator_semantics"] == "UNCHANGED_ORACLE_3"
    assert protocol["initial_program"] == "BYTE_IDENTICAL_ORACLE_3_BASELINE"
    assert len(protocol["arms"]) == 3
    assert protocol["replicates"]["count"] == 3
    assert protocol["replicates"]["local_seeds"] == [101, 202, 303]

    ceilings = protocol["search_ceilings_per_arm_replicate"]
    assert ceilings == {
        "generation_calls": 10,
        "dev_evaluator_attempts": 10,
        "total_tokens_input_plus_output": 300000,
        "provider_retries_per_failed_generation": 1,
    }


def test_hidden_v4_is_not_materialized_or_exposed_during_search():
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    hidden = protocol["hidden_adjudication"]
    assert hidden["split"] == "hidden-v4"
    assert hidden["materialized"] is False
    assert hidden["attempts_per_arm_replicate"] == 10
    assert hidden["results_returned_to_search"] is False
    assert set(protocol["execution_blockers"]) == {
        "common_budget_accounting_harness_preflight",
        "fresh_hidden_v4_materialization_and_hash_freeze",
    }


def test_anytime_auc_is_absolute_and_attempt_normalized():
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    auc = protocol["behavioral_anytime_auc"]
    assert auc["y"] == "best_so_far_hidden_substantive_score_delta"
    assert auc["x"] == "hidden_adjudication_attempt_1_through_10"
    assert auc["invalid_or_missing_value"] == 0.0
    assert auc["divide_area_by"] == 10
    assert auc["normalize_by_best_arm"] is False


def test_token_ceiling_is_bound_to_recorded_oracle_3_usage():
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    basis = json.loads(BUDGET_BASIS_PATH.read_text(encoding="utf-8"))
    calls = basis["generation_calls"]
    observed_total = sum(call["input_tokens"] + call["output_tokens"] for call in calls)
    ceiling = protocol["search_ceilings_per_arm_replicate"]["total_tokens_input_plus_output"]
    assert len(calls) == 10
    assert observed_total == basis["totals"]["input_plus_output_tokens"] == 291255
    assert basis["selected_ceiling"] == ceiling == 300000
    assert observed_total < ceiling
