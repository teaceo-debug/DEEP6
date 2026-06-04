from __future__ import annotations

from collections import deque

import pytest

from deep6v2.config.signals import SignalConfig
from deep6v2.signals.vol_patterns import VolPatternDetector
from deep6v2.types.bar import FootprintBar, SessionType
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId
from tests_v2.fixtures.loader import load_signal_fixture


def _bar_from_fixture(name: str) -> FootprintBar:
    data = load_signal_fixture(name)
    return FootprintBar.model_validate(data["bar"])


def _ctx(
    *,
    atr: float = 10.0,
    vol_history: list[int] | None = None,
    poc_history: list[float] | None = None,
    delta_history: list[int] | None = None,
    bar_history: list[FootprintBar] | None = None,
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
        poc_history=deque(poc_history or [], maxlen=50),
        delta_history=deque(delta_history or [], maxlen=50),
        bar_history=deque(bar_history or [], maxlen=50),
    )


def _historical_bar(base: FootprintBar, *, open: float, close: float, total_volume: int, poc_price: float) -> FootprintBar:
    return base.model_copy(
        update={
            "open": open,
            "close": close,
            "high": max(open, close) + 1.0,
            "low": min(open, close) - 1.0,
            "total_volume": total_volume,
            "poc_price": poc_price,
        }
    )


def _signal(results, signal_id: SignalId):
    return next(result for result in results if result.signal_id is signal_id)


def test_volp01_volume_sequencing_bullish():
    bar = _bar_from_fixture("volp_01")
    detector = VolPatternDetector()
    prev_1 = _historical_bar(bar, open=21495.0, close=21502.0, total_volume=3000, poc_price=21500.0)
    prev_2 = _historical_bar(bar, open=21502.0, close=21508.0, total_volume=3400, poc_price=21504.0)

    results = detector.on_bar(
        bar,
        _ctx(vol_history=[3000, 3400], bar_history=[prev_1, prev_2], current_bar=bar),
    )

    signal = _signal(results, SignalId.VOLP_01)
    assert signal.signal_id is SignalId.VOLP_01
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.VOLP_01
    assert signal.price == bar.close
    assert signal.strength == pytest.approx((3800 / 3000) - 1.0)
    assert "Volume sequencing" in signal.detail


def test_volp02_volume_bubble_bearish():
    bar = _bar_from_fixture("volp_02")
    bar = bar.model_copy(update={"total_volume": 4200})
    detector = VolPatternDetector()

    results = detector.on_bar(bar, _ctx(vol_history=[900, 1000, 800], current_bar=bar))

    signal = _signal(results, SignalId.VOLP_02)
    assert signal.signal_id is SignalId.VOLP_02
    assert signal.direction is Direction.BEARISH
    assert signal.flag_bit == SignalFlagBits.VOLP_02
    assert signal.price == bar.close
    assert signal.strength == 1.0
    assert "Volume bubble" in signal.detail


def test_volp03_volume_surge_bullish():
    bar = _bar_from_fixture("volp_03")
    detector = VolPatternDetector()

    results = detector.on_bar(bar, _ctx(vol_history=[1300, 1500, 1600], current_bar=bar))

    signal = _signal(results, SignalId.VOLP_03)
    assert signal.signal_id is SignalId.VOLP_03
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.VOLP_03
    assert signal.price == bar.close
    assert signal.strength == 1.0
    assert "Volume surge" in signal.detail


def test_volp04_poc_momentum_wave_bullish():
    bar = _bar_from_fixture("volp_04")
    detector = VolPatternDetector()

    results = detector.on_bar(bar, _ctx(atr=20.0, poc_history=[21516.0, 21518.0, 21521.0], current_bar=bar))

    signal = _signal(results, SignalId.VOLP_04)
    assert signal.signal_id is SignalId.VOLP_04
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.VOLP_04
    assert signal.price == bar.poc_price
    assert signal.strength == pytest.approx((21525.0 - 21516.0) / 20.0)
    assert "POC momentum wave" in signal.detail


def test_volp05_delta_velocity_spike_bullish():
    bar = _bar_from_fixture("volp_05")
    detector = VolPatternDetector()

    results = detector.on_bar(bar, _ctx(delta_history=[100, 200], current_bar=bar))

    signal = _signal(results, SignalId.VOLP_05)
    assert signal.signal_id is SignalId.VOLP_05
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.VOLP_05
    assert signal.price == bar.close
    assert signal.strength == pytest.approx(350 / 400)
    assert "Delta velocity spike" in signal.detail


def test_volp06_big_delta_per_level_bullish():
    bar = _bar_from_fixture("volp_06")
    detector = VolPatternDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    signal = _signal(results, SignalId.VOLP_06)
    assert signal.signal_id is SignalId.VOLP_06
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.VOLP_06
    assert signal.price == 21505.0
    assert signal.strength == 1.0
    assert "Big delta per level" in signal.detail


def test_no_signal_when_insufficient_history():
    bar = _bar_from_fixture("volp_01")
    bar = bar.model_copy(
        update={
            "ask_volumes": {21500.0: 250, 21505.0: 350, 21508.0: 400, 21510.0: 300, 21512.0: 250, 21515.0: 200},
            "bid_volumes": {21498.0: 100, 21500.0: 200, 21505.0: 300, 21508.0: 250, 21510.0: 200, 21512.0: 200},
        }
    )
    detector = VolPatternDetector()

    assert detector.on_bar(bar, _ctx(current_bar=bar)) == []


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
    detector = VolPatternDetector(config=SignalConfig())

    assert detector.on_bar(bar, _ctx(current_bar=bar)) == []


def bar_timestamp():
    from datetime import UTC, datetime

    return datetime(2026, 5, 14, 14, 0, tzinfo=UTC)
