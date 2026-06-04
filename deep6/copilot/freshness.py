"""Freshness tracking for copilot data sources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Callable

from .types import DataSourceStatus


_DEFAULT_SOURCES: dict[str, int] = {
    "calendar": 300,
    "news": 120,
    "sentiment": 300,
    "options_flow": 180,
    "internals": 1,
    "bridge_tcp": 1,
    "bridge_ws": 1,
    "vision": 30,
}


@dataclass(slots=True)
class _SourceState:
    polling_interval_sec: int
    last_update: datetime
    error: str | None = None


class FreshnessTracker:
    """Track data-source update recency and staleness."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._lock = RLock()
        self._sources: dict[str, _SourceState] = {}

        for name, polling_interval_sec in _DEFAULT_SOURCES.items():
            self.register_source(name, polling_interval_sec)

    def register_source(self, name: str, polling_interval_sec: int) -> None:
        """Register or refresh a source definition."""
        if polling_interval_sec <= 0:
            raise ValueError("polling_interval_sec must be positive")

        with self._lock:
            self._sources[name] = _SourceState(
                polling_interval_sec=polling_interval_sec,
                last_update=self._clock(),
            )

    def record_update(self, source_name: str, error: str | None = None) -> None:
        """Record a successful or failed update for a source."""
        with self._lock:
            state = self._sources.get(source_name)
            if state is None:
                raise KeyError(f"Unknown data source: {source_name}")
            state.last_update = self._clock()
            state.error = error

    def get_status_all(self) -> list[DataSourceStatus]:
        """Return status objects for all registered sources."""
        with self._lock:
            return [self._build_status(name, state) for name, state in self._sources.items()]

    def get_status(self, source_name: str) -> DataSourceStatus | None:
        """Return the status for one source."""
        with self._lock:
            state = self._sources.get(source_name)
            if state is None:
                return None
            return self._build_status(source_name, state)

    def is_stale(self, source_name: str) -> bool:
        """True when the source has not updated for more than 2x its interval."""
        with self._lock:
            state = self._sources.get(source_name)
            if state is None:
                return True
            age = self._clock() - state.last_update
            return age > timedelta(seconds=state.polling_interval_sec * 2)

    def _build_status(self, source_name: str, state: _SourceState) -> DataSourceStatus:
        return DataSourceStatus(
            source_name=source_name,
            last_update=state.last_update,
            is_stale=self._is_stale_state(state),
            error=state.error,
        )

    def _is_stale_state(self, state: _SourceState) -> bool:
        age = self._clock() - state.last_update
        return age > timedelta(seconds=state.polling_interval_sec * 2)
