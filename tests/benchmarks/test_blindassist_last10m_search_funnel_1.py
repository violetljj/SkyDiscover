from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "benchmarks" / "blindassist_last10m_search_funnel_1" / "audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("l10m_search_funnel_1_audit", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hidden_value_is_nonnegative() -> None:
    module = _load_module()
    assert module._hidden_value({"metrics": {"substantive_score_delta": -0.25}}) == 0.0
    assert module._hidden_value({"metrics": {"substantive_score_delta": 0.02}}) == 0.02


def test_robust_safe_requires_all_hard_conditions() -> None:
    module = _load_module()
    row = {
        "metrics": {
            "validity": 1.0,
            "task_success": 1.0,
            "safe_termination": 1.0,
            "unsafe_forward_count": 0.0,
            "premature_arrival_count": 0.0,
        }
    }
    assert module._robust_safe(row)
    row["metrics"]["unsafe_forward_count"] = 1.0
    assert not module._robust_safe(row)


def test_summary_reports_selection_gap_and_conversion() -> None:
    module = _load_module()
    rows = [
        {
            "generated_candidates": 2,
            "missing_candidate_opportunities": 0,
            "unique_solution_hashes": 2,
            "retained_is_generated": True,
            "has_robust_safe_positive_candidate": True,
            "oracle_generated_hidden_value": 0.02,
            "retained_hidden_value": 0.0,
            "oracle_minus_retained_hidden_value": 0.02,
            "dev_improving_children": 1,
            "dev_improving_children_with_hidden_gain": 1,
        },
        {
            "generated_candidates": 2,
            "missing_candidate_opportunities": 1,
            "unique_solution_hashes": 1,
            "retained_is_generated": False,
            "has_robust_safe_positive_candidate": False,
            "oracle_generated_hidden_value": 0.0,
            "retained_hidden_value": 0.0,
            "oracle_minus_retained_hidden_value": 0.0,
            "dev_improving_children": 1,
            "dev_improving_children_with_hidden_gain": 0,
        },
    ]
    summary = module._summarize(rows)
    assert summary["blocks"] == 2
    assert summary["unique_solution_rate"] == 0.75
    assert summary["missing_candidate_opportunities"] == 1
    assert summary["mean_oracle_minus_retained_hidden_value"] == 0.01
    assert summary["positive_selection_gap_blocks"] == 1
    assert summary["dev_improving_child_hidden_conversion_rate"] == 0.5
