"""Session edge case handlers."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


# US market holidays (2026 list)
MARKET_HOLIDAYS_2026 = {
    date(2026, 1, 1),   # New Year's Day
    date(2026, 1, 19),  # MLK Day
    date(2026, 2, 16),  # Presidents' Day
    date(2026, 4, 3),   # Good Friday
    date(2026, 5, 25),  # Memorial Day
    date(2026, 7, 3),   # Independence Day (observed)
    date(2026, 9, 7),   # Labor Day
    date(2026, 11, 26), # Thanksgiving
    date(2026, 12, 25), # Christmas
}

# Half-day early closes (1:00 PM ET)
HALF_DAYS_2026 = {
    date(2026, 11, 27), # Day after Thanksgiving
    date(2026, 12, 24), # Christmas Eve
}


class HaltState(str, Enum):
    NORMAL = "NORMAL"
    SUSPECTED_HALT = "SUSPECTED_HALT"
    CONFIRMED_HALT = "CONFIRMED_HALT"


class CMEHaltDetector:
    """Detect CME circuit breaker halts from tick silence."""

    def __init__(self, silence_threshold_s: float = 30.0):
        self._threshold = silence_threshold_s
        self._last_tick_time: float = 0.0
        self._state = HaltState.NORMAL

    def on_tick(self, timestamp: float) -> None:
        self._last_tick_time = timestamp
        self._state = HaltState.NORMAL

    def check(self, current_time: float) -> HaltState:
        if self._last_tick_time == 0:
            return HaltState.NORMAL

        silence = current_time - self._last_tick_time
        if silence > self._threshold:
            self._state = HaltState.CONFIRMED_HALT
        elif silence > self._threshold * 0.5:
            self._state = HaltState.SUSPECTED_HALT
        else:
            self._state = HaltState.NORMAL
        return self._state

    @property
    def state(self) -> HaltState:
        return self._state


class ContractRollDetector:
    """NQ quarterly roll: March, June, September, December."""

    ROLL_MONTHS = {3, 6, 9, 12}

    @staticmethod
    def is_roll_week(dt: datetime) -> bool:
        """Roll typically occurs 2nd Thursday of roll month."""
        if dt.month not in ContractRollDetector.ROLL_MONTHS:
            return False

        second_thursday = None
        for day in range(8, 15):
            candidate = date(dt.year, dt.month, day)
            if candidate.weekday() == 3:
                second_thursday = candidate
                break

        if second_thursday is None:
            return False

        roll_start = second_thursday - timedelta(days=2)
        roll_end = second_thursday + timedelta(days=1)
        return roll_start <= dt.date() <= roll_end

    @staticmethod
    def front_month_symbol(dt: datetime) -> str:
        """Return NQ front-month symbol code."""
        month_codes = {3: "H", 6: "M", 9: "U", 12: "Z"}
        year = dt.year % 100

        for month in sorted(month_codes):
            if dt.month < month or (dt.month == month and dt.day < 15):
                return f"NQ{month_codes[month]}{year}"

        return f"NQH{(year + 1) % 100}"


def is_market_holiday(dt: date) -> bool:
    return dt in MARKET_HOLIDAYS_2026


def is_half_day(dt: date) -> bool:
    return dt in HALF_DAYS_2026


def get_session_end(dt: date) -> str:
    """Return session end time in ET. Half-days close at 13:00."""
    if is_half_day(dt):
        return "13:00"
    return "16:00"


def is_weekend(dt: date) -> bool:
    return dt.weekday() >= 5


def should_trade(dt: datetime | date) -> tuple[bool, str]:
    """Master guard: should trading be active?"""
    current_date = dt.date() if isinstance(dt, datetime) else dt
    if is_weekend(current_date):
        return False, "weekend"
    if is_market_holiday(current_date):
        return False, "market_holiday"
    return True, "ok"


__all__ = [
    "CMEHaltDetector",
    "ContractRollDetector",
    "ET",
    "HALF_DAYS_2026",
    "HaltState",
    "MARKET_HOLIDAYS_2026",
    "get_session_end",
    "is_half_day",
    "is_market_holiday",
    "is_weekend",
    "should_trade",
]
