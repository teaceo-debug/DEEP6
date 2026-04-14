"""Tests for ML backend components — ML-01 through ML-08.

Covers:
- EventStore: CRUD, schema, tier filter, OOS count
- FeatureBuilder: feature vector shape, category flags, GEX one-hot
- DeployGate: token validation, WFE gate, OOS gate, weight cap
- WeightLoader: atomic write, backup, rollback, mtime cache
- PerformanceTracker: rolling windows, regime slices, empty data
- E7MLQualityEngine: stub mode, live weights, clamp behaviour

All tests are self-contained: SQLite :memory: for DB, tempfile.TemporaryDirectory
for file-based tests. No external services required.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time

import numpy as np
import pytest

from deep6.api.schemas import SignalEventIn, TradeEventIn
from deep6.api.store import EventStore
from deep6.ml.deploy_gate import DeployGate
from deep6.ml.feature_builder import FEATURE_NAMES, build_feature_matrix
from deep6.ml.lgbm_trainer import WeightFile
from deep6.ml.performance_tracker import PerformanceTracker, TierMetrics
from deep6.ml.weight_loader import WeightLoader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_signal_event(**kwargs) -> SignalEventIn:
    defaults = dict(
        ts=time.time(),
        bar_index_in_session=42,
        total_score=75.0,
        tier="TYPE_A",
        direction=1,
        engine_agreement=0.8,
        category_count=3,
        categories_firing=["absorption", "delta"],
        gex_regime="NEUTRAL",
        kronos_bias=0.0,
    )
    defaults.update(kwargs)
    return SignalEventIn(**defaults)


def _make_trade_event(**kwargs) -> TradeEventIn:
    defaults = dict(
        ts=time.time(),
        position_id="pos-001",
        event_type="TARGET_HIT",
        side="LONG",
        entry_price=21000.0,
        exit_price=21050.0,
        pnl=500.0,
        bars_held=3,
        signal_tier="TYPE_A",
        signal_score=75.0,
        regime_label="UNKNOWN",
    )
    defaults.update(kwargs)
    return TradeEventIn(**defaults)


def _make_weight_file(
    wfe: float | None = 0.75,
    weights: dict | None = None,
    training_date: str = "2026-04-13",
    n_samples: int = 300,
) -> WeightFile:
    return WeightFile(
        weights=weights or {"absorption": 1.5, "delta": 1.2},
        regime_adjustments={},
        feature_importances={},
        training_date=training_date,
        n_samples=n_samples,
        metrics={"accuracy": 0.72, "roc_auc": 0.78},
        wfe=wfe,
        model_path="./fake_model.pkl",
        model_checksum="",
    )


# ---------------------------------------------------------------------------
# EventStore tests
# ---------------------------------------------------------------------------

class TestEventStore:
    """Tests for EventStore CRUD operations and schema correctness."""

    def setup_method(self):
        self.store = EventStore(":memory:")
        asyncio.run(self.store.initialize())

    def test_initialize_creates_tables(self):
        """EventStore.initialize() creates signal_events and trade_events tables."""
        # Tables exist — we can insert without error
        ev = _make_signal_event()
        row_id = asyncio.run(self.store.insert_signal_event(ev))
        assert isinstance(row_id, int)
        assert row_id > 0

    def test_insert_signal_event_returns_id(self):
        """insert_signal_event returns a positive autoincrement ID."""
        ev = _make_signal_event(tier="TYPE_B", total_score=60.0)
        row_id = asyncio.run(self.store.insert_signal_event(ev))
        assert row_id == 1

        ev2 = _make_signal_event(tier="TYPE_A")
        row_id2 = asyncio.run(self.store.insert_signal_event(ev2))
        assert row_id2 == 2

    def test_insert_trade_event_returns_id(self):
        """insert_trade_event returns a positive autoincrement ID."""
        ev = _make_trade_event(pnl=300.0)
        row_id = asyncio.run(self.store.insert_trade_event(ev))
        assert isinstance(row_id, int)
        assert row_id == 1

    def test_insert_trade_event_stores_regime_label(self):
        """insert_trade_event persists the regime_label field."""
        ev = _make_trade_event(regime_label="ABSORPTION_FRIENDLY")
        asyncio.run(self.store.insert_trade_event(ev))
        rows = asyncio.run(self.store.fetch_trade_events(limit=1))
        assert rows[0]["regime_label"] == "ABSORPTION_FRIENDLY"

    def test_fetch_signal_events_order(self):
        """fetch_signal_events returns rows in descending ts order."""
        now = time.time()
        asyncio.run(self.store.insert_signal_event(_make_signal_event(ts=now - 10)))
        asyncio.run(self.store.insert_signal_event(_make_signal_event(ts=now - 5)))
        asyncio.run(self.store.insert_signal_event(_make_signal_event(ts=now)))
        rows = asyncio.run(self.store.fetch_signal_events())
        tss = [r["ts"] for r in rows]
        assert tss == sorted(tss, reverse=True)

    def test_fetch_trade_events_tier_filter(self):
        """fetch_trade_events respects tier_filter parameter."""
        asyncio.run(self.store.insert_trade_event(_make_trade_event(signal_tier="TYPE_A")))
        asyncio.run(self.store.insert_trade_event(_make_trade_event(signal_tier="TYPE_B")))
        asyncio.run(self.store.insert_trade_event(_make_trade_event(signal_tier="TYPE_A")))

        rows_a = asyncio.run(self.store.fetch_trade_events(tier_filter="TYPE_A"))
        rows_b = asyncio.run(self.store.fetch_trade_events(tier_filter="TYPE_B"))
        rows_all = asyncio.run(self.store.fetch_trade_events())

        assert len(rows_a) == 2
        assert len(rows_b) == 1
        assert len(rows_all) == 3
        assert all(r["signal_tier"] == "TYPE_A" for r in rows_a)

    def test_count_oos_trades_per_signal_empty(self):
        """count_oos_trades_per_signal returns empty dict when no closed trades."""
        result = asyncio.run(self.store.count_oos_trades_per_signal())
        assert result == {}

    def test_count_oos_trades_per_signal_counts_closed(self):
        """count_oos_trades_per_signal counts only CLOSED event types."""
        asyncio.run(self.store.insert_trade_event(_make_trade_event(signal_tier="TYPE_A", event_type="TARGET_HIT")))
        asyncio.run(self.store.insert_trade_event(_make_trade_event(signal_tier="TYPE_A", event_type="STOP_HIT")))
        asyncio.run(self.store.insert_trade_event(_make_trade_event(signal_tier="TYPE_A", event_type="ENTRY")))  # Not closed
        asyncio.run(self.store.insert_trade_event(_make_trade_event(signal_tier="TYPE_B", event_type="TARGET_HIT")))

        result = asyncio.run(self.store.count_oos_trades_per_signal())
        assert result.get("TYPE_A") == 2
        assert result.get("TYPE_B") == 1
        assert "TYPE_A" in result


# ---------------------------------------------------------------------------
# FeatureBuilder tests
# ---------------------------------------------------------------------------

class TestFeatureBuilder:
    """Tests for build_feature_matrix and FEATURE_NAMES correctness."""

    def test_feature_count_is_47(self):
        """FEATURE_NAMES must contain exactly 47 features."""
        assert len(FEATURE_NAMES) == 47

    def test_feature_names_unique(self):
        """All feature names must be unique."""
        assert len(FEATURE_NAMES) == len(set(FEATURE_NAMES))

    def test_category_flags_set_correctly(self):
        """Category binary flags are set for matching categories."""
        signal_rows = [{
            "ts": time.time(),
            "bar_index": 10,
            "total_score": 80.0,
            "engine_agreement": 0.9,
            "category_count": 2,
            "direction": 1,
            "categories": json.dumps(["absorption", "delta"]),
            "gex_regime": "NEUTRAL",
            "kronos_bias": 0.0,
        }]
        trade_rows = [{
            "ts": time.time() + 10,
            "pnl": 500.0,
        }]
        X, y = build_feature_matrix(signal_rows, trade_rows)
        assert X.shape == (1, 47)
        assert X[0, FEATURE_NAMES.index("cat_absorption")] == 1.0
        assert X[0, FEATURE_NAMES.index("cat_delta")] == 1.0
        assert X[0, FEATURE_NAMES.index("cat_exhaustion")] == 0.0

    def test_gex_one_hot(self):
        """GEX regime one-hot encoding is set correctly."""
        signal_rows = [{
            "ts": time.time(),
            "bar_index": 5,
            "total_score": 70.0,
            "engine_agreement": 0.75,
            "category_count": 1,
            "direction": -1,
            "categories": json.dumps([]),
            "gex_regime": "POSITIVE_DAMPENING",
            "kronos_bias": 0.5,
        }]
        trade_rows = [{"ts": time.time() + 10, "pnl": 300.0}]
        X, y = build_feature_matrix(signal_rows, trade_rows)
        assert X[0, FEATURE_NAMES.index("gex_positive")] == 1.0
        assert X[0, FEATURE_NAMES.index("gex_negative")] == 0.0

    def test_empty_input_returns_empty_arrays(self):
        """Empty signal_rows or trade_rows returns zero-shaped arrays."""
        X, y = build_feature_matrix([], [])
        assert X.shape == (0, 47)
        assert y.shape == (0,)

        X2, y2 = build_feature_matrix([{"ts": 1.0}], [])
        assert X2.shape == (0, 47)


# ---------------------------------------------------------------------------
# DeployGate tests
# ---------------------------------------------------------------------------

class TestDeployGate:
    """Tests for DeployGate multi-gate validation logic."""

    def setup_method(self):
        self.gate = DeployGate(wfe_threshold=0.70, min_oos_trades=200, weight_cap=3.0)
        self.token = self.gate.generate_token()
        self.oos = {"TYPE_A": 120, "TYPE_B": 100}  # total 220

    def test_wrong_token_returns_not_allowed(self):
        """Gate 1: Wrong confirmation token must block deploy."""
        candidate = _make_weight_file(wfe=0.75, weights={"absorption": 1.5})
        decision = self.gate.evaluate(candidate, None, self.oos, "wrong_token", self.token)
        assert not decision.allowed
        assert "token" in decision.reason.lower()

    def test_wfe_below_threshold_blocked(self):
        """Gate 2: WFE below threshold must block deploy."""
        candidate = _make_weight_file(wfe=0.65, weights={"absorption": 1.5})
        decision = self.gate.evaluate(candidate, None, self.oos, self.token, self.token)
        assert not decision.allowed
        assert "WFE" in decision.reason or "wfe" in decision.reason.lower()

    def test_wfe_none_blocked(self):
        """Gate 2: WFE=None must block deploy (model not validated)."""
        candidate = _make_weight_file(wfe=None, weights={"absorption": 1.5})
        decision = self.gate.evaluate(candidate, None, self.oos, self.token, self.token)
        assert not decision.allowed

    def test_insufficient_oos_trades_blocked(self):
        """Gate 3: Total OOS trades below min_oos_trades must block."""
        low_oos = {"TYPE_A": 50, "TYPE_B": 80}  # total 130 < 200
        candidate = _make_weight_file(wfe=0.75, weights={"absorption": 1.5})
        decision = self.gate.evaluate(candidate, None, low_oos, self.token, self.token)
        assert not decision.allowed
        assert "OOS" in decision.reason or "trades" in decision.reason.lower()

    def test_weight_cap_exceeded_blocked(self):
        """Gate 4: Weight exceeding 3x cap must block deploy."""
        candidate = _make_weight_file(wfe=0.75, weights={"absorption": 3.5, "delta": 1.0})
        decision = self.gate.evaluate(candidate, None, self.oos, self.token, self.token)
        assert not decision.allowed
        assert "absorption" in decision.reason or len(decision.weight_cap_violations) > 0

    def test_all_gates_pass(self):
        """All gates passing produces decision.allowed == True."""
        candidate = _make_weight_file(wfe=0.80, weights={"absorption": 1.5, "delta": 1.2})
        decision = self.gate.evaluate(candidate, None, self.oos, self.token, self.token)
        assert decision.allowed
        assert decision.reason == "All gates passed"

    def test_before_after_populated(self):
        """evaluate() always populates before_after comparison dict."""
        current = _make_weight_file(wfe=0.71, weights={"absorption": 1.0})
        candidate = _make_weight_file(wfe=0.80, weights={"absorption": 1.5})
        decision = self.gate.evaluate(candidate, current, self.oos, self.token, self.token)
        assert decision.before_after is not None
        assert "before" in decision.before_after
        assert "after" in decision.before_after


# ---------------------------------------------------------------------------
# WeightLoader tests
# ---------------------------------------------------------------------------

class TestWeightLoader:
    """Tests for WeightLoader atomic write, backup, rollback, and mtime caching."""

    def test_read_current_none_when_no_file(self):
        """read_current() returns None when weight file does not exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "weights.json")
            loader = WeightLoader(weights_path=path)
            assert loader.read_current() is None

    def test_write_atomic_creates_file(self):
        """write_atomic() creates the weight file on disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "weights.json")
            backup_path = os.path.join(tmpdir, "weights_prev.json")
            loader = WeightLoader(weights_path=path, backup_path=backup_path)
            wf = _make_weight_file()
            loader.write_atomic(wf)
            assert os.path.exists(path)
            data = loader.read_current()
            assert data is not None
            assert "weights" in data

    def test_write_atomic_creates_backup_on_second_write(self):
        """write_atomic() backs up existing file before writing new one."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "weights.json")
            backup_path = os.path.join(tmpdir, "weights_prev.json")
            loader = WeightLoader(weights_path=path, backup_path=backup_path)

            # First write — no backup yet
            wf1 = _make_weight_file(weights={"absorption": 1.0})
            loader.write_atomic(wf1)
            assert not os.path.exists(backup_path)

            # Second write — should create backup of first
            wf2 = _make_weight_file(weights={"absorption": 2.0})
            loader.write_atomic(wf2)
            assert os.path.exists(backup_path)

    def test_rollback_restores_previous(self):
        """rollback() restores backup weight file as current."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "weights.json")
            backup_path = os.path.join(tmpdir, "weights_prev.json")
            loader = WeightLoader(weights_path=path, backup_path=backup_path)

            wf1 = _make_weight_file(weights={"absorption": 1.0})
            loader.write_atomic(wf1)
            wf2 = _make_weight_file(weights={"absorption": 2.5})
            loader.write_atomic(wf2)

            # Current should be wf2
            current = loader.read_current()
            assert current["weights"]["absorption"] == 2.5

            # Rollback → should restore wf1
            ok = loader.rollback()
            assert ok is True
            restored = loader.read_current()
            assert restored["weights"]["absorption"] == 1.0

    def test_rollback_returns_false_when_no_backup(self):
        """rollback() returns False when no backup file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "weights.json")
            backup_path = os.path.join(tmpdir, "weights_prev.json")
            loader = WeightLoader(weights_path=path, backup_path=backup_path)
            assert loader.rollback() is False

    def test_read_current_uses_mtime_cache(self):
        """read_current() returns cached data without re-reading when file unchanged (T-09-14)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "weights.json")
            backup_path = os.path.join(tmpdir, "weights_prev.json")
            loader = WeightLoader(weights_path=path, backup_path=backup_path)

            wf = _make_weight_file(weights={"absorption": 1.2})
            loader.write_atomic(wf)

            # First read populates cache
            data1 = loader.read_current()
            assert data1 is not None

            # Mutate the cached dict in place — next read should return same object (cached)
            cached_id = id(loader._cached_data)
            data2 = loader.read_current()
            assert id(data2) == cached_id  # Same object from cache


# ---------------------------------------------------------------------------
# PerformanceTracker tests
# ---------------------------------------------------------------------------

class TestPerformanceTracker:
    """Tests for PerformanceTracker rolling window and regime slice computation."""

    def _make_trade_rows(self, n: int = 30, tier: str = "TYPE_A", regime: str = "ABSORPTION_FRIENDLY") -> list[dict]:
        rows = []
        now = time.time()
        for i in range(n):
            rows.append({
                "event_type": "TARGET_HIT" if i % 3 != 0 else "STOP_HIT",
                "pnl": 600.0 if i % 3 != 0 else -300.0,
                "signal_tier": tier,
                "signal_score": 80.0,
                "ts": now - (n - i) * 60,
                "bars_held": 3,
                "regime_label": regime,
            })
        return rows

    def test_compute_returns_tier_metrics_list(self):
        """compute() returns a list of TierMetrics instances."""
        tracker = PerformanceTracker(windows=[50])
        rows = self._make_trade_rows(30)
        metrics = tracker.compute(rows)
        assert isinstance(metrics, list)
        assert all(isinstance(m, TierMetrics) for m in metrics)

    def test_compute_empty_input_returns_zero_metrics(self):
        """compute() returns zero-valued TierMetrics for empty input."""
        tracker = PerformanceTracker(windows=[50])
        metrics = tracker.compute([])
        all_regime_none = [m for m in metrics if m.regime is None]
        assert len(all_regime_none) > 0
        for m in all_regime_none:
            assert m.n_trades == 0
            assert m.win_rate == 0.0

    def test_compute_win_rate_correct(self):
        """win_rate is computed as wins / n_trades."""
        tracker = PerformanceTracker(windows=[50])
        rows = self._make_trade_rows(30)  # 2/3 TARGET_HIT wins
        metrics = tracker.compute(rows)
        type_a = [m for m in metrics if m.tier == "TYPE_A" and m.regime is None and m.window == 50]
        assert len(type_a) == 1
        # 20 wins out of 30 trades
        assert abs(type_a[0].win_rate - (20 / 30)) < 0.01

    def test_compute_profit_factor_no_losses(self):
        """profit_factor is inf when there are no losing trades."""
        tracker = PerformanceTracker(windows=[50])
        rows = [{"event_type": "TARGET_HIT", "pnl": 500.0, "signal_tier": "TYPE_A",
                 "ts": time.time() + i, "regime_label": "UNKNOWN"} for i in range(10)]
        metrics = tracker.compute(rows)
        type_a = [m for m in metrics if m.tier == "TYPE_A" and m.regime is None and m.window == 50]
        assert type_a[0].profit_factor == float("inf")

    def test_compute_regime_slices_populated(self):
        """Per-regime TierMetrics are returned with regime != None."""
        tracker = PerformanceTracker(windows=[50])
        rows = self._make_trade_rows(20, tier="TYPE_A", regime="ABSORPTION_FRIENDLY")
        metrics = tracker.compute(rows)
        af_metrics = [m for m in metrics if m.regime == "ABSORPTION_FRIENDLY" and m.tier == "TYPE_A"]
        assert len(af_metrics) > 0
        assert af_metrics[0].n_trades == 20

    def test_compute_rolling_window_limits(self):
        """Rolling window of 10 uses only last 10 trades, not all."""
        tracker = PerformanceTracker(windows=[10])
        rows = self._make_trade_rows(30)
        metrics = tracker.compute(rows)
        type_a_10 = [m for m in metrics if m.tier == "TYPE_A" and m.regime is None and m.window == 10]
        assert type_a_10[0].n_trades == 10

    def test_compute_all_three_windows(self):
        """PerformanceTracker produces metrics for all three default windows."""
        tracker = PerformanceTracker()
        rows = self._make_trade_rows(60)
        metrics = tracker.compute(rows)
        for window in [50, 200, 500]:
            wm = [m for m in metrics if m.tier == "TYPE_A" and m.regime is None and m.window == window]
            assert len(wm) == 1, f"Missing window={window}"

    def test_tier_metrics_to_dict_json_safe(self):
        """TierMetrics.to_dict() returns a JSON-serialisable dict."""
        tm = TierMetrics(
            tier="TYPE_A", n_trades=10, win_rate=0.7, profit_factor=float("inf"),
            sharpe=1.5, avg_pnl=300.0, total_pnl=3000.0, regime=None, window=50,
        )
        d = tm.to_dict()
        # inf should be replaced with None for JSON safety
        assert d["profit_factor"] is None
        import json as _json
        _json.dumps(d)  # should not raise

    def test_open_trades_excluded(self):
        """Trades with non-closed event_type are excluded from metrics."""
        tracker = PerformanceTracker(windows=[50])
        rows = [
            {"event_type": "ENTRY", "pnl": 0.0, "signal_tier": "TYPE_A", "ts": time.time(), "regime_label": "UNKNOWN"},
            {"event_type": "TARGET_HIT", "pnl": 500.0, "signal_tier": "TYPE_A", "ts": time.time() + 1, "regime_label": "UNKNOWN"},
        ]
        metrics = tracker.compute(rows)
        type_a = [m for m in metrics if m.tier == "TYPE_A" and m.regime is None and m.window == 50]
        assert type_a[0].n_trades == 1  # Only TARGET_HIT counted


# ---------------------------------------------------------------------------
# E7MLQualityEngine tests
# ---------------------------------------------------------------------------

class TestE7MLQualityEngine:
    """Tests for E7MLQualityEngine stub vs live weights behaviour."""

    def test_score_returns_1_0_when_no_weight_loader(self):
        """score() returns 1.0 (neutral stub) when weight_loader is None."""
        from deep6.engines.vp_context_engine import E7MLQualityEngine
        engine = E7MLQualityEngine()
        assert engine.score() == 1.0

    def test_process_alias_returns_same_as_score(self):
        """process() is an alias for score() — must return identical value."""
        from deep6.engines.vp_context_engine import E7MLQualityEngine
        engine = E7MLQualityEngine()
        assert engine.process() == engine.score()

    def test_score_returns_1_0_when_no_weight_file(self):
        """score() returns 1.0 when weight file does not exist on disk."""
        from deep6.engines.vp_context_engine import E7MLQualityEngine
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "weights.json")
            loader = WeightLoader(weights_path=path)
            engine = E7MLQualityEngine(weight_loader=loader)
            assert engine.score() == 1.0

    def test_score_returns_float_in_range_with_weights(self):
        """score() returns float in [0.5, 1.5] when weights are loaded."""
        from deep6.engines.vp_context_engine import E7MLQualityEngine
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "weights.json")
            backup_path = os.path.join(tmpdir, "weights_prev.json")
            loader = WeightLoader(weights_path=path, backup_path=backup_path)
            wf = _make_weight_file(weights={"absorption": 1.2, "delta": 0.9, "exhaustion": 1.1})
            loader.write_atomic(wf)

            engine = E7MLQualityEngine(weight_loader=loader)
            result = engine.score()
            assert isinstance(result, float)
            assert 0.5 <= result <= 1.5

    def test_score_clamped_below_0_5(self):
        """score() clamps very low weights to 0.5."""
        from deep6.engines.vp_context_engine import E7MLQualityEngine
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "weights.json")
            backup_path = os.path.join(tmpdir, "weights_prev.json")
            loader = WeightLoader(weights_path=path, backup_path=backup_path)
            # Mean weight of 0.1 → should clamp to 0.5
            wf = _make_weight_file(weights={"absorption": 0.1, "delta": 0.1})
            loader.write_atomic(wf)

            engine = E7MLQualityEngine(weight_loader=loader)
            result = engine.score()
            assert result == 0.5

    def test_score_clamped_above_1_5(self):
        """score() clamps very high weights to 1.5."""
        from deep6.engines.vp_context_engine import E7MLQualityEngine
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "weights.json")
            backup_path = os.path.join(tmpdir, "weights_prev.json")
            loader = WeightLoader(weights_path=path, backup_path=backup_path)
            # Mean weight of 3.0 → should clamp to 1.5
            wf = _make_weight_file(weights={"absorption": 3.0, "delta": 3.0})
            loader.write_atomic(wf)

            engine = E7MLQualityEngine(weight_loader=loader)
            result = engine.score()
            assert result == 1.5

    def test_score_correct_mean_calculation(self):
        """score() computes mean of signal weights correctly."""
        from deep6.engines.vp_context_engine import E7MLQualityEngine
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "weights.json")
            backup_path = os.path.join(tmpdir, "weights_prev.json")
            loader = WeightLoader(weights_path=path, backup_path=backup_path)
            # Mean = (1.2 + 0.9 + 1.1 + 1.0) / 4 = 1.05
            wf = _make_weight_file(weights={"absorption": 1.2, "delta": 0.9, "exhaustion": 1.1, "trapped": 1.0})
            loader.write_atomic(wf)

            engine = E7MLQualityEngine(weight_loader=loader)
            result = engine.score()
            assert abs(result - 1.05) < 0.001
