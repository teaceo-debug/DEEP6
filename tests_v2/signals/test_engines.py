from __future__ import annotations

from collections import deque
from datetime import UTC, datetime

import pytest

from deep6v2.signals.engines import (
    CounterSpoofDetector,
    IcebergDetector,
    MicroProbDetector,
    RegimeDetector,
    TrespassDetector,
    VPContextDetector,
)
from deep6v2.types.bar import FootprintBar, SessionType
from deep6v2.types.dom import DOMSnapshot
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult
from tests_v2.fixtures.loader import load_signal_fixture


def _bar_from_fixture(name: str) -> FootprintBar:
    data = load_signal_fixture(name)
    return FootprintBar.model_validate(data["bar"])


def _ctx(name: str, *, bar: FootprintBar | None = None) -> SessionContext:
    data = load_signal_fixture(name)
    context = data["context"]
    price_history = context.get("price_history", [])
    return SessionContext(
        atr=context["atr"],
        cvd=context["cvd"],
        vah=context["vah"],
        val=context["val"],
        poc=context["poc"],
        session_type=SessionType(context["session_type"]),
        session_open_bar_index=context["session_open_bar_index"],
        current_bar=bar,
        price_history=deque(price_history, maxlen=50),
        delta_history=deque([], maxlen=50),
        vol_history=deque([], maxlen=50),
    )


def _snapshot(name: str) -> DOMSnapshot:
    data = load_signal_fixture(name)
    snapshot = data["context"]["dom_snapshot"]
    return DOMSnapshot.model_validate(
        {
            "timestamp": bar_timestamp().isoformat(),
            "bids": snapshot["bids"],
            "asks": snapshot["asks"],
        }
    )


def test_eng02_depth_imbalance_uses_recent_snapshot():
    bar = _bar_from_fixture("eng_02")
    detector = TrespassDetector()
    detector.on_depth(_snapshot("eng_02"))

    results = detector.on_bar(bar, _ctx("eng_02", bar=bar))

    assert len(results) == 1
    signal = results[0]
    assert signal.signal_id is SignalId.ENG_02
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.ENG_02
    assert signal.strength == pytest.approx(1 / (1 + 2.718281828459045 ** (-(5 * ((940 - 150) / (940 + 150))))), rel=1e-3)


def test_eng03_spoof_detection_emits_veto():
    detector = CounterSpoofDetector()
    previous = DOMSnapshot.model_validate(
        {
            "timestamp": bar_timestamp().isoformat(),
            "bids": [{"price": 21500.0 - (0.25 * i), "volume": 1200} for i in range(5)],
            "asks": [{"price": 21500.25 + (0.25 * i), "volume": 1200} for i in range(5)],
        }
    )
    current = DOMSnapshot.model_validate(
        {
            "timestamp": bar_timestamp().isoformat(),
            "bids": [{"price": 21500.0 - (0.25 * i), "volume": 50} for i in range(5)],
            "asks": [{"price": 21500.25 + (0.25 * i), "volume": 50} for i in range(5)],
        }
    )
    detector.on_depth(previous)
    detector.on_depth(current)
    bar = _bar_from_fixture("eng_03")

    results = detector.on_bar(bar, _ctx("eng_03", bar=bar))

    assert len(results) == 1
    signal = results[0]
    assert signal.signal_id is SignalId.SPOOF_VETO
    assert signal.direction is Direction.NEUTRAL
    assert signal.flag_bit == SignalFlagBits.ENG_03
    assert signal.strength > 0.6


def test_eng04_iceberg_detects_fill_over_displayed_size():
    bar = _bar_from_fixture("eng_04")
    detector = IcebergDetector()
    detector.on_depth(_snapshot("eng_04"))

    results = detector.on_bar(bar, _ctx("eng_04", bar=bar))

    assert len(results) == 1
    signal = results[0]
    assert signal.signal_id is SignalId.ENG_04
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.ENG_04
    assert signal.price == 21500.0
    assert signal.strength == 1.0


def test_eng04_receives_absorption_zone_notifications():
    bar = _bar_from_fixture("eng_04")
    detector = IcebergDetector()
    detector.on_depth(_snapshot("eng_04"))
    detector.mark_absorption_zone(21500.0, Direction.BEARISH, 0.9)

    results = detector.on_bar(bar, _ctx("eng_04", bar=bar))

    assert len(results) == 1
    assert results[0].direction is Direction.BEARISH


def test_eng05_naive_bayes_with_known_signals():
    bar = _bar_from_fixture("eng_05")
    detector = MicroProbDetector()
    signals = [
        SignalResult(
            signal_id=SignalId.ABS_01,
            direction=Direction.BULLISH,
            strength=0.8,
            detail="abs",
            price=bar.low,
            flag_bit=SignalFlagBits.ABS_01,
        ),
        SignalResult(
            signal_id=SignalId.IMB_03,
            direction=Direction.BULLISH,
            strength=0.7,
            detail="imb",
            price=bar.close,
            flag_bit=SignalFlagBits.IMB_03,
        ),
        SignalResult(
            signal_id=SignalId.DELT_01,
            direction=Direction.BULLISH,
            strength=0.6,
            detail="delt",
            price=bar.close,
            flag_bit=SignalFlagBits.DELT_01,
        ),
    ]

    results = detector.evaluate(bar, _ctx("eng_05", bar=bar), signals)

    assert len(results) == 1
    signal = results[0]
    assert signal.signal_id is SignalId.ENG_05
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.ENG_05
    assert signal.strength == pytest.approx((0.65 * 0.55 * 0.5) / ((0.65 * 0.55 * 0.5) + (0.35 * 0.45 * 0.5)))


def test_eng06_zone_proximity_detection():
    bar = _bar_from_fixture("eng_06")
    detector = VPContextDetector()

    results = detector.on_bar(bar, _ctx("eng_06", bar=bar))

    assert len(results) == 1
    signal = results[0]
    assert signal.signal_id is SignalId.ENG_06
    assert signal.direction is Direction.BEARISH
    assert signal.flag_bit == SignalFlagBits.ENG_06
    assert signal.price == 21518.0
    assert signal.strength == 1.0


def test_eng07_regime_change_emission():
    bar = _bar_from_fixture("eng_07")
    ctx = _ctx("eng_07", bar=bar)
    ctx.price_history = deque([21480.0, 21490.0, 21500.0, 21510.0], maxlen=50)
    ctx.delta_history = deque([200, 220, 210, 230], maxlen=50)
    detector = RegimeDetector()

    assert detector.on_bar(bar, ctx) == []

    ctx.price_history = deque([21510.0, 21511.0, 21510.5, 21511.5, 21511.0, 21510.75], maxlen=50)
    ctx.delta_history = deque([20, -15, 10, -10, 5, -5, 8, -7, 6], maxlen=50)
    results = detector.on_bar(bar, ctx)

    assert len(results) == 1
    signal = results[0]
    assert signal.signal_id is SignalId.REGIME_CHANGE
    assert signal.direction is Direction.NEUTRAL
    assert signal.flag_bit == SignalFlagBits.ENG_07
    assert 0.0 <= signal.strength <= 1.0


def bar_timestamp() -> datetime:
    return datetime(2026, 5, 14, 14, 0, tzinfo=UTC)
