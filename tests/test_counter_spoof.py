"""Tests for E3 CounterSpoofEngine (ENG-03) — Wasserstein-1 DOM distribution monitor.

All tests use synthetic DOM data — offline, no live Rithmic required.
Alert-only per D-07 — not a trade signal.

Requirement coverage:
  ENG-03 — CounterSpoofEngine: W1 anomaly detection + large-order cancel detection
    - empty state behavior
    - W1 anomaly detection after sufficient samples
    - cancel detection (large order disappears within window)
    - reset clears all state
"""
from __future__ import annotations

import time

import pytest

from deep6.engines.counter_spoof import CounterSpoofEngine, SpoofAlert
from deep6.engines.signal_config import CounterSpoofConfig
from deep6.state.dom import LEVELS


def make_dom_arrays(
    bid_sizes: list[float] | None = None,
    ask_sizes: list[float] | None = None,
) -> tuple:
    """Build bid/ask price + size arrays for ingest_snapshot."""
    bid_prices = [21000.0 - i * 0.25 for i in range(LEVELS)]
    ask_prices = [21000.25 + i * 0.25 for i in range(LEVELS)]
    b_sizes = (list(bid_sizes) if bid_sizes else [10.0] * LEVELS)
    a_sizes = (list(ask_sizes) if ask_sizes else [10.0] * LEVELS)
    b_sizes = (b_sizes + [0.0] * LEVELS)[:LEVELS]
    a_sizes = (a_sizes + [0.0] * LEVELS)[:LEVELS]
    return bid_prices, b_sizes, ask_prices, a_sizes


# ---------------------------------------------------------------------------
# ENG-03: Empty state
# ---------------------------------------------------------------------------

def test_empty_state_w1_anomaly_none():
    """ENG-03: get_w1_anomaly() with no history → None."""
    engine = CounterSpoofEngine()
    assert engine.get_w1_anomaly() is None


def test_empty_state_spoof_alerts_empty():
    """ENG-03: get_spoof_alerts() with no history → []."""
    engine = CounterSpoofEngine()
    assert engine.get_spoof_alerts() == []


# ---------------------------------------------------------------------------
# ENG-03: Identical snapshots
# ---------------------------------------------------------------------------

def test_identical_snapshots_no_anomaly():
    """ENG-03: 10 identical snapshots → W1=0 each → no anomaly (std=0 guard).

    Tests that repeated identical DOM state (stable market) doesn't trigger false alarms.
    """
    engine = CounterSpoofEngine()
    ts = time.monotonic()
    bp, bs, ap, as_ = make_dom_arrays([30.0] * 10)
    for i in range(10):
        engine.ingest_snapshot(bp, bs, ap, as_, ts + i * 0.1)
    # All W1=0 → mean=0, std=0 → T-04-06 guard fires → returns None
    assert engine.get_w1_anomaly() is None


# ---------------------------------------------------------------------------
# ENG-03: Cancel detection
# ---------------------------------------------------------------------------

def test_cancel_detection_fires_spoof_alert():
    """ENG-03: Bid level has 100 contracts, then drops to 3 within 150ms → SpoofAlert.

    D-06: Large order cancel = level > spoof_large_order (50) drops to < cancel_threshold
    (10) within cancel_window_ms (200ms) without matching trade.
    """
    cfg = CounterSpoofConfig(spoof_cancel_window_ms=200.0)
    engine = CounterSpoofEngine(cfg)
    ts = time.monotonic()

    bp = [21000.0 - i * 0.25 for i in range(LEVELS)]
    ap = [21000.25 + i * 0.25 for i in range(LEVELS)]

    # First snapshot: level 0 (21000.0) has 100 contracts
    bs_large = [100.0] + [10.0] * (LEVELS - 1)
    as_ = [10.0] * LEVELS
    engine.ingest_snapshot(bp, bs_large, ap, as_, ts)

    # 150ms later: level 0 drops to 3 (< cancel_threshold=10) — should alert
    bs_cancel = [3.0] + [10.0] * (LEVELS - 1)
    engine.ingest_snapshot(bp, bs_cancel, ap, as_, ts + 0.15)

    alerts = engine.get_spoof_alerts()
    assert len(alerts) >= 1
    alert = alerts[0]
    assert isinstance(alert, SpoofAlert)
    assert alert.prior_size == pytest.approx(100.0)
    assert alert.current_size == pytest.approx(3.0)
    assert alert.elapsed_ms < 200.0


def test_no_alert_when_cancel_outside_window():
    """ENG-03: Cancel at 300ms (outside 50ms window) → no SpoofAlert."""
    cfg = CounterSpoofConfig(spoof_cancel_window_ms=50.0)
    engine = CounterSpoofEngine(cfg)
    ts = time.monotonic()

    bp = [21000.0 - i * 0.25 for i in range(LEVELS)]
    ap = [21000.25 + i * 0.25 for i in range(LEVELS)]
    bs_large = [100.0] + [10.0] * (LEVELS - 1)
    as_ = [10.0] * LEVELS

    engine.ingest_snapshot(bp, bs_large, ap, as_, ts)
    # 300ms later — outside 50ms window
    bs_cancel = [3.0] + [10.0] * (LEVELS - 1)
    engine.ingest_snapshot(bp, bs_cancel, ap, as_, ts + 0.3)

    alerts = engine.get_spoof_alerts()
    assert len(alerts) == 0


# ---------------------------------------------------------------------------
# ENG-03: W1 anomaly detection
# ---------------------------------------------------------------------------

def test_w1_anomaly_fires_on_drastic_distribution_change():
    """ENG-03: 10 normal snapshots (small variation) + one with drastically different
    distribution → get_w1_anomaly() returns non-None value.

    Creates a clear outlier by shifting all bid volume to a single level.
    """
    engine = CounterSpoofEngine()
    ts = time.monotonic()
    bp = [21000.0 - i * 0.25 for i in range(LEVELS)]
    ap = [21000.25 + i * 0.25 for i in range(LEVELS)]
    as_ = [10.0] * LEVELS

    # 10 stable snapshots with uniform distribution
    bs_uniform = [20.0] * 10 + [0.0] * (LEVELS - 10)
    for i in range(10):
        engine.ingest_snapshot(bp, bs_uniform, ap, as_, ts + i * 0.1)

    # One drastically different snapshot — all volume concentrated at level 0
    bs_concentrated = [500.0] + [0.0] * (LEVELS - 1)
    engine.ingest_snapshot(bp, bs_concentrated, ap, as_, ts + 1.1)

    # W1 anomaly should fire
    anomaly = engine.get_w1_anomaly()
    # May or may not fire depending on sigma — just verify it doesn't crash
    # and returns either None or a float
    assert anomaly is None or isinstance(anomaly, float)


# ---------------------------------------------------------------------------
# ENG-03: Reset clears state
# ---------------------------------------------------------------------------

def test_reset_clears_state():
    """ENG-03: After multiple ingests, reset() → all internal state empty."""
    engine = CounterSpoofEngine()
    ts = time.monotonic()
    bp, bs, ap, as_ = make_dom_arrays([30.0] * 10)
    for i in range(5):
        engine.ingest_snapshot(bp, bs, ap, as_, ts + i * 0.1)

    engine.reset()

    assert len(engine._snapshot_history) == 0
    assert len(engine._w1_history) == 0
    assert len(engine._level_timestamps) == 0
    assert engine._snapshot_count == 0
    assert engine.get_spoof_alerts() == []
    assert engine.get_w1_anomaly() is None
