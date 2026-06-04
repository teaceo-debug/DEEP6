from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from deep6v2.clock import EventClock
from deep6v2.data.bar_builder import BarBuilder
from deep6v2.data.tick_classifier import AggressorSide, ClassifiedTick
from deep6v2.types.bar import SessionType


ET = ZoneInfo("America/New_York")


def make_rth_time(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 5, 13, hour, minute, second, tzinfo=ET)


def make_tick(price: float, size: int, aggressor: AggressorSide, clock: EventClock) -> ClassifiedTick:
    return ClassifiedTick(price=price, size=size, timestamp=clock.now(), aggressor=aggressor)


def test_bar_boundary_at_minute_mark() -> None:
    """Bar closes at minute boundary, new bar starts on next tick."""
    clock = EventClock()
    bars = []

    builder = BarBuilder(clock=clock, on_bar_close=lambda b, ctx: bars.append(b))

    clock.advance(make_rth_time(9, 30, 0))
    builder.on_tick(make_tick(21450.0, 100, AggressorSide.BUY, clock))

    clock.advance(make_rth_time(9, 30, 30))
    builder.on_tick(make_tick(21451.0, 50, AggressorSide.SELL, clock))

    assert len(bars) == 0

    clock.advance(make_rth_time(9, 31, 0))
    builder.on_tick(make_tick(21452.0, 80, AggressorSide.BUY, clock))

    assert len(bars) == 1
    bar0 = bars[0]
    assert bar0.open == 21450.0
    assert bar0.high == 21451.0
    assert bar0.low == 21450.0
    assert bar0.close == 21451.0
    assert bar0.total_volume == 150
    assert bar0.bar_index == 0


def test_poc_is_max_volume_level() -> None:
    """POC = price level with highest total volume."""
    clock = EventClock()
    bars = []

    builder = BarBuilder(clock=clock, on_bar_close=lambda b, ctx: bars.append(b))

    clock.advance(make_rth_time(9, 30, 0))
    builder.on_tick(make_tick(21450.0, 500, AggressorSide.BUY, clock))
    builder.on_tick(make_tick(21450.25, 300, AggressorSide.SELL, clock))
    builder.on_tick(make_tick(21449.75, 200, AggressorSide.SELL, clock))

    clock.advance(make_rth_time(9, 31, 0))
    builder.on_tick(make_tick(21450.0, 1, AggressorSide.BUY, clock))

    assert len(bars) == 1
    assert bars[0].poc_price == 21450.0


def test_rth_gating_rejects_premarket() -> None:
    """Pre-market ticks (before 9:30 ET) are rejected."""
    clock = EventClock()
    bars = []

    builder = BarBuilder(clock=clock, on_bar_close=lambda b, ctx: bars.append(b))

    clock.advance(make_rth_time(9, 0, 0))
    builder.on_tick(make_tick(21450.0, 100, AggressorSide.BUY, clock))

    clock.advance(make_rth_time(9, 30, 0))
    builder.on_tick(make_tick(21451.0, 50, AggressorSide.BUY, clock))

    assert len(bars) == 0


def test_cvd_accumulates_across_session() -> None:
    """CVD accumulates across bars within a session."""
    clock = EventClock()
    bars = []

    builder = BarBuilder(clock=clock, on_bar_close=lambda b, ctx: bars.append(b))

    clock.advance(make_rth_time(9, 30, 0))
    builder.on_tick(make_tick(21450.0, 100, AggressorSide.BUY, clock))

    clock.advance(make_rth_time(9, 31, 0))
    builder.on_tick(make_tick(21451.0, 50, AggressorSide.SELL, clock))

    clock.advance(make_rth_time(9, 32, 0))
    builder.on_tick(make_tick(21451.0, 1, AggressorSide.BUY, clock))

    assert len(bars) == 2
    assert bars[0].cvd == 100.0
    assert bars[1].cvd == 50.0


