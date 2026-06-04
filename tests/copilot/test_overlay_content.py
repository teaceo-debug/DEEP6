"""Tests for OverlayContentRenderer."""

from __future__ import annotations

import asyncio

import pytest

from deep6.copilot.overlay_content import OverlayContentRenderer
from deep6.copilot.types import CalendarEvent, DataSourceStatus, MADLevel, TradeCall


# ── Fakes ────────────────────────────────────────────────────────────────


class FakeOverlay:
    """Records overlay update calls for assertions."""

    def __init__(self) -> None:
        self.narratives: list[str] = []
        self.trade_calls: list[TradeCall | None] = []
        self.source_statuses: list[list[DataSourceStatus]] = []
        self.countdowns: list[list[CalendarEvent]] = []

    def update_narrative(self, text: str) -> None:
        self.narratives.append(text)

    def update_trade_call(self, call: TradeCall | None) -> None:
        self.trade_calls.append(call)

    def update_source_status(self, statuses: list[DataSourceStatus]) -> None:
        self.source_statuses.append(statuses)

    def update_countdowns(self, events: list[CalendarEvent]) -> None:
        self.countdowns.append(events)


class FakeNarrativeEngine:
    """Stores callbacks and allows manual dispatch."""

    def __init__(self) -> None:
        self._callbacks: list = []

    def on_narrative_complete(self, cb):
        self._callbacks.append(cb)

    def fire(self, text: str) -> None:
        for cb in self._callbacks:
            cb(text)


class FakeTradeCallEngine:
    """Stores callbacks and allows manual dispatch."""

    def __init__(self) -> None:
        self._callbacks: list = []

    def on_trade_call(self, cb):
        self._callbacks.append(cb)

    def fire(self, call: TradeCall) -> None:
        for cb in self._callbacks:
            cb(call)


class FakeFreshnessTracker:
    """Returns canned statuses."""

    def __init__(self, statuses: list[DataSourceStatus] | None = None) -> None:
        self._statuses = statuses or []

    def get_status_all(self) -> list[DataSourceStatus]:
        return list(self._statuses)


class FakeCalendarAdapter:
    """Returns canned upcoming events."""

    def __init__(self, events: list[CalendarEvent] | None = None) -> None:
        self._events = events or []

    def get_upcoming(self, minutes: int = 60) -> list[CalendarEvent]:
        return list(self._events)


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_narrative_formatted_and_sent_to_overlay():
    """Narrative text is truncated at sentence boundary and forwarded."""
    overlay = FakeOverlay()
    narr_engine = FakeNarrativeEngine()
    trade_engine = FakeTradeCallEngine()
    freshness = FakeFreshnessTracker()

    renderer = OverlayContentRenderer(
        overlay=overlay,
        narrative_engine=narr_engine,
        trade_engine=trade_engine,
        freshness_tracker=freshness,
    )
    await renderer.start()

    # Short text — should pass through unchanged
    narr_engine.fire("Market is quiet.")
    assert overlay.narratives == ["Market is quiet."]

    # Long text — should truncate at sentence boundary
    long_text = (
        "NQ absorption detected at 18,450. "
        "Delta reversed sharply lower. "
        "Volume profile shows a ledge forming. "
        + "x" * 300
    )
    narr_engine.fire(long_text)
    last = overlay.narratives[-1]
    assert len(last) <= 305  # some tolerance for the "..." suffix
    # Should end at a sentence boundary or with ellipsis
    assert last.endswith(".") or last.endswith("...")

    # History capped at 3
    narr_engine.fire("Third entry.")
    narr_engine.fire("Fourth entry — pushes first out.")
    assert len(renderer._narrative_history) == 3

    await renderer.stop()


@pytest.mark.asyncio
async def test_trade_call_displayed_and_auto_cleared():
    """Trade call is sent to overlay and cleared after timeout."""
    overlay = FakeOverlay()
    narr_engine = FakeNarrativeEngine()
    trade_engine = FakeTradeCallEngine()
    freshness = FakeFreshnessTracker()

    renderer = OverlayContentRenderer(
        overlay=overlay,
        narrative_engine=narr_engine,
        trade_engine=trade_engine,
        freshness_tracker=freshness,
    )
    await renderer.start()

    call = TradeCall(
        direction="LONG",
        entry=18445,
        stop=18430,
        target=18490,
        confidence=85,
        mad_levels=(MADLevel(price=18450, label="MAD R1"),),
        rationale="Strong absorption at support",
    )
    trade_engine.fire(call)

    # Trade call sent to overlay
    assert len(overlay.trade_calls) == 1
    assert overlay.trade_calls[0] is call

    # Format helper produces expected string
    display = OverlayContentRenderer._format_trade_call_display(call)
    assert "LONG @ 18,445" in display
    assert "Stop: 18,430" in display
    assert "Target: 18,490" in display
    assert "Conf: 85%" in display
    assert "MAD R1 (18,450)" in display

    # Auto-clear fires after delay — use short delay to test
    renderer._clear_task.cancel()  # cancel the 600s timer
    renderer._clear_task = asyncio.get_running_loop().create_task(
        renderer._auto_clear_trade_call(delay_sec=0),
    )
    await asyncio.sleep(0.05)

    assert overlay.trade_calls[-1] is None  # cleared

    await renderer.stop()


@pytest.mark.asyncio
async def test_status_refresh_updates_source_status():
    """Status refresh loop pushes freshness and calendar to overlay."""
    statuses = [
        DataSourceStatus(source_name="bridge_tcp", is_stale=False),
        DataSourceStatus(source_name="calendar", is_stale=True, error="timeout"),
    ]
    events = [CalendarEvent(name="CPI", time="10:30", impact="high")]

    overlay = FakeOverlay()
    narr_engine = FakeNarrativeEngine()
    trade_engine = FakeTradeCallEngine()
    freshness = FakeFreshnessTracker(statuses)
    calendar = FakeCalendarAdapter(events)

    renderer = OverlayContentRenderer(
        overlay=overlay,
        narrative_engine=narr_engine,
        trade_engine=trade_engine,
        freshness_tracker=freshness,
        calendar_adapter=calendar,
    )
    await renderer.start()

    # Let the refresh loop run at least once
    await asyncio.sleep(0.1)

    assert len(overlay.source_statuses) >= 1
    assert overlay.source_statuses[0] == statuses

    assert len(overlay.countdowns) >= 1
    assert overlay.countdowns[0] == events

    await renderer.stop()
