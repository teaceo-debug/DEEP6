from datetime import datetime
from zoneinfo import ZoneInfo

from deep6.engines.intermarket_registry import IntermarketRegistry


EASTERN = ZoneInfo("America/New_York")


def et_ts(year: int, month: int, day: int, hour: int, minute: int) -> float:
    return datetime(year, month, day, hour, minute, tzinfo=EASTERN).timestamp()


def test_is_stale_threshold_boundary() -> None:
    registry = IntermarketRegistry(staleness_sec=300)
    registry.update("ZN", 125.0, ts=1_000.0)

    assert registry.is_stale("ZN", now=1_299.0) is False
    assert registry.is_stale("ZN", now=1_301.0) is True


def test_rth_only_expected_stale_outside_rth() -> None:
    registry = IntermarketRegistry()
    now = et_ts(2026, 5, 12, 20, 0)

    assert registry.is_expected_stale("TICK", now=now) is True


def test_get_available_symbols_returns_recent_symbols_only() -> None:
    registry = IntermarketRegistry(staleness_sec=300)
    now = 10_000.0
    registry.update("ZN", 124.0, ts=now)
    registry.update("DXY", 104.5, ts=now)
    registry.update("RTY", 2100.0, ts=now - 400.0)

    available = registry.get_available_symbols(now=now)

    assert "ZN" in available
    assert "DXY" in available
    assert "RTY" not in available
    assert "VIX" not in available
