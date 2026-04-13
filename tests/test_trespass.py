"""Tests for E2 TrespassEngine (ENG-02) — multi-level weighted DOM queue imbalance.

All tests use synthetic DOM snapshots — offline, no live Rithmic required.

Requirement coverage:
  ENG-02 — TrespassEngine: multi-level weighted DOM imbalance
    - neutral fallback when DOM unavailable (D-13)
    - bull/bear/balanced snapshot detection
    - depth gradient computation
"""
from __future__ import annotations

import pytest

from deep6.engines.trespass import TrespassEngine, TrespassResult
from deep6.engines.signal_config import TrespassConfig
from deep6.state.dom import LEVELS


def make_dom_snapshot(
    bid_depths: list[float] | None = None,
    ask_depths: list[float] | None = None,
) -> tuple:
    """Build a synthetic DOM snapshot for testing.

    Args:
        bid_depths: Bid sizes at levels 0..N (best bid first). Padded to LEVELS.
        ask_depths: Ask sizes at levels 0..N. Padded to LEVELS.

    Returns:
        (bid_prices, bid_sizes, ask_prices, ask_sizes) as lists of length LEVELS.
    """
    bd = (bid_depths or [100.0] * 10) + [0.0] * LEVELS
    ad = (ask_depths or [100.0] * 10) + [0.0] * LEVELS
    bp = [20000.0 - i * 0.25 for i in range(LEVELS)]
    ap = [20000.25 + i * 0.25 for i in range(LEVELS)]
    return (bp, bd[:LEVELS], ap, ad[:LEVELS])


# ---------------------------------------------------------------------------
# ENG-02: Neutral fallback (D-13)
# ---------------------------------------------------------------------------

def test_dom_unavailable():
    """ENG-02: process(None) → direction=0, imbalance_ratio=1.0 (D-13 neutral fallback)."""
    engine = TrespassEngine()
    result = engine.process(None)
    assert isinstance(result, TrespassResult)
    assert result.direction == 0
    assert result.imbalance_ratio == pytest.approx(1.0)
    assert result.probability == pytest.approx(0.5)
    assert "UNAVAILABLE" in result.detail


# ---------------------------------------------------------------------------
# ENG-02: Equal sides
# ---------------------------------------------------------------------------

def test_equal_sides_returns_neutral():
    """ENG-02: Snapshot with equal bid and ask depths → direction=0 (neutral)."""
    engine = TrespassEngine()
    snap = make_dom_snapshot(
        bid_depths=[50.0] * 10,
        ask_depths=[50.0] * 10,
    )
    result = engine.process(snap)
    assert result.direction == 0
    assert result.imbalance_ratio == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# ENG-02: Heavy bid (bull)
# ---------------------------------------------------------------------------

def test_heavy_bid_returns_bull():
    """ENG-02: bid_depths[0]=500, ask_depths[0]=50 → direction=+1, ratio >> 1.0."""
    engine = TrespassEngine()
    snap = make_dom_snapshot(
        bid_depths=[500.0] * 10,
        ask_depths=[50.0] * 10,
    )
    result = engine.process(snap)
    assert result.direction == 1
    assert result.imbalance_ratio > 1.2
    assert result.probability > 0.5


# ---------------------------------------------------------------------------
# ENG-02: Heavy ask (bear)
# ---------------------------------------------------------------------------

def test_heavy_ask_returns_bear():
    """ENG-02: bid_depths[0]=50, ask_depths[0]=500 → direction=-1, ratio << 1.0."""
    engine = TrespassEngine()
    snap = make_dom_snapshot(
        bid_depths=[50.0] * 10,
        ask_depths=[500.0] * 10,
    )
    result = engine.process(snap)
    assert result.direction == -1
    assert result.imbalance_ratio < 0.8
    assert result.probability < 0.5


# ---------------------------------------------------------------------------
# ENG-02: Depth gradient
# ---------------------------------------------------------------------------

def test_depth_gradient_computed_for_thinning_book():
    """ENG-02: bid_depths=[500, 400, 300, 200, 100, ...] → depth_gradient > 0 (book thinning)."""
    engine = TrespassEngine()
    bid_depths = [500.0, 400.0, 300.0, 200.0, 100.0, 80.0, 60.0, 40.0, 20.0, 10.0]
    ask_depths = [200.0] * 10
    snap = make_dom_snapshot(bid_depths=bid_depths, ask_depths=ask_depths)
    result = engine.process(snap)
    # depth_gradient = (bid[0] - bid[depth-1]) / depth = (500 - 10) / 10 = 49.0
    assert result.depth_gradient > 0
    assert result.depth_gradient == pytest.approx((500.0 - 10.0) / 10, rel=1e-5)


def test_flat_book_zero_depth_gradient():
    """ENG-02: Flat book → depth_gradient = 0."""
    engine = TrespassEngine()
    snap = make_dom_snapshot(
        bid_depths=[100.0] * 10,
        ask_depths=[100.0] * 10,
    )
    result = engine.process(snap)
    assert result.depth_gradient == pytest.approx(0.0)
