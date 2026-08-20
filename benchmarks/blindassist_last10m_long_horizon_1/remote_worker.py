#!/usr/bin/env python3
"""Persistent, task-owned evaluator data-plane worker for LONG-HORIZON-1."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE_EVALUATOR = ROOT / "benchmarks/blindassist_last10m_v3/evaluator/evaluator.py"


class IdempotencyConflict(RuntimeError):
    """A request ID was reused for a different evaluation identity."""


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _expanded(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scenarios = copy.deepcopy(raw)
    for scenario in scenarios:
        defaults = scenario.pop("node_defaults", {})
        defaults.setdefault("rgb_ref", None)
        scenario["nodes"] = [{**defaults, **node} for node in scenario["nodes"]]
    return scenarios


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")


def _cache_key(request: dict[str, Any]) -> str:
    identity = {
        "candidate_sha256": request["candidate_sha256"],
        "mode": request["mode"],
        "scenarios": request["scenarios"],
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _compute(request: dict[str, Any]) -> dict[str, Any]:
    source = request["candidate_source"]
    raw_scenarios = request["scenarios"]
    with tempfile.TemporaryDirectory(prefix="l10m_long_horizon_worker_") as temp:
        candidate_path = Path(temp) / "candidate.py"
        candidate_path.write_text(source, encoding="utf-8", newline="\n")
        base = _load(BASE_EVALUATOR, f"long_horizon_worker_evaluator_{request['request_id']}")
        scenarios = _expanded(raw_scenarios)
        base._load_scenarios = lambda requested_mode: copy.deepcopy(scenarios)
        return base.evaluate(str(candidate_path), request["mode"])


def _cached_compute(request: dict[str, Any], cache_root: Path) -> tuple[dict[str, Any], bool]:
    key = _cache_key(request)
    receipt = cache_root / key[:2] / f"{key}.json"
    lock = receipt.with_suffix(".lock")
    receipt.parent.mkdir(parents=True, exist_ok=True)
    if receipt.is_file():
        return json.loads(receipt.read_text(encoding="utf-8"))["result"], True
    deadline = time.monotonic() + 180.0
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            if receipt.is_file():
                return json.loads(receipt.read_text(encoding="utf-8"))["result"], True
            if time.monotonic() >= deadline:
                raise TimeoutError(f"cache lock timeout: {key}")
            time.sleep(0.05)
    try:
        if receipt.is_file():
            return json.loads(receipt.read_text(encoding="utf-8"))["result"], True
        result = _compute(request)
        temporary = receipt.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps({"cache_key": key, "result": result}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, receipt)
        return result, False
    finally:
        lock.rmdir()


def evaluate(request: dict[str, Any], worker_root: Path, cache_root: Path) -> dict[str, Any]:
    request_id = request["request_id"]
    receipt_path = worker_root / "receipts" / f"{request_id}.json"
    started_path = worker_root / "started" / f"{request_id}.json"
    if request.get("operation") == "query":
        if receipt_path.is_file():
            return json.loads(receipt_path.read_text(encoding="utf-8"))
        return {
            "request_id": request_id,
            "status": "IN_DOUBT" if started_path.is_file() else "NOT_DISPATCHED",
        }
    identity = {
        "request_id": request_id,
        "candidate_sha256": request.get("candidate_sha256"),
        "arm": request.get("arm"),
        "mode": request.get("mode"),
    }
    if receipt_path.is_file():
        if json.loads(started_path.read_text(encoding="utf-8")) != identity:
            raise IdempotencyConflict("idempotency key reused with different evaluation identity")
        return json.loads(receipt_path.read_text(encoding="utf-8"))
    if started_path.is_file():
        return {"request_id": request_id, "status": "IN_DOUBT"}
    _write_once(
        started_path,
        identity,
    )
    result, cache_hit = _cached_compute(request, cache_root)
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    response = {
        "request_id": request_id,
        "status": "COMPLETED",
        "result": result,
        "result_sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "cache_hit": cache_hit,
    }
    _write_once(receipt_path, response)
    return response


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-root", type=Path, required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    args = parser.parse_args()
    args.worker_root.mkdir(parents=True, exist_ok=True)
    for line in sys.stdin:
        if not line.strip():
            continue
        request: dict[str, Any] = {}
        try:
            request = json.loads(line)
            response = evaluate(request, args.worker_root, args.cache_root)
        except IdempotencyConflict as exc:
            response = {
                "request_id": request.get("request_id"),
                "status": "SYSTEMIC_INTEGRITY_FAILURE",
                "error": f"{type(exc).__name__}: {exc}",
            }
        except Exception as exc:
            response = {
                "request_id": request.get("request_id") if isinstance(request, dict) else None,
                "status": "ARM_RELATED_EVALUATOR_FAILURE",
                "error": f"{type(exc).__name__}: {exc}",
            }
            if response["request_id"]:
                receipt = args.worker_root / "receipts" / f"{response['request_id']}.json"
                if not receipt.exists():
                    _write_once(receipt, response)
        print(json.dumps(response, sort_keys=True, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
