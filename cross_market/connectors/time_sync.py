"""Unified time management — monotonic clock, dual timestamps, UTC everywhere."""
from __future__ import annotations

import time
from zoneinfo import ZoneInfo
from datetime import datetime, timezone
from typing import Tuple

ET = ZoneInfo("America/New_York")
UTC = timezone.utc


class UnifiedClock:
    """Monotonically increasing event clock."""

    def __init__(self):
        self._sequence = 0
        self._last_ns = 0
        self._latencies: dict[str, list[float]] = {}

    def next(self, provider_ns: int | None = None) -> Tuple[int, int]:
        """Return (sequence, monotonic_ns). Guarantees monotonic ordering."""
        now_ns = time.time_ns()
        if provider_ns is not None:
            event_ns = provider_ns
        else:
            event_ns = now_ns

        # Enforce monotonic
        if event_ns <= self._last_ns:
            event_ns = self._last_ns + 1
        self._last_ns = event_ns
        self._sequence += 1

        # Track latency
        latency_ms = (now_ns - event_ns) / 1e6  # noqa: F841
        return self._sequence, event_ns

    def record_latency(self, source: str, latency_ms: float) -> None:
        if source not in self._latencies:
            self._latencies[source] = []
        self._latencies[source].append(latency_ms)
        if len(self._latencies[source]) > 1000:
            self._latencies[source] = self._latencies[source][-500:]

    def avg_latency_ms(self, source: str) -> float:
        lats = self._latencies.get(source, [])
        return sum(lats) / len(lats) if lats else 0.0

    @staticmethod
    def to_et(ts_ns: int) -> datetime:
        return datetime.fromtimestamp(ts_ns / 1e9, tz=UTC).astimezone(ET)

    @staticmethod
    def is_rth(ts_ns: int) -> bool:
        dt = UnifiedClock.to_et(ts_ns)
        return (9 * 60 + 30) <= (dt.hour * 60 + dt.minute) < (16 * 60 + 15)
