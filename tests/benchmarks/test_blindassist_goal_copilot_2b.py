import importlib.util
from pathlib import Path

CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "benchmarks"
    / "blindassist_goal_copilot_2b"
    / "contract.py"
)
SPEC = importlib.util.spec_from_file_location("blindassist_goal_copilot_2b_contract", CONTRACT_PATH)
assert SPEC and SPEC.loader
contract_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract_module)


def test_gc2b_design_is_consistent_and_non_executable() -> None:
    result = contract_module.validate_design()
    contract = result["contract"]
    blueprint = result["blueprint"]
    assert contract["sky_authority"] == "CANDIDATE_PROPOSAL_AND_SEARCH_ONLY"
    assert contract["blindassist_authority"].endswith("WINNER_LOCK_ACCEPTANCE")
    assert contract["generation_attempts_total"] == 32
    assert contract["generation_retries"] == 0
    assert contract["evaluator_retries"] == 0
    assert not contract["search_authorized"]
    assert not contract["model_calls_authorized"]
    assert not contract["heldout_material_exported_to_sky"]
    assert not blueprint["enabled"]
