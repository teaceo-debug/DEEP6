from __future__ import annotations

from collections import deque
from datetime import UTC, datetime

import pytest

from deep6v2.signals.trap import TrapDetector
from deep6v2.types.bar import FootprintBar, SessionType
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId
from tests_v2.fixtures.loader import load_signal_fixture


def _bar_from_fixture(name: str) -> FootprintBar:
    data = load_signal_fixture(name)
    return FootprintBar.model_validate(data["bar"])


def _bar_timestamp() -> datetime:
    return datetime(2026, 5, 13, 14, 45, tzinfo=UTC)


def _make_prior_bar(
    *,
    close: float,
    high: float = 21520.0,
    low: float = 21500.0,
    open_: float = 21510.0,
    delta: int = 100,
    total_volume: int = 2000,
) -> FootprintBar:
    return FootprintBar(
        open=open_,
        high=high,
        low=low,
        close=close,
        delta=delta,
        total_volume=total_volume,
        bid_volumes={low: 500, close: 500},
        ask_volumes={high: 500, close: 500},
        poc_price=close,
        poc_volume=500,
        vah=high - 2,
        val=low + 2,
        cvd=50.0,
        bar_index=59,
        timestamp=_bar_timestamp(),
        session_type=SessionType.RTH,
    )


def _ctx(
    *,
    atr: float = 10.0,
    vol_history: list[int] | None = None,
    delta_history: list[int] | None = None,
    cvd_history: list[float] | None = None,
    price_history: list[float] | None = None,
    imbalance_history: list[dict[float, float]] | None = None,
    bar_history: list[FootprintBar] | None = None,
    current_bar: FootprintBar | None = None,
) -> SessionContext:
    return SessionContext(
        atr=atr,
        cvd=0.0,
        vah=21512.0,
        val=21497.0,
        poc=21498.0,
        session_type=SessionType.RTH,
        session_open_bar_index=0,
        current_bar=current_bar,
        vol_history=deque(vol_history or [], maxlen=50),
        delta_history=deque(delta_history or [], maxlen=50),
        cvd_history=deque(cvd_history or [], maxlen=50),
        price_history=deque(price_history or [], maxlen=50),
        imbalance_history=deque(imbalance_history or [], maxlen=50),
        bar_history=deque(bar_history or [], maxlen=50),
    )


# ---------------------------------------------------------------------------
# Disabled-by-default tests
# ---------------------------------------------------------------------------


def test_trap_disabled_by_default():
    """TrapDetector with enabled=False (default) returns empty even with triggering data."""
    bar = _bar_from_fixture("trap_01")
    detector = TrapDetector()
    ctx = _ctx(
        imbalance_history=[{21515.0: 3.0, 21518.0: 3.2}],
        current_bar=bar,
    )
    assert detector.on_bar(bar, ctx) == []


def test_trap_enabled_returns_signals():
    """Same setup with enabled=True produces signals."""
    bar = _bar_from_fixture("trap_01")
    detector = TrapDetector(enabled=True)
    ctx = _ctx(
        imbalance_history=[{21515.0: 3.0, 21518.0: 3.2}],
        current_bar=bar,
    )
    results = detector.on_bar(bar, ctx)
    assert len(results) >= 1
    assert any(r.signal_id is SignalId.TRAP_01 for r in results)


# ---------------------------------------------------------------------------
# TRAP_01 — Inverse Imbalance Trap
# ---------------------------------------------------------------------------


def test_trap01_inverse_imbalance_bearish():
    fixture = load_signal_fixture("trap_01")
    expected = fixture["expected_signal"]
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = TrapDetector(enabled=True)

    ctx = _ctx(
        imbalance_history=[{21515.0: 3.0, 21518.0: 3.2}],
        current_bar=bar,
    )
    results = detector.on_bar(bar, ctx)

    signal = next(r for r in results if r.signal_id is SignalId.TRAP_01)
    assert signal.direction is Direction.BEARISH
    assert signal.flag_bit == SignalFlagBits.TRAP_01
    assert expected["strength_min"] <= signal.strength <= expected["strength_max"]


def test_trap01_no_signal_without_imbalance_history():
    bar = _bar_from_fixture("trap_01")
    detector = TrapDetector(enabled=True)
    ctx = _ctx(current_bar=bar)
    results = detector.on_bar(bar, ctx)
    assert not any(r.signal_id is SignalId.TRAP_01 for r in results)


