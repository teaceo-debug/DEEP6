"""Tests for VolPatternEngine — VOLP-01..06 (6 volume pattern signal variants).

All tests use synthetic FootprintBar data — offline, no live Rithmic required.

Requirement coverage:
  VOLP-01 — volume sequencing: 3+ consecutive bars with escalating volume
  VOLP-02 — volume bubble: single price level with outsized volume concentration
  VOLP-03 — volume surge: bar volume > 3× vol_ema
  VOLP-04 — POC momentum wave: POC migrated directionally for N consecutive bars
  VOLP-05 — delta velocity spike: rapid change in bar delta between consecutive bars
  VOLP-06 — big delta per level: one price level with dominant net_delta
"""
from __future__ import annotations

from collections import defaultdict

import pytest

from deep6.engines.vol_patterns import VolPatternEngine, VolPatternSignal, VolPatternType
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
    poc_price: float = 21000.0,
    levels: dict | None = None,
) -> FootprintBar:
    """Build a minimal FootprintBar for offline tests.

    Automatically adds minimal levels so empty-bar guard doesn't prevent testing
    unless total_vol=0 is explicitly passed.
    """
    bar = FootprintBar(
        open=open_,
        high=high,
        low=low,
        close=close,
        bar_delta=delta,
        total_vol=total_vol,
        bar_range=high - low,
        poc_price=poc_price,
    )
    if levels is not None:
        bar.levels = levels
    else:
        # Default: minimal single level at poc_price
        d = defaultdict(FootprintLevel)
        half = total_vol // 2
        d[price_to_tick(poc_price)] = FootprintLevel(bid_vol=half, ask_vol=total_vol - half)
        bar.levels = d
    return bar


def make_levels(price_vols: dict[float, tuple[int, int]]) -> dict:
    """Build levels dict from {price: (bid_vol, ask_vol)}."""
    d = defaultdict(FootprintLevel)
    for price, (bid, ask) in price_vols.items():
        tick = price_to_tick(price)
        d[tick] = FootprintLevel(bid_vol=bid, ask_vol=ask)
    return d


# ---------------------------------------------------------------------------
# Edge case: empty bar
# ---------------------------------------------------------------------------

def test_empty_bar_returns_empty_list():
    """T-04-02: Zero-volume bars must return [] immediately."""
    engine = VolPatternEngine()
    bar = FootprintBar(total_vol=0)
    result = engine.process(bar, bar_history=[], vol_ema=200.0, poc_history=[])
    assert result == []


# ---------------------------------------------------------------------------
# VOLP-01: Volume sequencing
# ---------------------------------------------------------------------------

def test_volp01_sequencing_fires_on_3_bars():
    """VOLP-01: bar_history with 3 consecutive bars each 15%+ larger than prior → SEQUENCING fires.

    Bar volumes: 1000, 1150, 1323 — each >= prior * 1.15.
    """
    engine = VolPatternEngine()
    history = [
        make_footprint_bar(total_vol=1000, delta=50),
        make_footprint_bar(total_vol=1150, delta=55),
    ]
    current = make_footprint_bar(total_vol=1323, delta=60)
    signals = engine.process(current, bar_history=history, vol_ema=500.0, poc_history=[])
    pattern_types = [s.pattern_type for s in signals]
    assert VolPatternType.SEQUENCING in pattern_types


def test_volp01_no_fire_only_2_bars_in_sequence():
    """VOLP-01 negative: only 2 bars in escalating sequence → no SEQUENCING (min_bars=3)."""
    engine = VolPatternEngine()
    history = [make_footprint_bar(total_vol=1000, delta=50)]
    current = make_footprint_bar(total_vol=1150, delta=55)
    signals = engine.process(current, bar_history=history, vol_ema=500.0, poc_history=[])
    pattern_types = [s.pattern_type for s in signals]
    assert VolPatternType.SEQUENCING not in pattern_types


def test_volp01_no_fire_step_too_small():
    """VOLP-01: Volume growth only 5% per bar — below 15% threshold → no SEQUENCING."""
    engine = VolPatternEngine()
    history = [
        make_footprint_bar(total_vol=1000, delta=10),
        make_footprint_bar(total_vol=1050, delta=10),
    ]
    current = make_footprint_bar(total_vol=1100, delta=10)
    signals = engine.process(current, bar_history=history, vol_ema=500.0, poc_history=[])
    pattern_types = [s.pattern_type for s in signals]
    assert VolPatternType.SEQUENCING not in pattern_types


# ---------------------------------------------------------------------------
# VOLP-02: Volume bubble
# ---------------------------------------------------------------------------

