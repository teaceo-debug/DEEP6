"""Tests for E6VPContextEngine and E7MLQualityEngine (ENG-06, ENG-07)."""
from __future__ import annotations

from collections import defaultdict

import pytest

from deep6.engines.vp_context_engine import E6VPContextEngine, E7MLQualityEngine, VPContextResult
from deep6.engines.zone_registry import ConfluenceResult
from deep6.state.footprint import FootprintBar, FootprintLevel, price_to_tick


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_levels(price_vol_pairs: list[tuple[float, int, int]]) -> dict[int, FootprintLevel]:
    levels = {}
    for price, bid, ask in price_vol_pairs:
        levels[price_to_tick(price)] = FootprintLevel(bid_vol=bid, ask_vol=ask)
    return levels


def make_bar(
    open_: float = 100.0,
    high: float = 100.75,
    low: float = 99.75,
    close: float = 100.5,
    poc_price: float = 100.25,
    levels: dict | None = None,
) -> FootprintBar:
    if levels is None:
        levels = make_levels([(100.0, 50, 100), (100.25, 80, 120)])
    total = sum(lv.bid_vol + lv.ask_vol for lv in levels.values())
    return FootprintBar(
        open=open_, high=high, low=low, close=close,
        total_vol=total, poc_price=poc_price,
        bar_range=high - low, levels=levels,
    )


# ---------------------------------------------------------------------------
# ENG-07: E7 always returns 1.0
# ---------------------------------------------------------------------------

def test_e7_returns_one():
    """E7MLQualityEngine().score() == 1.0 in all calls."""
    eng = E7MLQualityEngine()
    assert eng.score() == 1.0
    # Also with a bar argument
    bar = make_bar()
    assert eng.score(bar) == 1.0
    # Multiple calls remain 1.0
    for _ in range(5):
        assert eng.score() == 1.0


# ---------------------------------------------------------------------------
# ENG-06: E6 instantiation
# ---------------------------------------------------------------------------

def test_e6_instantiates():
    """E6VPContextEngine('key') creates all sub-engines without error."""
    eng = E6VPContextEngine("test_api_key")
    assert eng.poc_engine is not None
    assert eng.session_profile is not None
    assert eng.gex_engine is not None
    assert eng.registry is not None


# ---------------------------------------------------------------------------
# ENG-06: E6 process()
# ---------------------------------------------------------------------------

def test_e6_process_returns_result():
    """Feed one bar → returns VPContextResult with correct field types."""
    eng = E6VPContextEngine("test_api_key")
    bar = make_bar()
    result = eng.process(bar)
    assert isinstance(result, VPContextResult)
    assert isinstance(result.poc_signals, list)
    assert isinstance(result.active_zones, list)
    assert isinstance(result.zone_events, list)
    assert isinstance(result.poc_migration, tuple)
    assert len(result.poc_migration) == 2


def test_e6_process_ml_quality_is_one():
    """result.ml_quality == 1.0 (E7 stub)."""
    eng = E6VPContextEngine("test_api_key")
    bar = make_bar()
    result = eng.process(bar)
    assert result.ml_quality == 1.0


def test_e6_confluence_field():
    """result.confluence is a ConfluenceResult instance."""
    eng = E6VPContextEngine("test_api_key")
    bar = make_bar()
    result = eng.process(bar)
    assert isinstance(result.confluence, ConfluenceResult)


def test_e6_poc_migration_in_result():
    """result.poc_migration is tuple of (int, float)."""
    eng = E6VPContextEngine("test_api_key")
    bar = make_bar()
    result = eng.process(bar)
    direction, velocity = result.poc_migration
    assert isinstance(direction, int)
    assert isinstance(velocity, float)


# ---------------------------------------------------------------------------
# ENG-06: on_session_start
# ---------------------------------------------------------------------------

def test_e6_on_session_start_resets():
    """After process(bar) + on_session_start(), internal bar_count resets to 0."""
    eng = E6VPContextEngine("test_api_key")
    bar = make_bar()
    eng.process(bar)
    eng.process(bar)
    assert eng._bar_count == 2

    eng.on_session_start()
    assert eng._bar_count == 0


def test_e6_on_session_start_prior_bins():
    """on_session_start(prior_bins={tick: 1000.0}) → session_profile.bins[tick] ≈ 700.0.

    VPRO-07: prior session bins decay by session_decay_weight=0.70.
    """
    eng = E6VPContextEngine("test_api_key")
    tick = price_to_tick(100.0)
    eng.on_session_start(prior_bins={tick: 1000.0})
    assert abs(eng.session_profile.bins[tick] - 700.0) < 1.0
