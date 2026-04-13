"""Tests for POCEngine — 8 signal variants + migration (POC-01..08, VPRO-08)."""
from __future__ import annotations

from collections import defaultdict

import pytest

from deep6.engines.poc import POCEngine, POCType
from deep6.engines.signal_config import POCConfig
from deep6.state.footprint import FootprintBar, FootprintLevel, price_to_tick


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_levels(price_vol_pairs: list[tuple[float, int, int]]) -> dict[int, FootprintLevel]:
    """Build levels dict from [(price, bid_vol, ask_vol), ...]."""
    levels = {}
    for price, bid, ask in price_vol_pairs:
        levels[price_to_tick(price)] = FootprintLevel(bid_vol=bid, ask_vol=ask)
    return levels


def make_bar(
    open_: float = 100.0,
    high: float = 100.75,
    low: float = 99.75,
    close: float = 100.5,
    poc_price: float = 100.25,
    levels: dict | None = None,
) -> FootprintBar:
    if levels is None:
        levels = make_levels([(100.0, 50, 100), (100.25, 80, 120)])
    total = sum(lv.bid_vol + lv.ask_vol for lv in levels.values())
    return FootprintBar(
        open=open_, high=high, low=low, close=close,
        total_vol=total, poc_price=poc_price,
        bar_range=high - low, levels=levels,
    )


# ---------------------------------------------------------------------------
# POC-01: Above/Below POC
# ---------------------------------------------------------------------------

def test_above_below_poc():
    """Close above session POC fires ABOVE_POC with direction=+1."""
    eng = POCEngine()
    # Prime session_poc by processing a bar first
    bar1 = make_bar(close=100.25, poc_price=100.25)
    eng.process(bar1)
    # Now session_poc is set; close above it should fire ABOVE_POC
    bar2 = make_bar(close=101.0, poc_price=100.25)
    sigs = eng.process(bar2)
    above = [s for s in sigs if s.poc_type == POCType.ABOVE_POC]
    assert len(above) >= 1
    assert above[0].direction == +1


def test_below_poc():
    """Close below session POC fires BELOW_POC with direction=-1."""
    eng = POCEngine()
    bar1 = make_bar(close=100.25, poc_price=100.25)
    eng.process(bar1)
    bar2 = make_bar(close=99.0, poc_price=100.25)
    sigs = eng.process(bar2)
    below = [s for s in sigs if s.poc_type == POCType.BELOW_POC]
    assert len(below) >= 1
    assert below[0].direction == -1


# ---------------------------------------------------------------------------
# POC-02: Extreme POC
# ---------------------------------------------------------------------------

def test_extreme_poc_high():
    """POC at top 15% of bar fires EXTREME_POC_HIGH with direction=-1."""
    eng = POCEngine()
    # Bar from 100.0 to 101.0, POC at 100.90 (top 10%)
    lvls = make_levels([(100.90, 0, 300)])  # high volume at top
    bar = make_bar(open_=100.0, high=101.0, low=100.0, close=100.0,
                   poc_price=100.90, levels=lvls)
    sigs = eng.process(bar)
    extreme_high = [s for s in sigs if s.poc_type == POCType.EXTREME_POC_HIGH]
    assert len(extreme_high) >= 1
    assert extreme_high[0].direction == -1


def test_extreme_poc_low():
    """POC at bottom 15% of bar fires EXTREME_POC_LOW with direction=+1."""
    eng = POCEngine()
    # Bar from 100.0 to 101.0, POC at 100.10 (bottom 10%)
    lvls = make_levels([(100.10, 300, 0)])  # high volume at bottom
    bar = make_bar(open_=101.0, high=101.0, low=100.0, close=101.0,
                   poc_price=100.10, levels=lvls)
    sigs = eng.process(bar)
    extreme_low = [s for s in sigs if s.poc_type == POCType.EXTREME_POC_LOW]
    assert len(extreme_low) >= 1
    assert extreme_low[0].direction == +1


