from __future__ import annotations

from collections import deque

import pytest

from deep6v2.types.bar import FootprintBar, SessionType
from deep6v2.types.interfaces import IAbsorptionZoneReceiver
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId
from tests_v2.fixtures.loader import load_signal_fixture

from deep6v2.signals.absorption import AbsorptionDetector


def _bar_from_fixture(name: str) -> FootprintBar:
    data = load_signal_fixture(name)
    return FootprintBar.model_validate(data["bar"])


def _ctx(
    *,
    atr: float = 10.0,
    vol_history: list[int] | None = None,
    current_bar: FootprintBar | None = None,
) -> SessionContext:
    return SessionContext(
        atr=atr,
        cvd=0.0,
        vah=21500.0,
        val=21480.0,
        poc=21490.0,
        session_type=SessionType.RTH,
        session_open_bar_index=0,
        current_bar=current_bar,
        vol_history=deque(vol_history or [], maxlen=50),
    )


class RecordingReceiver(IAbsorptionZoneReceiver):
    def __init__(self) -> None:
        self.calls: list[tuple[float, Direction, float]] = []

    def mark_absorption_zone(self, price: float, direction: Direction, strength: float) -> None:
        self.calls.append((price, direction, strength))


class ExplodingReceiver(IAbsorptionZoneReceiver):
    def mark_absorption_zone(self, price: float, direction: Direction, strength: float) -> None:
        raise RuntimeError("boom")


def test_abs01_low_wick_bullish():
    bar = _bar_from_fixture("abs_01")
    bar = bar.model_copy(update={"delta": -150})
    detector = AbsorptionDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    assert len(results) == 1
    signal = results[0]
    assert signal.signal_id is SignalId.ABS_01
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.ABS_01
    assert signal.price == bar.low
    assert signal.strength == pytest.approx(1930 / 3200)
    assert "Low wick absorption" in signal.detail


def test_abs01_high_wick_bearish():
    bar = FootprintBar(
        open=21490.0,
        high=21500.0,
        low=21480.0,
        close=21486.0,
        delta=80,
        total_volume=2000,
        bid_volumes={21480.0: 120, 21485.0: 180, 21490.0: 150},
        ask_volumes={21496.5: 250, 21497.0: 250, 21498.0: 200, 21499.0: 200, 21500.0: 100},
        poc_price=21498.0,
        poc_volume=450,
        vah=21498.0,
        val=21484.0,
        cvd=25.0,
        bar_index=21,
        timestamp=bar_timestamp(),
        session_type=SessionType.RTH,
    )
    detector = AbsorptionDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    assert len(results) == 1
    signal = results[0]
    assert signal.signal_id is SignalId.ABS_01
    assert signal.direction is Direction.BEARISH
    assert signal.flag_bit == SignalFlagBits.ABS_01
    assert signal.price == bar.high
    assert signal.strength == pytest.approx(1000 / 2000)
    assert "High wick absorption" in signal.detail


def test_abs01_no_signal_when_delta_not_neutral():
    bar = _bar_from_fixture("abs_01")
    bar = bar.model_copy(update={"delta": -500})
    detector = AbsorptionDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    assert results == []


def test_abs02_passive_bullish():
    bar = _bar_from_fixture("abs_02")
    detector = AbsorptionDetector()

    results = detector.on_bar(bar, _ctx(vol_history=[900, 1000, 1100], current_bar=bar))

    signal = next(result for result in results if result.signal_id is SignalId.ABS_02)
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.ABS_02
    assert signal.price == bar.low
    assert signal.strength == 1.0


def test_abs03_stopping_volume_at_low():
    bar = _bar_from_fixture("abs_03")
    detector = AbsorptionDetector()

    results = detector.on_bar(bar, _ctx(vol_history=[2000, 2100, 2200], current_bar=bar))

    signal = next(result for result in results if result.signal_id is SignalId.ABS_03)
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.ABS_03
    assert signal.price == bar.low
    assert signal.strength == pytest.approx(750 / 3800)


def test_abs04_effort_vs_result():
    bar = _bar_from_fixture("abs_04")
    detector = AbsorptionDetector()

    results = detector.on_bar(bar, _ctx(atr=12.0, vol_history=[2200, 2400, 2600], current_bar=bar))

    signal = next(result for result in results if result.signal_id is SignalId.ABS_04)
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.ABS_04
    assert signal.price == bar.low
    assert signal.strength == 1.0


def test_absorption_zone_notification_fires():
    bar = _bar_from_fixture("abs_01")
    bar = bar.model_copy(update={"delta": -150})
    receiver = RecordingReceiver()
    detector = AbsorptionDetector(receivers=[ExplodingReceiver(), receiver])

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    assert any(result.signal_id is SignalId.ABS_01 for result in results)
    assert receiver.calls == [(bar.low, Direction.BULLISH, pytest.approx(1930 / 3200))]


def test_no_signal_empty_bar():
    bar = FootprintBar(
        open=21490.0,
        high=21490.0,
        low=21490.0,
        close=21490.0,
        delta=0,
        total_volume=0,
        bid_volumes={},
        ask_volumes={},
        poc_price=21490.0,
        poc_volume=0,
        vah=21490.0,
        val=21490.0,
        cvd=0.0,
        bar_index=0,
        timestamp=bar_timestamp(),
        session_type=SessionType.RTH,
    )
    detector = AbsorptionDetector()

    assert detector.on_bar(bar, _ctx(current_bar=bar)) == []


def bar_timestamp():
    from datetime import UTC, datetime

    return datetime(2026, 5, 14, 14, 0, tzinfo=UTC)
