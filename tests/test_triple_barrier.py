"""Unit tests for ATR triple barrier labeling.

Covers stop/target/timeout exits, trailing stop activation, MFE/MAE tracking,
and edge cases (zero ATR, bounded end bar).
"""
from __future__ import annotations

import numpy as np
import pytest

from deep6.backtest.triple_barrier import (
    ExitReason,
    Trade,
    compute_triple_barrier,
)


ATR = 10.0
ENTRY = 21000.0
# With defaults: stop_mult=0.8, target_mult=1.5 -> stop 8pt, target 15pt
STOP_DIST = 0.8 * ATR   # 8.0
TARGET_DIST = 1.5 * ATR # 15.0


def _make_bars(n: int, price: float = ENTRY) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Create n sideways bars at a single price."""
    highs = np.full(n, price, dtype=float)
    lows = np.full(n, price, dtype=float)
    closes = np.full(n, price, dtype=float)
    return highs, lows, closes


def test_long_stop_hit():
    highs, lows, closes = _make_bars(30)
    # Bar 1: drop below stop (entry - 8)
    lows[1] = ENTRY - STOP_DIST - 1.0
    highs[1] = ENTRY - 0.5
    closes[1] = ENTRY - STOP_DIST - 0.5

    trade = compute_triple_barrier(highs, lows, closes, entry_bar=0, direction=1, atr=ATR)
    assert trade.exit_reason == ExitReason.STOP
    assert trade.r_multiple <= -1.0 + 1e-9
    assert trade.exit_bar == 1


def test_long_target_hit():
    highs, lows, closes = _make_bars(30)
    # Bar 2: push above target (entry + 15)
    highs[2] = ENTRY + TARGET_DIST + 1.0
    lows[2] = ENTRY + 0.5
    closes[2] = ENTRY + TARGET_DIST

    trade = compute_triple_barrier(highs, lows, closes, entry_bar=0, direction=1, atr=ATR)
    assert trade.exit_reason == ExitReason.TARGET
    # 1.875 R:R by construction
    assert trade.r_multiple >= 1.875 - 1e-6
    assert trade.exit_bar == 2


def test_short_stop_hit():
    highs, lows, closes = _make_bars(30)
    # For short: stop = entry + 8; bar must push above
    highs[1] = ENTRY + STOP_DIST + 1.0
    lows[1] = ENTRY + 0.5
    closes[1] = ENTRY + STOP_DIST + 0.5

    trade = compute_triple_barrier(highs, lows, closes, entry_bar=0, direction=-1, atr=ATR)
    assert trade.exit_reason == ExitReason.STOP
    assert trade.r_multiple <= -1.0 + 1e-9


def test_short_target_hit():
    highs, lows, closes = _make_bars(30)
    # For short: target = entry - 15
    lows[2] = ENTRY - TARGET_DIST - 1.0
    highs[2] = ENTRY - 0.5
    closes[2] = ENTRY - TARGET_DIST

    trade = compute_triple_barrier(highs, lows, closes, entry_bar=0, direction=-1, atr=ATR)
    assert trade.exit_reason == ExitReason.TARGET
    assert trade.r_multiple >= 1.875 - 1e-6


def test_timeout_exit():
    # All sideways at ENTRY, no barrier hit
    highs, lows, closes = _make_bars(30)

    trade = compute_triple_barrier(highs, lows, closes, entry_bar=0, direction=1, atr=ATR)
    assert trade.exit_reason == ExitReason.TIMEOUT
    assert trade.exit_bar == 15  # entry_bar + max_hold_bars default
    assert trade.bars_held == 15


def test_trailing_breakeven():
    """Price runs +1 ATR (activates breakeven trail), then reverses through entry."""
    n = 30
    highs, lows, closes = _make_bars(n)
    # Bar 1: price runs favorable by 1 ATR (activate trail @ breakeven)
    highs[1] = ENTRY + ATR + 0.5  # favorable = 10.5 > trail_activation (10)
    lows[1] = ENTRY + 2.0
    closes[1] = ENTRY + ATR  # close at +10; new_trail = close - 1*ATR = ENTRY; trail = max(stop, ENTRY) = ENTRY
    # Bar 2: reverses down to touch breakeven (ENTRY)
    highs[2] = ENTRY + 1.0
    lows[2] = ENTRY - 1.0  # crosses trail_stop at ENTRY
    closes[2] = ENTRY - 0.5

    trade = compute_triple_barrier(highs, lows, closes, entry_bar=0, direction=1, atr=ATR)
    assert trade.exit_reason == ExitReason.TRAIL
    # Trail at breakeven -> exit price == ENTRY -> pnl == 0
    assert trade.exit_price == pytest.approx(ENTRY)
    assert trade.pnl_points == pytest.approx(0.0)


def test_trailing_lock_in():
    """Price runs +2 ATR, then reverses. Trail locks in gain > 0.

    Uses a distant target so trail path (not target) is exercised.
    """
    n = 30
    highs, lows, closes = _make_bars(n)
    # Bar 1: run up to +2 ATR, but below far target (5 ATR away)
    highs[1] = ENTRY + 2 * ATR  # favorable = 20
    lows[1] = ENTRY + 1.0
    closes[1] = ENTRY + 2 * ATR  # close at +20; trail = 20 - 10 = ENTRY+10
    # Bar 2: reverses down, hits trail at ENTRY+10
    highs[2] = ENTRY + 2 * ATR - 0.5
    lows[2] = ENTRY + ATR - 1.0  # dips below ENTRY+10 trail
    closes[2] = ENTRY + 5.0

    trade = compute_triple_barrier(
        highs, lows, closes, entry_bar=0, direction=1, atr=ATR,
        target_atr_mult=5.0,  # push target far away so trail engages
    )
    assert trade.exit_reason == ExitReason.TRAIL
    # Trail locked at approx ENTRY + 10 -> pnl ~10 points -> r_multiple ~ 10/8 = 1.25
    assert trade.r_multiple > 0.5
    assert trade.pnl_points > 0


def test_max_favorable_tracked():
    """Peak MFE should be captured even if we eventually lose."""
    n = 30
    highs, lows, closes = _make_bars(n)
    # Bar 1: big favorable wick but close near entry (no trail activate)
    highs[1] = ENTRY + 0.9 * ATR  # 9 points favorable, below activation (10)
    lows[1] = ENTRY - 0.5
    closes[1] = ENTRY + 0.1
    # Bar 2: stop out
    highs[2] = ENTRY + 0.5
    lows[2] = ENTRY - STOP_DIST - 1.0
    closes[2] = ENTRY - STOP_DIST - 0.5

    trade = compute_triple_barrier(highs, lows, closes, entry_bar=0, direction=1, atr=ATR)
    # MFE in R: 9 points / 8 (r_unit) = 1.125
    assert trade.max_favorable == pytest.approx(9.0 / STOP_DIST, rel=1e-6)
    assert trade.max_adverse < 0


def test_zero_atr_safe():
    """ATR=0 must not divide by zero."""
    highs, lows, closes = _make_bars(30)
    # With ATR=0, stop == target == entry; sideways -> timeout path
    trade = compute_triple_barrier(highs, lows, closes, entry_bar=0, direction=1, atr=0.0)
    assert trade.r_multiple == 0
    assert trade.max_favorable == 0
    assert trade.max_adverse == 0


def test_bounded_end_bar():
    """entry_bar near end of array: end_bar clamps to len(closes)-1, no overflow."""
    n = 5  # far shorter than max_hold_bars (15)
    highs, lows, closes = _make_bars(n)

    trade = compute_triple_barrier(highs, lows, closes, entry_bar=2, direction=1, atr=ATR)
    assert trade.exit_bar == n - 1
    assert trade.exit_reason == ExitReason.TIMEOUT
    assert trade.bars_held == (n - 1) - 2
