"""Mechanical invariants for the consumed long-horizon calibration."""

import json
from pathlib import Path

from skydiscover.config import load_config

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "benchmarks/blindassist_last10m_long_horizon_1"


def test_protocol_uses_prefix_consistent_ten_iteration_observations():
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))

    assert protocol["horizon"]["solution_candidate_generations"] == 200
    assert protocol["horizon"]["prefix_observations"] == list(range(10, 201, 10))
    assert protocol["horizon"]["single_prefix_consistent_trajectory"] is True
    assert protocol["replicates"]["total_trajectories"] == 108


def test_arm_configs_are_serial_and_checkpoint_every_iteration():
    configs = {
        arm: load_config(HERE / "configs" / f"{arm}.yaml") for arm in ("naked", "adaevolve", "evox")
    }

    assert {config.max_iterations for config in configs.values()} == {200}
    assert {config.checkpoint_interval for config in configs.values()} == {1}
    assert {config.max_parallel_iterations for config in configs.values()} == {1}
    assert {config.llm.retries for config in configs.values()} == {0}
    assert configs["naked"].search.type == "incumbent_only"
    assert configs["adaevolve"].search.type == "adaevolve"
    assert configs["evox"].search.type == "evox"


def test_remote_parallelism_matches_32_visible_cores_with_headroom():
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    parallelism = protocol["parallelism"]

    assert parallelism["remote_visible_cpu_expected"] == 32
    assert parallelism["remote_cpu_reserve"] == 6
    assert parallelism["remote_evaluator_process_ceiling"] == 26
    assert set(parallelism["thread_env"].values()) == {"1"}
