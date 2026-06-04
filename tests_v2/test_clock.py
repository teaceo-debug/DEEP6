from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from deep6v2.clock import EventClock, WallClock


ET = ZoneInfo("America/New_York")


@pytest.mark.parametrize(
    "dt, expected",
    [
        (datetime(2026, 5, 11, 9, 29, 59, tzinfo=ET), False),
        (datetime(2026, 5, 11, 9, 30, 0, tzinfo=ET), True),
        (datetime(2026, 5, 11, 16, 0, 0, tzinfo=ET), True),
        (datetime(2026, 5, 11, 16, 0, 1, tzinfo=ET), False),
        (datetime(2026, 5, 10, 12, 0, 0, tzinfo=ET), False),
        (datetime(2026, 5, 9, 12, 0, 0, tzinfo=ET), False),
    ],
)
def test_rth_boundaries(dt, expected):
    clock = WallClock()
    assert clock.is_rth(dt) is expected


@pytest.mark.parametrize(
    "dt, expected",
    [
        (datetime(2026, 5, 11, 9, 30, 0, tzinfo=ET), 0),
        (datetime(2026, 5, 11, 10, 29, 0, tzinfo=ET), 59),
        (datetime(2026, 5, 11, 10, 30, 0, tzinfo=ET), 60),
        (datetime(2026, 5, 11, 13, 30, 0, tzinfo=ET), 240),
        (datetime(2026, 5, 11, 15, 59, 0, tzinfo=ET), 389),
    ],
)
def test_bar_index(dt, expected):
    clock = WallClock()
    assert clock.session_bar_index(dt) == expected


def test_event_clock_advance():
    clock = EventClock()
    dt = datetime(2026, 5, 11, 10, 0, 0, tzinfo=ET)
    clock.advance(dt)
    assert clock.now() == dt


def test_wall_clock_returns_et_aware_datetime():
    clock = WallClock()
    now = clock.now()
    assert now.tzinfo == ET
    assert now.tzinfo is not None


def test_weekend_not_rth():
    clock = WallClock()
    saturday = datetime(2026, 5, 9, 12, 0, 0, tzinfo=ET)
    sunday = datetime(2026, 5, 10, 12, 0, 0, tzinfo=ET)
    assert clock.is_rth(saturday) is False
    assert clock.is_rth(sunday) is False
