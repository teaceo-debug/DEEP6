"""DEEP6 copilot package."""

import time
from datetime import UTC, datetime

from .config import CopilotConfig
from . import budget as _budget_module
from .types import BudgetStatus
from .trade_calls import TradeCallEngine

_TokenBudgetTracker = _budget_module.TokenBudgetTracker
_original_init = _TokenBudgetTracker.__init__
_original_maybe_reset_hour = _TokenBudgetTracker._maybe_reset_hour
_original_record_usage = _TokenBudgetTracker.record_usage


def _compat_init(
    self,
    token_budget_per_hour: int = 500_000,
    budget_per_hour: int | None = None,
) -> None:
    if budget_per_hour is not None:
        token_budget_per_hour = budget_per_hour
    _original_init(self, token_budget_per_hour=token_budget_per_hour)
    self._hour_calls = 0


def _compat_maybe_reset_hour(self) -> None:
    before = getattr(self, "_hour_start", None)
    _original_maybe_reset_hour(self)
    if getattr(self, "_hour_start", None) != before:
        self._hour_calls = 0


def _compat_record_usage(
    self,
    input_tokens: int,
    output_tokens: int,
    call_type: str = "narrative",
    **kwargs: object,
) -> None:
    call_type = str(kwargs.get("model", call_type))
    _original_record_usage(self, input_tokens, output_tokens, call_type)
    self._hour_calls = getattr(self, "_hour_calls", 0) + 1


def _compat_can_make_call(self, estimated_tokens: int) -> bool:
    return self.get_remaining_budget() >= max(0, estimated_tokens)


def _compat_get_status(self) -> BudgetStatus:
    self._maybe_reset_hour()
    used_tokens = getattr(self, "_hour_input", 0) + getattr(self, "_hour_output", 0)
    budget_per_hour = getattr(self, "_budget", 0)
    remaining_tokens = max(0, budget_per_hour - used_tokens)
    hour_start = getattr(self, "_hour_start", time.time())
    reset_at = datetime.fromtimestamp(hour_start + 3600, tz=UTC)
    pct_used = (used_tokens / budget_per_hour) if budget_per_hour > 0 else 0.0
    return BudgetStatus(
        used_tokens=used_tokens,
        budget_per_hour=budget_per_hour,
        remaining_tokens=remaining_tokens,
        calls_this_hour=getattr(self, "_hour_calls", 0),
        pct_used=pct_used,
        reset_at=reset_at,
    )


_TokenBudgetTracker.__init__ = _compat_init  # type: ignore[assignment]
_TokenBudgetTracker._maybe_reset_hour = _compat_maybe_reset_hour  # type: ignore[assignment]
_TokenBudgetTracker.record_usage = _compat_record_usage  # type: ignore[assignment]
_TokenBudgetTracker.can_make_call = _compat_can_make_call  # type: ignore[assignment]
_TokenBudgetTracker.get_status = _compat_get_status  # type: ignore[assignment]

__all__ = ["CopilotConfig", "TradeCallEngine"]
