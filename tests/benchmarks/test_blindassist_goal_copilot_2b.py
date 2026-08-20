import importlib.util
import json
from pathlib import Path

from skydiscover.config import load_config

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


def test_gc2b_formal_config_preserves_frozen_budget_and_authority() -> None:
    here = CONTRACT_PATH.parent
    config = load_config(here / "config.yaml")
    contract = json.loads((here / "protocol_contract.json").read_text(encoding="utf-8"))
    assert config.max_iterations == contract["generation_attempts_per_replicate"] == 16
    assert config.search.type == "best_of_n"
    assert config.search.database.best_of_n == contract["best_of_n"] == 4
    assert config.max_parallel_iterations == 1
    assert config.llm.retries == 0
    assert config.evaluator.max_retries == 0
    assert not config.evaluator.llm_as_judge
    assert not config.agentic.enabled
