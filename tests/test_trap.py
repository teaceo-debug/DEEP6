"""Tests for TrapEngine — TRAP-01..05 (trapped trader signal variants).

TRAP-01 (INVERSE_TRAP) is already implemented in deep6/engines/imbalance.py
as ImbalanceType.INVERSE_TRAP. It is tested in test_imbalance.py::test_inverse_trap.
Cross-reference: see tests/test_imbalance.py for TRAP-01 coverage.

This file covers TRAP-02..05 using synthetic FootprintBar data (offline, no Rithmic).

Requirement coverage:
  TRAP-01 — cross-reference to test_imbalance.py (INVERSE_TRAP)
  TRAP-02 — delta trap: prior strong directional delta reverses on current bar
  TRAP-03 — false breakout: bar breaks prior extreme then closes back inside
  TRAP-04 — high volume rejection: high-vol bar with dominant wick rejection
  TRAP-05 — CVD trap: cumulative volume delta trend reverses direction
"""
from __future__ import annotations

from collections import defaultdict

import pytest

from deep6.engines.trap import TrapEngine, TrapSignal, TrapType
from deep6.state.footprint import FootprintBar, FootprintLevel, price_to_tick


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_footprint_bar(
    open_: float = 21000.0,
    close: float = 21000.0,
    high: float = 21010.0,
    low: float = 20990.0,
    delta: int = 0,
    total_vol: int = 1000,
    levels: dict | None = None,
) -> FootprintBar:
    """Build a minimal FootprintBar for offline tests."""
    bar = FootprintBar(
        open=open_,
        high=high,
        low=low,
        close=close,
        bar_delta=delta,
        total_vol=total_vol,
        bar_range=high - low,
    )
    if levels is not None:
        bar.levels = levels
    return bar


def make_levels(price_vols: dict[float, tuple[int, int]]) -> dict:
    """Build levels dict from {price: (bid_vol, ask_vol)}."""
    d = defaultdict(FootprintLevel)
    for price, (bid, ask) in price_vols.items():
        tick = price_to_tick(price)
        d[tick] = FootprintLevel(bid_vol=bid, ask_vol=ask)
    return d


# ---------------------------------------------------------------------------
# TRAP-01: Cross-reference only (INVERSE_TRAP lives in imbalance.py)
# ---------------------------------------------------------------------------

def test_trap01_cross_reference():
    """TRAP-01: INVERSE_TRAP is tested in tests/test_imbalance.py.

    See test_imbalance.py::TestInverseTrap for TRAP-01 coverage.
    This test exists as a requirement cross-reference placeholder.
    ImbalanceType.INVERSE_TRAP is implemented in deep6/engines/imbalance.py
    and fires from detect_imbalances() for IMB-05.
    """
    from deep6.engines.imbalance import ImbalanceType
    assert ImbalanceType.INVERSE_TRAP is not None
    # Actual TRAP-01 test: see tests/test_imbalance.py — search for INVERSE_TRAP


# ---------------------------------------------------------------------------
# Edge case: empty bar
# ---------------------------------------------------------------------------

def test_empty_bar_returns_empty_list():
    """T-04-02: Zero-volume bars must return [] immediately."""
    engine = TrapEngine()
    bar = make_footprint_bar(total_vol=0)
    result = engine.process(bar, prior_bar=None, vol_ema=200.0, cvd_history=[])
    assert result == []


# ---------------------------------------------------------------------------
# TRAP-02: Delta trap
# ---------------------------------------------------------------------------

