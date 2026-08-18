"""Contract checks for the L10M-COMP-1 preregistration."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = ROOT / "benchmarks" / "blindassist_last10m_comp_1" / "protocol.json"
BUDGET_BASIS_PATH = ROOT / "benchmarks" / "blindassist_last10m_comp_1" / "budget_basis.json"
BENCHMARK = ROOT / "benchmarks" / "blindassist_last10m_comp_1"

sys.path.insert(0, str(BENCHMARK))
import harness  # noqa: E402
import generate_hidden_v4  # noqa: E402


def test_comparison_protocol_freezes_equal_three_arm_budgets():
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    assert protocol["experiment_id"] == "L10M-COMP-1"
    assert protocol["status"] == "EXECUTION_PROTOCOL_FROZEN"
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


def test_hidden_v4_is_frozen_and_never_exposed_during_search():
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    hidden = protocol["hidden_adjudication"]
    assert hidden["split"] == "hidden-v4"
    assert hidden["materialized"] is True
    assert hidden["sha256"] == harness._sha256(
        BENCHMARK / "evaluator" / "scenarios" / "hidden_v4.json"
    )
    assert hidden["generator_seed"] == 40419
    assert hidden["episode_count"] == 8
    assert hidden["attempts_per_arm_replicate"] == 10
    assert hidden["results_returned_to_search"] is False
    assert protocol["execution_blockers"] == []


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


def test_synthetic_preflight_uses_one_ledger_contract_for_all_arms():
    receipt = harness.synthetic_preflight()
    assert receipt["preflight"] == "PASS"
    assert receipt["hidden_materialized"] is True
    arms = receipt["arm_receipts"]
    assert set(arms) == set(json.loads(PROTOCOL_PATH.read_text())["arms"])
    for arm_receipt in arms.values():
        assert arm_receipt["usage"]["generation_calls"] == 10
        assert arm_receipt["usage"]["total_tokens"] < 300000
        assert arm_receipt["stop_reason"] is None
    assert arms["skydiscover_best_of_n_3"]["usage"]["evaluator_attempts"] == 10
    assert arms["naked_codex_incumbent_only"]["usage"]["evaluator_attempts"] == 10
    assert arms["evox"]["usage"]["evaluator_attempts"] == 7


def test_execution_manifest_matches_every_frozen_file():
    harness._validate_execution_manifest()


def test_hidden_v4_generator_reproduces_frozen_split():
    frozen = json.loads(
        (BENCHMARK / "evaluator" / "scenarios" / "hidden_v4.json").read_text(encoding="utf-8")
    )
    assert generate_hidden_v4.build_hidden_v4() == frozen


def test_sealed_adjudicator_replays_only_the_frozen_baseline():
    evaluator = harness._load_oracle3_with_hidden_v4()
    baseline = (ROOT / "benchmarks" / "blindassist_last10m_v3" / "initial_program.py").read_text(
        encoding="utf-8"
    )
    result = harness._evaluate_hidden_candidate(evaluator, baseline)
    assert result["status"] == "success"
    assert result["combined_score"] == 0.894375
    assert result["metrics"]["validity"] == 1.0
    assert result["metrics"]["task_success"] == 1.0
    assert result["metrics"]["behavioral_improvement_detected"] == 0.0


def test_arm_configs_share_model_prompt_and_harness_rules():
    configs = {arm: harness.load_config(path) for arm, path in harness.ARM_CONFIGS.items()}
    prompts = {config.context_builder.system_message for config in configs.values()}
    assert len(prompts) == 1
    for config in configs.values():
        assert config.llm.models[0].name == "codex-cli/gpt-5.6-sol"
        assert config.llm.reasoning_effort == "medium"
        assert config.llm.retries == 1
        assert config.evaluator.max_retries == 0
        assert config.max_iterations == 10
        assert config.max_parallel_iterations == 1
    assert configs["evox"].search.share_llm is True
    assert configs["naked_codex_incumbent_only"].search.num_context_programs == 0
