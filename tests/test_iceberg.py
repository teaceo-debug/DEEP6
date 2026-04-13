"""Tests for E4 IcebergEngine (ENG-04) — native and synthetic iceberg detection.

All tests use synthetic DOM snapshots and controlled timestamps — offline.

Requirement coverage:
  ENG-04 — IcebergEngine:
    - native iceberg detection (trade fill > DOM depth * ratio)
    - synthetic iceberg detection (level refills within window after depletion)
    - absorption zone conviction bonus (+3 at registered zone)
    - reset clears all state

Per D-08: NATIVE fires when trade.size > dom_size * 1.5.
Per D-09: SYNTHETIC fires after synthetic_min_refills refills within refill_window_ms.
Per D-10: conviction_bonus=3 when iceberg fires at absorption zone.
"""
from __future__ import annotations

import pytest

from deep6.engines.iceberg import IcebergEngine, IcebergSignal, IcebergType
from deep6.engines.signal_config import IcebergConfig
from deep6.state.dom import LEVELS


def make_dom_snapshot(
    ask_sizes: list[float] | None = None,
    bid_sizes: list[float] | None = None,
    center_price: float = 20000.0,
) -> tuple:
    """Build a DOM snapshot for iceberg tests.

    Returns (bid_prices, bid_sizes, ask_prices, ask_sizes) with LEVELS entries.
    """
    bid_prices = [center_price - i * 0.25 for i in range(LEVELS)]
    ask_prices = [center_price + 0.25 + i * 0.25 for i in range(LEVELS)]

    b_sizes_default = [10.0] * LEVELS
    a_sizes_default = [10.0] * LEVELS

    bs = list(bid_sizes) if bid_sizes else b_sizes_default
    as_ = list(ask_sizes) if ask_sizes else a_sizes_default

    bs = (bs + [0.0] * LEVELS)[:LEVELS]
    as_ = (as_ + [0.0] * LEVELS)[:LEVELS]

    return (bid_prices, bs, ask_prices, as_)


# ---------------------------------------------------------------------------
# ENG-04: Native iceberg detection
# ---------------------------------------------------------------------------

def test_native_iceberg_fires_when_trade_exceeds_dom():
    """ENG-04: snap with ask_sizes[0]=40; trade at same price with size=70 (> 40*1.5=60).

    Condition: size=70 > dom_size=40 * native_ratio=1.5 = 60 → NATIVE IcebergSignal.
    DOM size must be >= iceberg_min_size (30) for the level to be tracked.
    """
    engine = IcebergEngine()
    # Ask side: level 0 shows 40 contracts at ask_price[0] = 20000.25
    a_sizes = [40.0] + [5.0] * (LEVELS - 1)
    snap = make_dom_snapshot(ask_sizes=a_sizes, center_price=20000.0)

    # Trade at ask level 0: size=70 > 40 * 1.5 = 60 → native iceberg
    signal = engine.check_trade(
        price=20000.25,
        size=70.0,
        aggressor_side=+1,   # buy aggressor hits ask
        dom_snapshot=snap,
        timestamp=1000.0,
    )
    assert signal is not None
    assert isinstance(signal, IcebergSignal)
    assert signal.iceberg_type == IcebergType.NATIVE


def test_native_below_threshold_no_iceberg():
    """ENG-04: trade size=40 at level with 40 showing → 40 < 40*1.5=60 → no iceberg."""
    engine = IcebergEngine()
    a_sizes = [40.0] + [5.0] * (LEVELS - 1)
    snap = make_dom_snapshot(ask_sizes=a_sizes, center_price=20000.0)

    signal = engine.check_trade(
        price=20000.25,
        size=40.0,    # 40 == 40*1.5=60 is not strictly greater, no iceberg
        aggressor_side=+1,
        dom_snapshot=snap,
        timestamp=1000.0,
    )
    assert signal is None


def test_native_dom_none_returns_none():
    """ENG-04: check_trade with dom_snapshot=None → returns None (D-13)."""
    engine = IcebergEngine()
    signal = engine.check_trade(
        price=20000.25,
        size=100.0,
        aggressor_side=+1,
        dom_snapshot=None,
        timestamp=1000.0,
    )
    assert signal is None


# ---------------------------------------------------------------------------
# ENG-04: Synthetic iceberg detection
# ---------------------------------------------------------------------------

