"""Byte-level component isolation guard for L10M-STRUCT-COMPONENT-1."""

from __future__ import annotations

import ast
from pathlib import Path

HERE = Path(__file__).resolve().parent
CANONICAL_PATH = HERE / "initial_program.py"

ARM_FUNCTIONS = {
    "raw_control": frozenset(),
    "progress_only": frozenset({"progress_contract"}),
    "moves_only": frozenset({"propose_moves"}),
    "progress_moves": frozenset({"progress_contract", "propose_moves"}),
}
TOP_LEVEL_FUNCTIONS = {
    "safety_contract",
    "tracking_contract",
    "propose_moves",
    "progress_contract",
    "termination_contract",
    "decide",
}
ACTION_LITERALS = {
    "FORWARD",
    "VEER_LEFT",
    "VEER_RIGHT",
    "STOP",
    "SLOW_DOWN",
    "SCAN_LEFT",
    "SCAN_RIGHT",
    "ARRIVED",
}
ALLOWED_PROGRESS_MEMORY_KEYS = {
    "failed_moves",
    "last_move",
    "last_move_progress",
    "progress_level",
    "stagnant_steps",
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
ALLOWED_COMPONENT_CALLS = {
    "abs",
    "bool",
    "enumerate",
    "float",
    "int",
    "len",
    "list",
    "max",
    "min",
    "next",
    "range",
    "round",
    "set",
    "sorted",
    "tuple",
    "zip",
}
ALLOWED_COMPONENT_NAMES = ALLOWED_COMPONENT_CALLS | {"dict"}


class CandidateRejected(ValueError):
    """Raised before evaluator import when a candidate crosses its arm boundary."""


def _normalized(source: str) -> str:
    return source.replace("\r\n", "\n")


def _tree(source: str) -> ast.Module:
    try:
        return ast.parse(source)
    except SyntaxError as exc:
        raise CandidateRejected(f"candidate syntax error: {exc}") from exc


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    result: dict[str, ast.FunctionDef] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            if node.name in result:
                raise CandidateRejected(f"duplicate function: {node.name}")
            result[node.name] = node
        elif isinstance(node, (ast.AsyncFunctionDef, ast.ClassDef)):
            raise CandidateRejected("async functions and classes are forbidden")
    if set(result) != TOP_LEVEL_FUNCTIONS:
        raise CandidateRejected(
            f"top-level functions must remain exact: {sorted(set(result) ^ TOP_LEVEL_FUNCTIONS)}"
        )
    nested = [
        node
        for function in result.values()
        for node in ast.walk(function)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
        and node is not function
    ]
    if nested:
        raise CandidateRejected("nested functions and lambdas are forbidden")
    return result


def _masked_source(source: str, allowed: frozenset[str]) -> str:
    normalized = _normalized(source)
    tree = _tree(normalized)
    functions = _functions(tree)
    lines = normalized.splitlines(keepends=True)
    spans = sorted(
        (
            functions[name].lineno - 1,
            functions[name].end_lineno,
            name,
        )
        for name in allowed
    )
    chunks: list[str] = []
    cursor = 0
    for start, end, name in spans:
        chunks.extend(lines[cursor:start])
        chunks.append(f"<ADMITTED_COMPONENT:{name}>\n")
        cursor = end
    chunks.extend(lines[cursor:])
    return "".join(chunks)


def _string_literals(node: ast.AST) -> set[str]:
    return {
        item.value
        for item in ast.walk(node)
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    }


def _subscript_key(node: ast.Subscript) -> str | None:
    value = node.slice
    return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None


def _mapping_keys(function: ast.FunctionDef, mapping_name: str) -> set[str]:
    keys: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            if node.value.id == mapping_name:
                key = _subscript_key(node)
                if key is None:
                    raise CandidateRejected(f"{mapping_name} keys must be static strings")
                keys.add(key)
                if isinstance(node.ctx, ast.Store):
                    raise CandidateRejected(f"component may not mutate {mapping_name}")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == mapping_name
            and node.func.attr == "get"
            and node.args
        ):
            key_node = node.args[0]
            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                raise CandidateRejected(f"{mapping_name} keys must be static strings")
            keys.add(key_node.value)
    return keys


def _reject_cross_contract_calls(function: ast.FunctionDef) -> None:
    for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
        if isinstance(call.func, ast.Name):
            if call.func.id in TOP_LEVEL_FUNCTIONS or call.func.id not in ALLOWED_COMPONENT_CALLS:
                raise CandidateRejected(
                    f"component call is outside the capability boundary: {call.func.id}"
                )
        if (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id in {"observation", "memory"}
            and call.func.attr != "get"
        ):
            raise CandidateRejected("component mapping access is outside the capability boundary")


def _reject_global_name_access(function: ast.FunctionDef) -> None:
    local_names = {arg.arg for arg in function.args.args}
    local_names.update(
        node.id
        for node in ast.walk(function)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    )
    allowed = local_names | ALLOWED_COMPONENT_NAMES
    for node in ast.walk(function):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in allowed:
            raise CandidateRejected(
                f"component may not read module or cross-contract name: {node.id}"
            )


