from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deep6.copilot.freshness import FreshnessTracker


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def test_source_is_not_stale_right_after_update() -> None:
    base = datetime(2026, 5, 12, 12, 0, tzinfo=UTC)
    clock = _Clock(base)
    tracker = FreshnessTracker(clock=clock)

    tracker.record_update("news")

    status = tracker.get_status("news")
    assert status is not None
    assert status.last_update == base
    assert status.is_stale is False


def test_source_becomes_stale_after_two_times_interval() -> None:
    base = datetime(2026, 5, 12, 12, 0, tzinfo=UTC)
    clock = _Clock(base)
    tracker = FreshnessTracker(clock=clock)
    tracker.register_source("custom", 10)
    tracker.record_update("custom")

    clock.now = base + timedelta(seconds=21)

    assert tracker.is_stale("custom") is True
    status = tracker.get_status("custom")
    assert status is not None
    assert status.is_stale is True


def test_error_is_tracked_and_propagated_in_status() -> None:
    base = datetime(2026, 5, 12, 12, 0, tzinfo=UTC)
    clock = _Clock(base)
    tracker = FreshnessTracker(clock=clock)

    tracker.record_update("calendar", error="feed down")

    status = tracker.get_status("calendar")
    assert status is not None
    assert status.error == "feed down"
    assert status.last_update == base
    assert status.is_stale is False
