"""Run a foreign evaluator without requiring SkyDiscover in its environment.

This module intentionally uses only the Python standard library.  It is invoked
as a script by a consumer-owned Python interpreter and emits one JSON document
on stdout.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import sys
import traceback
import types
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Union

SCHEMA = "skydiscover-assist-evaluation-v1"


@dataclass
class EvaluationResult:
    """Small compatibility type for consumer evaluators importing SkyDiscover."""

    metrics: Dict[str, float]
    artifacts: Dict[str, Union[str, bytes]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, metrics: Dict[str, float]) -> "EvaluationResult":
        return cls(metrics=metrics)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = dict(self.metrics)
        if self.artifacts:
            result["artifacts"] = self.artifacts
        return result


def _install_compatibility_module() -> None:
    """Expose only the evaluator result seam expected by foreign evaluators."""

    package = types.ModuleType("skydiscover")
    package.__path__ = []  # type: ignore[attr-defined]
    evaluation = types.ModuleType("skydiscover.evaluation")
    evaluation.__path__ = []  # type: ignore[attr-defined]
    evaluation.EvaluationResult = EvaluationResult  # type: ignore[attr-defined]
    result_module = types.ModuleType("skydiscover.evaluation.evaluation_result")
    result_module.EvaluationResult = EvaluationResult  # type: ignore[attr-defined]
    optimize = types.ModuleType("skydiscover.optimize")
    optimize.__path__ = []  # type: ignore[attr-defined]
    optimize.evaluation = evaluation  # type: ignore[attr-defined]
    package.optimize = optimize  # type: ignore[attr-defined]
    sys.modules["skydiscover.optimize"] = optimize
    sys.modules["skydiscover.optimize.evaluation"] = evaluation
    sys.modules["skydiscover.optimize.evaluation.evaluation_result"] = result_module
    package.evaluation = evaluation  # type: ignore[attr-defined]
    sys.modules["skydiscover"] = package
    sys.modules["skydiscover.evaluation"] = evaluation
    sys.modules["skydiscover.evaluation.evaluation_result"] = result_module


def _load_evaluator(path: Path) -> Any:
    _install_compatibility_module()
    evaluator_dir = str(path.parent)
    if evaluator_dir not in sys.path:
        sys.path.insert(0, evaluator_dir)
    module_name = f"_skydiscover_assist_consumer_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load evaluator from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    if not callable(getattr(module, "evaluate", None)):
        raise AttributeError(f"evaluator has no callable evaluate(program_path): {path}")
    return module


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return {"encoding": "base64", "data": base64.b64encode(value).decode("ascii")}
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _normalize(result: Any) -> tuple[dict[str, float], dict[str, Any]]:
    if hasattr(result, "metrics"):
        metrics_value = result.metrics
        artifacts_value = getattr(result, "artifacts", {})
    elif isinstance(result, Mapping) and isinstance(result.get("metrics"), Mapping):
        metrics_value = result["metrics"]
        artifacts_value = result.get("artifacts", {})
    elif isinstance(result, Mapping):
        metrics_value = result
        artifacts_value = {}
    else:
        raise TypeError(f"evaluate() returned unsupported type {type(result).__name__}")

    metrics: dict[str, float] = {}
    for key, value in metrics_value.items():
        if isinstance(value, bool):
            metrics[str(key)] = float(value)
        elif isinstance(value, (int, float)):
            metrics[str(key)] = float(value)
        else:
            raise TypeError(f"metric {key!r} is not numeric: {type(value).__name__}")
    artifacts = _json_safe(artifacts_value)
    if not isinstance(artifacts, dict):
        raise TypeError("artifacts must be a mapping")
    return metrics, artifacts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SkyDiscover consumer evaluator worker")
    parser.add_argument("command", choices=("probe", "evaluate"))
    parser.add_argument("--evaluator", required=True)
    parser.add_argument("--program")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        evaluator_path = Path(args.evaluator).resolve(strict=True)
        module = _load_evaluator(evaluator_path)
        if args.command == "probe":
            payload = {"schema": SCHEMA, "status": "ok", "evaluator": str(evaluator_path)}
        else:
            if not args.program:
                raise ValueError("evaluate requires --program")
            program_path = Path(args.program).resolve(strict=True)
            real_stdout = sys.stdout
            sys.stdout = sys.stderr
            try:
                result = module.evaluate(str(program_path))
            finally:
                sys.stdout = real_stdout
            metrics, artifacts = _normalize(result)
            payload = {
                "schema": SCHEMA,
                "status": "ok",
                "metrics": metrics,
                "artifacts": artifacts,
            }
        print(json.dumps(payload, sort_keys=True))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                },
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
