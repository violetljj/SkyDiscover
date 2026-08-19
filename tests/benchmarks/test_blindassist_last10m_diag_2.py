"""Focused contract tests for L10M-DIAG-2."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIAG = ROOT / "benchmarks" / "blindassist_last10m_diag_2"
RECEIPT = DIAG / "receipts" / "development_audit.json"


def _load_policy():
    path = DIAG / "policies" / "structured_temporal_policy.py"
    spec = importlib.util.spec_from_file_location("diag_2_structured_policy", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_protocol_is_consumed_only_and_search_free():
    protocol = json.loads((DIAG / "protocol.json").read_text(encoding="utf-8"))
    assert protocol["fresh_blind_split_access"] == "forbidden"
    assert protocol["search_calls"] == 0
    assert protocol["success_rules"]["robust_safe_instances"] == 12


def test_candidate_language_exposes_independent_contract_units():
    policy = _load_policy()
    assert callable(policy.safety_contract)
    assert callable(policy.tracking_contract)
    assert callable(policy.propose_moves)
    assert callable(policy.progress_contract)


def test_structured_policy_repairs_timeout_and_meets_frozen_rules():
    subprocess.run(
        [sys.executable, str(DIAG / "run.py")], cwd=ROOT, check=True, capture_output=True, text=True
    )
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    summary = receipt["summary"]
    assert summary["behavioral_pass_instances"] >= 10
    assert summary["mean_substantive_score_delta"] > 0.005
    assert summary["robust_safe_instances"] == 12
    assert receipt["decision"]["success_rules_met"] is True
    assert receipt["decision"]["search_restart_authorized"] is True
    diagnosis = receipt["target_episode_diagnosis"]
    assert diagnosis["cause"] == "REPEATED_NON_TRANSITIONING_STEERING_WITHOUT_PROGRESS_CONTRACT"
    assert diagnosis["traces"]["diag_1_policy"][-1]["node"] == "turn"
    assert diagnosis["traces"]["structured_temporal_policy"][-1]["action"] == "ARRIVED"
