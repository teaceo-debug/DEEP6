"""Tests for TrapEngine — TRAP-02..05 (4 trapped trader signal variants).

TRAP-01 (INVERSE_TRAP) lives in imbalance.py and is tested in test_imbalance.py.
"""
from __future__ import annotations

import math
from collections import defaultdict

import pytest

from deep6.state.footprint import FootprintBar, FootprintLevel, price_to_tick


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_bar(
    open_: float = 21000.0,
    high: float = 21010.0,
    low: float = 20990.0,
    close: float = 21000.0,
    bar_delta: int = 0,
    total_vol: int = 100,
    levels: dict | None = None,
) -> FootprintBar:
    """Build a minimal FootprintBar for tests — no finalize() needed."""
    bar = FootprintBar(
        open=open_,
        high=high,
        low=low,
        close=close,
        bar_delta=bar_delta,
        total_vol=total_vol,
        bar_range=high - low,
    )
    if levels is not None:
        bar.levels = levels
    return bar


def make_levels(ticks_vols: dict[float, tuple[int, int]]) -> dict:
    """Build levels dict from {price: (bid_vol, ask_vol)}."""
    d = defaultdict(FootprintLevel)
    for price, (bid, ask) in ticks_vols.items():
        tick = price_to_tick(price)
        d[tick] = FootprintLevel(bid_vol=bid, ask_vol=ask)
    return d


# ---------------------------------------------------------------------------
# Import smoke test
# ---------------------------------------------------------------------------

def test_imports():
    from deep6.engines.trap import TrapEngine, TrapSignal, TrapType
    from deep6.engines.signal_config import TrapConfig
    assert TrapConfig  # frozen dataclass
    assert TrapEngine


def test_trap_config_fields():
    from deep6.engines.signal_config import TrapConfig
    c = TrapConfig()
    assert hasattr(c, "trap_delta_ratio")
    assert hasattr(c, "false_breakout_vol_mult")
    assert hasattr(c, "hvr_vol_mult")
    assert hasattr(c, "hvr_wick_min")
    assert hasattr(c, "cvd_trap_lookback")
    assert hasattr(c, "cvd_trap_min_slope")
    # Frozen — must not be mutable
    with pytest.raises(Exception):
        c.trap_delta_ratio = 0.99  # type: ignore[misc]


def test_trap_type_variants():
    from deep6.engines.trap import TrapType
    assert TrapType.DELTA_TRAP
    assert TrapType.FALSE_BREAKOUT_TRAP
    assert TrapType.HIGH_VOL_REJECTION_TRAP
    assert TrapType.CVD_TRAP


def test_trap_signal_fields():
    from deep6.engines.trap import TrapSignal, TrapType
    sig = TrapSignal(
        trap_type=TrapType.DELTA_TRAP,
        direction=1,
        price=21000.0,
        strength=0.5,
        detail="test",
    )
    assert sig.trap_type == TrapType.DELTA_TRAP
    assert sig.direction == 1
    assert 0.0 <= sig.strength <= 1.0


# ---------------------------------------------------------------------------
# Empty bar guard
# ---------------------------------------------------------------------------

def test_empty_bar_returns_empty():
    from deep6.engines.trap import TrapEngine
    engine = TrapEngine()
    empty_bar = make_bar(total_vol=0)
    prior = make_bar()
    result = engine.process(empty_bar, prior, vol_ema=100.0, cvd_history=[])
    assert result == []


# ---------------------------------------------------------------------------
# TRAP-02: Delta trap
# ---------------------------------------------------------------------------

