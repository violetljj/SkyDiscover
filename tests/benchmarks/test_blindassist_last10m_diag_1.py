"""Focused contract tests for the development-only L10M-DIAG-1 audit."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIAG = ROOT / "benchmarks" / "blindassist_last10m_diag_1"
RECEIPT = DIAG / "receipts" / "development_audit.json"


def test_protocol_forbids_fresh_blind_data_and_search_calls():
    protocol = json.loads((DIAG / "protocol.json").read_text(encoding="utf-8"))
    assert protocol["splits"] == [
        "consumed_development_train",
        "consumed_l10m_sky_1_hidden",
    ]
    assert protocol["fresh_blind_split_access"] == "forbidden"
    assert protocol["search_calls"] == 0


def test_audit_records_objective_and_reachability_signals():
    subprocess.run(
        [sys.executable, str(DIAG / "run.py")], cwd=ROOT, check=True, capture_output=True, text=True
    )
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    assert receipt["fresh_blind_split_evaluated"] is False
    assert receipt["search_calls"] == 0
    assert receipt["decision"]["objective_signal"] is True
    assert receipt["decision"]["reachable_effect_signal"] is True
    assert receipt["decision"]["robust_safe_reachability"] is False
    assert (
        receipt["decision"]["verdict"]
        == "OBJECTIVE_SIGNAL_PRESENT_ROBUST_REACHABILITY_NOT_ESTABLISHED"
    )
    assert set(receipt["authority_sha256"]) == {
        "protocol",
        "runner",
        "evaluator",
        "sky_1_cohort_manifest",
    }
    instruction = receipt["results"]["instruction_only_counterfactual"]["metrics"]
    assert instruction["score_delta"] > 0.005
    assert instruction["substantive_score_delta"] == 0.0
    reachable = receipt["results"]["reachable_path_counterfactual"]["metrics"]
    assert reachable["substantive_score_delta"] > 0.005
    assert reachable["substantive_score_share"] >= 0.5
    hidden = receipt["consumed_hidden_summary"]
    assert hidden["instance_count"] == 12
    assert hidden["reachable_mean_substantive_score_delta"] > 0.005
    assert hidden["reachable_behavioral_pass_rate"] >= 0.5
    assert hidden["reachable_robust_safe_rate"] < 1.0
