"""Tests for deep6v2.ops.observability — metrics, health, GC."""

from __future__ import annotations

import gc
import time
from unittest.mock import patch

import pytest

from deep6v2.ops.observability import GCManager, HealthMonitor, SystemMetrics


# --- SystemMetrics ---


class TestSystemMetrics:
    def test_defaults(self):
        m = SystemMetrics()
        assert m.bars_processed == 0
        assert m.signals_fired == 0
        assert m.dom_callbacks == 0
        assert m.bar_latency_ms == 0.0
        assert m.signal_latency_ms == 0.0
        assert m.daily_pnl == 0.0
        assert m.connection_uptime_s == 0.0
        assert m.last_dom_update == 0.0

    def test_mutation(self):
        m = SystemMetrics()
        m.bars_processed = 42
        m.daily_pnl = -150.50
        assert m.bars_processed == 42
        assert m.daily_pnl == -150.50


# --- HealthMonitor ---


class TestHealthMonitor:
    def test_fresh_dom_no_update_yet(self):
        h = HealthMonitor()
        assert h.check_dom_freshness() is True
        assert h.get_alerts() == []

    def test_fresh_dom_recent_update(self):
        h = HealthMonitor(dom_stale_threshold_s=10.0)
        h.metrics.last_dom_update = time.time() - 1.0
        assert h.check_dom_freshness() is True
        assert h.get_alerts() == []

    def test_stale_dom_triggers_alert(self):
        h = HealthMonitor(dom_stale_threshold_s=5.0)
        h.metrics.last_dom_update = time.time() - 20.0
        assert h.check_dom_freshness() is False
        alerts = h.get_alerts()
        assert len(alerts) == 1
        assert alerts[0]["type"] == "dom_stale"
        assert alerts[0]["age_s"] >= 15.0

    def test_bar_regularity_no_bars_yet(self):
        h = HealthMonitor()
        assert h.check_bar_regularity(0.0) is True

    def test_bar_regularity_recent(self):
        h = HealthMonitor(bar_gap_threshold_s=300.0)
        assert h.check_bar_regularity(time.time() - 10.0) is True

    def test_bar_gap_triggers_alert(self):
        h = HealthMonitor(bar_gap_threshold_s=60.0)
        assert h.check_bar_regularity(time.time() - 120.0) is False
        alerts = h.get_alerts()
        assert len(alerts) == 1
        assert alerts[0]["type"] == "bar_gap"
        assert alerts[0]["gap_s"] >= 60.0

    def test_alerts_cleared_after_get(self):
        h = HealthMonitor(dom_stale_threshold_s=1.0)
        h.metrics.last_dom_update = time.time() - 10.0
        h.check_dom_freshness()
        assert len(h.get_alerts()) == 1
        assert h.get_alerts() == []

    def test_to_dict(self):
        h = HealthMonitor()
        h.metrics.bars_processed = 100
        h.metrics.signals_fired = 5
        h.metrics.bar_latency_ms = 2.3
        h.metrics.daily_pnl = 500.0
        d = h.to_dict()
        assert d == {
            "bars_processed": 100,
            "signals_fired": 5,
            "bar_latency_ms": 2.3,
            "daily_pnl": 500.0,
        }

    def test_multiple_alerts_accumulate(self):
        h = HealthMonitor(dom_stale_threshold_s=1.0, bar_gap_threshold_s=1.0)
        h.metrics.last_dom_update = time.time() - 10.0
        h.check_dom_freshness()
        h.check_bar_regularity(time.time() - 10.0)
        alerts = h.get_alerts()
        assert len(alerts) == 2
        types = {a["type"] for a in alerts}
        assert types == {"dom_stale", "bar_gap"}


# --- GCManager ---


class TestGCManager:
    def test_initial_state(self):
        mgr = GCManager()
        assert mgr.is_disabled is False

    def test_on_rth_open_disables_gc(self):
        mgr = GCManager()
        mgr.on_rth_open()
        assert mgr.is_disabled is True
        assert not gc.isenabled()
        # Cleanup: re-enable GC
        gc.enable()

    def test_on_rth_close_enables_gc(self):
        mgr = GCManager()
        mgr.on_rth_open()
        mgr.on_rth_close()
        assert mgr.is_disabled is False
        assert gc.isenabled()

    def test_on_rth_close_collects(self):
        mgr = GCManager()
        mgr.on_rth_open()
        with patch.object(gc, "collect", wraps=gc.collect) as mock_collect:
            mgr.on_rth_close()
            mock_collect.assert_called_once()

    def test_lifecycle_round_trip(self):
        mgr = GCManager()
        assert mgr.is_disabled is False
        mgr.on_rth_open()
        assert mgr.is_disabled is True
        mgr.on_rth_close()
        assert mgr.is_disabled is False
        assert gc.isenabled()