class TestDeltaTrap:
    def test_fires_when_prior_high_delta_and_current_reverses(self):
        """Prior bar: strong bull delta. Current bar: close below open (bear), negative delta."""
        from deep6.engines.trap import TrapEngine, TrapType

        engine = TrapEngine()
        # Prior bar: bar_delta / total_vol = 30/100 = 0.30 >= 0.25 (threshold) — bull
        prior = make_bar(open_=21000.0, close=21005.0, bar_delta=30, total_vol=100)
        # Current bar: closes bearish AND bar_delta is negative (reversal confirmed)
        current = make_bar(open_=21005.0, close=20995.0, bar_delta=-20, total_vol=100)
        result = engine.process(current, prior, vol_ema=100.0, cvd_history=[])
        trap_types = [s.trap_type for s in result]
        assert TrapType.DELTA_TRAP in trap_types

    def test_does_not_fire_when_prior_delta_too_small(self):
        """Prior bar delta/vol ratio below threshold — no delta trap."""
        from deep6.engines.trap import TrapEngine, TrapType

        engine = TrapEngine()
        # Prior bar: delta/vol = 10/100 = 0.10 < 0.25 — too weak
        prior = make_bar(open_=21000.0, close=21005.0, bar_delta=10, total_vol=100)
        current = make_bar(open_=21005.0, close=20995.0, bar_delta=-25, total_vol=100)
        result = engine.process(current, prior, vol_ema=100.0, cvd_history=[])
        trap_types = [s.trap_type for s in result]
        assert TrapType.DELTA_TRAP not in trap_types

    def test_does_not_fire_when_current_bar_no_reversal(self):
        """Prior strong bull, current also bull closes up — no trap."""
        from deep6.engines.trap import TrapEngine, TrapType

        engine = TrapEngine()
        prior = make_bar(open_=21000.0, close=21005.0, bar_delta=30, total_vol=100)
        current = make_bar(open_=21005.0, close=21010.0, bar_delta=20, total_vol=100)
        result = engine.process(current, prior, vol_ema=100.0, cvd_history=[])
        trap_types = [s.trap_type for s in result]
        assert TrapType.DELTA_TRAP not in trap_types

    def test_no_prior_bar_returns_no_delta_trap(self):
        from deep6.engines.trap import TrapEngine, TrapType

        engine = TrapEngine()
        current = make_bar(open_=21005.0, close=20995.0, bar_delta=-20, total_vol=100)
        result = engine.process(current, None, vol_ema=100.0, cvd_history=[])
        trap_types = [s.trap_type for s in result]
        assert TrapType.DELTA_TRAP not in trap_types

    def test_direction_is_sign_of_current_delta(self):
        from deep6.engines.trap import TrapEngine, TrapType

        engine = TrapEngine()
        prior = make_bar(open_=21000.0, close=21005.0, bar_delta=30, total_vol=100)
        current = make_bar(open_=21005.0, close=20995.0, bar_delta=-20, total_vol=100)
        result = engine.process(current, prior, vol_ema=100.0, cvd_history=[])
        delta_trap = next((s for s in result if s.trap_type == TrapType.DELTA_TRAP), None)
        assert delta_trap is not None
        assert delta_trap.direction == -1  # sign of -20


# ---------------------------------------------------------------------------
# TRAP-03: False breakout trap
# ---------------------------------------------------------------------------

