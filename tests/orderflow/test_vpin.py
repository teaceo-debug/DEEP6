"""Unit tests for VPINEngine (Phase 12, plan 01).

Tests cover:
- Warmup behavior (<10 buckets completed → neutral 1.0 modifier)
- Exact aggressor split from FootprintBar.levels (NO BVC / normal-CDF)
- Bucket completion at fixed 1000-contract volume clock
- Percentile rising with imbalance
- Modifier always bounded in [0.2, 1.2]
- Hard guarantee that vpin module does NOT import or use math.erf
"""
from __future__ import annotations

import inspect

import pytest

from deep6.state.footprint import FootprintBar, FootprintLevel


def _make_bar(ask_vol: int, bid_vol: int, price: float = 21000.0) -> FootprintBar:
    """Build a minimal FootprintBar with a single level carrying the requested
    aggressor-split volume.

    ask_vol = buy-aggressor contracts (hit the ask)
    bid_vol = sell-aggressor contracts (hit the bid)
    """
    bar = FootprintBar(
        timestamp=0.0,
        open=price,
        high=price,
        low=price,
        close=price,
    )
    bar.levels[int(round(price / 0.25))] = FootprintLevel(
        bid_vol=bid_vol, ask_vol=ask_vol
    )
    bar.total_vol = ask_vol + bid_vol
    bar.bar_delta = ask_vol - bid_vol
    return bar


def test_warmup_returns_neutral():
    """Before 10 buckets are completed, modifier must be exactly 1.0."""
    from deep6.orderflow.vpin import VPINEngine

    engine = VPINEngine(bucket_volume=1000, warmup_buckets=10)

    # Feed a handful of small bars (well under warmup threshold)
    for _ in range(3):
        engine.update_from_bar(_make_bar(ask_vol=300, bid_vol=200))

    assert engine.get_confidence_modifier() == 1.0


def test_exact_aggressor_split():
    """update_from_bar must use ask_vol/bid_vol directly — NOT BVC."""
    from deep6.orderflow.vpin import VPINEngine

    engine = VPINEngine(bucket_volume=1000)
    bar = _make_bar(ask_vol=800, bid_vol=200)
    engine.update_from_bar(bar)

    # Exactly 1000 contracts → 1 completed bucket; buy=800, sell=200
    assert engine.buckets_completed == 1
    last = engine.completed_buckets[-1]
    # Accept either (buy, sell) tuple or dict depending on storage
    if isinstance(last, dict):
        assert last["buy"] == 800
        assert last["sell"] == 200
    else:
        buy, sell = last
        assert buy == 800
        assert sell == 200


def test_bucket_completion_at_1000():
    """Total accumulated volume hitting 1000 must close a bucket."""
    from deep6.orderflow.vpin import VPINEngine

    engine = VPINEngine(bucket_volume=1000)

    # Two 500-volume bars → exactly one bucket completes
    engine.update_from_bar(_make_bar(ask_vol=250, bid_vol=250))
    assert engine.buckets_completed == 0
    engine.update_from_bar(_make_bar(ask_vol=250, bid_vol=250))
    assert engine.buckets_completed == 1


def test_percentile_grows_with_imbalance():
    """Sequence of highly imbalanced bars must push VPIN percentile high."""
    from deep6.orderflow.vpin import VPINEngine

    engine = VPINEngine(bucket_volume=1000, num_buckets=50, warmup_buckets=10)

    # Seed history with ~60 balanced buckets (low VPIN baseline)
    for _ in range(60):
        engine.update_from_bar(_make_bar(ask_vol=500, bid_vol=500))

    baseline_percentile = engine.get_percentile()

    # Now a long run of severely imbalanced buckets
    for _ in range(40):
        engine.update_from_bar(_make_bar(ask_vol=980, bid_vol=20))

    assert engine.get_percentile() > baseline_percentile
    assert engine.get_percentile() > 0.8


def test_confidence_modifier_bounded():
    """Modifier must always stay in [0.2, 1.2] across varied bars."""
    from deep6.orderflow.vpin import VPINEngine

    engine = VPINEngine()
    import random
    random.seed(42)
    for _ in range(200):
        ask = random.randint(0, 1000)
        bid = random.randint(0, 1000)
        if ask == 0 and bid == 0:
            ask = 1
        engine.update_from_bar(_make_bar(ask_vol=ask, bid_vol=bid))
        m = engine.get_confidence_modifier()
        assert 0.2 <= m <= 1.2, f"modifier out of bounds: {m}"


def test_no_bvc_path():
    """The vpin module must NOT use math.erf — DEEP6 has exact aggressor (DATA-02).

    Protects against accidentally copying the reference impl's BVC branch.
    """
    from deep6.orderflow import vpin as vpin_module

    src = inspect.getsource(vpin_module)
    assert "math.erf" not in src, (
        "VPIN module must not use math.erf — DEEP6 uses exact aggressor "
        "split per DATA-02; BVC (normal-CDF) is forbidden."
    )
    assert "erf(" not in src, "No normal-CDF / BVC branch allowed in VPIN."


def test_zero_volume_bar_is_safe():
    """A FootprintBar with total_vol=0 must not crash VPINEngine."""
    from deep6.orderflow.vpin import VPINEngine

    engine = VPINEngine()
    empty = FootprintBar(timestamp=0.0, open=0.0, high=0.0, low=0.0, close=0.0)
    empty.total_vol = 0
    # Must be a no-op
    engine.update_from_bar(empty)
    assert engine.buckets_completed == 0
    assert engine.get_confidence_modifier() == 1.0