def test_unspecified_ticks_total_volume_only() -> None:
    """UNSPECIFIED ticks count in total_volume but not bid/ask volumes."""
    clock = EventClock()
    bars = []

    builder = BarBuilder(clock=clock, on_bar_close=lambda b, ctx: bars.append(b))

    clock.advance(make_rth_time(9, 30, 0))
    builder.on_tick(make_tick(21450.0, 100, AggressorSide.UNSPECIFIED, clock))

    clock.advance(make_rth_time(9, 31, 0))
    builder.on_tick(make_tick(21450.0, 1, AggressorSide.BUY, clock))

    assert len(bars) == 1
    bar = bars[0]
    assert bar.total_volume == 100
    assert bar.delta == 0
    assert sum(bar.bid_volumes.values()) == 0
    assert sum(bar.ask_volumes.values()) == 0


def test_value_area_70_percent() -> None:
    """Value Area contains at least 70% of total volume."""
    clock = EventClock()
    bars = []

    builder = BarBuilder(clock=clock, on_bar_close=lambda b, ctx: bars.append(b))

    clock.advance(make_rth_time(9, 30, 0))
    for _ in range(500):
        builder.on_tick(make_tick(21450.0, 1, AggressorSide.BUY, clock))
    for _ in range(300):
        builder.on_tick(make_tick(21450.25, 1, AggressorSide.BUY, clock))
    for _ in range(100):
        builder.on_tick(make_tick(21450.50, 1, AggressorSide.BUY, clock))
    for _ in range(200):
        builder.on_tick(make_tick(21449.75, 1, AggressorSide.SELL, clock))

    clock.advance(make_rth_time(9, 31, 0))
    builder.on_tick(make_tick(21450.0, 1, AggressorSide.BUY, clock))

    assert len(bars) == 1
    bar = bars[0]
    total_vol = bar.total_volume
    va_prices = [
        price
        for price in (bar.bid_volumes.keys() | bar.ask_volumes.keys())
        if bar.val <= price <= bar.vah
    ]
    va_vol = sum(bar.bid_volumes.get(price, 0) + bar.ask_volumes.get(price, 0) for price in va_prices)
    assert va_vol >= total_vol * 0.70


def test_session_context_updates_and_session_resets_on_rth_open() -> None:
    """Bar close updates session context and next-day RTH open resets session CVD/type."""
    clock = EventClock()
    callbacks: list[tuple[object, object]] = []

    builder = BarBuilder(clock=clock, on_bar_close=lambda b, ctx: callbacks.append((b, ctx)))

    clock.advance(make_rth_time(9, 30, 0))
    builder.on_tick(make_tick(21450.0, 10, AggressorSide.BUY, clock))

    clock.advance(make_rth_time(9, 31, 0))
    builder.on_tick(make_tick(21450.25, 5, AggressorSide.BUY, clock))

    assert len(callbacks) == 1
    bar0, ctx0 = callbacks[0]
    assert bar0.session_type == SessionType.RTH
    assert ctx0.current_bar == bar0
    assert ctx0.cvd == 10.0
    assert list(ctx0.price_history) == [21450.0]
    assert list(ctx0.cvd_history) == [10.0]
    assert list(ctx0.delta_history) == [10]
    assert list(ctx0.poc_history) == [21450.0]
    assert list(ctx0.vol_history) == [10]

    clock.advance(datetime(2026, 5, 14, 9, 30, 0, tzinfo=ET))
    builder.on_tick(make_tick(21500.0, 20, AggressorSide.SELL, clock))
    clock.advance(datetime(2026, 5, 14, 9, 31, 0, tzinfo=ET))
    builder.on_tick(make_tick(21499.75, 1, AggressorSide.BUY, clock))

    assert len(callbacks) == 2
    bar1, ctx1 = callbacks[1]
    assert bar1.session_type == SessionType.RTH
    assert bar1.cvd == -20.0
    assert ctx1.session_open_bar_index == 0
    assert ctx1.session_type == SessionType.RTH
    assert list(ctx1.cvd_history) == [-20.0]
