"""Focused tests for comparison-grade execution accounting."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from skydiscover.execution_budget import BudgetCeilings, BudgetExceeded, BudgetLedger
from skydiscover.llm.codex_cli import CodexCliLLM


def _codex_stub() -> CodexCliLLM:
    llm = object.__new__(CodexCliLLM)
    llm.model = "gpt-5.6-sol"
    llm.timeout = 10
    llm.retries = 1
    llm.retry_delay = 0
    llm.reasoning_effort = "medium"
    llm.executable = "codex"
    llm.version = "codex-cli test"
    return llm


def _usage(input_tokens: int, output_tokens: int) -> dict:
    return {
        "codex_usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_output_tokens": 0,
        }
    }


@pytest.mark.asyncio
async def test_provider_retries_each_consume_a_generation_call():
    llm = _codex_stub()
    llm._run_once = AsyncMock(side_effect=[RuntimeError("transient"), ("candidate", _usage(20, 5))])
    ledger = BudgetLedger(BudgetCeilings(3, 2, 100))

    with ledger.activate():
        response = await llm.generate("system", [{"role": "user", "content": "task"}])

    assert response.text == "candidate"
    assert ledger.generation_calls == 2
    assert ledger.total_tokens == 25
    assert [event["status"] for event in ledger.events] == ["failed", "accepted"]


@pytest.mark.asyncio
async def test_token_crossing_response_is_recorded_but_not_admitted_or_retried():
    llm = _codex_stub()
    llm._run_once = AsyncMock(return_value=("candidate", _usage(90, 11)))
    ledger = BudgetLedger(BudgetCeilings(3, 2, 100))

    with ledger.activate(), pytest.raises(BudgetExceeded, match="token_ceiling_crossed"):
        await llm.generate("system", [{"role": "user", "content": "task"}])

    assert llm._run_once.await_count == 1
    assert ledger.generation_calls == 1
    assert ledger.total_tokens == 101
    assert ledger.discarded_generation_calls == 1
    assert ledger.events[0]["status"] == "discarded_token_ceiling_crossed"


def test_evaluator_attempt_ceiling_is_admitted_before_execution():
    ledger = BudgetLedger(BudgetCeilings(2, 1, 100))
    with ledger.activate():
        ledger.start_evaluation(program_id="p1", mode="train")
        with pytest.raises(BudgetExceeded, match="evaluator_attempt_ceiling"):
            ledger.start_evaluation(program_id="p2", mode="train")

    assert ledger.evaluator_attempts == 1
    assert ledger.stop_reason == "evaluator_attempt_ceiling"
    assert ledger.events[0]["program_id"] == "p1"


def test_durable_journal_marks_interrupted_dispatches_in_doubt(tmp_path):
    journal = tmp_path / "budget.json"
    ledger = BudgetLedger(BudgetCeilings(3, 2, 100), journal_path=journal)
    ledger.start_generation(provider="codex-cli", model="test", attempt=1)
    ledger.start_evaluation(program_id="p1", mode="train")

    restored = BudgetLedger.from_journal(journal)

    assert restored.generation_calls == 1
    assert restored.evaluator_attempts == 1
    assert [event["status"] for event in restored.events] == ["in_doubt", "in_doubt"]
    assert [event["status"] for event in BudgetLedger.from_journal(journal).events] == [
        "in_doubt",
        "in_doubt",
    ]


def test_durable_journal_records_completion(tmp_path):
    journal = tmp_path / "budget.json"
    ledger = BudgetLedger(BudgetCeilings(3, 2, 100), journal_path=journal)
    event_id = ledger.start_generation(provider="codex-cli", model="test", attempt=1)
    ledger.finish_generation(event_id, metadata=_usage(20, 5))

    restored = BudgetLedger.from_journal(journal)

    assert restored.total_tokens == 25
    assert restored.events[0]["status"] == "accepted"


def test_durable_journal_records_evaluation_completion(tmp_path):
    journal = tmp_path / "budget.json"
    ledger = BudgetLedger(BudgetCeilings(3, 2, 100), journal_path=journal)
    event_id = ledger.start_evaluation(program_id="p1", mode="train")
    ledger.finish_evaluation(event_id, outcome="result")

    restored = BudgetLedger.from_journal(journal)

    assert restored.events[0]["status"] == "completed"
    assert restored.events[0]["outcome"] == "result"
