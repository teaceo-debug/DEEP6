"""Magnet level scorer — wraps gexdoctor MagnetScorer for anti-flicker level selection."""
from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Import constants from gexdoctor when available, else use local defaults
try:
    from gexdoctor.monitor.magnet_scorer import (
        ANTI_FLICKER_MARGIN as _FLICKER_MARGIN,
        LEVEL_TYPE_WEIGHTS as _LEVEL_TYPE_WEIGHTS,
        MIN_CONFIDENCE as _MIN_CONFIDENCE,
    )
except Exception:
    _LEVEL_TYPE_WEIGHTS: dict[str, float] = {
        "pin_magnet_strike": 1.00,
        "gamma_flip": 0.90,
        "call_wall": 0.85,
        "put_wall": 0.85,
        "max_pain_expiry": 0.80,
        "max_pain": 0.40,
        "hvl": 0.70,
        "zero_dte_magnet": 0.95,
    }
    _FLICKER_MARGIN = 0.12
    _MIN_CONFIDENCE = 0.65

_STALE_SEC = 300


class GEXMagnetSelector:
    """Selects primary magnet with anti-flicker from GEX levels.

    Scoring mirrors gexdoctor.monitor.magnet_scorer.MagnetScorer logic:
        score = base_weight × distance_relevance × regime_alignment
    Anti-flicker: new candidate must exceed current by ANTI_FLICKER_MARGIN.
    Stale: force-switch after _STALE_SEC seconds without update.
    """

    def __init__(self) -> None:
        self._current_magnet: Optional[float] = None
        self._current_score: float = 0.0
        self._current_ts: float = 0.0

    def select(
        self,
        gamma_flip: Optional[float],
        call_wall: Optional[float],
        put_wall: Optional[float],
        hvl: Optional[float] = None,
        zero_dte_magnet: Optional[float] = None,
        regime: str = "neutral",
        spot_nq: Optional[float] = None,
    ) -> tuple[Optional[float], float]:
        """Return (magnet_price, confidence).

        Anti-flicker: new candidate must exceed current score by _FLICKER_MARGIN.
        """
        candidates: list[tuple[str, float, float]] = []

        if gamma_flip is not None and gamma_flip > 0:
            candidates.append(("gamma_flip", gamma_flip, _LEVEL_TYPE_WEIGHTS.get("gamma_flip", 0.90)))
        if call_wall is not None and call_wall > 0:
            candidates.append(("call_wall", call_wall, _LEVEL_TYPE_WEIGHTS.get("call_wall", 0.85)))
        if put_wall is not None and put_wall > 0:
            candidates.append(("put_wall", put_wall, _LEVEL_TYPE_WEIGHTS.get("put_wall", 0.85)))
        if hvl is not None and hvl > 0:
            candidates.append(("hvl", hvl, _LEVEL_TYPE_WEIGHTS.get("hvl", 0.70)))
        if zero_dte_magnet is not None and zero_dte_magnet > 0:
            candidates.append(("zero_dte_magnet", zero_dte_magnet, _LEVEL_TYPE_WEIGHTS.get("zero_dte_magnet", 0.95)))

        if not candidates:
            return None, 0.0

        # Score each candidate: base_weight × distance_relevance × regime_alignment
        scored: list[tuple[float, float, str]] = []
        for name, price, base_weight in candidates:
            dist_score = 1.0
            if spot_nq is not None and spot_nq > 0:
                dist = abs(price - spot_nq)
                if dist < 1:
                    dist_score = 1.0
                elif dist > 500:
                    dist_score = 0.1
                else:
                    dist_score = max(0.1, 1.0 - dist / 500.0)

            regime_score = self._regime_alignment(name, price, regime, spot_nq)
            score = round(min(base_weight * dist_score * regime_score, 1.0), 4)
            scored.append((score, price, name))

        scored.sort(reverse=True)
        best_score, best_price, best_name = scored[0]

        if best_score < _MIN_CONFIDENCE:
            logger.debug("magnet: best %s=%.2f score=%.4f below min_confidence=%.2f", best_name, best_price, best_score, _MIN_CONFIDENCE)
            return None, 0.0

        result_price, result_score = self._apply_antiflicker(best_price, best_score)
        logger.debug("magnet: selected %.2f (type=%s score=%.4f)", result_price, best_name, result_score)
        return result_price, result_score

    @staticmethod
    def _regime_alignment(
        level_type: str,
        price: float,
        regime: str,
        spot_nq: Optional[float],
    ) -> float:
        """Regime-sensitive scoring — mirrors gexdoctor logic."""
        if regime == "positive":
            if level_type == "call_wall" and spot_nq and price > spot_nq:
                return 1.0
            if level_type == "put_wall" and spot_nq and price < spot_nq:
                return 1.0
            if level_type == "gamma_flip":
                return 0.9
        elif regime == "negative":
            if level_type in ("call_wall", "put_wall"):
                return 0.7
            if level_type == "gamma_flip":
                return 1.0
        return 1.0

    def _apply_antiflicker(self, new_price: float, new_score: float) -> tuple[float, float]:
        """Anti-flicker gate: only switch magnet if new candidate significantly better or current stale."""
        now = time.time()
        stale = (now - self._current_ts) > _STALE_SEC

        if self._current_magnet is None or stale:
            self._current_magnet = new_price
            self._current_score = new_score
            self._current_ts = now
            return new_price, new_score

        if new_score > self._current_score + _FLICKER_MARGIN:
            self._current_magnet = new_price
            self._current_score = new_score
            self._current_ts = now

        return self._current_magnet, self._current_score


__all__ = ["GEXMagnetSelector"]
