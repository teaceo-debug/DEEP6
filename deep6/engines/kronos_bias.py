"""E10: Kronos foundation model bias engine.

Kronos is a decoder-only foundation model trained on K-line (OHLCV) data
from 45+ global exchanges. It predicts future candlesticks and provides
directional bias via stochastic ensemble sampling.

Per KRON-01..06:
  - Kronos-small (24.7M params) loaded from HuggingFace
  - 20 stochastic samples for confidence scoring
  - Re-inference every 5 bars with 0.95/bar decay between inferences
  - CPU or GPU inference (GPU preferred)

Integration: E10 contributes a directional bias score to the confluence scorer.

Production use: KronosSubprocessBridge (subprocess-isolated, async-safe).
Legacy use:     KronosEngine (synchronous, blocks event loop — for unit tests only).
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from deep6.engines.signal_config import KronosConfig
from deep6.engines.kronos_worker import KronosWorkerProcess


@dataclass
class KronosBias:
    """Output from Kronos directional prediction."""
    direction: int          # +1 bull, -1 bear, 0 neutral
    confidence: float       # 0-100
    predicted_close: float  # mean predicted close price
    current_close: float    # current close for delta
    samples: int            # number of stochastic samples
    inference_time_ms: float
    bars_since_inference: int
    detail: str


class KronosEngine:
    """E10: Kronos bias engine with lazy model loading and inference caching.

    Deprecated: Use KronosSubprocessBridge for production. Kept for unit testing
    without subprocess overhead.

    The model is loaded on first use and kept in memory permanently.
    Inference runs every `inference_interval` bars; between inferences,
    confidence decays by `decay_factor` per bar.
    """

    def __init__(
        self,
        model_name: str = "NeoQuasar/Kronos-small",
        tokenizer_name: str = "NeoQuasar/Kronos-Tokenizer-base",
        inference_interval: int = 5,
        num_samples: int = 20,
        lookback: int = 100,
        pred_len: int = 5,
        decay_factor: float = 0.95,
        device: str = "cpu",
    ):
        self.model_name = model_name
        self.tokenizer_name = tokenizer_name
        self.inference_interval = inference_interval
        self.num_samples = num_samples
        self.lookback = lookback
        self.pred_len = pred_len
        self.decay_factor = decay_factor
        self.device = device

        self._model = None
        self._tokenizer = None
        self._predictor = None
        self._loaded = False

        # Cached state
        self._last_bias: Optional[KronosBias] = None
        self._bars_since: int = 0
        self._ohlcv_buffer: list[dict] = []

    def _ensure_loaded(self) -> bool:
        """Lazy-load model on first inference. Returns True if loaded."""
        if self._loaded:
            return True

        try:
            # Import Kronos — requires cloned repo on PYTHONPATH or installed
            from model import Kronos, KronosTokenizer, KronosPredictor

            self._tokenizer = KronosTokenizer.from_pretrained(self.tokenizer_name)
            self._model = Kronos.from_pretrained(self.model_name)
            if self.device != "cpu":
                self._model = self._model.to(self.device)
            self._predictor = KronosPredictor(
                self._model, self._tokenizer, max_context=512
            )
            self._loaded = True
            return True
        except ImportError:
            # Kronos not installed — return gracefully
            return False
        except Exception:
            return False

    def add_bar(self, open_: float, high: float, low: float, close: float, volume: float) -> None:
        """Buffer OHLCV data for Kronos inference."""
        self._ohlcv_buffer.append({
            "open": open_, "high": high, "low": low,
            "close": close, "volume": volume,
        })
        # Keep buffer at lookback size
        if len(self._ohlcv_buffer) > self.lookback:
            self._ohlcv_buffer = self._ohlcv_buffer[-self.lookback:]

    def process(self) -> KronosBias:
        """Get current Kronos bias — infer or return decayed cache."""
        self._bars_since += 1

        # Not enough data yet
        if len(self._ohlcv_buffer) < 20:
            return KronosBias(
                direction=0, confidence=0, predicted_close=0,
                current_close=self._ohlcv_buffer[-1]["close"] if self._ohlcv_buffer else 0,
                samples=0, inference_time_ms=0, bars_since_inference=self._bars_since,
                detail="KRONOS: insufficient data (need 20+ bars)",
            )

        # Check if we should re-infer
        if self._bars_since >= self.inference_interval or self._last_bias is None:
            bias = self._run_inference()
            if bias is not None:
                self._last_bias = bias
                self._bars_since = 0
                return bias

        # Return decayed cache
        if self._last_bias is not None:
            decayed_conf = self._last_bias.confidence * (self.decay_factor ** self._bars_since)
            return KronosBias(
                direction=self._last_bias.direction,
                confidence=decayed_conf,
                predicted_close=self._last_bias.predicted_close,
                current_close=self._ohlcv_buffer[-1]["close"],
                samples=self._last_bias.samples,
                inference_time_ms=self._last_bias.inference_time_ms,
                bars_since_inference=self._bars_since,
                detail=f"KRONOS: cached bias (decayed {decayed_conf:.0f}%, "
                       f"{self._bars_since} bars ago)",
            )

        return KronosBias(
            direction=0, confidence=0, predicted_close=0,
            current_close=self._ohlcv_buffer[-1]["close"] if self._ohlcv_buffer else 0,
            samples=0, inference_time_ms=0, bars_since_inference=self._bars_since,
            detail="KRONOS: no model loaded",
        )

    def _run_inference(self) -> Optional[KronosBias]:
        """Run Kronos inference with stochastic sampling."""
        if not self._ensure_loaded():
            # Fallback: simple momentum bias without Kronos
            return self._fallback_bias()

        try:
            df = pd.DataFrame(self._ohlcv_buffer[-self.lookback:])
            current_close = df.iloc[-1]["close"]

            t0 = time.perf_counter()

            # Generate stochastic samples
            predictions = []
            for _ in range(self.num_samples):
                pred = self._predictor.predict(
                    df=df[["open", "high", "low", "close", "volume"]],
                    x_timestamp=pd.Series(range(len(df))),
                    y_timestamp=pd.Series(range(len(df), len(df) + self.pred_len)),
                    T=1.0, top_p=0.9,
                )
                if pred is not None and len(pred) > 0:
                    predictions.append(pred.iloc[-1]["close"])

            elapsed_ms = (time.perf_counter() - t0) * 1000

            if not predictions:
                return self._fallback_bias()

            mean_close = np.mean(predictions)
            std_close = np.std(predictions)
            delta = mean_close - current_close

            # Direction from mean prediction
            direction = +1 if delta > 0 else -1 if delta < 0 else 0

            # Confidence: inverse of uncertainty relative to delta
            if abs(delta) > 0:
                uncertainty = std_close / abs(delta)
                confidence = max(0, min(100, (1.0 - uncertainty) * 100))
            else:
                confidence = 0

            return KronosBias(
                direction=direction,
                confidence=confidence,
                predicted_close=mean_close,
                current_close=current_close,
                samples=len(predictions),
                inference_time_ms=elapsed_ms,
                bars_since_inference=0,
                detail=f"KRONOS: {'BULL' if direction > 0 else 'BEAR'} bias "
                       f"conf={confidence:.0f}% pred={mean_close:.2f} "
                       f"({elapsed_ms:.0f}ms, {len(predictions)} samples)",
            )
        except Exception:
            return self._fallback_bias()

    def _fallback_bias(self) -> KronosBias:
        """Simple momentum fallback when Kronos isn't available."""
        if len(self._ohlcv_buffer) < 10:
            return KronosBias(0, 0, 0, 0, 0, 0, 0, "KRONOS: fallback — no data")

        closes = [b["close"] for b in self._ohlcv_buffer[-10:]]
        slope = np.polyfit(range(len(closes)), closes, 1)[0]
        current = closes[-1]
        direction = +1 if slope > 0 else -1 if slope < 0 else 0
        confidence = min(abs(slope) / 2.0 * 100, 50)  # Cap at 50 for fallback

        return KronosBias(
            direction=direction,
            confidence=confidence,
            predicted_close=current + slope * 5,
            current_close=current,
            samples=0,
            inference_time_ms=0,
            bars_since_inference=0,
            detail=f"KRONOS FALLBACK: momentum {'BULL' if direction > 0 else 'BEAR'} "
                   f"slope={slope:.2f} conf={confidence:.0f}%",
        )