def test_trap02_delta_trap_fires():
    """TRAP-02: Prior bar |delta/vol|=0.35 bull; current bar closes bearish with negative delta.

    Verifies TrapType.DELTA_TRAP fires, direction=-1 (bear delta caught longs).
    prior ratio = 350/1000 = 0.35 >= 0.25 threshold (bull).
    current: close < open (bearish) AND delta < 0 (confirms reversal).
    """
    engine = TrapEngine()
    prior = make_footprint_bar(
        open_=21000.0, close=21005.0,
        delta=350, total_vol=1000,
    )
    current = make_footprint_bar(
        open_=21005.0, close=20995.0,
        delta=-200, total_vol=1000,
    )
    signals = engine.process(current, prior_bar=prior, vol_ema=200.0, cvd_history=[])
    trap_types = [s.trap_type for s in signals]
    assert TrapType.DELTA_TRAP in trap_types
    trap = next(s for s in signals if s.trap_type == TrapType.DELTA_TRAP)
    assert trap.direction == -1


def test_trap02_no_fire_insufficient_prior_delta():
    """TRAP-02 negative: prior delta ratio below threshold → no DELTA_TRAP.

    prior ratio = 50/1000 = 0.05 < 0.25 threshold.
    """
    engine = TrapEngine()
    prior = make_footprint_bar(open_=21000.0, close=21005.0, delta=50, total_vol=1000)
    current = make_footprint_bar(open_=21005.0, close=20995.0, delta=-200, total_vol=1000)
    signals = engine.process(current, prior_bar=prior, vol_ema=200.0, cvd_history=[])
    trap_types = [s.trap_type for s in signals]
    assert TrapType.DELTA_TRAP not in trap_types


def test_trap02_no_fire_no_prior_bar():
    """TRAP-02: No prior bar → no delta trap (cannot measure prior ratio)."""
    engine = TrapEngine()
    current = make_footprint_bar(open_=21005.0, close=20995.0, delta=-200, total_vol=1000)
    signals = engine.process(current, prior_bar=None, vol_ema=200.0, cvd_history=[])
    trap_types = [s.trap_type for s in signals]
    assert TrapType.DELTA_TRAP not in trap_types


# ---------------------------------------------------------------------------
# TRAP-03: False breakout trap
# ---------------------------------------------------------------------------

def test_trap03_false_breakout_fires_above():
    """TRAP-03: bar.high > prior.high, bar.close < prior.high, vol > vol_ema * 1.8.

    Bear false breakout — longs trapped above prior high.
    """
    engine = TrapEngine()
    prior = make_footprint_bar(high=21010.0, low=20990.0)
    current = make_footprint_bar(
        open_=21005.0,
        high=21020.0,     # above prior high 21010
        low=20998.0,
        close=21005.0,    # closes BELOW prior high → false breakout
        delta=-100,
        total_vol=2000,   # 2000 > 200 * 1.8 = 360
    )
    signals = engine.process(current, prior_bar=prior, vol_ema=200.0, cvd_history=[])
    trap_types = [s.trap_type for s in signals]
    assert TrapType.FALSE_BREAKOUT_TRAP in trap_types


def test_trap03_false_breakout_no_fire_low_volume():
    """TRAP-03: Breakout occurred but volume not elevated enough → no trap."""
    engine = TrapEngine()
    prior = make_footprint_bar(high=21010.0)
    current = make_footprint_bar(
        high=21020.0,
        close=21005.0,    # below prior high
        total_vol=300,    # 300 < 200 * 1.8 = 360
    )
    signals = engine.process(current, prior_bar=prior, vol_ema=200.0, cvd_history=[])
    trap_types = [s.trap_type for s in signals]
    assert TrapType.FALSE_BREAKOUT_TRAP not in trap_types


# ---------------------------------------------------------------------------
# TRAP-04: High volume rejection trap
# ---------------------------------------------------------------------------

