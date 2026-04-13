"""Tests for E3 CounterSpoofEngine (ENG-03) — Wasserstein-1 DOM distribution monitor.

Alert-only — per D-07, not a trade signal.
"""
import time
import pytest
from deep6.engines.counter_spoof import CounterSpoofEngine, SpoofAlert
from deep6.engines.signal_config import CounterSpoofConfig
from deep6.state.dom import LEVELS


def _make_dom_arrays(bid_sizes=None, ask_sizes=None):
    """Build bid/ask price + size arrays for ingest_snapshot."""
    bid_prices = [21000.0 - i * 0.25 for i in range(LEVELS)]
    ask_prices = [21000.25 + i * 0.25 for i in range(LEVELS)]
    b_sizes = list(bid_sizes) if bid_sizes else [0.0] * LEVELS
    a_sizes = list(ask_sizes) if ask_sizes else [0.0] * LEVELS
    # Pad to LEVELS
    b_sizes = (b_sizes + [0.0] * LEVELS)[:LEVELS]
    a_sizes = (a_sizes + [0.0] * LEVELS)[:LEVELS]
    return bid_prices, b_sizes, ask_prices, a_sizes


class TestCounterSpoofConfig:
    def test_default_config_fields(self):
        cfg = CounterSpoofConfig()
        assert cfg.spoof_history_len == 20
        assert cfg.spoof_large_order == 50.0
        assert cfg.spoof_cancel_threshold == 10.0
        assert cfg.spoof_cancel_window_ms == 200.0
        assert cfg.w1_anomaly_sigma == 3.0
        assert cfg.w1_min_samples == 5

    def test_config_is_frozen(self):
        cfg = CounterSpoofConfig()
        with pytest.raises((AttributeError, TypeError)):
            cfg.spoof_history_len = 5  # type: ignore

    def test_config_has_six_fields(self):
        assert len(CounterSpoofConfig.__dataclass_fields__) == 6


class TestCounterSpoofEngineEmptyState:
    def test_w1_anomaly_returns_none_with_no_history(self):
        e = CounterSpoofEngine()
        assert e.get_w1_anomaly() is None

    def test_spoof_alerts_empty_with_no_snapshots(self):
        e = CounterSpoofEngine()
        assert e.get_spoof_alerts() == []

    def test_get_spoof_alerts_clears_buffer(self):
        """get_spoof_alerts returns copy and clears internal buffer."""
        e = CounterSpoofEngine()
        alerts1 = e.get_spoof_alerts()
        alerts2 = e.get_spoof_alerts()
        assert alerts1 == []
        assert alerts2 == []


class TestCounterSpoofEngineW1:
    def test_w1_none_with_insufficient_samples(self):
        """W1 anomaly needs >= w1_min_samples (default 5) history entries."""
        e = CounterSpoofEngine()
        ts = time.monotonic()
        bp, bs, ap, as_ = _make_dom_arrays([20.0] * 10)
        # Ingest 4 identical snapshots (< min_samples=5)
        for i in range(4):
            e.ingest_snapshot(bp, bs, ap, as_, ts + i * 0.1)
        # Only 3 W1 distances stored (need 5) — should still return None
        assert e.get_w1_anomaly() is None

    def test_identical_snapshots_no_anomaly(self):
        """Repeated identical snapshots → W1=0 → no anomaly."""
        e = CounterSpoofEngine()
        ts = time.monotonic()
        bp, bs, ap, as_ = _make_dom_arrays([30.0] * 10)
        # Ingest 10 identical snapshots → W1 distances all 0
        for i in range(10):
            e.ingest_snapshot(bp, bs, ap, as_, ts + i * 0.1)
        # All W1=0 → mean=0, std=0 → guard std<1e-9 returns None
        result = e.get_w1_anomaly()
        assert result is None

    def test_w1_computed_after_min_samples(self):
        """After enough varied snapshots, W1 history is populated."""
        e = CounterSpoofEngine()
        ts = time.monotonic()
        # Alternate between two different distributions to get non-zero W1
        sizes_a = [10.0] * 10
        sizes_b = [100.0] * 10
        bp, _, ap, _ = _make_dom_arrays([0.0] * LEVELS)
        for i in range(10):
            if i % 2 == 0:
                _, bs, _, as_ = _make_dom_arrays(sizes_a)
            else:
                _, bs, _, as_ = _make_dom_arrays(sizes_b)
            e.ingest_snapshot(bp, bs, ap, as_, ts + i * 0.1)
        # W1 history should have entries
        assert len(e._w1_history) > 0