def test_volp02_bubble_fires_on_single_level_spike():
    """VOLP-02: single level with ask_vol + bid_vol = 500 in a bar where avg_level_vol = 50
    (10x bubble) → BUBBLE fires at that price.

    5 levels: 4 × 50 vol + 1 × 500 vol = 700 total.
    avg_level_vol = 700/5 = 140. 500/140 = 3.57. Need > 4×. Use 4 × 10 + 1 × 500.
    avg = 540/5 = 108. 500/108 = 4.63 > 4.0 → fires.
    """
    engine = VolPatternEngine()
    levels = make_levels({
        21000.0: (5, 5),     # 10 vol
        21005.0: (5, 5),     # 10 vol
        21010.0: (5, 5),     # 10 vol
        21015.0: (5, 5),     # 10 vol
        21020.0: (250, 250), # 500 vol — bubble level
    })
    bar = make_footprint_bar(total_vol=540, levels=levels)
    signals = engine.process(bar, bar_history=[], vol_ema=200.0, poc_history=[])
    pattern_types = [s.pattern_type for s in signals]
    assert VolPatternType.BUBBLE in pattern_types


def test_volp02_no_fire_uniform_levels():
    """VOLP-02 negative: all levels roughly equal → no bubble."""
    engine = VolPatternEngine()
    levels = make_levels({
        21000.0: (100, 100),
        21005.0: (100, 100),
        21010.0: (100, 100),
    })
    bar = make_footprint_bar(total_vol=600, levels=levels)
    signals = engine.process(bar, bar_history=[], vol_ema=200.0, poc_history=[])
    pattern_types = [s.pattern_type for s in signals]
    assert VolPatternType.BUBBLE not in pattern_types


# ---------------------------------------------------------------------------
# VOLP-03: Volume surge
# ---------------------------------------------------------------------------

def test_volp03_surge_fires_above_threshold():
    """VOLP-03: bar.total_vol = vol_ema * 4.0 → SURGE fires."""
    engine = VolPatternEngine()
    bar = make_footprint_bar(total_vol=4000, delta=0)  # 4000 > 1000 * 3.0 = 3000
    signals = engine.process(bar, bar_history=[], vol_ema=1000.0, poc_history=[])
    pattern_types = [s.pattern_type for s in signals]
    assert VolPatternType.SURGE in pattern_types


def test_volp03_no_fire_below_surge_threshold():
    """VOLP-03: bar.total_vol = vol_ema * 2.5 → no SURGE (below 3.0× threshold)."""
    engine = VolPatternEngine()
    bar = make_footprint_bar(total_vol=2500, delta=0)  # 2500 < 1000 * 3.0 = 3000
    signals = engine.process(bar, bar_history=[], vol_ema=1000.0, poc_history=[])
    pattern_types = [s.pattern_type for s in signals]
    assert VolPatternType.SURGE not in pattern_types


# ---------------------------------------------------------------------------
# VOLP-04: POC momentum wave
# ---------------------------------------------------------------------------

def test_volp04_poc_wave_fires_upward_migration():
    """VOLP-04: poc_history = [100.0, 101.0, 102.0, 103.0] (3 bars migrating up) →
    POC_MOMENTUM_WAVE fires, direction=+1.
    """
    engine = VolPatternEngine()
    poc_history = [100.0, 101.0, 102.0, 103.0]
    bar = make_footprint_bar(poc_price=103.0)
    signals = engine.process(bar, bar_history=[], vol_ema=200.0, poc_history=poc_history)
    pattern_types = [s.pattern_type for s in signals]
    assert VolPatternType.POC_MOMENTUM_WAVE in pattern_types
    sig = next(s for s in signals if s.pattern_type == VolPatternType.POC_MOMENTUM_WAVE)
    assert sig.direction == +1


def test_volp04_poc_wave_fires_downward_migration():
    """VOLP-04: POC migrating downward → direction=-1."""
    engine = VolPatternEngine()
    poc_history = [103.0, 102.0, 101.0, 100.0]
    bar = make_footprint_bar(poc_price=100.0)
    signals = engine.process(bar, bar_history=[], vol_ema=200.0, poc_history=poc_history)
    pattern_types = [s.pattern_type for s in signals]
    assert VolPatternType.POC_MOMENTUM_WAVE in pattern_types
    sig = next(s for s in signals if s.pattern_type == VolPatternType.POC_MOMENTUM_WAVE)
    assert sig.direction == -1


def test_volp04_no_fire_choppy_poc():
    """VOLP-04: POC oscillates — not directional → no POC_MOMENTUM_WAVE."""
    engine = VolPatternEngine()
    poc_history = [100.0, 102.0, 101.0, 103.0]  # non-monotonic
    bar = make_footprint_bar(poc_price=103.0)
    signals = engine.process(bar, bar_history=[], vol_ema=200.0, poc_history=poc_history)
    pattern_types = [s.pattern_type for s in signals]
    assert VolPatternType.POC_MOMENTUM_WAVE not in pattern_types