def _validate_global_capabilities(tree: ast.Module) -> None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise CandidateRejected("imports are forbidden")
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            raise CandidateRejected(f"forbidden capability: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise CandidateRejected("dunder attribute access is forbidden")
        if isinstance(node, (ast.Global, ast.Nonlocal, ast.With, ast.AsyncWith, ast.Try)):
            raise CandidateRejected(
                "global, nonlocal, context-manager, and exception machinery is forbidden"
            )


def _validate_progress(function: ast.FunctionDef, canonical: ast.FunctionDef) -> None:
    if ast.dump(function, include_attributes=False) == ast.dump(
        canonical, include_attributes=False
    ):
        raise CandidateRejected("enabled progress component must differ from raw control")
    if [arg.arg for arg in function.args.args] != ["observation", "memory", "candidates"]:
        raise CandidateRejected("progress_contract signature changed")
    literals = _string_literals(function)
    if literals & ACTION_LITERALS:
        raise CandidateRejected("progress_contract may not manufacture action literals")
    if "progress" not in literals:
        raise CandidateRejected("progress_contract must observe progress")
    observation_keys = _mapping_keys(function, "observation")
    if observation_keys != {"progress"}:
        raise CandidateRejected("progress_contract may observe only the progress field")
    _reject_cross_contract_calls(function)
    _reject_global_name_access(function)
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    if not {"observation", "memory", "candidates"}.issubset(names):
        raise CandidateRejected(
            "progress_contract must use observation, memory, and supplied candidates"
        )
    memory_keys: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            if node.value.id == "memory":
                key = _subscript_key(node)
                if key is None or key not in ALLOWED_PROGRESS_MEMORY_KEYS:
                    raise CandidateRejected("progress_contract uses an unregistered memory key")
    for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
        if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
            if call.func.value.id == "memory" and call.args:
                key_node = call.args[0]
                if (
                    not isinstance(key_node, ast.Constant)
                    or key_node.value not in ALLOWED_PROGRESS_MEMORY_KEYS
                ):
                    raise CandidateRejected("progress_contract uses an unregistered memory key")
                memory_keys.add(str(key_node.value))
    for node in ast.walk(function):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            if node.value.id == "memory" and (key := _subscript_key(node)):
                memory_keys.add(key)
    if not memory_keys:
        raise CandidateRejected("progress_contract must use bounded progress memory")


def _validate_moves(function: ast.FunctionDef, canonical: ast.FunctionDef) -> None:
    if ast.dump(function, include_attributes=False) == ast.dump(
        canonical, include_attributes=False
    ):
        raise CandidateRejected("enabled move-proposal component must differ from raw control")
    if [arg.arg for arg in function.args.args] != ["observation"]:
        raise CandidateRejected("propose_moves signature changed")
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    if "memory" in names:
        raise CandidateRejected("move proposals may not use memory")
    literals = _string_literals(function)
    required = {"corridor_left", "corridor_center", "corridor_right", "target_bearing"}
    observation_keys = _mapping_keys(function, "observation")
    if observation_keys != required:
        raise CandidateRejected("move proposals must use the full observable corridor geometry")
    _reject_cross_contract_calls(function)
    _reject_global_name_access(function)
    if len(literals & {"FORWARD", "VEER_LEFT", "VEER_RIGHT"}) < 3:
        raise CandidateRejected("move proposals must expose all three motion actions")
    has_deduplication = any(
        (isinstance(node, ast.Attribute) and node.attr == "fromkeys")
        or (isinstance(node, ast.Compare) and any(isinstance(op, ast.NotIn) for op in node.ops))
        for node in ast.walk(function)
    )
    if not has_deduplication:
        raise CandidateRejected("move proposals must enforce duplicate-free candidates")


def validate_source(source: str, arm: str) -> None:
    if arm not in ARM_FUNCTIONS:
        raise ValueError(f"unknown arm: {arm}")
    source = _normalized(source)
    canonical_source = _normalized(CANONICAL_PATH.read_text(encoding="utf-8"))
    if source == canonical_source:
        return  # Runner's common iteration-zero initial-program evaluation.
    candidate_canonical = canonical_source.replace(
        "# CANDIDATE-TAG: initial", "# CANDIDATE-TAG: generated", 1
    )
    if "# CANDIDATE-TAG: initial" in source or "# CANDIDATE-TAG: generated" not in source:
        raise CandidateRejected("candidate did not apply the exact inert candidate tag")
    allowed = ARM_FUNCTIONS[arm]
    tree = _tree(source)
    canonical_tree = _tree(candidate_canonical)
    _validate_global_capabilities(tree)
    functions = _functions(tree)
    canonical_functions = _functions(canonical_tree)
    if _masked_source(source, allowed) != _masked_source(candidate_canonical, allowed):
        raise CandidateRejected("candidate changed locked scaffold bytes")
    if "progress_contract" in allowed:
        _validate_progress(functions["progress_contract"], canonical_functions["progress_contract"])
    if "propose_moves" in allowed:
        _validate_moves(functions["propose_moves"], canonical_functions["propose_moves"])


def validate_path(path: Path, arm: str) -> None:
    validate_source(path.read_text(encoding="utf-8"), arm)