def test_trap04_high_vol_rejection_fires():
    """TRAP-04: vol = vol_ema * 3.0, upper wick vol fraction = 0.4 → HIGH_VOL_REJECTION_TRAP.

    Bar range: 20990–21010 (20 pts). Upper quarter: >= 21005.
    Place 400 contracts in upper zone out of 1000 total → 40% > 35% threshold.
    vol = 3000 > 200 * 2.5 = 500 threshold.
    """
    engine = TrapEngine()
    levels = make_levels({
        20992.0: (100, 100),  # 200 contracts — body
        20996.0: (100, 100),  # 200 contracts — body
        21000.0: (100, 100),  # 200 contracts — body
        21006.0: (0, 400),    # 400 contracts — upper wick zone (>= 21005)
    })
    bar = make_footprint_bar(
        open_=20993.0,
        high=21010.0,
        low=20990.0,
        close=20995.0,
        delta=400,
        total_vol=1000,
        levels=levels,
    )
    signals = engine.process(bar, prior_bar=None, vol_ema=200.0, cvd_history=[])
    trap_types = [s.trap_type for s in signals]
    assert TrapType.HIGH_VOL_REJECTION_TRAP in trap_types


def test_trap04_no_fire_vol_too_low():
    """TRAP-04: Volume below 2.5× vol_ema threshold → no HIGH_VOL_REJECTION_TRAP."""
    engine = TrapEngine()
    bar = make_footprint_bar(total_vol=400)  # 400 < 200 * 2.5 = 500
    signals = engine.process(bar, prior_bar=None, vol_ema=200.0, cvd_history=[])
    trap_types = [s.trap_type for s in signals]
    assert TrapType.HIGH_VOL_REJECTION_TRAP not in trap_types


# ---------------------------------------------------------------------------
# TRAP-05: CVD trap
# ---------------------------------------------------------------------------

def test_trap05_cvd_trap_fires_on_trend_reversal():
    """TRAP-05: cvd_history trending up then current bar has negative delta → CVD_TRAP.

    cvd_history = [10, 20, 30, 40, 50, 60, 70, 80, 5] is a long uptrend then drop.
    We use a clean uptrend of 8+ values to satisfy lookback=8.
    current bar_delta < 0 → reverses uptrend.
    """
    engine = TrapEngine()
    # 9 strongly trending CVD values (slope > 0.05 threshold)
    cvd_history = [i * 50 for i in range(9)]  # [0, 50, 100, 150, ..., 400]
    current = make_footprint_bar(
        open_=21005.0, close=20995.0,
        delta=-300, total_vol=1000,
    )
    signals = engine.process(current, prior_bar=None, vol_ema=200.0, cvd_history=cvd_history)
    trap_types = [s.trap_type for s in signals]
    assert TrapType.CVD_TRAP in trap_types


def test_trap05_no_fire_insufficient_cvd_history():
    """TRAP-05: Not enough CVD history (< lookback) → no CVD_TRAP."""
    engine = TrapEngine()
    cvd_history = [0, 50, 100]  # only 3 entries < lookback=8
    current = make_footprint_bar(delta=-300, total_vol=1000)
    signals = engine.process(current, prior_bar=None, vol_ema=200.0, cvd_history=cvd_history)
    trap_types = [s.trap_type for s in signals]
    assert TrapType.CVD_TRAP not in trap_types


def test_trap05_no_fire_flat_cvd():
    """TRAP-05: CVD is flat (slope ≈ 0) → no meaningful trend → no CVD_TRAP."""
    engine = TrapEngine()
    cvd_history = [100] * 10  # completely flat — slope = 0
    current = make_footprint_bar(delta=-300, total_vol=1000)
    signals = engine.process(current, prior_bar=None, vol_ema=200.0, cvd_history=cvd_history)
    trap_types = [s.trap_type for s in signals]
    assert TrapType.CVD_TRAP not in trap_types


def test_trap05_cvd_history_not_mutated():
    """T-04-01: Engine must not mutate caller-owned cvd_history list."""
    engine = TrapEngine()
    cvd_history = list(range(0, 450, 50))  # 9 values
    original = list(cvd_history)
    current = make_footprint_bar(delta=-300, total_vol=1000)
    engine.process(current, prior_bar=None, vol_ema=200.0, cvd_history=cvd_history)
    assert cvd_history == original
