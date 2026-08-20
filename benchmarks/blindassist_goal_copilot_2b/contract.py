"""Fail-closed validation for the non-executable GC2-B Sky contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CONTRACT = HERE / "protocol_contract.json"
BLUEPRINT = HERE / "search_blueprint.json"


def validate_design() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    blueprint = json.loads(BLUEPRINT.read_text(encoding="utf-8"))
    if contract["protocol_id"] != "GOAL-COPILOT-2B":
        raise RuntimeError("protocol identity mismatch")
    if contract["search_authorized"] or contract["model_calls_authorized"]:
        raise RuntimeError("design contract cannot authorize execution")
    if contract["provider_frozen"] or contract["bundle_frozen"]:
        raise RuntimeError("unmaterialized execution inputs claimed frozen")
    if contract["heldout_material_exported_to_sky"]:
        raise RuntimeError("held-out leakage")
    if blueprint["enabled"] or blueprint["model_provider"] != "UNFROZEN_NO_EXECUTION":
        raise RuntimeError("search blueprint is executable before a run seal")
    expected_total = len(contract["replicates"]) * contract["generation_attempts_per_replicate"]
    if contract["generation_attempts_total"] != expected_total:
        raise RuntimeError("budget arithmetic mismatch")
    if blueprint["max_iterations"] != contract["generation_attempts_per_replicate"]:
        raise RuntimeError("iteration budget mismatch")
    if blueprint["best_of_n"] != contract["best_of_n"]:
        raise RuntimeError("search-shape mismatch")
    return {"contract": contract, "blueprint": blueprint}
