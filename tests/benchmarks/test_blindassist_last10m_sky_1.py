"""Contract checks for the L10M-SKY-1 direct search-value trial."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmarks" / "blindassist_last10m_sky_1"
PROTOCOL_PATH = BENCHMARK / "protocol.json"

sys.path.insert(0, str(BENCHMARK))
import analysis  # noqa: E402
import closeout  # noqa: E402
import generate_cohort  # noqa: E402
import harness  # noqa: E402

from skydiscover.config import load_config  # noqa: E402
from skydiscover.search.base_database import Program  # noqa: E402
from skydiscover.search.best_of_n.database import BestOfNDatabase  # noqa: E402


def test_protocol_is_a_two_arm_fresh_instance_trial():
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    assert protocol["experiment_id"] == "L10M-SKY-1"
    assert protocol["status"] in {
        "DESIGN_FROZEN_PENDING_FRESH_COHORT",
        "FRESH_COHORT_FROZEN_PENDING_EXECUTION_MANIFEST",
        "EXECUTION_PROTOCOL_FROZEN",
    }
    assert protocol["experimental_unit"] == "fresh_instance"
    assert protocol["arms"] == ["naked_codex", "sky_search"]
    assert protocol["instances"]["count"] == 12
    assert protocol["nested_replicates"]["count_per_instance"] == 2
    assert protocol["nested_replicates"]["provider_sampling_seed_claimed"] is False
    assert protocol["primary_analysis"]["minimum_meaningful_effect"] == 0.005


def test_headroom_rule_is_pre_treatment_and_candidate_independent():
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    headroom = protocol["instances"]["headroom_rule"]
    assert headroom["information_time"] == "pre_treatment_frozen_initial_policy_only"
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


def test_arms_share_model_prompt_and_ceilings_but_route_search_differently():
    naked = load_config(BENCHMARK / "configs" / "naked_codex.yaml")
    sky = load_config(BENCHMARK / "configs" / "sky_search.yaml")
    assert naked.llm == sky.llm
    assert naked.context_builder.system_message == sky.context_builder.system_message
    assert naked.max_iterations == sky.max_iterations == 10
    assert naked.max_solution_length == sky.max_solution_length
    assert naked.search.type == "incumbent_only"
    assert naked.search.num_context_programs == 0
    assert naked.evaluator.inject_evaluator_context is False
    assert sky.search.type == "best_of_n"
    assert sky.search.database.best_of_n == 3
    assert sky.search.num_context_programs == 2
    assert sky.evaluator.inject_evaluator_context is True


def test_sky_reuses_parent_for_three_candidate_additions():
    config = load_config(BENCHMARK / "configs" / "sky_search.yaml")
    database = BestOfNDatabase("test", config.search.database)
    baseline = Program(id="baseline", solution="", metrics={"combined_score": 0.5})
    database.add(baseline, iteration=0)
    for iteration, score in enumerate((0.6, 0.7, 0.8), start=1):
        parent, _ = database.sample(2)
        assert parent.id == "baseline"
        database.add(
            Program(
                id=f"candidate-{iteration}",
                solution="",
                metrics={"combined_score": score},
                iteration_found=iteration,
            ),
            iteration=iteration,
        )
    parent, _ = database.sample(2)
    assert parent.id == "candidate-3"


def test_exact_sign_flip_uses_instance_count_not_nested_run_count():
    effects = [0.01] * 12
    assert analysis.exact_sign_flip_greater(effects, 0.005) == 1 / 4096
    assert analysis.exact_sign_flip_greater([0.005] * 12, 0.005) == 1.0


def test_common_harness_preflight_applies_equal_budget_ceilings():
    receipt = harness.synthetic_preflight()
    assert receipt["preflight"] == "PASS"
    assert receipt["arms"] == ["naked_codex", "sky_search"]
    for arm_receipt in receipt["arm_budget_receipts"].values():
        assert arm_receipt["usage"]["generation_calls"] == 10
        assert arm_receipt["usage"]["evaluator_attempts"] == 10
        assert arm_receipt["usage"]["total_tokens"] < 300000


def test_frozen_execution_manifest_and_cohort_files_match_when_authorized():
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    if protocol["status"] != "EXECUTION_PROTOCOL_FROZEN":
        return
    harness._validate_execution_manifest()
    cohort = json.loads((BENCHMARK / "cohort_manifest.json").read_text(encoding="utf-8"))
    assert cohort["treatment_runs_observed"] == 0
    assert len(cohort["instances"]) == 12
    for record in cohort["instances"]:
        assert harness._scenario_path(record, "dev").is_file()
        assert harness._scenario_path(record, "hidden").is_file()


def test_closeout_applies_preregistered_itt_zero_floor():
    assert (
        closeout._itt_best_substantive_delta({"best_discovered_substantive_score_delta": -0.0675})
        == 0.0
    )
    assert (
        closeout._itt_best_substantive_delta({"best_discovered_substantive_score_delta": 0.02})
        == 0.02
    )


def test_frozen_primary_result_records_no_direct_sky_value():
    result = json.loads(
        (BENCHMARK / "receipts" / "execution" / "FINAL_RESULT.json").read_text(encoding="utf-8")
    )
    delta = result["DELTA_SKY"]
    assert delta["observed_mean"] == 0.0012499999999999998
    assert delta["one_sided_exact_p"] == 1.0
    assert delta["superiority_established"] is False
    assert delta["equivalence_established"] is False
    assert delta["meaningful_harm_established"] is False
    assert result["architecture_decision"] == "SKY_DIRECT_SEARCH_VALUE_NOT_ESTABLISHED"