# ---------------------------------------------------------------------------
# TRAP_02 — Delta Trap
# ---------------------------------------------------------------------------


def test_trap02_delta_trap_bearish():
    fixture = load_signal_fixture("trap_02")
    expected = fixture["expected_signal"]
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = TrapDetector(enabled=True)

    prior_bar = _make_prior_bar(close=21520.0, high=21525.0)
    ctx = _ctx(
        delta_history=[250],
        bar_history=[prior_bar],
        current_bar=bar,
    )
    results = detector.on_bar(bar, ctx)

    signal = next(r for r in results if r.signal_id is SignalId.TRAP_02)
    assert signal.direction is Direction.BEARISH
    assert signal.flag_bit == SignalFlagBits.TRAP_02
    assert expected["strength_min"] <= signal.strength <= expected["strength_max"]


def test_trap02_delta_trap_bullish():
    """Large negative prior delta + price rises → trapped sellers → BULLISH."""
    bar = _bar_from_fixture("trap_02")
    bar = bar.model_copy(update={"close": 21525.0})
    detector = TrapDetector(enabled=True)

    prior_bar = _make_prior_bar(close=21505.0)
    ctx = _ctx(
        delta_history=[-300],
        bar_history=[prior_bar],
        current_bar=bar,
    )
    results = detector.on_bar(bar, ctx)

    signal = next(r for r in results if r.signal_id is SignalId.TRAP_02)
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.TRAP_02


def test_trap02_no_signal_without_history():
    bar = _bar_from_fixture("trap_02")
    detector = TrapDetector(enabled=True)
    ctx = _ctx(current_bar=bar)
    results = detector.on_bar(bar, ctx)
    assert not any(r.signal_id is SignalId.TRAP_02 for r in results)


def test_trap02_no_signal_small_delta():
    """Prior delta below threshold → no TRAP_02."""
    bar = _bar_from_fixture("trap_02")
    detector = TrapDetector(enabled=True)
    prior_bar = _make_prior_bar(close=21520.0)
    ctx = _ctx(
        delta_history=[100],
        bar_history=[prior_bar],
        current_bar=bar,
    )
    results = detector.on_bar(bar, ctx)
    assert not any(r.signal_id is SignalId.TRAP_02 for r in results)


# ---------------------------------------------------------------------------
# TRAP_03 — False Breakout
# ---------------------------------------------------------------------------


def test_trap03_false_breakout_bearish():
    fixture = load_signal_fixture("trap_03")
    expected = fixture["expected_signal"]
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = TrapDetector(enabled=True)

    prior_bar = _make_prior_bar(
        close=21510.0,
        high=float(fixture["context"]["prior_bar_high"]),
        low=float(fixture["context"]["prior_bar_low"]),
    )
    ctx = _ctx(
        atr=fixture["context"]["atr"],
        bar_history=[prior_bar],
        current_bar=bar,
    )
    results = detector.on_bar(bar, ctx)

    signal = next(r for r in results if r.signal_id is SignalId.TRAP_03)
    assert signal.direction is Direction.BEARISH
    assert signal.flag_bit == SignalFlagBits.TRAP_03
    assert expected["strength_min"] <= signal.strength <= expected["strength_max"]


def test_trap03_false_breakout_bullish():
    """Price dips below prior low then closes back above → BULLISH."""
    bar = FootprintBar(
        open=21505.0,
        high=21515.0,
        low=21492.0,
        close=21510.0,
        delta=150,
        total_volume=2500,
        bid_volumes={21492.0: 300, 21495.0: 400, 21500.0: 300},
        ask_volumes={21505.0: 400, 21510.0: 500, 21515.0: 300},
        poc_price=21510.0,
        poc_volume=500,
        vah=21512.0,
        val=21496.0,
        cvd=100.0,
        bar_index=69,
        timestamp=_bar_timestamp(),
        session_type=SessionType.RTH,
    )
    detector = TrapDetector(enabled=True)

    prior_bar = _make_prior_bar(close=21505.0, high=21520.0, low=21495.0)
    ctx = _ctx(atr=10.0, bar_history=[prior_bar], current_bar=bar)
    results = detector.on_bar(bar, ctx)

    signal = next(r for r in results if r.signal_id is SignalId.TRAP_03)
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.TRAP_03
    assert 0.0 < signal.strength <= 1.0


