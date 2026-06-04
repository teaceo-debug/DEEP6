from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deep6.copilot import budget as budget_module
from deep6.copilot.budget import TokenBudgetTracker


def test_budget_enforcement_and_status() -> None:
    tracker = TokenBudgetTracker(token_budget_per_hour=100)

    tracker.record_usage(30, 20, call_type="narrative")
    status = tracker.get_status()

    assert status.used_tokens == 50
    assert status.remaining_tokens == 50
    assert status.calls_this_hour == 1
    assert tracker.can_make_call(50) is True


def test_hourly_reset_resets_usage() -> None:
    base = datetime(2026, 5, 12, 10, 5, tzinfo=UTC)

    def fake_now() -> datetime:
        return base

    original_time = budget_module.time.time
    budget_module.time.time = lambda: fake_now().timestamp()
    try:
        tracker = TokenBudgetTracker(token_budget_per_hour=100)
        tracker.record_usage(60, 10, call_type="vision")
        assert tracker.get_status().used_tokens == 70

        budget_module.time.time = lambda: (base + timedelta(hours=1, minutes=1)).timestamp()
        status = tracker.get_status()

        assert status.used_tokens == 0
        assert status.calls_this_hour == 0
        assert tracker.can_make_call(100) is True
    finally:
        budget_module.time.time = original_time


def test_can_make_call_returns_false_when_over_budget() -> None:
    tracker = TokenBudgetTracker(token_budget_per_hour=100)
    tracker.record_usage(80, 10, call_type="narrative")

    assert tracker.can_make_call(20) is False