def test_synthetic_iceberg_fires_after_refills():
    """ENG-04: Level refills after depletion → SYNTHETIC after synthetic_min_refills.

    Use IcebergConfig with synthetic_min_refills=2 (default).
    Sequence:
      1. update_dom with ask_sizes[0]=50 (large, tracked as peak)
      2. update_dom with ask_sizes[0]=2 (< depletion_threshold * 50) → depletion recorded
      3. update_dom with ask_sizes[0]=45 (>= 50 * 0.8 = 40) → refill #1
      4. update_dom with ask_sizes[0]=2 → depletion again
      5. update_dom with ask_sizes[0]=45 → refill #2 → SYNTHETIC fires
    """
    cfg = IcebergConfig(
        iceberg_min_size=20.0,
        depletion_threshold=0.15,  # drop to < 50 * 0.15 = 7.5 to deplete
        refill_window_ms=1000.0,   # 1 second window for easy testing
        refill_ratio=0.8,          # refill to >= 50 * 0.8 = 40 to confirm
        synthetic_min_refills=2,
    )
    engine = IcebergEngine(cfg)
    center = 20000.0
    ask_prices = [center + 0.25 + i * 0.25 for i in range(LEVELS)]
    bid_prices = [center - i * 0.25 for i in range(LEVELS)]

    def make_snap_with_ask0(ask0_size: float) -> tuple:
        bs = [10.0] * LEVELS
        as_ = [ask0_size] + [10.0] * (LEVELS - 1)
        return (bid_prices, bs, ask_prices, as_)

    ts = 1000.0
    interval = 0.05  # 50ms between snapshots

    all_signals = []

    # Step 1: Large level appears
    signals = engine.update_dom(*make_snap_with_ask0(50.0)[1:3], *make_snap_with_ask0(50.0)[0:1], make_snap_with_ask0(50.0)[3], ts)
    # Correct call:
    snap = make_snap_with_ask0(50.0)
    signals = engine.update_dom(snap[0], snap[1], snap[2], snap[3], ts)
    all_signals.extend(signals)
    ts += interval

    # Step 2: Depletion — ask drops to 2
    snap = make_snap_with_ask0(2.0)
    signals = engine.update_dom(snap[0], snap[1], snap[2], snap[3], ts)
    all_signals.extend(signals)
    ts += interval

    # Step 3: Refill #1 — ask refills to 45
    snap = make_snap_with_ask0(45.0)
    signals = engine.update_dom(snap[0], snap[1], snap[2], snap[3], ts)
    all_signals.extend(signals)
    ts += interval

    # Step 4: Depletion again
    snap = make_snap_with_ask0(2.0)
    signals = engine.update_dom(snap[0], snap[1], snap[2], snap[3], ts)
    all_signals.extend(signals)
    ts += interval

    # Step 5: Refill #2 → should fire SYNTHETIC
    snap = make_snap_with_ask0(45.0)
    signals = engine.update_dom(snap[0], snap[1], snap[2], snap[3], ts)
    all_signals.extend(signals)

    synthetic_signals = [s for s in all_signals if s.iceberg_type == IcebergType.SYNTHETIC]
    assert len(synthetic_signals) >= 1


# ---------------------------------------------------------------------------
# ENG-04: Absorption zone conviction bonus
# ---------------------------------------------------------------------------

def test_absorption_zone_bonus_at_registered_price():
    """ENG-04 / D-10: mark_absorption_zone at ask level, then fire NATIVE there →
    conviction_bonus=3.

    DOM must show >= iceberg_min_size (30) at the level; trade must exceed dom * 1.5.
    """
    engine = IcebergEngine()
    engine.mark_absorption_zone(20000.25, radius_ticks=4)

    # Ask level 0 shows 40 contracts (>= iceberg_min_size=30)
    a_sizes = [40.0] + [5.0] * (LEVELS - 1)
    snap = make_dom_snapshot(ask_sizes=a_sizes, center_price=20000.0)

    # Trade size=70 > 40 * 1.5 = 60 → native iceberg
    signal = engine.check_trade(
        price=20000.25,
        size=70.0,
        aggressor_side=+1,
        dom_snapshot=snap,
        timestamp=1000.0,
    )
    assert signal is not None
    assert signal.at_absorption_zone is True
    assert signal.conviction_bonus == 3


def test_no_absorption_zone_bonus_unregistered_price():
    """ENG-04: NATIVE at unregistered price → conviction_bonus=0, at_absorption_zone=False."""
    engine = IcebergEngine()
    # No mark_absorption_zone called

    # Ask level 0 shows 40 contracts (>= iceberg_min_size=30)
    a_sizes = [40.0] + [5.0] * (LEVELS - 1)
    snap = make_dom_snapshot(ask_sizes=a_sizes, center_price=20000.0)

    # Trade size=70 > 40 * 1.5 = 60 → native iceberg (but no zone registered)
    signal = engine.check_trade(
        price=20000.25,
        size=70.0,
        aggressor_side=+1,
        dom_snapshot=snap,
        timestamp=1000.0,
    )
    assert signal is not None
    assert signal.at_absorption_zone is False
    assert signal.conviction_bonus == 0


# ---------------------------------------------------------------------------
# ENG-04: Reset clears state
# ---------------------------------------------------------------------------

def test_reset_clears_all_state():
    """ENG-04: After tracking, reset() → no state remains."""
    engine = IcebergEngine()
    engine.mark_absorption_zone(20000.0, radius_ticks=4)

    # Trigger some state
    a_sizes = [50.0] + [5.0] * (LEVELS - 1)
    snap = make_dom_snapshot(ask_sizes=a_sizes, center_price=20000.0)
    engine.update_dom(snap[0], snap[1], snap[2], snap[3], 1000.0)

    engine.reset()

    assert len(engine._level_depletions) == 0
    assert len(engine._level_prior_sizes) == 0
    assert len(engine._level_peak_sizes) == 0
    assert len(engine._refill_counts) == 0
    assert len(engine._absorption_zone_prices) == 0


# ---------------------------------------------------------------------------
# ENG-04: is_at_absorption_zone
# ---------------------------------------------------------------------------

def test_is_at_absorption_zone_within_radius():
    """ENG-04: Prices within radius_ticks=4 of marked zone → True."""
    engine = IcebergEngine()
    engine.mark_absorption_zone(21000.0, radius_ticks=4)

    assert engine.is_at_absorption_zone(21000.0) is True
    assert engine.is_at_absorption_zone(21001.0) is True   # 4 ticks above
    assert engine.is_at_absorption_zone(20999.0) is True   # 4 ticks below


def test_is_at_absorption_zone_outside_radius():
    """ENG-04: Price outside radius_ticks → False."""
    engine = IcebergEngine()
    engine.mark_absorption_zone(21000.0, radius_ticks=2)

    # 3 ticks above = 21000 + 3*0.25 = 21000.75 → outside radius 2
    assert engine.is_at_absorption_zone(21000.75) is False