def test_trap03_no_signal_without_bar_history():
    bar = _bar_from_fixture("trap_03")
    detector = TrapDetector(enabled=True)
    ctx = _ctx(current_bar=bar)
    results = detector.on_bar(bar, ctx)
    assert not any(r.signal_id is SignalId.TRAP_03 for r in results)


def test_trap03_no_signal_zero_atr():
    bar = _bar_from_fixture("trap_03")
    detector = TrapDetector(enabled=True)
    prior_bar = _make_prior_bar(close=21510.0, high=21518.0, low=21500.0)
    ctx = _ctx(atr=0.0, bar_history=[prior_bar], current_bar=bar)
    results = detector.on_bar(bar, ctx)
    assert not any(r.signal_id is SignalId.TRAP_03 for r in results)


# ---------------------------------------------------------------------------
# TRAP_04 — High Volume Rejection
# ---------------------------------------------------------------------------


def test_trap04_high_volume_rejection_bearish():
    fixture = load_signal_fixture("trap_04")
    expected = fixture["expected_signal"]
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = TrapDetector(enabled=True)

    ctx = _ctx(
        atr=fixture["context"]["atr"],
        vol_history=fixture["context"]["vol_history"],
        current_bar=bar,
    )
    results = detector.on_bar(bar, ctx)

    signal = next(r for r in results if r.signal_id is SignalId.TRAP_04)
    assert signal.direction is Direction.BEARISH
    assert signal.flag_bit == SignalFlagBits.TRAP_04
    assert expected["strength_min"] <= signal.strength <= expected["strength_max"]


def test_trap04_no_signal_without_vol_history():
    bar = _bar_from_fixture("trap_04")
    detector = TrapDetector(enabled=True)
    ctx = _ctx(current_bar=bar)
    results = detector.on_bar(bar, ctx)
    assert not any(r.signal_id is SignalId.TRAP_04 for r in results)


# ---------------------------------------------------------------------------
# TRAP_05 — CVD Trap
# ---------------------------------------------------------------------------


def test_trap05_cvd_trap_bearish():
    fixture = load_signal_fixture("trap_05")
    expected = fixture["expected_signal"]
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = TrapDetector(enabled=True)

    ctx = _ctx(
        cvd_history=fixture["context"]["cvd_history"],
        price_history=fixture["context"]["price_history"],
        current_bar=bar,
    )
    results = detector.on_bar(bar, ctx)

    signal = next(r for r in results if r.signal_id is SignalId.TRAP_05)
    assert signal.direction is Direction.BEARISH
    assert signal.flag_bit == SignalFlagBits.TRAP_05
    assert expected["strength_min"] <= signal.strength <= expected["strength_max"]


def test_trap05_no_signal_insufficient_cvd_history():
    bar = _bar_from_fixture("trap_05")
    detector = TrapDetector(enabled=True)
    ctx = _ctx(
        cvd_history=[400.0, 500.0],
        price_history=[21510.0, 21500.0],
        current_bar=bar,
    )
    results = detector.on_bar(bar, ctx)
    assert not any(r.signal_id is SignalId.TRAP_05 for r in results)


# ---------------------------------------------------------------------------
# Composite — multiple traps fire together
# ---------------------------------------------------------------------------


def test_trap_composite_multiple_signals():
    fixture = load_signal_fixture("composite_trapped")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = TrapDetector(enabled=True)

    prior_bar = _make_prior_bar(
        close=21518.0,
        high=float(fixture["context"]["prior_bar_high"]),
        low=float(fixture["context"]["prior_bar_low"]),
    )
    ctx = _ctx(
        atr=fixture["context"]["atr"],
        bar_history=[prior_bar],
        delta_history=[280],
        imbalance_history=[{21525.0: 3.1, 21530.0: 3.3}],
        current_bar=bar,
    )
    results = detector.on_bar(bar, ctx)

    fired_ids = {r.signal_id for r in results}
    assert SignalId.TRAP_01 in fired_ids
    assert SignalId.TRAP_02 in fired_ids
    assert SignalId.TRAP_03 in fired_ids

    for r in results:
        assert r.direction is Direction.BEARISH


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


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
        timestamp=_bar_timestamp(),
        session_type=SessionType.RTH,
    )
    detector = TrapDetector(enabled=True)
    assert detector.on_bar(bar, _ctx(current_bar=bar)) == []
