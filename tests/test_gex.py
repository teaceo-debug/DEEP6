"""Tests for GexEngine — regime, staleness, near-wall, config (GEX-01..06)."""
from __future__ import annotations

import time

import pytest

from deep6.engines.gex import GexEngine, GexLevels, GexRegime, GexSignal
from deep6.engines.signal_config import GexConfig


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

def test_gex_config_default():
    """GexEngine default staleness_seconds == 900.0."""
    eng = GexEngine(api_key="test")
    assert eng.staleness_seconds == 900.0


def test_gex_config_override():
    """GexEngine with GexConfig(staleness_seconds=300) applies override."""
    eng = GexEngine(api_key="test", config=GexConfig(staleness_seconds=300.0))
    assert eng.staleness_seconds == 300.0


# ---------------------------------------------------------------------------
# GEX-06: Staleness
# ---------------------------------------------------------------------------

def test_gex_staleness_flag():
    """GexLevels already marked stale → get_signal() returns NEUTRAL immediately.

    The stale flag is set by a prior get_signal() call when age > staleness_seconds.
    On the *next* call, levels.stale=True causes early return with NEUTRAL.
    """
    eng = GexEngine(api_key="test")
    # Inject levels already marked stale (as would happen after first detection)
    eng._levels = GexLevels(
        call_wall=500.0,
        put_wall=480.0,
        gamma_flip=490.0,
        hvl=495.0,
        regime=GexRegime.POSITIVE_DAMPENING,
        net_gex_at_spot=5e9,
        timestamp=time.time() - 1000.0,
        stale=True,  # Already marked stale
    )
    sig = eng.get_signal(nq_price=20000.0)
    assert sig.regime == GexRegime.NEUTRAL


def test_gex_staleness_marks_levels_stale():
    """After get_signal() detects age > staleness_seconds, levels.stale becomes True."""
    eng = GexEngine(api_key="test")
    eng._levels = GexLevels(
        call_wall=500.0,
        put_wall=480.0,
        gamma_flip=490.0,
        regime=GexRegime.POSITIVE_DAMPENING,
        timestamp=time.time() - 2000.0,  # Way past 900s threshold
        stale=False,
    )
    eng.get_signal(nq_price=20000.0)
    # After the call, the flag should be set for next call
    assert eng._levels.stale is True


# ---------------------------------------------------------------------------
# No data
# ---------------------------------------------------------------------------

def test_gex_no_data_returns_neutral():
    """GexEngine with no fetch → get_signal() returns GexRegime.NEUTRAL."""
    eng = GexEngine(api_key="test")
    sig = eng.get_signal(nq_price=20000.0)
    assert sig.regime == GexRegime.NEUTRAL
    assert sig.direction == 0


# ---------------------------------------------------------------------------
# GEX regime classification
# ---------------------------------------------------------------------------

def test_gex_regime_positive():
    """Spot above gamma_flip → POSITIVE_DAMPENING, direction=+1.

    QQQ_approx = 500.0 (NQ 20000 / 40), gamma_flip = 490.0 → spot > flip.
    """
    eng = GexEngine(api_key="test")
    eng._levels = GexLevels(
        call_wall=520.0,
        put_wall=470.0,
        gamma_flip=490.0,
        hvl=510.0,
        regime=GexRegime.POSITIVE_DAMPENING,
        net_gex_at_spot=5e9,
        timestamp=time.time(),
        stale=False,
    )
    sig = eng.get_signal(nq_price=20000.0)  # QQQ approx = 500.0 > gamma_flip=490.0
    assert sig.regime == GexRegime.POSITIVE_DAMPENING
    assert sig.direction == +1


def test_gex_regime_negative():
    """Spot below gamma_flip → NEGATIVE_AMPLIFYING, direction=-1.

    QQQ_approx = 500.0 (NQ 20000 / 40), gamma_flip = 510.0 → spot < flip.
    """
    eng = GexEngine(api_key="test")
    eng._levels = GexLevels(
        call_wall=530.0,
        put_wall=480.0,
        gamma_flip=510.0,
        hvl=520.0,
        regime=GexRegime.NEGATIVE_AMPLIFYING,
        net_gex_at_spot=-5e9,
        timestamp=time.time(),
        stale=False,
    )
    sig = eng.get_signal(nq_price=20000.0)  # QQQ approx = 500.0 < gamma_flip=510.0
    assert sig.regime == GexRegime.NEGATIVE_AMPLIFYING
    assert sig.direction == -1


# ---------------------------------------------------------------------------
# GEX-05: Near wall detection
# ---------------------------------------------------------------------------

def test_near_call_wall():
    """Spot within 0.5% of call_wall → near_call_wall=True.

    NQ=20000 → QQQ_approx=500.0. Call wall at 502.0:
    |500.0 - 502.0| / 502.0 = 0.4% < 0.5% → near.
    """
    eng = GexEngine(api_key="test")
    call_wall = 502.0  # Within 0.5% of 500.0
    eng._levels = GexLevels(
        call_wall=call_wall,
        put_wall=470.0,
        gamma_flip=490.0,
        regime=GexRegime.POSITIVE_DAMPENING,
        net_gex_at_spot=5e9,
        timestamp=time.time(),
        stale=False,
    )
    sig = eng.get_signal(nq_price=20000.0)
    assert sig.near_call_wall is True


def test_near_put_wall():
    """Spot within 0.5% of put_wall → near_put_wall=True.

    NQ=20000 → QQQ_approx=500.0. Put wall at 498.0:
    |500.0 - 498.0| / 498.0 = 0.4% < 0.5% → near.
    """
    eng = GexEngine(api_key="test")
    put_wall = 498.0  # Within 0.5% of 500.0
    eng._levels = GexLevels(
        call_wall=530.0,
        put_wall=put_wall,
        gamma_flip=490.0,
        regime=GexRegime.POSITIVE_DAMPENING,
        net_gex_at_spot=5e9,
        timestamp=time.time(),
        stale=False,
    )
    sig = eng.get_signal(nq_price=20000.0)
    assert sig.near_put_wall is True


def test_not_near_call_wall():
    """Spot more than 0.5% away from call_wall → near_call_wall=False."""
    eng = GexEngine(api_key="test")
    call_wall = 510.0  # 2% away from 500.0
    eng._levels = GexLevels(
        call_wall=call_wall,
        put_wall=470.0,
        gamma_flip=490.0,
        regime=GexRegime.POSITIVE_DAMPENING,
        net_gex_at_spot=5e9,
        timestamp=time.time(),
        stale=False,
    )
    sig = eng.get_signal(nq_price=20000.0)
    assert sig.near_call_wall is False
