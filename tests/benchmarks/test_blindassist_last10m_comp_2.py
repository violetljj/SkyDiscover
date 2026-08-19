"""Contract checks for the L10M-COMP-2 preregistration."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmarks" / "blindassist_last10m_comp_2"
PROTOCOL_PATH = BENCHMARK / "protocol.json"

sys.path.insert(0, str(BENCHMARK))
import analysis  # noqa: E402
import generate_cohort  # noqa: E402
import harness  # noqa: E402

from skydiscover.config import load_config  # noqa: E402
from skydiscover.search.base_database import Program  # noqa: E402
from skydiscover.search.registry import load_database_from_file  # noqa: E402


def test_protocol_uses_fresh_instances_and_nested_replicates():
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    assert protocol["experiment_id"] == "L10M-COMP-2"
    assert protocol["status"] == "EXECUTION_PROTOCOL_FROZEN"
    assert protocol["experimental_unit"] == "fresh_instance"
    assert protocol["instances"]["count"] == 12
    assert protocol["nested_replicates"] == {
        "count_per_instance": 2,
        "local_seeds": [411, 733],
        "provider_sampling_seed_claimed": False,
    }
    assert protocol["primary_analysis"]["fixed_sequence"] == [
        "G1_DELTA_E",
        "G2_DELTA_H",
    ]


def test_headroom_rule_is_pre_treatment_and_candidate_independent():
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    headroom = protocol["instances"]["headroom_rule"]
    assert headroom["information_time"] == "pre_treatment_frozen_initial_policy_only"
    assert headroom["development_initial_score_strictly_below"] == 0.91
    assert headroom["hidden_initial_score_strictly_below"] == 0.91
    cohort, audit = generate_cohort.build_cohort()
    assert len(cohort) == 12
    assert len(audit["candidate_audit"]) <= protocol["instances"]["candidate_pool_limit"]
    for instance in cohort:
        for split in ("dev_initial", "hidden_initial"):
            result = instance[split]
            assert result["validity"] == 1.0
            assert result["task_success"] == 1.0
            assert result["safe_termination"] == 1.0
            assert result["combined_score"] < 0.91


def test_evox_arms_differ_only_by_initial_database_file():
    standard = load_config(BENCHMARK / "configs" / "evox.yaml")
    hybrid = load_config(BENCHMARK / "configs" / "sky_evox.yaml")
    assert standard.llm == hybrid.llm
    assert standard.context_builder == hybrid.context_builder
    assert standard.evaluator == hybrid.evaluator
    assert standard.max_iterations == hybrid.max_iterations == 10
    assert standard.search.type == hybrid.search.type == "evox"
    assert standard.search.share_llm is hybrid.search.share_llm is True
    assert standard.search.num_context_programs == hybrid.search.num_context_programs == 2
    assert standard.search.database.auto_generate_variation_operators is True
    assert hybrid.search.database.auto_generate_variation_operators is True
    assert standard.search.database.database_file_path.endswith("initial_search_strategy.py")
    assert hybrid.search.database.database_file_path.endswith("sky_best_of_three_initial.py")


def test_sky_evox_initial_strategy_reuses_best_parent_three_times():
    database_class, _ = load_database_from_file(
        str(BENCHMARK / "search_strategies" / "sky_best_of_three_initial.py")
    )
    config = load_config(BENCHMARK / "configs" / "sky_evox.yaml")
    database = database_class("test", config.search.database)
    baseline = Program(id="baseline", solution="", metrics={"combined_score": 0.5})
    database.add(baseline, iteration=0)
    parent, _ = database.sample(2)
    assert parent[""].id == "baseline"
    for iteration, score in enumerate((0.6, 0.7, 0.8), start=1):
        database.add(
            Program(
                id=f"candidate-{iteration}",
                solution="",
                metrics={"combined_score": score},
                iteration_found=iteration,
            ),
            iteration=iteration,
        )
        if iteration < 3:
            parent, _ = database.sample(2)
            assert parent[""].id == "baseline"
    parent, _ = database.sample(2)
    assert parent[""].id == "candidate-3"


def test_exact_sign_flip_uses_instance_count_not_nested_run_count():
    effects = [0.01] * 12
    assert analysis.exact_sign_flip_greater(effects, 0.005) == 1 / 4096
    assert analysis.exact_sign_flip_greater([0.005] * 12, 0.005) == 1.0


def test_common_harness_preflight_applies_equal_budget_ceilings():
    receipt = harness.synthetic_preflight()
    assert receipt["preflight"] == "PASS"
    assert receipt["arms"] == ["evox", "naked_codex", "sky_evox"]
    for arm_receipt in receipt["arm_budget_receipts"].values():
        assert arm_receipt["usage"]["generation_calls"] == 10
        assert arm_receipt["usage"]["evaluator_attempts"] == 10
        assert arm_receipt["usage"]["total_tokens"] < 300000


def test_frozen_execution_manifest_and_cohort_files_match():
    harness._validate_execution_manifest()
    cohort = json.loads((BENCHMARK / "cohort_manifest.json").read_text(encoding="utf-8"))
    assert cohort["treatment_runs_observed"] == 0
    assert len(cohort["instances"]) == 12
    for record in cohort["instances"]:
        assert harness._scenario_path(record, "dev").is_file()
        assert harness._scenario_path(record, "hidden").is_file()


def test_completed_result_preserves_fixed_sequence_gatekeeping():
    result_path = BENCHMARK / "receipts" / "execution" / "FINAL_RESULT.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["instance_count"] == 12
    assert result["G1_DELTA_E"]["established"] is False
    assert result["G1_DELTA_E"]["observed_mean"] < 0.005
    assert result["G2_DELTA_H"]["tested"] is False
    assert result["G2_DELTA_H"]["one_sided_exact_p"] is None
    assert result["architecture_decision"] == (
        "EVOX_INCREMENTAL_VALUE_NOT_ESTABLISHED_G2_NOT_TESTED"
    )
