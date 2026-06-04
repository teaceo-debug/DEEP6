"""Tests for Kronos model manager."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from deep6v2.config.kronos import KronosConfig
from deep6v2.kronos.model import KronosModelManager

# ---------------------------------------------------------------------------
# Torch availability flag
# ---------------------------------------------------------------------------
try:
    import torch  # noqa: F401

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

needs_torch = pytest.mark.skipif(not HAS_TORCH, reason="torch not installed")


# ── Construction & defaults ───────────────────────────────────────────────

class TestConstruction:
    def test_defaults(self) -> None:
        mgr = KronosModelManager()
        assert mgr.device == "cpu"
        assert mgr.is_loaded is False

    def test_custom_config(self) -> None:
        cfg = KronosConfig(model_name="custom/model", context_length=256)
        mgr = KronosModelManager(config=cfg)
        assert mgr.config.model_name == "custom/model"
        assert mgr.config.context_length == 256

    def test_default_config_created_when_none(self) -> None:
        mgr = KronosModelManager(config=None)
        assert mgr.config.model_name == "NeoQuasar/Kronos-small"


# ── Device detection ──────────────────────────────────────────────────────

class TestDeviceDetection:
    def test_defaults_to_cpu(self) -> None:
        mgr = KronosModelManager()
        assert mgr._detect_device() == "cpu"

    def test_cpu_when_use_gpu_false(self) -> None:
        cfg = KronosConfig(use_gpu=False)
        mgr = KronosModelManager(config=cfg)
        assert mgr._detect_device() == "cpu"

    @needs_torch
    def test_cuda_when_available(self) -> None:
        cfg = KronosConfig(use_gpu=True)
        mgr = KronosModelManager(config=cfg)
        with patch("torch.cuda.is_available", return_value=True):
            assert mgr._detect_device() == "cuda"

    @needs_torch
    def test_mps_when_cuda_unavailable(self) -> None:
        cfg = KronosConfig(use_gpu=True)
        mgr = KronosModelManager(config=cfg)
        mock_mps = MagicMock()
        mock_mps.is_available.return_value = True
        with (
            patch("torch.cuda.is_available", return_value=False),
            patch("torch.backends.mps", mock_mps, create=True),
        ):
            assert mgr._detect_device() == "mps"

    @needs_torch
    def test_cpu_fallback_when_no_gpu(self) -> None:
        cfg = KronosConfig(use_gpu=True)
        mgr = KronosModelManager(config=cfg)
        mock_mps = MagicMock()
        mock_mps.is_available.return_value = False
        with (
            patch("torch.cuda.is_available", return_value=False),
            patch("torch.backends.mps", mock_mps, create=True),
        ):
            assert mgr._detect_device() == "cpu"

    def test_cpu_when_torch_missing(self) -> None:
        """Even with use_gpu=True, returns cpu if torch can't be imported."""
        cfg = KronosConfig(use_gpu=True)
        mgr = KronosModelManager(config=cfg)
        with patch.dict("sys.modules", {"torch": None}):
            assert mgr._detect_device() == "cpu"


# ── Predict before load ──────────────────────────────────────────────────

class TestPredictBeforeLoad:
    def test_raises_runtime_error(self) -> None:
        mgr = KronosModelManager()
        with pytest.raises(RuntimeError, match="not loaded"):
            mgr.predict([{"open": 1, "high": 2, "low": 0.5, "close": 1.5}])

    def test_empty_data_raises_after_load(self) -> None:
        mgr = KronosModelManager()
        mgr._loaded = True  # simulate loaded state
        with pytest.raises(ValueError, match="must not be empty"):
            mgr.predict([])


# ── Unload ────────────────────────────────────────────────────────────────

class TestUnload:
    def test_clears_state(self) -> None:
        mgr = KronosModelManager()
        mgr._loaded = True
        mgr._model = "fake-model"
        mgr._tokenizer = "fake-tokenizer"
        mgr.unload()
        assert mgr.is_loaded is False
        assert mgr._model is None
        assert mgr._tokenizer is None

    def test_unload_idempotent(self) -> None:
        mgr = KronosModelManager()
        mgr.unload()  # already unloaded
        assert mgr.is_loaded is False


# ── Load ──────────────────────────────────────────────────────────────────

class TestLoad:
    def test_raises_when_torch_missing(self) -> None:
        """If torch is genuinely absent, load() should raise RuntimeError."""
        if HAS_TORCH:
            pytest.skip("torch is installed; cannot test missing-torch path")
        mgr = KronosModelManager()
        with pytest.raises(RuntimeError, match="PyTorch not installed"):
            mgr.load()

    @needs_torch
    def test_raises_when_huggingface_hub_missing(self) -> None:
        mgr = KronosModelManager()
        with patch.dict("sys.modules", {"huggingface_hub": None}):
            with pytest.raises(RuntimeError, match="huggingface_hub not installed"):
                mgr.load()

    @needs_torch
    def test_load_succeeds_with_deps(self) -> None:
        """Load succeeds when both torch and huggingface_hub are available."""
        mgr = KronosModelManager()
        mock_hf = MagicMock()
        with patch.dict("sys.modules", {"huggingface_hub": mock_hf}):
            mgr.load()
        assert mgr.is_loaded is True

    @needs_torch
    def test_double_load_is_noop(self) -> None:
        mgr = KronosModelManager()
        mock_hf = MagicMock()
        with patch.dict("sys.modules", {"huggingface_hub": mock_hf}):
            mgr.load()
            mgr.load()  # should warn but not crash
        assert mgr.is_loaded is True


# ── Predict (placeholder) ────────────────────────────────────────────────

class TestPredict:
    def test_returns_ohlcv_dict(self) -> None:
        mgr = KronosModelManager()
        mgr._loaded = True
        result = mgr.predict([{"open": 1, "high": 2, "low": 0.5, "close": 1.5}])
        assert set(result.keys()) == {"open", "high", "low", "close", "volume"}

    def test_all_values_are_float(self) -> None:
        mgr = KronosModelManager()
        mgr._loaded = True
        result = mgr.predict([{"open": 1, "high": 2, "low": 0.5, "close": 1.5}])
        for v in result.values():
            assert isinstance(v, float)
