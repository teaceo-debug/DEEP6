"""BracketExitTracker unit + integration tests (Phase 13-03).

Covers the four critical behaviors required by the plan:
  1. Target hit → exit_reason=TARGET, positive pnl, commissions deducted.
  2. Stop hit   → exit_reason=STOP, negative pnl, slippage applied.
  3. Tight bar straddling both levels → STOP wins (pessimistic tie-break).
  4. Sideways hold beyond max_hold_bars → force-exit at HOLD_EXPIRY.

These are unit tests against BracketExitTracker directly — they do not
spin up a ReplaySession. They verify the math precisely so that the
ReplaySession integration is free to focus on wiring.
"""
from __future__ import annotations

from datetime import datetime, timezone

from deep6.backtest.bracket_exit import BracketExitTracker
from deep6.backtest.config import BacktestConfig
from deep6.state.footprint import FootprintBar


def _cfg(**overrides) -> BacktestConfig:
    base = dict(
        dataset="GLBX.MDP3",
        symbol="NQ.c.0",
        start=datetime(2026, 4, 9, tzinfo=timezone.utc),
        end=datetime(2026, 4, 10, tzinfo=timezone.utc),
        # NQ-realistic defaults — overridden in individual tests.
        stop_ticks=16,      # 4 points at 0.25 tick
        target_ticks=24,    # 6 points
        commission_per_side=0.35,
        tick_value=5.0,
        slippage_ticks=1,
        max_hold_bars=5,
    )
    base.update(overrides)
    return BacktestConfig(**base)


def _bar(high: float, low: float, close: float | None = None) -> FootprintBar:
    b = FootprintBar()
    b.high = high
    b.low = low
    b.close = close if close is not None else (high + low) / 2
    b.open = b.low
    return b


# ----------------------------------------------------------------------
# 1. TARGET hit → winner
# ----------------------------------------------------------------------

def test_target_hit_long_emits_positive_pnl() -> None:
    cfg = _cfg()
    tracker = BracketExitTracker(cfg)
    tracker.open_trade(
        trade_id="t1", entry_price=21000.0, direction=1, entry_ts=0.0,
    )

    # Bar moves UP past target (21000 + 6 = 21006).
    closed = tracker.on_bar(_bar(high=21007.0, low=21000.5), ts=60.0)

    assert len(closed) == 1
    ct = closed[0]
    assert ct.trade_id == "t1"
    assert ct.exit_reason == "TARGET"
    assert ct.exit_price == 21006.0    # target fills at limit, no slippage
    # 6 points = 24 ticks × $5 = $120 gross; minus 2×$0.35 = $119.30 net.
    assert ct.pnl_ticks == 24.0
    assert abs(ct.pnl_dollars - 119.30) < 1e-6
    assert tracker.open_count == 0


# ----------------------------------------------------------------------
# 2. STOP hit → loser with slippage
# ----------------------------------------------------------------------

def test_stop_hit_long_emits_negative_pnl_with_slippage() -> None:
    cfg = _cfg()
    tracker = BracketExitTracker(cfg)
    tracker.open_trade(
        trade_id="t1", entry_price=21000.0, direction=1, entry_ts=0.0,
    )

    # Bar dips to stop (21000 - 4 = 20996).
    closed = tracker.on_bar(_bar(high=21001.0, low=20995.0), ts=60.0)

    assert len(closed) == 1
    ct = closed[0]
    assert ct.exit_reason == "STOP"
    # Slippage 1 tick = 0.25pt adverse: long stop fills at 20996 - 0.25 = 20995.75
    assert abs(ct.exit_price - 20995.75) < 1e-9
    # -4.25 points = -17 ticks × $5 = -$85 gross; minus $0.70 commission = -$85.70
    assert abs(ct.pnl_ticks + 17.0) < 1e-9
    assert abs(ct.pnl_dollars + 85.70) < 1e-6


def test_stop_hit_short_emits_negative_pnl_with_slippage() -> None:
    cfg = _cfg()
    tracker = BracketExitTracker(cfg)
    tracker.open_trade(
        trade_id="s1", entry_price=21000.0, direction=-1, entry_ts=0.0,
    )

    # Short stop = 21004. Bar rips up through it.
    closed = tracker.on_bar(_bar(high=21005.0, low=20998.0), ts=60.0)

    ct = closed[0]
    assert ct.exit_reason == "STOP"
    # Short stop fills WORSE (higher): 21004 + 0.25 = 21004.25
    assert abs(ct.exit_price - 21004.25) < 1e-9
    # Short direction: pnl_points = (21004.25 - 21000) * -1 = -4.25 pts
    assert abs(ct.pnl_dollars + 85.70) < 1e-6


# ----------------------------------------------------------------------
# 3. Tight bar: both stop AND target inside range → STOP wins
# ----------------------------------------------------------------------

def test_both_inside_bar_pessimistic_stop_wins() -> None:
    cfg = _cfg()
    tracker = BracketExitTracker(cfg)
    tracker.open_trade(
        trade_id="t1", entry_price=21000.0, direction=1, entry_ts=0.0,
    )

    # Bar range straddles BOTH stop (20996) and target (21006).
    # Pessimistic tie-break: STOP fills first.
    closed = tracker.on_bar(_bar(high=21008.0, low=20994.0), ts=60.0)

    ct = closed[0]
    assert ct.exit_reason == "STOP", (
        "Pessimistic tie-break broken: target won when both inside bar"
    )
    assert ct.pnl_dollars < 0


# ----------------------------------------------------------------------
# 4. Hold expiry → force-exit at bar close
# ----------------------------------------------------------------------

def test_hold_expiry_force_closes_at_bar_close() -> None:
    cfg = _cfg(max_hold_bars=3)
    tracker = BracketExitTracker(cfg)
    tracker.open_trade(
        trade_id="t1", entry_price=21000.0, direction=1, entry_ts=0.0,
    )

    # Sideways bars that never touch the bracket.
    sideways = _bar(high=21001.0, low=20999.0, close=21000.5)
    assert tracker.on_bar(sideways, ts=60.0) == []   # bars_held = 1
    assert tracker.on_bar(sideways, ts=120.0) == []  # bars_held = 2
    closed = tracker.on_bar(sideways, ts=180.0)      # bars_held = 3 → expiry
    assert len(closed) == 1
    ct = closed[0]
    assert ct.exit_reason == "HOLD_EXPIRY"
    assert ct.exit_price == 21000.5   # forced to bar.close
    # 0.5 points = 2 ticks × $5 = $10 gross − $0.70 = $9.30 net
    assert abs(ct.pnl_dollars - 9.30) < 1e-6
    assert tracker.open_count == 0


# ----------------------------------------------------------------------
# 5. force_close_all — session truncation path
# ----------------------------------------------------------------------

def test_force_close_all_marks_truncated() -> None:
    cfg = _cfg()
    tracker = BracketExitTracker(cfg)
    tracker.open_trade("a", 21000.0, 1, entry_ts=0.0)
    tracker.open_trade("b", 21000.0, -1, entry_ts=0.0)
    closed = tracker.force_close_all(last_price=21000.0, ts=300.0)
    assert {c.trade_id for c in closed} == {"a", "b"}
    assert all(c.exit_reason == "TRUNCATED" for c in closed)
    assert tracker.open_count == 0


# ----------------------------------------------------------------------
# 6. Validation
# ----------------------------------------------------------------------

def test_invalid_direction_raises() -> None:
    import pytest

    tracker = BracketExitTracker(_cfg())
    with pytest.raises(ValueError):
        tracker.open_trade("x", 21000.0, direction=0, entry_ts=0.0)