class TestFalseBreakoutTrap:
    def _make_breakout_bar(self, *, above: bool, vol_ema: float = 100.0) -> tuple:
        """Returns (current_bar, prior_bar, vol_ema) for a bear false breakout above."""
        prior = make_bar(high=21010.0, low=20990.0)
        if above:
            # Broke above prior high but closed back below it — longs trapped
            current = make_bar(
                open_=21008.0,
                high=21020.0,  # above prior high of 21010
                low=20995.0,
                close=21005.0,  # closed BELOW prior high of 21010 → trap
                bar_delta=-10,
                total_vol=int(vol_ema * 2.0),  # above 1.8x threshold
            )
        else:
            # Broke below prior low but closed back above it — shorts trapped
            current = make_bar(
                open_=20992.0,
                high=21005.0,
                low=20980.0,   # below prior low of 20990
                close=20995.0,  # closed ABOVE prior low of 20990 → trap
                bar_delta=10,
                total_vol=int(vol_ema * 2.0),
            )
        return current, prior, vol_ema

    def test_bear_false_breakout_fires(self):
        from deep6.engines.trap import TrapEngine, TrapType

        engine = TrapEngine()
        current, prior, vol_ema = self._make_breakout_bar(above=True)
        result = engine.process(current, prior, vol_ema=vol_ema, cvd_history=[])
        trap_types = [s.trap_type for s in result]
        assert TrapType.FALSE_BREAKOUT_TRAP in trap_types

    def test_bull_false_breakout_fires(self):
        from deep6.engines.trap import TrapEngine, TrapType

        engine = TrapEngine()
        current, prior, vol_ema = self._make_breakout_bar(above=False)
        result = engine.process(current, prior, vol_ema=vol_ema, cvd_history=[])
        trap_types = [s.trap_type for s in result]
        assert TrapType.FALSE_BREAKOUT_TRAP in trap_types

    def test_no_trap_when_close_above_breakout_level(self):
        """Close remains above prior high — real breakout, not false."""
        from deep6.engines.trap import TrapEngine, TrapType

        engine = TrapEngine()
        prior = make_bar(high=21010.0)
        current = make_bar(
            high=21020.0,
            close=21018.0,  # closed ABOVE prior high — breakout held
            total_vol=200,
        )
        result = engine.process(current, prior, vol_ema=100.0, cvd_history=[])
        trap_types = [s.trap_type for s in result]
        assert TrapType.FALSE_BREAKOUT_TRAP not in trap_types

    def test_no_trap_when_volume_too_low(self):
        """Breakout occurred but volume not elevated enough."""
        from deep6.engines.trap import TrapEngine, TrapType

        engine = TrapEngine()
        prior = make_bar(high=21010.0)
        current = make_bar(
            high=21020.0,
            close=21005.0,
            total_vol=100,   # vol_ema=100 → ratio=1.0 < 1.8 threshold
        )
        result = engine.process(current, prior, vol_ema=100.0, cvd_history=[])
        trap_types = [s.trap_type for s in result]
        assert TrapType.FALSE_BREAKOUT_TRAP not in trap_types

    def test_direction_longs_trapped(self):
        from deep6.engines.trap import TrapEngine, TrapType

        engine = TrapEngine()
        current, prior, vol_ema = self._make_breakout_bar(above=True)
        result = engine.process(current, prior, vol_ema=vol_ema, cvd_history=[])
        sig = next(s for s in result if s.trap_type == TrapType.FALSE_BREAKOUT_TRAP)
        assert sig.direction == -1  # longs trapped


# ---------------------------------------------------------------------------
# TRAP-04: High volume rejection trap
# ---------------------------------------------------------------------------

class TestHighVolRejectionTrap:
    def test_fires_on_high_vol_upper_wick(self):
        """High volume bar with large upper wick — direction -1 (longs rejected)."""
        from deep6.engines.trap import TrapEngine, TrapType

        engine = TrapEngine()
        levels = make_levels({
            21000.0: (10, 10),
            21005.0: (5, 60),   # heavy volume near high → upper wick
            21010.0: (3, 5),
        })
        bar = make_bar(
            open_=21000.0,
            high=21012.0,
            low=20999.0,
            close=21001.0,
            total_vol=280,   # well above vol_ema * 2.5 = 100*2.5=250 threshold
            bar_delta=50,
            levels=levels,
        )
        result = engine.process(bar, None, vol_ema=100.0, cvd_history=[])
        trap_types = [s.trap_type for s in result]
        assert TrapType.HIGH_VOL_REJECTION_TRAP in trap_types

    def test_does_not_fire_when_vol_too_low(self):
        """Volume below 2.5× vol_ema — no HVR trap."""
        from deep6.engines.trap import TrapEngine, TrapType

        engine = TrapEngine()
        bar = make_bar(total_vol=200, bar_range=10.0)  # vol_ema=100 → 2.0x < 2.5
        result = engine.process(bar, None, vol_ema=100.0, cvd_history=[])
        trap_types = [s.trap_type for s in result]
        assert TrapType.HIGH_VOL_REJECTION_TRAP not in trap_types

    def test_direction_upper_wick_is_bear(self):
        from deep6.engines.trap import TrapEngine, TrapType

        engine = TrapEngine()
        # Build bar where upper wick volume dominates
        levels = make_levels({
            21008.0: (1, 200),  # massive ask vol near top = upper wick rejection
            21000.0: (5, 5),
        })
        bar = make_bar(
            open_=21000.0,
            high=21010.0,
            low=20998.0,
            close=21001.0,
            total_vol=270,
            bar_delta=194,
            levels=levels,
        )
        result = engine.process(bar, None, vol_ema=100.0, cvd_history=[])
        trap_types = [s.trap_type for s in result]
        assert TrapType.HIGH_VOL_REJECTION_TRAP in trap_types
        sig = next(s for s in result if s.trap_type == TrapType.HIGH_VOL_REJECTION_TRAP)
        assert sig.direction == -1  # upper wick → bear direction