class TestCounterSpoofEngineAlerts:
    def test_spoof_alert_fired_on_large_order_cancel(self):
        """D-06: Level had > 50 contracts → drops to < 10 within 200ms = SpoofAlert."""
        cfg = CounterSpoofConfig(spoof_cancel_window_ms=200.0)
        e = CounterSpoofEngine(cfg)
        ts = time.monotonic()

        # Price level 0 has 100 contracts (> spoof_large_order=50) — record it
        bp = [21000.0 - i * 0.25 for i in range(LEVELS)]
        ap = [21000.25 + i * 0.25 for i in range(LEVELS)]
        bs_large = [100.0] + [10.0] * (LEVELS - 1)
        as_ = [10.0] * LEVELS

        e.ingest_snapshot(bp, bs_large, ap, as_, ts)

        # 100ms later: price level 0 drops to 5 (< cancel_threshold=10) — should alert
        bs_cancel = [5.0] + [10.0] * (LEVELS - 1)
        e.ingest_snapshot(bp, bs_cancel, ap, as_, ts + 0.1)

        alerts = e.get_spoof_alerts()
        assert len(alerts) >= 1
        alert = alerts[0]
        assert isinstance(alert, SpoofAlert)
        assert alert.price == pytest.approx(21000.0)
        assert alert.prior_size == pytest.approx(100.0)
        assert alert.current_size == pytest.approx(5.0)
        assert alert.elapsed_ms < 200.0

    def test_no_alert_when_cancel_outside_window(self):
        """Cancel happening after spoof_cancel_window_ms should NOT fire alert."""
        cfg = CounterSpoofConfig(spoof_cancel_window_ms=50.0)  # very tight window
        e = CounterSpoofEngine(cfg)
        ts = time.monotonic()

        bp = [21000.0 - i * 0.25 for i in range(LEVELS)]
        ap = [21000.25 + i * 0.25 for i in range(LEVELS)]
        bs_large = [100.0] + [10.0] * (LEVELS - 1)
        as_ = [10.0] * LEVELS

        e.ingest_snapshot(bp, bs_large, ap, as_, ts)

        # 300ms later — outside 50ms window
        bs_cancel = [5.0] + [10.0] * (LEVELS - 1)
        e.ingest_snapshot(bp, bs_cancel, ap, as_, ts + 0.3)

        alerts = e.get_spoof_alerts()
        assert len(alerts) == 0

    def test_get_spoof_alerts_clears_after_call(self):
        """Alerts returned once, then buffer clears."""
        cfg = CounterSpoofConfig(spoof_cancel_window_ms=200.0)
        e = CounterSpoofEngine(cfg)
        ts = time.monotonic()

        bp = [21000.0 - i * 0.25 for i in range(LEVELS)]
        ap = [21000.25 + i * 0.25 for i in range(LEVELS)]
        bs_large = [100.0] + [10.0] * (LEVELS - 1)
        as_ = [10.0] * LEVELS

        e.ingest_snapshot(bp, bs_large, ap, as_, ts)
        bs_cancel = [5.0] + [10.0] * (LEVELS - 1)
        e.ingest_snapshot(bp, bs_cancel, ap, as_, ts + 0.1)

        alerts1 = e.get_spoof_alerts()
        alerts2 = e.get_spoof_alerts()
        assert len(alerts1) >= 1
        assert len(alerts2) == 0  # cleared after first call


class TestCounterSpoofEngineReset:
    def test_reset_clears_state(self):
        e = CounterSpoofEngine()
        ts = time.monotonic()
        bp, bs, ap, as_ = _make_dom_arrays([30.0] * 10)
        for i in range(5):
            e.ingest_snapshot(bp, bs, ap, as_, ts + i * 0.1)
        e.reset()
        assert len(e._snapshot_history) == 0
        assert len(e._w1_history) == 0
        assert len(e._level_timestamps) == 0
        assert e.get_spoof_alerts() == []


class TestSpoofAlertFields:
    def test_spoof_alert_has_all_fields(self):
        alert = SpoofAlert(price=21000.0, prior_size=100.0, current_size=5.0,
                           elapsed_ms=100.0, detail="spoof")
        assert hasattr(alert, "price")
        assert hasattr(alert, "prior_size")
        assert hasattr(alert, "current_size")
        assert hasattr(alert, "elapsed_ms")
        assert hasattr(alert, "detail")


class TestCounterSpoofEngineThreatMitigations:
    def test_t04_05_empty_arrays_no_crash(self):
        """T-04-05: scipy W1 on near-empty arrays must not crash."""
        e = CounterSpoofEngine()
        ts = time.monotonic()
        bp = [21000.0] * LEVELS
        ap = [21000.25] * LEVELS
        bs = [0.0] * LEVELS
        as_ = [0.0] * LEVELS
        # Ingest all-zero snapshots — should not raise
        for i in range(10):
            e.ingest_snapshot(bp, bs, ap, as_, ts + i * 0.1)
        # No crash
        e.get_w1_anomaly()

    def test_t04_06_std_zero_guard(self):
        """T-04-06: W1 std=0 (all identical distances) → get_w1_anomaly returns None."""
        e = CounterSpoofEngine()
        ts = time.monotonic()
        bp, bs, ap, as_ = _make_dom_arrays([20.0] * 10)
        # All identical → W1=0 for each consecutive pair → std=0
        for i in range(15):
            e.ingest_snapshot(bp, bs, ap, as_, ts + i * 0.1)
        result = e.get_w1_anomaly()
        assert result is None  # std=0 → guard fires

    def test_t04_07_level_timestamps_bounded(self):
        """T-04-07: _level_timestamps dict must not grow beyond LEVELS entries."""
        e = CounterSpoofEngine()
        ts = time.monotonic()
        # Each snapshot has different large orders across all levels
        bp = [21000.0 - i * 0.25 for i in range(LEVELS)]
        ap = [21000.25 + i * 0.25 for i in range(LEVELS)]
        as_ = [10.0] * LEVELS
        for snap_i in range(30):
            bs = [100.0] * LEVELS  # all levels have large orders
            e.ingest_snapshot(bp, bs, ap, as_, ts + snap_i * 0.1)
        # Dict should be bounded to LEVELS
        assert len(e._level_timestamps) <= LEVELS
