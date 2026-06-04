"""Metrics, health monitoring, GC management."""

from __future__ import annotations

import gc
import time
from dataclasses import dataclass, field


@dataclass
class SystemMetrics:
    """Core system metrics for health monitoring and dashboards."""

    bars_processed: int = 0
    signals_fired: int = 0
    dom_callbacks: int = 0
    bar_latency_ms: float = 0.0
    signal_latency_ms: float = 0.0
    daily_pnl: float = 0.0
    connection_uptime_s: float = 0.0
    last_dom_update: float = 0.0


class HealthMonitor:
    """Watches system vitals and raises alerts on anomalies."""

    def __init__(
        self,
        dom_stale_threshold_s: float = 10.0,
        bar_gap_threshold_s: float = 300.0,
    ) -> None:
        self._dom_stale_threshold = dom_stale_threshold_s
        self._bar_gap_threshold = bar_gap_threshold_s
        self._metrics = SystemMetrics()
        self._alerts: list[dict] = []

    @property
    def metrics(self) -> SystemMetrics:
        return self._metrics

    def check_dom_freshness(self) -> bool:
        """Return True if DOM data is fresh, False if stale."""
        if self._metrics.last_dom_update == 0:
            return True  # No DOM yet, not stale
        age = time.time() - self._metrics.last_dom_update
        if age > self._dom_stale_threshold:
            self._alerts.append({"type": "dom_stale", "age_s": age})
            return False
        return True

    def check_bar_regularity(self, last_bar_time: float) -> bool:
        """Return True if bars are arriving on schedule."""
        if last_bar_time == 0:
            return True
        gap = time.time() - last_bar_time
        if gap > self._bar_gap_threshold:
            self._alerts.append({"type": "bar_gap", "gap_s": gap})
            return False
        return True

    def get_alerts(self) -> list[dict]:
        """Return and clear pending alerts."""
        alerts = self._alerts[:]
        self._alerts.clear()
        return alerts

    def to_dict(self) -> dict:
        """Snapshot of key metrics for API/dashboard consumption."""
        return {
            "bars_processed": self._metrics.bars_processed,
            "signals_fired": self._metrics.signals_fired,
            "bar_latency_ms": self._metrics.bar_latency_ms,
            "daily_pnl": self._metrics.daily_pnl,
        }


class GCManager:
    """Disable GC during RTH for latency, re-enable outside."""

    def __init__(self) -> None:
        self._gc_disabled = False

    def on_rth_open(self) -> None:
        gc.disable()
        self._gc_disabled = True

    def on_rth_close(self) -> None:
        gc.enable()
        gc.collect()
        self._gc_disabled = False

    @property
    def is_disabled(self) -> bool:
        return self._gc_disabled


__all__ = ["GCManager", "HealthMonitor", "SystemMetrics"]
