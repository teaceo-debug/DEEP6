"""Tests for edge case detection."""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from gex_terminal.engine.edge_cases import (
    check_source_staleness,
    classify_http_error,
    get_market_status_badge,
    has_0dte_today,
    is_opex_day,
    is_options_market_open,
)

ET = ZoneInfo("America/New_York")


def test_market_open_during_hours():
    """Market is open at 10 AM ET on a weekday."""
    dt = datetime(2026, 5, 29, 10, 0, 0, tzinfo=ET)  # Friday 10 AM
    assert is_options_market_open(dt) is True


def test_market_closed_before_open():
    """Market is closed at 9 AM ET."""
    dt = datetime(2026, 5, 29, 9, 0, 0, tzinfo=ET)
    assert is_options_market_open(dt) is False


def test_market_closed_after_close():
    """Market is closed at 4:30 PM ET."""
    dt = datetime(2026, 5, 29, 16, 30, 0, tzinfo=ET)
    assert is_options_market_open(dt) is False


def test_market_closed_on_weekend():
    """Market is closed on Saturday."""
    dt = datetime(2026, 5, 30, 10, 0, 0, tzinfo=ET)  # Saturday
    assert is_options_market_open(dt) is False


def test_market_open_at_exactly_930():
    """Market opens at exactly 9:30 AM ET."""
    dt = datetime(2026, 5, 29, 9, 30, 0, tzinfo=ET)
    assert is_options_market_open(dt) is True


def test_market_closed_at_exactly_4pm():
    """Market closes at exactly 4:00 PM ET (exclusive)."""
    dt = datetime(2026, 5, 29, 16, 0, 0, tzinfo=ET)
    assert is_options_market_open(dt) is False


def test_stale_detection_fresh():
    """Source updated 10s ago is not stale (ttl=30s, multiplier=2 -> threshold=60s)."""
    last_update = time.time() - 10
    assert check_source_staleness(last_update, ttl_sec=30) is False


def test_stale_detection_stale():
    """Source updated 90s ago is stale (threshold=60s)."""
    last_update = time.time() - 90
    assert check_source_staleness(last_update, ttl_sec=30) is True


def test_stale_detection_none():
    """Source with no update is stale."""
    assert check_source_staleness(None) is True


def test_stale_detection_custom_multiplier():
    """Custom multiplier changes threshold."""
    last_update = time.time() - 50
    # ttl=30, multiplier=1 -> threshold=30s, 50s > 30s -> stale
    assert check_source_staleness(last_update, ttl_sec=30, stale_multiplier=1) is True
    # ttl=30, multiplier=3 -> threshold=90s, 50s < 90s -> fresh
    assert check_source_staleness(last_update, ttl_sec=30, stale_multiplier=3) is False


def test_0dte_on_monday():
    """0DTE available on Monday."""
    dt = datetime(2026, 6, 1, 10, 0, 0, tzinfo=ET)  # Monday
    assert has_0dte_today(dt) is True


def test_0dte_on_wednesday():
    """0DTE available on Wednesday."""
    dt = datetime(2026, 6, 3, 10, 0, 0, tzinfo=ET)  # Wednesday
    assert has_0dte_today(dt) is True


def test_0dte_on_friday():
    """0DTE available on Friday."""
    dt = datetime(2026, 5, 29, 10, 0, 0, tzinfo=ET)  # Friday
    assert has_0dte_today(dt) is True


def test_no_0dte_on_tuesday():
    """No 0DTE on Tuesday."""
    dt = datetime(2026, 6, 2, 10, 0, 0, tzinfo=ET)  # Tuesday
    assert has_0dte_today(dt) is False


def test_no_0dte_on_thursday():
    """No 0DTE on Thursday."""
    dt = datetime(2026, 6, 4, 10, 0, 0, tzinfo=ET)  # Thursday
    assert has_0dte_today(dt) is False


def test_opex_third_friday():
    """3rd Friday of June 2026 is OpEx."""
    dt = datetime(2026, 6, 19, 10, 0, 0, tzinfo=ET)  # 3rd Friday
    assert is_opex_day(dt) is True


def test_not_opex_second_friday():
    """2nd Friday is not OpEx."""
    dt = datetime(2026, 6, 12, 10, 0, 0, tzinfo=ET)  # 2nd Friday
    assert is_opex_day(dt) is False


def test_not_opex_on_thursday():
    """Thursday is never OpEx."""
    dt = datetime(2026, 6, 18, 10, 0, 0, tzinfo=ET)  # Thursday
    assert is_opex_day(dt) is False


def test_classify_auth_error():
    assert classify_http_error(401) == "AUTH FAILED"
    assert classify_http_error(403) == "AUTH FAILED"


def test_classify_rate_limit():
    assert classify_http_error(429) == "RATE LIMITED"


def test_classify_server_error():
    assert classify_http_error(500) == "SERVER ERROR"
    assert classify_http_error(502) == "SERVER ERROR"
    assert classify_http_error(503) == "SERVER ERROR"


def test_classify_other_error():
    assert classify_http_error(404) == "error"
    assert classify_http_error(400) == "error"


def test_market_status_badge_live():
    """Badge shows LIVE during market hours."""
    dt = datetime(2026, 5, 29, 12, 0, 0, tzinfo=ET)
    assert get_market_status_badge(dt) == "LIVE"


def test_market_status_badge_after_hours():
    """Badge shows AFTER HOURS outside market."""
    dt = datetime(2026, 5, 29, 20, 0, 0, tzinfo=ET)
    assert get_market_status_badge(dt) == "AFTER HOURS"


def test_market_status_badge_weekend():
    """Badge shows AFTER HOURS on weekend."""
    dt = datetime(2026, 5, 30, 12, 0, 0, tzinfo=ET)  # Saturday
    assert get_market_status_badge(dt) == "AFTER HOURS"
