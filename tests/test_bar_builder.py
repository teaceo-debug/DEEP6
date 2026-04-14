"""BarBuilder timing and RTH gate tests."""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from deep6.data.bar_builder import BarBuilder, next_boundary
from deep6.state.session import SessionContext
from deep6.signals.atr import ATRTracker


# --- next_boundary tests ---

def test_next_boundary_60s():
    """next_boundary(60) returns a datetime whose timestamp % 60 == 0."""
    boundary = next_boundary(60)
    ts = boundary.timestamp()
    assert ts % 60 == 0, f"Boundary {ts} is not divisible by 60"


def test_next_boundary_is_future():
    boundary = next_boundary(60)
    now = datetime.now(timezone.utc)
    assert boundary > now


# --- RTH gate tests ---

def test_on_trade_blocked_outside_rth():
    """Trades outside 9:30-16:00 ET must not accumulate."""
    from zoneinfo import ZoneInfo
    state = MagicMock()
    state.freeze_guard.is_frozen = False
    # Phase 13-01: _is_rth now reads state.clock.now(); mock it to an
    # epoch whose ET representation is 8:00 AM (outside RTH).
    et_time = datetime(2026, 4, 11, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    state.clock.now.return_value = et_time.timestamp()
    builder = BarBuilder(period_seconds=60, label="1m", state=state)
    builder.on_trade(21000.0, 10, aggressor=1)
    assert builder.current_bar.total_vol == 0


def test_on_trade_allowed_inside_rth():
    """Trades at 10:00 AM ET (inside RTH) must accumulate."""
    from zoneinfo import ZoneInfo
    state = MagicMock()
    state.freeze_guard.is_frozen = False
    et_time = datetime(2026, 4, 11, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    state.clock.now.return_value = et_time.timestamp()
    builder = BarBuilder(period_seconds=60, label="1m", state=state)
    builder.on_trade(21000.0, 5, aggressor=1)
    assert builder.current_bar.total_vol == 5


# --- ATRTracker tests ---

def test_atr_not_ready_before_20_bars():
    tracker = ATRTracker(period=20)
    for i in range(19):
        tracker.update(high=100.0 + i, low=99.0 + i, close=100.0 + i)
    assert not tracker.ready


def test_atr_ready_after_20_bars():
    tracker = ATRTracker(period=20)
    for i in range(20):
        tracker.update(high=100.0 + i, low=99.0 + i, close=100.0 + i)
    assert tracker.ready


def test_atr_seed_value():
    """First 20 TRs all equal 1.0 → initial ATR should be 1.0."""
    tracker = ATRTracker(period=20)
    for i in range(20):
        tracker.update(high=101.0, low=100.0, close=100.5)
    assert tracker.atr == pytest.approx(1.0, abs=1e-9)


# --- SessionContext tests ---

def test_session_context_initial_cvd():
    ctx = SessionContext()
    assert ctx.cvd == 0


def test_session_context_reset():
    ctx = SessionContext()
    ctx.cvd = 500
    ctx.vwap_numerator = 1000.0
    ctx.reset()
    assert ctx.cvd == 0
    assert ctx.vwap_numerator == 0.0
