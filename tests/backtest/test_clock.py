"""Tests for deep6.backtest.clock — WallClock + EventClock.

Phase 13-01: Clock abstraction so time-sensitive logic works in both live
(wall clock) and replay (event-driven) modes.
"""
import time

import pytest

from deep6.backtest.clock import Clock, EventClock, WallClock


def test_wallclock_returns_current_time() -> None:
    wc = WallClock()
    t0 = time.time()
    t1 = wc.now()
    t2 = time.time()
    assert t0 <= t1 <= t2 + 1.0  # within 1s
    assert abs(t1 - t0) < 1.0


def test_wallclock_monotonic_increases() -> None:
    wc = WallClock()
    a = wc.monotonic()
    b = wc.monotonic()
    assert b >= a


def test_eventclock_starts_at_zero_then_advances() -> None:
    ec = EventClock()
    assert ec.now() == 0.0
    ec.advance(1_700_000_000.0)
    assert ec.now() == 1_700_000_000.0


def test_eventclock_clamps_backward() -> None:
    ec = EventClock()
    ec.advance(100.0)
    ec.advance(50.0)
    # clamp forward: now stays at 100
    assert ec.now() == 100.0


def test_eventclock_monotonic_independent() -> None:
    ec = EventClock()
    m0 = ec.monotonic()
    ec.advance(1_000_000.0)
    m1 = ec.monotonic()
    ec.advance(2_000_000.0)
    m2 = ec.monotonic()
    assert m1 > m0
    assert m2 > m1
    # Fixed delta per advance — not tied to wall ts magnitude
    assert (m1 - m0) == pytest.approx(m2 - m1)


def test_clock_protocol_structural() -> None:
    wc = WallClock()
    ec = EventClock()
    assert isinstance(wc, Clock)
    assert isinstance(ec, Clock)
