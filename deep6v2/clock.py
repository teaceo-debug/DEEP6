from __future__ import annotations

from datetime import datetime, time
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo


ET = ZoneInfo("America/New_York")


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...

    def is_rth(self, dt: datetime | None = None) -> bool: ...

    def session_bar_index(self, dt: datetime | None = None) -> int: ...


class WallClock:
    def now(self) -> datetime:
        return datetime.now(tz=ET)

    def is_rth(self, dt: datetime | None = None) -> bool:
        dt = self.now() if dt is None else _to_et(dt)
        if dt.weekday() >= 5:
            return False
        return time(9, 30) <= dt.time() <= time(16, 0)

    def session_bar_index(self, dt: datetime | None = None) -> int:
        dt = self.now() if dt is None else _to_et(dt)
        rth_open = dt.replace(hour=9, minute=30, second=0, microsecond=0)
        delta = dt - rth_open
        return int(delta.total_seconds() // 60)


class EventClock:
    def __init__(self) -> None:
        self._current: datetime = datetime.now(tz=ET)

    def advance(self, dt: datetime) -> None:
        self._current = _to_et(dt)

    def now(self) -> datetime:
        return self._current

    def is_rth(self, dt: datetime | None = None) -> bool:
        dt = self.now() if dt is None else _to_et(dt)
        if dt.weekday() >= 5:
            return False
        return time(9, 30) <= dt.time() <= time(16, 0)

    def session_bar_index(self, dt: datetime | None = None) -> int:
        dt = self.now() if dt is None else _to_et(dt)
        rth_open = dt.replace(hour=9, minute=30, second=0, microsecond=0)
        delta = dt - rth_open
        return int(delta.total_seconds() // 60)


def _to_et(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ET)
    return dt.astimezone(ET)
