#!/usr/bin/env python3
"""Zero-model-call canary for the local-control/remote-evaluator data plane."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COHORT = ROOT / "benchmarks/blindassist_last10m_comp_2/cohort_manifest.json"


def _load_transport():
    spec = importlib.util.spec_from_file_location(
        "l10m_component_2_canary_transport", HERE / "transport.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load transport")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(manifest_path: Path, output_root: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    head = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if manifest.get("source_commit") != head:
        raise RuntimeError("canary manifest source commit is not the current frozen commit")
    cohort = json.loads(COHORT.read_text(encoding="utf-8"))
    scenario = ROOT / cohort["instances"][0]["dev_path"]
    source = (
        (ROOT / "benchmarks/blindassist_last10m_struct_component_1/initial_program.py")
        .read_text(encoding="utf-8")
        .replace("# CANDIDATE-TAG: initial", "# CANDIDATE-TAG: generated", 1)
    )
    output_root.mkdir(parents=True, exist_ok=True)
    transport = _load_transport()
    client = transport.RemoteEvaluationClient(
        manifest, output_root / "dispatch", "transport_canary"
    )
    try:
        result = client.evaluate(
            candidate_source=source,
            scenarios=json.loads(scenario.read_text(encoding="utf-8")),
            arm="raw_control",
            mode="train",
            request_id="canary-raw-control-0001",
        )
        invalid = source.replace(
            'observation["closing_risk"] >= 0.75',
            'observation["closing_risk"] >= 0.95',
            1,
        )
        try:
            client.evaluate(
                candidate_source=invalid,
                scenarios=json.loads(scenario.read_text(encoding="utf-8")),
                arm="raw_control",
                mode="train",
                request_id="canary-confirmed-failure-0001",
            )
        except transport.RemoteEvaluationError:
            pass
        else:
            raise RuntimeError("canary expected a confirmed guard failure")
    finally:
        client.close()
    replay_client = transport.RemoteEvaluationClient(
        manifest, output_root / "dispatch_replay", "transport_canary"
    )
    try:
        replay_result = replay_client.evaluate(
            candidate_source=source,
            scenarios=json.loads(scenario.read_text(encoding="utf-8")),
            arm="raw_control",
            mode="train",
            request_id="canary-raw-control-0001",
        )
    finally:
        replay_client.close()
    if replay_result != result:
        raise RuntimeError("create-once replay did not return the original remote receipt")
    if not isinstance(result, dict) or "metrics" not in result or "artifacts" not in result:
        raise RuntimeError("canary response lacks evaluator result fields")
    failure_root = output_root / "dispatch" / "transport_canary"
    if not (failure_root / "canary-confirmed-failure-0001.after.json").is_file():
        raise RuntimeError("confirmed failure lacks an after journal")
    if (failure_root / "canary-confirmed-failure-0001.in_doubt.json").exists():
        raise RuntimeError("confirmed failure was incorrectly classified in_doubt")
    receipt = {
        "status": "REMOTE_TRANSPORT_CANARY_PASS",
        "model_calls": 0,
        "experiment_receipts_created": 0,
        "source_commit": head,
        "remote_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "request_id": "canary-raw-control-0001",
        "confirmed_failure_request_id": "canary-confirmed-failure-0001",
        "confirmed_failure_classified_in_doubt": False,
        "create_once_replay": "PASS",
        "worker_id": "transport_canary",
        "result_fields": sorted(result),
    }
    with (output_root / "canary_receipt.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.remote_manifest.resolve(), args.output_root.resolve()),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
