"""Intrabar delta tracking tests for FootprintBar (Plan 12-02, Task 1).

Verifies:
  - running_delta is updated on every add_trade (BUY=+size, SELL=-size)
  - max_delta / min_delta track running extremes
  - delta_quality_scalar() returns 1.15 when closing-at-extreme, 0.7 when peaked-and-faded,
    and interpolates linearly between
  - Existing footprint fields (bar_delta, total_vol, levels) are unaffected by default-zero values

These fields underpin the DELT_TAIL (bit 22) fix in Task 2 — the scalar is consumed
by the delta engine; bit positions 0-43 remain stable (no new signal bit).
"""
from __future__ import annotations

import pytest

from deep6.state.footprint import FootprintBar


# ---------------------------------------------------------------------------
# Running max/min delta updates
# ---------------------------------------------------------------------------

def test_intrabar_monotonic_rise():
    """10 buy trades of size 5 → running_delta=50, max_delta=50, min_delta=0."""
    bar = FootprintBar()
    for _ in range(10):
        bar.add_trade(21000.0, 5, aggressor=1)  # BUY
    assert bar.running_delta == 50
    assert bar.max_delta == 50
    assert bar.min_delta == 0


def test_intrabar_reversal():
    """5 buys size 5 then 10 sells size 5 → running=-25, max=25, min=-25."""
    bar = FootprintBar()
    for _ in range(5):
        bar.add_trade(21000.0, 5, aggressor=1)  # BUY (+25 cumulative)
    for _ in range(10):
        bar.add_trade(21000.0, 5, aggressor=2)  # SELL
    assert bar.running_delta == -25
    assert bar.max_delta == 25
    assert bar.min_delta == -25


def test_intrabar_running_delta_matches_bar_delta_after_finalize():
    """After finalize(), bar.bar_delta should equal bar.running_delta (same quantity)."""
    bar = FootprintBar()
    bar.add_trade(21000.0, 7, aggressor=1)
    bar.add_trade(21000.25, 3, aggressor=2)
    bar.add_trade(21000.0, 4, aggressor=1)
    bar.finalize()
    # bar_delta is derived from levels (ask_vol - bid_vol).
    # running_delta is the live running sum from add_trade.
    # Invariant: the two must agree (both are sum of signed trade sizes).
    assert bar.bar_delta == bar.running_delta == (7 - 3 + 4)


# ---------------------------------------------------------------------------
# delta_quality_scalar() — closing-at-extreme vs peaked-and-faded
# ---------------------------------------------------------------------------

def test_delta_quality_scalar_closing_at_max():
    """running_delta==max_delta at close → scalar == 1.15 (closing-at-extreme)."""
    bar = FootprintBar()
    for _ in range(10):
        bar.add_trade(21000.0, 5, aggressor=1)
    # running_delta=50, max_delta=50, ratio = 1.0 >= 0.95
    assert bar.delta_quality_scalar() == pytest.approx(1.15)


def test_delta_quality_scalar_peaked_and_faded():
    """max_delta=100, final running_delta=20 → scalar == 0.7 (peaked-and-faded).

    Ratio = 20/100 = 0.2, which is < 0.35 floor → 0.7.
    """
    bar = FootprintBar()
    # Push to +100
    for _ in range(20):
        bar.add_trade(21000.0, 5, aggressor=1)
    # Fade back to +20 via 16 sells of size 5 = -80
    for _ in range(16):
        bar.add_trade(21000.0, 5, aggressor=2)
    assert bar.running_delta == 20
    assert bar.max_delta == 100
    assert bar.delta_quality_scalar() == pytest.approx(0.7)


def test_delta_quality_scalar_neutral_mixed():
    """Mixed case in the linear-interpolation zone (0.35 < ratio < 0.95) returns (0.7, 1.15)."""
    bar = FootprintBar()
    # Push to +100
    for _ in range(20):
        bar.add_trade(21000.0, 5, aggressor=1)
    # Fade back to +60 (ratio = 0.60 — mid zone)
    for _ in range(8):
        bar.add_trade(21000.0, 5, aggressor=2)
    assert bar.running_delta == 60
    assert bar.max_delta == 100
    q = bar.delta_quality_scalar()
    assert 0.7 < q < 1.15


def test_delta_quality_scalar_empty_bar_returns_neutral():
    """Empty bar: no trades, running_delta=0, max_delta=0 → scalar == 1.0 (neutral)."""
    bar = FootprintBar()
    assert bar.delta_quality_scalar() == pytest.approx(1.0)


def test_delta_quality_scalar_negative_extreme():
    """Sell-dominated bar closing at min_delta (running_delta==min_delta) → 1.15."""
    bar = FootprintBar()
    for _ in range(10):
        bar.add_trade(21000.0, 5, aggressor=2)  # SELL → -50
    assert bar.running_delta == -50
    assert bar.min_delta == -50
    assert bar.delta_quality_scalar() == pytest.approx(1.15)


# ---------------------------------------------------------------------------
# No regression: existing level accumulation still works
# ---------------------------------------------------------------------------

def test_level_vol_accumulation_unchanged():
    """add_trade still accumulates bid/ask vol per level (intrabar fields don't break it)."""
    bar = FootprintBar()
    bar.add_trade(21000.0, 5, aggressor=1)
    bar.add_trade(21000.0, 3, aggressor=2)
    tick = 84000  # 21000.0 / 0.25
    assert bar.levels[tick].ask_vol == 5
    assert bar.levels[tick].bid_vol == 3
    assert bar.total_vol == 8
