"""Token budget tracker and cost controller for Claude API usage."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Claude API pricing (per million tokens)
_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet": (3.0, 15.0),   # (input, output) per MTok
    "claude-opus": (15.0, 75.0),
}


class TokenBudgetTracker:
    """Track Claude API token usage and enforce hourly budget."""

    def __init__(self, token_budget_per_hour: int = 500_000) -> None:
        self._budget = token_budget_per_hour
        self._hour_start = time.time()
        self._hour_input = 0
        self._hour_output = 0
        self._session_input = 0
        self._session_output = 0
        self._session_cost = 0.0
        self._hour_cost = 0.0
        self._log_path = Path.home() / ".deep6" / "copilot_usage.jsonl"
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def record_usage(self, input_tokens: int, output_tokens: int, model: str) -> None:
        """Record API token usage from a Claude call."""
        self._maybe_reset_hour()
        self._hour_input += input_tokens
        self._hour_output += output_tokens
        self._session_input += input_tokens
        self._session_output += output_tokens
        cost = self._compute_cost(input_tokens, output_tokens, model)
        self._hour_cost += cost
        self._session_cost += cost
        self._write_log(input_tokens, output_tokens, model, cost)

    def get_remaining_budget(self) -> int:
        """Return tokens remaining in current hour budget."""
        self._maybe_reset_hour()
        used = self._hour_input + self._hour_output
        return max(0, self._budget - used)

    def is_within_budget(self) -> bool:
        """Return True if there is budget remaining for another API call."""
        return self.get_remaining_budget() > 0

    def get_hourly_cost(self) -> float:
        """Return estimated cost for the current hour."""
        return self._hour_cost

    def get_session_cost(self) -> float:
        """Return total cost since copilot started."""
        return self._session_cost

    def should_reduce_frequency(self) -> bool:
        """Return True if >80% of budget is used — reduce screenshot frequency."""
        self._maybe_reset_hour()
        used = self._hour_input + self._hour_output
        return used >= self._budget * 0.8

    def _maybe_reset_hour(self) -> None:
        now = time.time()
        if now - self._hour_start >= 3600:
            self._hour_start = now
            self._hour_input = 0
            self._hour_output = 0
            self._hour_cost = 0.0

    def _compute_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        model_lower = model.lower()
        if "opus" in model_lower:
            key = "claude-opus"
        else:
            key = "claude-sonnet"
        in_rate, out_rate = _PRICING[key]
        return (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate

    def _write_log(self, input_tokens: int, output_tokens: int, model: str, cost: float) -> None:
        try:
            entry = {
                "ts": time.time(),
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost,
            }
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as exc:
            logger.warning("budget.log_write_failed error=%s", exc)