# ---------------------------------------------------------------------------
# TRAP-05: CVD trap
# ---------------------------------------------------------------------------

class TestCVDTrap:
    def _make_trending_cvd(self, n: int = 10, uptrend: bool = True) -> list[int]:
        """Generate a monotonically trending CVD history."""
        step = 50 if uptrend else -50
        return list(range(0, step * n, step))

    def test_fires_on_cvd_trend_reversal_uptrend(self):
        """CVD has been rising, then reverses. Close is below open (bearish reversal)."""
        from deep6.engines.trap import TrapEngine, TrapType

        engine = TrapEngine()
        cvd_history = self._make_trending_cvd(n=10, uptrend=True)
        # Bar that reverses the CVD trend: strongly negative delta
        bar = make_bar(open_=21005.0, close=20995.0, bar_delta=-80, total_vol=100)
        result = engine.process(bar, None, vol_ema=100.0, cvd_history=cvd_history)
        trap_types = [s.trap_type for s in result]
        assert TrapType.CVD_TRAP in trap_types

    def test_fires_on_cvd_trend_reversal_downtrend(self):
        """CVD has been falling, then reverses upward."""
        from deep6.engines.trap import TrapEngine, TrapType

        engine = TrapEngine()
        cvd_history = self._make_trending_cvd(n=10, uptrend=False)
        bar = make_bar(open_=20995.0, close=21005.0, bar_delta=80, total_vol=100)
        result = engine.process(bar, None, vol_ema=100.0, cvd_history=cvd_history)
        trap_types = [s.trap_type for s in result]
        assert TrapType.CVD_TRAP in trap_types

    def test_no_fire_when_cvd_insufficient_history(self):
        """Not enough CVD history — no CVD trap."""
        from deep6.engines.trap import TrapEngine, TrapType

        engine = TrapEngine()
        bar = make_bar(bar_delta=-80, total_vol=100)
        result = engine.process(bar, None, vol_ema=100.0, cvd_history=[0, 10, 20])
        trap_types = [s.trap_type for s in result]
        assert TrapType.CVD_TRAP not in trap_types

    def test_no_fire_when_cvd_flat(self):
        """CVD is flat (slope ≈ 0) — no meaningful trend to trap against."""
        from deep6.engines.trap import TrapEngine, TrapType

        engine = TrapEngine()
        cvd_history = [100] * 10  # completely flat
        bar = make_bar(bar_delta=-80, total_vol=100)
        result = engine.process(bar, None, vol_ema=100.0, cvd_history=cvd_history)
        trap_types = [s.trap_type for s in result]
        assert TrapType.CVD_TRAP not in trap_types

    def test_cvd_history_not_mutated(self):
        """Engine must not mutate caller-owned cvd_history list (T-04-01)."""
        from deep6.engines.trap import TrapEngine

        engine = TrapEngine()
        cvd_history = list(range(0, 500, 50))
        original = list(cvd_history)
        bar = make_bar(bar_delta=-80, total_vol=100)
        engine.process(bar, None, vol_ema=100.0, cvd_history=cvd_history)
        assert cvd_history == original
