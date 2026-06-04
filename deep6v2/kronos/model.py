"""Kronos-small model loading and tokenizer for E10 directional bias.

Kronos is a foundation model for financial K-lines (24.7M params).
All dependencies are optional — the system degrades gracefully when
PyTorch or the Kronos package is not installed.
"""

from __future__ import annotations

import logging
from typing import Any

from deep6v2.config.kronos import KronosConfig

logger = logging.getLogger(__name__)


class KronosModelManager:
    """Manages Kronos-small model lifecycle.

    Handles lazy loading from HuggingFace Hub (or local cache),
    device auto-detection (CUDA > MPS > CPU), and memory cleanup.
    """

    def __init__(self, config: KronosConfig | None = None) -> None:
        self._config = config or KronosConfig()
        self._model: Any = None
        self._tokenizer: Any = None
        self._device: str = "cpu"
        self._loaded: bool = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def device(self) -> str:
        return self._device

    @property
    def config(self) -> KronosConfig:
        return self._config

    def _detect_device(self) -> str:
        """Auto-detect best available device: CUDA > MPS > CPU."""
        if not self._config.use_gpu:
            return "cpu"
        try:
            import torch  # type: ignore[import-untyped]

            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            logger.debug("PyTorch not installed; falling back to CPU")
        return "cpu"

    def load(self) -> None:
        """Load model from HuggingFace Hub (or local cache).

        Raises:
            RuntimeError: If required dependencies (torch, huggingface_hub)
                are not installed.
        """
        if self._loaded:
            logger.warning("Model already loaded; call unload() first")
            return

        torch = _require_torch()

        self._device = self._detect_device()
        logger.info(
            "Loading Kronos model %s on %s",
            self._config.model_name,
            self._device,
        )

        # Attempt kronos-specific package first, then generic HF pattern.
        # Actual weight loading will be refined when Kronos package API is
        # confirmed — for now we verify the dependency chain is importable.
        try:
            from huggingface_hub import hf_hub_download  # type: ignore[import-untyped]  # noqa: F401
        except ImportError:
            raise RuntimeError(
                "huggingface_hub not installed. "
                "Install with: pip install huggingface_hub"
            )

        self._loaded = True
        logger.info("Kronos model marked as loaded (device=%s)", self._device)

    def predict(self, ohlcv_data: list[dict[str, float]]) -> dict[str, float]:
        """Run inference on OHLCV data.

        Args:
            ohlcv_data: List of bar dicts with keys
                ``open``, ``high``, ``low``, ``close``, and optionally
                ``volume``.  Most recent bar last.

        Returns:
            Predicted next-bar OHLCV as a dict.

        Raises:
            RuntimeError: If model has not been loaded via :meth:`load`.
            ValueError: If *ohlcv_data* is empty.
        """
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load() first.")
        if not ohlcv_data:
            raise ValueError("ohlcv_data must not be empty")

        # Placeholder — real inference wired in T29 pipeline task
        return {
            "open": 0.0,
            "high": 0.0,
            "low": 0.0,
            "close": 0.0,
            "volume": 0.0,
        }

    def unload(self) -> None:
        """Release model from memory."""
        self._model = None
        self._tokenizer = None
        self._loaded = False
        logger.info("Kronos model unloaded")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _require_torch() -> Any:
    """Import and return ``torch``, raising a clear error if absent."""
    try:
        import torch  # type: ignore[import-untyped]

        return torch
    except ImportError:
        raise RuntimeError(
            "PyTorch not installed. "
            "Install with: pip install torch"
        )


__all__ = ["KronosModelManager"]
