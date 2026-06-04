"""Kronos domain adapter — translates KronosBias into DomainScore -3..+3.

Maps Kronos direction (±1/0) and confidence (0-100) into the bias-v3
domain scoring system. Stateless: no model loading, no inference.

Translation table (configurable via KronosDomainConfig):
  confidence >= high_conf_threshold (70%)  → |score| = 3
  confidence >= 50%                        → |score| = 2
  confidence >= low_conf_threshold  (30%)  → |score| = 1
  confidence < low_conf_threshold          → |score| = 0  (ignore)

  score = direction * magnitude

Stale: inference older than STALE_SECONDS (300s) → stale=True.
Cold start (None input) → available=False, score=0.
"""
from __future__ import annotations

import time
from typing import Optional

from deep6.engines.bias_contracts import DomainScore
from deep6.engines.kronos_bias import KronosBias
from deep6.engines.signal_config import KronosDomainConfig


class KronosDomainAdapter:
    """Translates KronosBias output into a DomainScore in -3..+3."""

    MAX_RANGE = 3
    DOMAIN = "kronos"

    def __init__(self, config: Optional[KronosDomainConfig] = None) -> None:
        self._config = config or KronosDomainConfig()

    def compute(
        self,
        kronos_bias: Optional[KronosBias],
        inference_ts: Optional[float] = None,
    ) -> DomainScore:
        """Translate KronosBias into DomainScore.

        Args:
            kronos_bias: Output from Kronos engine, or None on cold start.
            inference_ts: Unix timestamp of the inference. If None, assumed
                fresh (time.time()). Used for stale detection.
        """
        now = time.time()

        if kronos_bias is None:
            return DomainScore(
                domain=self.DOMAIN,
                score=0,
                max_range=self.MAX_RANGE,
                available=False,
                stale=False,
                detail={"reason": "cold start"},
                updated_at=now,
            )

        stale = False
        if inference_ts is not None:
            stale = (now - inference_ts) > self._config.stale_threshold_sec

        magnitude = self._confidence_to_magnitude(kronos_bias.confidence)
        score = kronos_bias.direction * magnitude

        return DomainScore(
            domain=self.DOMAIN,
            score=score,
            max_range=self.MAX_RANGE,
            available=True,
            stale=stale,
            detail={
                "direction": kronos_bias.direction,
                "confidence": kronos_bias.confidence,
                "magnitude": magnitude,
                "predicted_close": kronos_bias.predicted_close,
                "current_close": kronos_bias.current_close,
                "samples": kronos_bias.samples,
                "bars_since_inference": kronos_bias.bars_since_inference,
            },
            updated_at=now,
        )

    def _confidence_to_magnitude(self, confidence: float) -> int:
        """Map confidence 0-100 to magnitude 0-3."""
        if confidence >= self._config.high_conf_threshold:
            return 3
        if confidence >= 50.0:
            return 2
        if confidence >= self._config.low_conf_threshold:
            return 1
        return 0
