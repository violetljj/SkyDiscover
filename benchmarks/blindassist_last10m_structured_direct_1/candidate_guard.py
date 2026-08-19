"""Static capability and interface boundary for both direct-generation arms."""

from __future__ import annotations

import ast
from pathlib import Path

STRUCTURED_FUNCTIONS = {
    "safety_contract",
    "tracking_contract",
    "propose_moves",
    "progress_contract",
    "termination_contract",
    "decide",
}
FORBIDDEN_NAMES = {
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "getattr",
    "globals",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}
FORBIDDEN_LITERALS = {
    "instance_07_H_08",
    "REPEATED_NON_TRANSITIONING_STEERING_WITHOUT_PROGRESS_CONTRACT",
    "last_move_progress",
    "failed_moves",
}


class CandidateRejected(ValueError):
    """Raised before evaluator import when a candidate exceeds its capability contract."""


def validate_source(source: str, expected_interface: str) -> None:
    tree = ast.parse(source)
    functions = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    if expected_interface == "structured_direct":
        missing = STRUCTURED_FUNCTIONS - functions
        if missing:
            raise CandidateRejected(f"missing structured contracts: {sorted(missing)}")
    elif expected_interface == "raw_direct":
        if "decide" not in functions:
            raise CandidateRejected("missing raw decide interface")
        unexpected = STRUCTURED_FUNCTIONS - {"decide"}
        if functions & unexpected:
            raise CandidateRejected("raw arm introduced structured contract functions")
    else:
        raise ValueError(f"unknown interface: {expected_interface}")
    for literal in FORBIDDEN_LITERALS:
        if literal in source:
            raise CandidateRejected("candidate contains a frozen oracle implementation marker")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise CandidateRejected("candidate imports are forbidden")
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            raise CandidateRejected(f"forbidden capability: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise CandidateRejected("dunder attribute access is forbidden")


def validate_path(path: Path, expected_interface: str) -> None:
    validate_source(path.read_text(encoding="utf-8"), expected_interface)
