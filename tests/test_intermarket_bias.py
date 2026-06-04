from __future__ import annotations

import time

from deep6.engines.intermarket_bias import MacroIntermarketDomain
from deep6.engines.intermarket_registry import IntermarketRegistry
from deep6.engines.ohlcv_accumulator import OHLCVBar


def make_bar(symbol: str, open_: float, close: float) -> OHLCVBar:
    high = max(open_, close)
    low = min(open_, close)
    return OHLCVBar(
        symbol=symbol,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        bar_start_ts=1000.0,
        bar_end_ts=1060.0,
        tick_count=10,
    )


def fresh_registry() -> IntermarketRegistry:
    registry = IntermarketRegistry(staleness_sec=300)
    now = time.time()
    for symbol in ("ZN", "DXY", "VIX"):
        registry.update(symbol, value=1.0, ts=now)
    return registry


def test_compute_all_bullish_returns_plus_three() -> None:
    domain = MacroIntermarketDomain()
    registry = fresh_registry()
    bars = {
        "ZN": make_bar("ZN", 110.0, 111.0),
        "DXY": make_bar("DXY", 105.0, 104.0),
        "VIX": make_bar("VIX", 19.5, 19.0),
    }

    result = domain.compute(bars, registry)

    assert result.score == 3
    assert result.max_range == 3
    assert result.available is True
    assert result.stale is False


def test_compute_all_bearish_returns_minus_three() -> None:
    domain = MacroIntermarketDomain()
    registry = fresh_registry()
    bars = {
        "ZN": make_bar("ZN", 111.0, 110.0),
        "DXY": make_bar("DXY", 104.0, 105.0),
        "VIX": make_bar("VIX", 25.5, 26.0),
    }

    result = domain.compute(bars, registry)

    assert result.score == -3
    assert result.max_range == 3
    assert result.available is True


def test_stale_zn_reduces_max_range() -> None:
    domain = MacroIntermarketDomain()
    registry = fresh_registry()
    registry.update("ZN", value=1.0, ts=time.time() - 301)
    bars = {
        "ZN": make_bar("ZN", 110.0, 111.0),
        "DXY": make_bar("DXY", 105.0, 104.0),
        "VIX": make_bar("VIX", 19.5, 19.0),
    }

    result = domain.compute(bars, registry)

    assert result.score == 2
    assert result.max_range == 2
    assert result.available is True
    assert result.detail["components"]["ZN"]["available"] is False


def test_all_stale_returns_unavailable_zero_score() -> None:
    domain = MacroIntermarketDomain()
    registry = IntermarketRegistry(staleness_sec=300)
    bars = {
        "ZN": make_bar("ZN", 110.0, 111.0),
        "DXY": make_bar("DXY", 105.0, 104.0),
        "VIX": make_bar("VIX", 19.5, 19.0),
    }

    result = domain.compute(bars, registry)

    assert result.score == 0
    assert result.max_range == 0
    assert result.available is False
    assert result.stale is True


def test_mixed_signals_sum_correctly() -> None:
    domain = MacroIntermarketDomain()
    registry = fresh_registry()
    bars = {
        "ZN": make_bar("ZN", 110.0, 111.0),
        "DXY": make_bar("DXY", 104.0, 105.0),
        "VIX": make_bar("VIX", 22.0, 22.5),
    }

    result = domain.compute(bars, registry)

    assert result.score == 0
    assert result.max_range == 3
    assert result.detail["components"]["VIX"]["score"] == 0


def test_missing_symbol_is_excluded_from_calculation() -> None:
    domain = MacroIntermarketDomain()
    registry = fresh_registry()
    bars = {
        "ZN": make_bar("ZN", 110.0, 111.0),
        "DXY": make_bar("DXY", 105.0, 104.0),
    }

    result = domain.compute(bars, registry)

    assert result.score == 2
    assert result.max_range == 2
    assert result.detail["components"]["VIX"]["reason"] == "missing_or_stale"


def test_flat_zn_bar_scores_neutral_component() -> None:
    domain = MacroIntermarketDomain()
    registry = fresh_registry()
    bars = {
        "ZN": make_bar("ZN", 110.0, 110.0),
        "DXY": make_bar("DXY", 105.0, 104.0),
        "VIX": make_bar("VIX", 19.5, 19.0),
    }

    result = domain.compute(bars, registry)

    assert result.score == 2
    assert result.max_range == 3
    assert result.detail["components"]["ZN"]["score"] == 0


def test_midrange_vix_scores_neutral() -> None:
    domain = MacroIntermarketDomain()
    registry = fresh_registry()
    bars = {
        "ZN": make_bar("ZN", 111.0, 110.0),
        "DXY": make_bar("DXY", 105.0, 104.0),
        "VIX": make_bar("VIX", 22.0, 23.0),
    }

    result = domain.compute(bars, registry)

    assert result.score == 0
    assert result.detail["components"]["VIX"]["score"] == 0