# ---------------------------------------------------------------------------
# VOLP-05: Delta velocity spike
# ---------------------------------------------------------------------------

def test_volp05_delta_velocity_spike_fires():
    """VOLP-05: prior bar delta=10, current bar delta=100 →
    velocity=90 > vol_ema * 0.6 = 60 → DELTA_VELOCITY_SPIKE fires.
    """
    engine = VolPatternEngine()
    prior = make_footprint_bar(delta=10, total_vol=1000)
    current = make_footprint_bar(delta=100, total_vol=1000)
    signals = engine.process(current, bar_history=[prior], vol_ema=100.0, poc_history=[])
    pattern_types = [s.pattern_type for s in signals]
    assert VolPatternType.DELTA_VELOCITY_SPIKE in pattern_types


def test_volp05_no_fire_small_velocity():
    """VOLP-05: velocity = 20 < vol_ema * 0.6 = 60 → no DELTA_VELOCITY_SPIKE."""
    engine = VolPatternEngine()
    prior = make_footprint_bar(delta=10, total_vol=1000)
    current = make_footprint_bar(delta=30, total_vol=1000)
    signals = engine.process(current, bar_history=[prior], vol_ema=100.0, poc_history=[])
    pattern_types = [s.pattern_type for s in signals]
    assert VolPatternType.DELTA_VELOCITY_SPIKE not in pattern_types


def test_volp05_no_prior_bar_no_spike():
    """VOLP-05: No history → cannot compute velocity → no DELTA_VELOCITY_SPIKE."""
    engine = VolPatternEngine()
    current = make_footprint_bar(delta=100, total_vol=1000)
    signals = engine.process(current, bar_history=[], vol_ema=100.0, poc_history=[])
    pattern_types = [s.pattern_type for s in signals]
    assert VolPatternType.DELTA_VELOCITY_SPIKE not in pattern_types


# ---------------------------------------------------------------------------
# VOLP-06: Big delta per level
# ---------------------------------------------------------------------------

def test_volp06_big_delta_per_level_fires_bear():
    """VOLP-06: one level with bid_vol=200, ask_vol=10 → net_delta=-190 →
    BIG_DELTA_PER_LEVEL fires, direction=-1.
    """
    engine = VolPatternEngine()
    levels = make_levels({
        21000.0: (200, 10),   # net_delta = 10 - 200 = -190 (bear dominated)
        21005.0: (10, 10),
    })
    bar = make_footprint_bar(total_vol=230, delta=-190, levels=levels)
    signals = engine.process(bar, bar_history=[], vol_ema=200.0, poc_history=[])
    pattern_types = [s.pattern_type for s in signals]
    assert VolPatternType.BIG_DELTA_PER_LEVEL in pattern_types
    sig = next(s for s in signals if s.pattern_type == VolPatternType.BIG_DELTA_PER_LEVEL)
    assert sig.direction == -1


def test_volp06_big_delta_per_level_fires_bull():
    """VOLP-06: one level with ask_vol dominance → net_delta > threshold → direction=+1."""
    engine = VolPatternEngine()
    levels = make_levels({
        21000.0: (10, 200),   # net_delta = 200 - 10 = +190 (bull)
        21005.0: (10, 10),
    })
    bar = make_footprint_bar(total_vol=230, delta=190, levels=levels)
    signals = engine.process(bar, bar_history=[], vol_ema=200.0, poc_history=[])
    pattern_types = [s.pattern_type for s in signals]
    assert VolPatternType.BIG_DELTA_PER_LEVEL in pattern_types
    sig = next(s for s in signals if s.pattern_type == VolPatternType.BIG_DELTA_PER_LEVEL)
    assert sig.direction == +1


def test_volp06_no_fire_small_delta():
    """VOLP-06: All levels below 80-contract threshold → no BIG_DELTA_PER_LEVEL."""
    engine = VolPatternEngine()
    levels = make_levels({
        21000.0: (40, 60),  # net_delta = +20 < 80
        21005.0: (35, 55),  # net_delta = +20 < 80
    })
    bar = make_footprint_bar(total_vol=190, delta=40, levels=levels)
    signals = engine.process(bar, bar_history=[], vol_ema=200.0, poc_history=[])
    pattern_types = [s.pattern_type for s in signals]
    assert VolPatternType.BIG_DELTA_PER_LEVEL not in pattern_types


def test_volp06_empty_bar_returns_empty():
    """T-04-02: Empty levels guard — no crash."""
    engine = VolPatternEngine()
    bar = FootprintBar(total_vol=0)
    bar.levels = {}
    result = engine.process(bar, bar_history=[], vol_ema=200.0, poc_history=[])
    assert result == []
