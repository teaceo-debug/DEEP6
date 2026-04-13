"""Tests for KronosConfig dataclass and KronosWorkerProcess.

Per 06-01-PLAN.md Task 1 TDD requirements.
Tests run against real subprocess to verify pipe protocol.
"""
from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

import pytest


class TestKronosConfigDefaults:
    """Test KronosConfig frozen dataclass defaults."""

    def test_kronos_config_defaults(self):
        from deep6.engines.signal_config import KronosConfig
        cfg = KronosConfig()
        assert cfg.num_samples == 20
        assert cfg.decay_factor == 0.95
        assert cfg.device == "auto"
        assert cfg.inference_interval == 5
        assert cfg.lookback == 100
        assert cfg.pred_len == 5
        assert cfg.model_name == "NeoQuasar/Kronos-small"
        assert cfg.tokenizer_name == "NeoQuasar/Kronos-Tokenizer-base"

    def test_kronos_config_frozen(self):
        """KronosConfig must be immutable (frozen=True)."""
        from deep6.engines.signal_config import KronosConfig
        cfg = KronosConfig()
        with pytest.raises((AttributeError, TypeError)):
            cfg.num_samples = 99


class TestSelectDevice:
    """Test _select_device() helper."""

    def test_device_selection_auto_cpu(self):
        """When neither mps nor cuda available, auto selects cpu."""
        import types
        from deep6.engines.kronos_worker import _select_device

        # torch is imported inside _select_device — patch the builtin import
        mock_torch = types.ModuleType("torch")
        mock_torch.backends = types.SimpleNamespace(
            mps=types.SimpleNamespace(is_available=lambda: False)
        )
        mock_torch.cuda = types.SimpleNamespace(is_available=lambda: False)

        with patch.dict(sys.modules, {"torch": mock_torch}):
            result = _select_device("auto")
        assert result == "cpu"

    def test_device_selection_explicit(self):
        """Explicit device request bypasses auto-detection."""
        from deep6.engines.kronos_worker import _select_device
        # When device is not "auto", it should return as-is
        result = _select_device("cpu")
        assert result == "cpu"


class TestKronosWorkerProcess:
    """Test KronosWorkerProcess lifecycle and pipe protocol."""

    def test_worker_ping(self):
        """Worker subprocess responds to ping without loading the model."""
        from deep6.engines.signal_config import KronosConfig
        from deep6.engines.kronos_worker import KronosWorkerProcess

        cfg = KronosConfig()
        worker = KronosWorkerProcess(cfg)
        worker.start()
        try:
            result = worker.ping()
            assert result is True
        finally:
            worker.stop()

    def test_worker_fallback_inference(self):
        """Worker falls back gracefully when Kronos model is not installed."""
        from deep6.engines.signal_config import KronosConfig
        from deep6.engines.kronos_worker import KronosWorkerProcess
        from deep6.engines.kronos_bias import KronosBias

        cfg = KronosConfig()
        worker = KronosWorkerProcess(cfg)
        worker.start()
        try:
            # 5 bars — will use fallback (fewer than 10 bars needed for momentum)
            ohlcv = [
                {"open": 17000 + i, "high": 17010 + i, "low": 16995 + i,
                 "close": 17005 + i, "volume": 1000.0}
                for i in range(5)
            ]
            bias = worker.request_inference(ohlcv, num_samples=5)
            assert isinstance(bias, KronosBias)
            assert bias.direction in {-1, 0, 1}
            # Fallback path — samples should be 0 (no real Kronos inference)
            assert bias.samples == 0
        finally:
            worker.stop()

    def test_worker_shutdown(self):
        """Worker subprocess terminates cleanly on stop()."""
        from deep6.engines.signal_config import KronosConfig
        from deep6.engines.kronos_worker import KronosWorkerProcess

        cfg = KronosConfig()
        worker = KronosWorkerProcess(cfg)
        worker.start()
        assert worker._process is not None
        assert worker._process.is_alive()
        worker.stop()
        assert worker._process.is_alive() is False
