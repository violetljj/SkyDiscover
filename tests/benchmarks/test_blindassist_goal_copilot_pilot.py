from __future__ import annotations

import json
from pathlib import Path

from skydiscover.config import load_config

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "benchmarks" / "blindassist_goal_copilot_pilot"


def test_frozen_pilot_config_has_exact_budget_mechanics():
    config = load_config(HERE / "config.yaml")
    assert config.max_iterations == 16
    assert config.search.type == "best_of_n"
    assert config.search.database.best_of_n == 4
    assert config.max_parallel_iterations == 1
    assert config.llm.retries == 0
    assert config.evaluator.max_retries == 0
    assert not config.evaluator.inject_evaluator_context
    assert not config.evaluator.llm_as_judge
    assert not config.agentic.enabled


def test_bundle_leakage_check_rejects_fresh_named_member(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("pilot_harness", HERE / "harness.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = tmp_path / "initial_policy.py"
    payload.write_text("pass\n")
    checksums = {payload.name: module._sha256(payload)}
    digest = __import__("hashlib").sha256(module._canonical(checksums)).hexdigest()
    bundle = tmp_path / digest
    bundle.mkdir()
    payload.replace(bundle / payload.name)
    (bundle / "fresh_truth.txt").write_text("forbidden")
    (bundle / "checksums.json").write_bytes(module._canonical(checksums))
    (bundle / "manifest.json").write_bytes(module._canonical({
        "payload_files": ["initial_policy.py"],
        "bundle_digest": digest,
        "fresh_material_exported": False,
    }))
    try:
        module.verify_bundle(bundle)
    except RuntimeError as exc:
        assert "FRESH_LEAKAGE" in str(exc)
    else:
        raise AssertionError("fresh leakage was accepted")
