from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta

import pytest

from deep6v2.signals.exhaustion import ExhaustionDetector
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
    bar_history: list[FootprintBar] | None = None,
    price_history: list[float] | None = None,
    delta_history: list[int] | None = None,
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
        bar_history=deque(bar_history or [], maxlen=50),
        price_history=deque(price_history or [], maxlen=50),
        delta_history=deque(delta_history or [], maxlen=50),
        vol_history=deque(vol_history or [], maxlen=50),
    )


def _signal(results: list, signal_id: SignalId):
    return next(result for result in results if result.signal_id is signal_id)


def _assert_fixture_strength(signal, fixture: dict) -> None:
    expected = fixture["expected_signal"]
    assert signal.strength == pytest.approx(expected["strength_min"], abs=0.15) or (
        expected["strength_min"] - 0.01 <= signal.strength <= expected["strength_max"] + 0.01
    )


def test_exh01_zero_print_at_high_bearish():
    fixture = load_signal_fixture("exh_01")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = ExhaustionDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    assert len(results) >= 1
    signal = _signal(results, SignalId.EXH_01)
    assert signal.direction is Direction.BEARISH
    assert signal.flag_bit == SignalFlagBits.EXH_01
    assert signal.price == bar.high
    assert "Zero print" in signal.detail
    assert fixture["expected_signal"]["strength_min"] - 0.01 <= signal.strength <= fixture["expected_signal"]["strength_max"] + 0.01


def test_exh01_zero_print_at_bottom_bullish():
    bar = FootprintBar(
        open=21500.0,
        high=21510.0,
        low=21490.0,
        close=21502.0,
        delta=40,
        total_volume=1800,
        bid_volumes={21492.0: 150, 21495.0: 250, 21500.0: 350, 21505.0: 250, 21510.0: 120},
        ask_volumes={21495.0: 160, 21500.0: 280, 21505.0: 200, 21508.0: 100, 21510.0: 80},
        poc_price=21500.0,
        poc_volume=630,
        vah=21506.0,
        val=21494.0,
        cvd=110.0,
        bar_index=5,
        timestamp=bar_timestamp(),
        session_type=SessionType.RTH,
    )
    detector = ExhaustionDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    signal = _signal(results, SignalId.EXH_01)
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.EXH_01
    assert signal.price == bar.low
    assert signal.strength >= 0.4


def test_exh02_exhaustion_print_bearish():
    fixture = load_signal_fixture("exh_02")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = ExhaustionDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    signal = _signal(results, SignalId.EXH_02)
    assert signal.direction is Direction.BEARISH
    assert signal.flag_bit == SignalFlagBits.EXH_02
    assert signal.price == bar.high
    assert fixture["expected_signal"]["strength_min"] - 0.01 <= signal.strength <= fixture["expected_signal"]["strength_max"] + 0.01


def test_exh03_thin_print_bearish():
    fixture = load_signal_fixture("exh_03")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = ExhaustionDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    signal = _signal(results, SignalId.EXH_03)
    assert signal.direction is Direction.BEARISH
    assert signal.flag_bit == SignalFlagBits.EXH_03
    assert signal.price == bar.high
    assert fixture["expected_signal"]["strength_min"] - 0.01 <= signal.strength <= fixture["expected_signal"]["strength_max"] + 0.01


def test_exh04_fat_print_neutral():
    fixture = load_signal_fixture("exh_04")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = ExhaustionDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    signal = _signal(results, SignalId.EXH_04)
    assert signal.direction is Direction.NEUTRAL
    assert signal.flag_bit == SignalFlagBits.EXH_04
    assert signal.price == 21500.0
    assert fixture["expected_signal"]["strength_min"] - 0.01 <= signal.strength <= fixture["expected_signal"]["strength_max"] + 0.01


def test_exh05_fading_momentum_bearish():
    fixture = load_signal_fixture("exh_05")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = ExhaustionDetector()

    results = detector.on_bar(
        bar,
        _ctx(
            current_bar=bar,
            price_history=fixture["context"]["price_history"],
            delta_history=fixture["context"]["delta_history"],
        ),
    )

    signal = _signal(results, SignalId.EXH_05)
    assert signal.direction is Direction.BEARISH
    assert signal.flag_bit == SignalFlagBits.EXH_05
    assert signal.price == fixture["context"]["price_history"][-1]
    assert fixture["expected_signal"]["strength_min"] - 0.01 <= signal.strength <= fixture["expected_signal"]["strength_max"] + 0.01


def test_exh06_ask_fade_bearish():
    fixture = load_signal_fixture("exh_06")
    bar = FootprintBar.model_validate(fixture["bar"])
    prior_same_high = _history_bar(high=21518.0, low=21509.0, ask_at_high=250, bid_at_low=130, bar_index=59)
    older = _history_bar(high=21520.0, low=21510.0, ask_at_high=400, bid_at_low=150, bar_index=58)
    detector = ExhaustionDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar, bar_history=[older, prior_same_high]))

    signal = _signal(results, SignalId.EXH_06)
    assert signal.direction is Direction.BEARISH
    assert signal.flag_bit == SignalFlagBits.EXH_06
    assert signal.price == bar.high
    assert fixture["expected_signal"]["strength_min"] - 0.01 <= signal.strength <= fixture["expected_signal"]["strength_max"] + 0.01


def test_delta_gate_suppresses_all_exhaustion_signals():
    bar = _bar_from_fixture("exh_01").model_copy(update={"delta": 1600})
    detector = ExhaustionDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    assert results == []


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
    detector = ExhaustionDetector()

    assert detector.on_bar(bar, _ctx(current_bar=bar)) == []


def _history_bar(*, high: float, low: float, ask_at_high: int, bid_at_low: int, bar_index: int) -> FootprintBar:
    return FootprintBar(
        open=low + 2.0,
        high=high,
        low=low,
        close=low + 4.0,
        delta=20,
        total_volume=1200,
        bid_volumes={low: bid_at_low, low + 2.0: 180, low + 4.0: 160},
        ask_volumes={low + 2.0: 170, low + 4.0: 160, high: ask_at_high},
        poc_price=low + 2.0,
        poc_volume=350,
        vah=high - 1.0,
        val=low + 1.0,
        cvd=150.0,
        bar_index=bar_index,
        timestamp=bar_timestamp() - timedelta(minutes=60 - bar_index),
        session_type=SessionType.RTH,
    )


def bar_timestamp():
    return datetime(2026, 5, 14, 14, 0, tzinfo=UTC)
