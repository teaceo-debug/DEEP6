"""Tests for DeployGate + WeightLoader (Plan 09-03 TDD).

RED phase: these tests are written before implementation.
GREEN phase: run after implementing deep6/ml/deploy_gate.py and deep6/ml/weight_loader.py.
"""
from __future__ import annotations

import json
import os
import tempfile

import pytest

from deep6.ml.lgbm_trainer import WeightFile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        metrics={"roc_auc": 0.62},
        wfe=wfe,
        model_path="x.pkl",
    )


# ---------------------------------------------------------------------------
# DeployGate tests
# ---------------------------------------------------------------------------

class TestDeployGate:
    """Unit tests for DeployGate.evaluate()."""

    def setup_method(self):
        from deep6.ml.deploy_gate import DeployGate
        self.gate = DeployGate(wfe_threshold=0.70, min_oos_trades=200, weight_cap=3.0)

    def test_generate_token_returns_32_char_hex(self):
        token = self.gate.generate_token()
        assert len(token) == 32
        assert all(c in "0123456789abcdef" for c in token)

    def test_wrong_token_rejected(self):
        candidate = _make_weight_file(wfe=0.80)
        decision = self.gate.evaluate(
            candidate=candidate,
            current=None,
            oos_counts={"TYPE_A": 100, "TYPE_B": 150},
            confirmation_token="wrong_token",
            expected_token="correct_token",
        )
        assert decision.allowed is False
        assert "token" in decision.reason.lower()

    def test_wfe_below_threshold_rejected(self):
        candidate = _make_weight_file(wfe=0.65)
        decision = self.gate.evaluate(
            candidate=candidate,
            current=None,
            oos_counts={"TYPE_A": 200, "TYPE_B": 100},
            confirmation_token="tok",
            expected_token="tok",
        )
        assert decision.allowed is False
        assert "WFE" in decision.reason
        assert "0.65" in decision.reason

    def test_wfe_none_rejected(self):
        candidate = _make_weight_file(wfe=None)
        decision = self.gate.evaluate(
            candidate=candidate,
            current=None,
            oos_counts={"TYPE_A": 300},
            confirmation_token="tok",
            expected_token="tok",
        )
        assert decision.allowed is False
        assert "WFE" in decision.reason

    def test_insufficient_oos_trades_rejected(self):
        candidate = _make_weight_file(wfe=0.80)
        decision = self.gate.evaluate(
            candidate=candidate,
            current=None,
            oos_counts={"TYPE_A": 50},  # total=50 < 200
            confirmation_token="tok",
            expected_token="tok",
        )
        assert decision.allowed is False
        assert "OOS" in decision.reason
        assert "50" in decision.reason

    def test_weight_cap_exceeded_rejected(self):
        candidate = _make_weight_file(
            wfe=0.80,
            weights={"absorption": 3.5, "delta": 1.0},  # 3.5 > 3.0
        )
        decision = self.gate.evaluate(
            candidate=candidate,
            current=None,
            oos_counts={"TYPE_A": 150, "TYPE_B": 100},
            confirmation_token="tok",
            expected_token="tok",
        )
        assert decision.allowed is False
        assert "absorption" in decision.reason
        assert "absorption" in decision.weight_cap_violations

    def test_all_gates_pass(self):
        candidate = _make_weight_file(wfe=0.80)
        current = _make_weight_file(wfe=0.72, training_date="2026-04-01")
        decision = self.gate.evaluate(
            candidate=candidate,
            current=current,
            oos_counts={"TYPE_A": 150, "TYPE_B": 100},  # total=250 >= 200
            confirmation_token="good_token",
            expected_token="good_token",
        )
        assert decision.allowed is True
        assert decision.wfe == 0.80
        assert decision.before_after is not None
        assert decision.before_after["before"]["training_date"] == "2026-04-01"
        assert decision.before_after["after"]["training_date"] == "2026-04-13"

    def test_before_after_none_current(self):
        candidate = _make_weight_file(wfe=0.80)
        decision = self.gate.evaluate(
            candidate=candidate,
            current=None,
            oos_counts={"TYPE_A": 250},
            confirmation_token="tok",
            expected_token="tok",
        )
        assert decision.allowed is True
        assert decision.before_after["before"] is None

    def test_fail_fast_token_before_wfe(self):
        """Token check fires before WFE check (fail-fast)."""
        candidate = _make_weight_file(wfe=0.50)  # would also fail WFE
        decision = self.gate.evaluate(
            candidate=candidate,
            current=None,
            oos_counts={},
            confirmation_token="bad",
            expected_token="good",
        )
        assert decision.allowed is False
        assert "token" in decision.reason.lower()


# ---------------------------------------------------------------------------
# WeightLoader tests
# ---------------------------------------------------------------------------