# ---------------------------------------------------------------------------
# POC-03: Continuous POC
# ---------------------------------------------------------------------------

def test_continuous_poc():
    """Same POC for enough bars fires CONTINUOUS_POC.

    The streak counter requires prev_poc > 0 to start, so:
    Bar 1: prev_poc=0, no streak check, prev_poc set to 100.25
    Bar 2: streak becomes 1 (< 3, no signal)
    Bar 3: streak becomes 2 (< 3, no signal)
    Bar 4: streak becomes 3, signal fires
    """
    eng = POCEngine()
    fired = False
    for i in range(4):
        bar = make_bar(poc_price=100.25)
        sigs = eng.process(bar)
        cont = [s for s in sigs if s.poc_type == POCType.CONTINUOUS_POC]
        if cont:
            fired = True
    assert fired, "CONTINUOUS_POC should have fired by bar 4"


# ---------------------------------------------------------------------------
# POC-04: POC Gap
# ---------------------------------------------------------------------------

def test_poc_gap():
    """POC jump of 10 ticks fires POC_GAP with correct direction."""
    eng = POCEngine()
    bar1 = make_bar(poc_price=100.00)
    eng.process(bar1)
    # Jump up by 10 ticks (10 * 0.25 = 2.50)
    bar2 = make_bar(poc_price=102.50, close=102.50)
    sigs = eng.process(bar2)
    gap = [s for s in sigs if s.poc_type == POCType.POC_GAP]
    assert len(gap) >= 1
    assert gap[0].direction == +1


# ---------------------------------------------------------------------------
# POC-05: POC Delta
# ---------------------------------------------------------------------------

def test_poc_delta():
    """POC level with ask_vol > bid_vol fires POC_DELTA with direction=+1."""
    eng = POCEngine()
    poc_price = 100.25
    lvls = make_levels([(poc_price, 20, 200)])  # ask dominant
    bar = make_bar(poc_price=poc_price, levels=lvls)
    sigs = eng.process(bar)
    delta = [s for s in sigs if s.poc_type == POCType.POC_DELTA]
    assert len(delta) >= 1
    assert delta[0].direction == +1


# ---------------------------------------------------------------------------
# POC-06: Engulfing VA
# ---------------------------------------------------------------------------

def test_engulfing_va():
    """Current VA that fully contains prior VA fires ENGULFING_VA."""
    eng = POCEngine()
    # Bar 1: narrow VA around 100.25
    narrow_levels = make_levels([
        (100.00, 10, 10),
        (100.25, 200, 200),   # POC — very heavy
        (100.50, 10, 10),
    ])
    bar1 = make_bar(open_=100.0, high=100.5, low=100.0, close=100.5,
                    poc_price=100.25, levels=narrow_levels)
    eng.process(bar1)
    # Bar 2: wider VA encompassing bar1 VA
    wide_levels = make_levels([
        (99.50, 5, 5),
        (99.75, 5, 5),
        (100.00, 100, 100),
        (100.25, 200, 200),  # POC
        (100.50, 100, 100),
        (100.75, 5, 5),
        (101.00, 5, 5),
    ])
    bar2 = make_bar(open_=99.5, high=101.0, low=99.5, close=100.75,
                    poc_price=100.25, levels=wide_levels)
    sigs = eng.process(bar2)
    engulf = [s for s in sigs if s.poc_type == POCType.ENGULFING_VA]
    assert len(engulf) >= 1


# ---------------------------------------------------------------------------
# POC-07: VA Gap
# ---------------------------------------------------------------------------

