"""Context-local hard accounting for bounded comparison experiments."""

from __future__ import annotations

import contextvars
import json
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, Optional


class BudgetExceeded(RuntimeError):
    """Raised before an inadmissible call or after a token-crossing response."""


@dataclass(frozen=True)
class BudgetCeilings:
    """Maximum useful opportunities admitted within one search run."""

    generation_calls: int
    evaluator_attempts: int
    total_tokens: int
    require_token_usage: bool = True

    def __post_init__(self) -> None:
        for name in ("generation_calls", "evaluator_attempts", "total_tokens"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass
class BudgetLedger:
    """Mutable receipt ledger shared by every provider and evaluator in a context."""

    ceilings: BudgetCeilings
    generation_calls: int = 0
    evaluator_attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    discarded_generation_calls: int = 0
    stop_reason: Optional[str] = None
    events: list[Dict[str, Any]] = field(default_factory=list)
    journal_path: Optional[str] = None

    def _journal(self, event: Dict[str, Any]) -> None:
        """Durably append a pre/post-dispatch snapshot when a formal run requests it."""
        if self.journal_path is None:
            return
        path = Path(self.journal_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(record)
            stream.flush()
            os.fsync(stream.fileno())

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def exhausted(self) -> bool:
        return self.stop_reason is not None

    def _reject(self, reason: str) -> None:
        if self.stop_reason is None:
            self.stop_reason = reason
        raise BudgetExceeded(self.stop_reason)

    def start_generation(self, *, provider: str, model: str, attempt: int) -> int:
        """Admit and count one provider attempt before external work starts."""
        if self.exhausted:
            self._reject(self.stop_reason or "budget_exhausted")
        if self.generation_calls >= self.ceilings.generation_calls:
            self._reject("generation_call_ceiling")
        if self.total_tokens >= self.ceilings.total_tokens:
            self._reject("token_ceiling")

        self.generation_calls += 1
        event_id = len(self.events)
        self.events.append(
            {
                "kind": "generation",
                "call": self.generation_calls,
                "provider": provider,
                "model": model,
                "provider_attempt": attempt,
                "status": "started",
                "input_tokens": 0,
                "output_tokens": 0,
            }
        )
        self._journal({"event_id": event_id, **self.events[event_id]})
        return event_id

    def finish_generation(
        self,
        event_id: int,
        *,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """Finish one provider attempt and discard responses that cross the token cap."""
        event = self.events[event_id]
        if error is not None:
            event["status"] = "failed"
            event["error"] = error
            self._journal({"event_id": event_id, **event})
            return

        usage = (metadata or {}).get("codex_usage")
        if not isinstance(usage, dict):
            event["status"] = "discarded_missing_usage"
            self.discarded_generation_calls += 1
            if self.ceilings.require_token_usage:
                self._journal({"event_id": event_id, **event})
                self._reject("missing_token_usage")
            self._journal({"event_id": event_id, **event})
            return

        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        if input_tokens < 0 or output_tokens < 0:
            event["status"] = "discarded_invalid_usage"
            self.discarded_generation_calls += 1
            self._journal({"event_id": event_id, **event})
            self._reject("invalid_token_usage")

        event["input_tokens"] = input_tokens
        event["output_tokens"] = output_tokens
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        if self.total_tokens > self.ceilings.total_tokens:
            event["status"] = "discarded_token_ceiling_crossed"
            self.discarded_generation_calls += 1
            self._journal({"event_id": event_id, **event})
            self._reject("token_ceiling_crossed")
        event["status"] = "accepted"
        self._journal({"event_id": event_id, **event})

    def start_evaluation(self, *, program_id: str, mode: str) -> int:
        """Admit and count one evaluator attempt before candidate execution."""
        if self.exhausted:
            self._reject(self.stop_reason or "budget_exhausted")
        if self.evaluator_attempts >= self.ceilings.evaluator_attempts:
            self._reject("evaluator_attempt_ceiling")
        self.evaluator_attempts += 1
        event_id = len(self.events)
        self.events.append(
            {
                "kind": "evaluation",
                "attempt": self.evaluator_attempts,
                "program_id": program_id,
                "mode": mode,
                "status": "admitted",
            }
        )
        self._journal({"event_id": event_id, **self.events[event_id]})
        return event_id

    def to_receipt(self) -> Dict[str, Any]:
        """Return a JSON-serializable immutable snapshot."""
        return {
            "ceilings": asdict(self.ceilings),
            "usage": {
                "generation_calls": self.generation_calls,
                "evaluator_attempts": self.evaluator_attempts,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.total_tokens,
                "discarded_generation_calls": self.discarded_generation_calls,
            },
            "stop_reason": self.stop_reason,
            "events": [dict(event) for event in self.events],
        }

    @contextmanager
    def activate(self) -> Iterator["BudgetLedger"]:
        """Activate this ledger for all async descendants in the current context."""
        token = _ACTIVE_LEDGER.set(self)
        try:
            yield self
        finally:
            _ACTIVE_LEDGER.reset(token)


_ACTIVE_LEDGER: contextvars.ContextVar[Optional[BudgetLedger]] = contextvars.ContextVar(
    "skydiscover_execution_budget", default=None
)


def active_budget() -> Optional[BudgetLedger]:
    """Return the active ledger, if a bounded experiment installed one."""
    return _ACTIVE_LEDGER.get()