class TestWeightLoader:
    """Unit tests for WeightLoader atomic write + rollback."""

    def test_read_current_returns_none_when_no_file(self):
        from deep6.ml.weight_loader import WeightLoader
        with tempfile.TemporaryDirectory() as d:
            loader = WeightLoader(
                weights_path=os.path.join(d, "weights.json"),
                backup_path=os.path.join(d, "weights_prev.json"),
            )
            assert loader.read_current() is None

    def test_write_atomic_creates_file(self):
        from deep6.ml.weight_loader import WeightLoader
        with tempfile.TemporaryDirectory() as d:
            loader = WeightLoader(
                weights_path=os.path.join(d, "weights.json"),
                backup_path=os.path.join(d, "weights_prev.json"),
            )
            wf = _make_weight_file()
            loader.write_atomic(wf)
            assert os.path.exists(os.path.join(d, "weights.json"))
            assert loader.read_current() is not None

    def test_second_write_creates_backup(self):
        from deep6.ml.weight_loader import WeightLoader
        with tempfile.TemporaryDirectory() as d:
            loader = WeightLoader(
                weights_path=os.path.join(d, "weights.json"),
                backup_path=os.path.join(d, "weights_prev.json"),
            )
            wf1 = _make_weight_file(training_date="2026-04-01")
            wf2 = _make_weight_file(training_date="2026-04-13")
            loader.write_atomic(wf1)
            loader.write_atomic(wf2)
            prev = loader.read_previous()
            assert prev is not None
            assert prev["training_date"] == "2026-04-01"

    def test_no_tmp_file_left_after_write(self):
        from deep6.ml.weight_loader import WeightLoader
        with tempfile.TemporaryDirectory() as d:
            loader = WeightLoader(
                weights_path=os.path.join(d, "weights.json"),
                backup_path=os.path.join(d, "weights_prev.json"),
            )
            loader.write_atomic(_make_weight_file())
            tmp = os.path.join(d, "weights.json.tmp")
            assert not os.path.exists(tmp), "Temp file should be renamed away"

    def test_rollback_restores_previous(self):
        from deep6.ml.weight_loader import WeightLoader
        with tempfile.TemporaryDirectory() as d:
            loader = WeightLoader(
                weights_path=os.path.join(d, "weights.json"),
                backup_path=os.path.join(d, "weights_prev.json"),
            )
            wf1 = _make_weight_file(training_date="2026-04-01")
            wf2 = _make_weight_file(training_date="2026-04-13")
            loader.write_atomic(wf1)
            loader.write_atomic(wf2)
            ok = loader.rollback()
            assert ok is True
            current = loader.read_current()
            assert current["training_date"] == "2026-04-01"

    def test_rollback_false_when_no_backup(self):
        from deep6.ml.weight_loader import WeightLoader
        with tempfile.TemporaryDirectory() as d:
            loader = WeightLoader(
                weights_path=os.path.join(d, "weights.json"),
                backup_path=os.path.join(d, "weights_prev.json"),
            )
            loader.write_atomic(_make_weight_file())
            # No second write → no backup
            ok = loader.rollback()
            assert ok is False

    def test_backup_age_days_none_when_no_backup(self):
        from deep6.ml.weight_loader import WeightLoader
        with tempfile.TemporaryDirectory() as d:
            loader = WeightLoader(
                weights_path=os.path.join(d, "weights.json"),
                backup_path=os.path.join(d, "weights_prev.json"),
            )
            assert loader.backup_age_days() is None

    def test_backup_age_days_returns_float_after_write(self):
        from deep6.ml.weight_loader import WeightLoader
        with tempfile.TemporaryDirectory() as d:
            loader = WeightLoader(
                weights_path=os.path.join(d, "weights.json"),
                backup_path=os.path.join(d, "weights_prev.json"),
            )
            loader.write_atomic(_make_weight_file(training_date="2026-04-01"))
            loader.write_atomic(_make_weight_file(training_date="2026-04-13"))
            age = loader.backup_age_days()
            assert age is not None
            assert isinstance(age, float)
            assert age >= 0.0

    def test_rollback_blocked_after_ttl_expired(self):
        """Rollback returns False if backup is older than backup_ttl_days."""
        import time
        from deep6.ml.weight_loader import WeightLoader
        with tempfile.TemporaryDirectory() as d:
            loader = WeightLoader(
                weights_path=os.path.join(d, "weights.json"),
                backup_path=os.path.join(d, "weights_prev.json"),
                backup_ttl_days=0,  # immediately expired
            )
            loader.write_atomic(_make_weight_file(training_date="2026-04-01"))
            loader.write_atomic(_make_weight_file(training_date="2026-04-13"))
            # Manually age the backup file
            backup_path = os.path.join(d, "weights_prev.json")
            old_time = time.time() - 1  # 1 second ago → older than 0-day TTL
            os.utime(backup_path, (old_time, old_time))
            ok = loader.rollback()
            assert ok is False
