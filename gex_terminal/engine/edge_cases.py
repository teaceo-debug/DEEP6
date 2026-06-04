"""Edge case detection for GEX Terminal — market hours, stale data, flash crashes."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Options market hours (ET)
OPTIONS_OPEN_HOUR = 9
OPTIONS_OPEN_MINUTE = 30
OPTIONS_CLOSE_HOUR = 16
OPTIONS_CLOSE_MINUTE = 0

# Stale threshold: 2× refresh interval
STALE_MULTIPLIER = 2
DEFAULT_REFRESH_SEC = 30


def is_options_market_open(now: Optional[datetime] = None) -> bool:
    """Returns True if options market is currently open (9:30 AM - 4:00 PM ET, Mon-Fri)."""
    if now is None:
        now = datetime.now(ET)

    # Weekend check
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    # Time check
    open_time = now.replace(hour=OPTIONS_OPEN_HOUR, minute=OPTIONS_OPEN_MINUTE, second=0, microsecond=0)
    close_time = now.replace(hour=OPTIONS_CLOSE_HOUR, minute=OPTIONS_CLOSE_MINUTE, second=0, microsecond=0)

    return open_time <= now < close_time


def is_opex_day(now: Optional[datetime] = None) -> bool:
    """Returns True if today is monthly OpEx (3rd Friday of month)."""
    if now is None:
        now = datetime.now(ET)

    if now.weekday() != 4:  # Not Friday
        return False

    # 3rd Friday: day is between 15 and 21
    return 15 <= now.day <= 21


def has_0dte_today(now: Optional[datetime] = None) -> bool:
    """Returns True if NQ weekly 0DTE options expire today (Mon/Wed/Fri)."""
    if now is None:
        now = datetime.now(ET)

    # NQ weekly options expire Mon (0), Wed (2), Fri (4)
    return now.weekday() in (0, 2, 4)


def check_source_staleness(
    last_update: Optional[float],
    ttl_sec: int = DEFAULT_REFRESH_SEC,
    stale_multiplier: float = STALE_MULTIPLIER,
) -> bool:
    """Returns True if source data is stale (older than ttl_sec × stale_multiplier)."""
    if last_update is None:
        return True

    age = time.time() - last_update
    return age > (ttl_sec * stale_multiplier)


def get_market_status_badge(now: Optional[datetime] = None) -> str:
    """Returns a status badge string for the current market state."""
    if now is None:
        now = datetime.now(ET)

    if not is_options_market_open(now):
        return "AFTER HOURS"

    if is_opex_day(now) and now.hour >= OPTIONS_CLOSE_HOUR:
        return "EXPIRY RESET"

    return "LIVE"


def classify_http_error(status_code: int) -> str:
    """Classify HTTP error status into source health status."""
    if status_code in (401, 403):
        return "AUTH FAILED"
    elif status_code == 429:
        return "RATE LIMITED"
    elif status_code >= 500:
        return "SERVER ERROR"
    else:
        return "error"


__all__ = [
    "is_options_market_open",
    "is_opex_day",
    "has_0dte_today",
    "check_source_staleness",
    "get_market_status_badge",
    "classify_http_error",
]