class KronosSubprocessBridge:
    """E10 production bridge: delegates inference to KronosWorkerProcess.

    Manages the 5-bar re-inference cadence and per-bar confidence decay.
    All inference is non-blocking — get_bias() uses run_in_executor.

    Per KRON-01..06, D-01..D-04.
    """

    def __init__(self, cfg: KronosConfig) -> None:
        self.cfg = cfg
        self._worker = KronosWorkerProcess(cfg)
        self._ohlcv_buffer: list[dict] = []
        self._last_bias: Optional[KronosBias] = None
        self._bars_since: int = 0

    def start(self) -> None:
        """Start the worker subprocess. Call once before any add_bar()."""
        self._worker.start()

    def stop(self) -> None:
        """Cleanly shut down the worker subprocess."""
        self._worker.stop()

    def add_bar(self, open_: float, high: float, low: float, close: float, volume: float) -> None:
        """Buffer one OHLCV bar. Call on every bar close before get_bias()."""
        self._ohlcv_buffer.append({
            "open": open_, "high": high, "low": low,
            "close": close, "volume": volume,
        })
        if len(self._ohlcv_buffer) > self.cfg.lookback:
            self._ohlcv_buffer = self._ohlcv_buffer[-self.cfg.lookback:]
        self._bars_since += 1

    async def get_bias(self) -> KronosBias:
        """Get current E10 bias. Non-blocking — safe to await in event loop.

        Returns fresh inference every cfg.inference_interval bars;
        returns decayed cached result between inferences.
        """
        current_close = self._ohlcv_buffer[-1]["close"] if self._ohlcv_buffer else 0.0

        if len(self._ohlcv_buffer) < 20:
            return KronosBias(
                direction=0, confidence=0, predicted_close=0,
                current_close=current_close, samples=0,
                inference_time_ms=0, bars_since_inference=self._bars_since,
                detail="KRONOS: insufficient data (need 20+ bars)",
            )

        should_infer = (
            self._last_bias is None
            or self._bars_since >= self.cfg.inference_interval
        )

        if should_infer:
            loop = asyncio.get_event_loop()
            bias = await loop.run_in_executor(
                None,
                self._worker.request_inference,
                list(self._ohlcv_buffer),
                self.cfg.num_samples,
            )
            self._last_bias = bias
            self._bars_since = 0
            return bias

        # Decay cached result
        decayed = self._last_bias.confidence * (self.cfg.decay_factor ** self._bars_since)
        return KronosBias(
            direction=self._last_bias.direction,
            confidence=decayed,
            predicted_close=self._last_bias.predicted_close,
            current_close=current_close,
            samples=self._last_bias.samples,
            inference_time_ms=self._last_bias.inference_time_ms,
            bars_since_inference=self._bars_since,
            detail=f"KRONOS: cached (decayed {decayed:.0f}%, {self._bars_since} bars ago)",
        )