def test_va_gap():
    """Current VAL above prior VAH fires VA_GAP with direction=+1."""
    eng = POCEngine()
    # Bar 1: VA from ~99.75 to ~100.50
    low_levels = make_levels([
        (99.75, 100, 100),
        (100.00, 200, 200),  # POC
        (100.25, 100, 100),
    ])
    bar1 = make_bar(open_=99.75, high=100.5, low=99.5, close=100.25,
                    poc_price=100.00, levels=low_levels)
    eng.process(bar1)
    # Bar 2: VA from ~101.25 to ~102.0 — gap above bar1's VAH
    high_levels = make_levels([
        (101.25, 100, 100),
        (101.50, 200, 200),  # POC
        (101.75, 100, 100),
    ])
    bar2 = make_bar(open_=101.25, high=102.0, low=101.0, close=101.75,
                    poc_price=101.50, levels=high_levels)
    sigs = eng.process(bar2)
    gap = [s for s in sigs if s.poc_type == POCType.VA_GAP]
    assert len(gap) >= 1
    assert gap[0].direction == +1


# ---------------------------------------------------------------------------
# POC-08: Bullish/Bearish POC
# ---------------------------------------------------------------------------

def test_bullish_poc():
    """POC at bottom 30% in green bar fires BULLISH_POC with direction=+1."""
    eng = POCEngine()
    # Bar from 100.0 to 101.0, POC at 100.10 (10% from bottom), green bar
    lvls = make_levels([(100.10, 200, 400), (100.50, 30, 30)])
    bar = make_bar(open_=100.0, high=101.0, low=100.0, close=101.0,
                   poc_price=100.10, levels=lvls)
    sigs = eng.process(bar)
    bull = [s for s in sigs if s.poc_type == POCType.BULLISH_POC]
    assert len(bull) >= 1
    assert bull[0].direction == +1


def test_bearish_poc():
    """POC at top 70% in red bar fires BEARISH_POC with direction=-1."""
    eng = POCEngine()
    # Bar from 100.0 to 101.0, POC at 100.90 (90% from bottom), red bar
    lvls = make_levels([(100.90, 400, 200), (100.50, 30, 30)])
    bar = make_bar(open_=101.0, high=101.0, low=100.0, close=100.0,
                   poc_price=100.90, levels=lvls)
    sigs = eng.process(bar)
    bear = [s for s in sigs if s.poc_type == POCType.BEARISH_POC]
    assert len(bear) >= 1
    assert bear[0].direction == -1


# ---------------------------------------------------------------------------
# VPRO-08: POC Migration
# ---------------------------------------------------------------------------

def test_migration_rising():
    """5 bars with POC ticking up 4 ticks each returns (direction=+1, velocity>0)."""
    eng = POCEngine()
    base = 100.00
    for i in range(5):
        price = base + i * 4 * 0.25  # 4 ticks up each bar
        lvls = make_levels([(price, 50, 100)])
        bar = make_bar(
            open_=price - 0.25, high=price + 0.50, low=price - 0.25,
            close=price + 0.25, poc_price=price, levels=lvls
        )
        eng.process(bar)
    direction, velocity = eng.get_migration()
    assert direction == +1
    assert velocity > 0.0


def test_migration_flat():
    """5 bars with same POC returns (direction=0, velocity≈0)."""
    eng = POCEngine()
    for _ in range(5):
        bar = make_bar(poc_price=100.25)
        eng.process(bar)
    direction, velocity = eng.get_migration()
    assert direction == 0
    # velocity should be tiny / near zero
    assert velocity < 1.0


# ---------------------------------------------------------------------------
# Config override
# ---------------------------------------------------------------------------

def test_config_override():
    """POCEngine with poc_gap_ticks=20 does not fire POC_GAP for 10-tick jump."""
    eng = POCEngine(config=POCConfig(poc_gap_ticks=20))
    bar1 = make_bar(poc_price=100.00)
    eng.process(bar1)
    # 10-tick jump (100.00 → 102.50) — below the 20-tick threshold
    bar2 = make_bar(poc_price=102.50, close=102.50)
    sigs = eng.process(bar2)
    gap = [s for s in sigs if s.poc_type == POCType.POC_GAP]
    assert len(gap) == 0
