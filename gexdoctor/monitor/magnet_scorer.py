from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from .schemas import FARegime, FlashAlphaSnapshot, MagnetCandidate, MagnetResult

log = logging.getLogger(__name__)
__all__ = ["MagnetScorer", "MagnetState", "LEVEL_TYPE_WEIGHTS", "MIN_CONFIDENCE", "ANTI_FLICKER_MARGIN"]

# Level type weights — from plan spec
LEVEL_TYPE_WEIGHTS: dict[str, float] = {
    "pin_magnet_strike": 1.00,   # FlashAlpha direct magnet when pin_risk > 65
    "gamma_flip":        0.90,
    "call_wall":         0.85,
    "put_wall":          0.85,
    "max_pain_expiry":   0.80,   # max_pain when 0DTE (dte <= 1)
    "max_pain":          0.40,   # max_pain otherwise
}

MIN_CONFIDENCE = 0.65
ANTI_FLICKER_MARGIN = 0.12


@dataclass
class MagnetState:
    """Persisted anti-flicker state."""

    current_magnet: MagnetResult | None = None
    current_score: float = 0.0
    locked_at: float = field(default_factory=time.monotonic)
    stale_threshold_sec: int = 300


class MagnetScorer:
    """Scores FlashAlpha levels as magnet candidates and selects primary magnet.

    Scoring formula:
        score = level_type_weight × distance_relevance × regime_alignment
                × flow_mult × pin_boost × confidence_modifier

    Anti-flicker: new candidate must exceed current by ANTI_FLICKER_MARGIN (0.12)
    or current must be stale/invalidated.
    """

    def __init__(
        self,
        min_confidence: float = MIN_CONFIDENCE,
        anti_flicker_margin: float = ANTI_FLICKER_MARGIN,
    ) -> None:
        self.min_confidence = min_confidence
        self.anti_flicker_margin = anti_flicker_margin
        self._state = MagnetState()

    def score(
        self,
        snapshot: FlashAlphaSnapshot,
        current_nq: float,
        force_refresh: bool = False,
    ) -> MagnetResult:
        """Select primary magnet from snapshot levels.

        Returns MagnetResult with status:
        - "valid": magnet selected with confidence >= min_confidence
        - "no_magnet": no candidate meets threshold
        """
        candidates = self._extract_candidates(snapshot, current_nq)

        if not candidates:
            return MagnetResult(
                primary_magnet=None,
                magnet_confidence=0.0,
                invalidation_level=None,
                invalidation_reason="no levels available",
                supporting_levels=[],
                status="no_magnet",
            )

        # Sort by score descending, pick best
        candidates.sort(key=lambda c: c.score, reverse=True)
        best = candidates[0]

        if best.confidence < self.min_confidence:
            return MagnetResult(
                primary_magnet=None,
                magnet_confidence=best.confidence,
                invalidation_level=None,
                invalidation_reason=f"best score {best.score:.3f} below threshold {self.min_confidence}",
                supporting_levels=candidates,
                status="no_magnet",
            )

        # Anti-flicker check
        if not force_refresh and self._state.current_magnet is not None:
            current_score = self._state.current_score
            if not self._should_replace(best.score, current_score, snapshot):
                log.debug(
                    "anti-flicker: keeping current magnet %.2f (margin %.3f < %.3f)",
                    self._state.current_magnet.primary_magnet or 0.0,
                    best.score - current_score,
                    self.anti_flicker_margin,
                )
                return self._state.current_magnet

        # Select new magnet
        invalidation_level, invalidation_reason = self._compute_invalidation(
            best, snapshot
        )

        result = MagnetResult(
            primary_magnet=best.level,
            magnet_confidence=best.confidence,
            invalidation_level=invalidation_level,
            invalidation_reason=invalidation_reason,
            supporting_levels=candidates[:5],  # top 5 for context
            status="valid",
        )
        self._state.current_magnet = result
        self._state.current_score = best.score
        self._state.locked_at = time.monotonic()

        log.info(
            "magnet selected: %.2f (type=%s score=%.3f confidence=%.3f)",
            best.level,
            best.level_type,
            best.score,
            best.confidence,
        )
        return result

    def _should_replace(
        self, new_score: float, current_score: float, snapshot: FlashAlphaSnapshot
    ) -> bool:
        """Return True if current magnet should be replaced by new candidate."""
        # Replace if new score is significantly better
        if new_score >= current_score + self.anti_flicker_margin:
            return True
        # Replace if current magnet is stale (feed quality degraded)
        if (
            snapshot.feed_quality.missing_fields
            and len(snapshot.feed_quality.missing_fields) > 3
        ):
            return True
        # Replace if current magnet tenure exceeds threshold
        tenure = time.monotonic() - self._state.locked_at
        if tenure > self._state.stale_threshold_sec:
            return True
        return False

    def _extract_candidates(
        self, snapshot: FlashAlphaSnapshot, current_nq: float
    ) -> list[MagnetCandidate]:
        """Extract magnet candidates from snapshot levels."""
        regime = snapshot.regime
        pin = snapshot.pin
        oi_conf = snapshot.oi_simulator.oi_delta_confidence or 1.0
        is_0dte = snapshot.dte is not None and snapshot.dte <= 1

        candidates: list[MagnetCandidate] = []

        def add(level: float | None, level_type: str) -> None:
            if level is None or level <= 0:
                return
            score = self._score_level(
                level=level,
                level_type=level_type,
                current_nq=current_nq,
                regime_sign=regime.gex_sign,
                flow_direction=snapshot.dealer_risk.flow_direction,
                pin_risk=pin.pin_risk or 0.0,
                oi_confidence=oi_conf,
                is_0dte=is_0dte,
            )
            confidence = min(score, 1.0)
            invalidation, inv_reason = self._compute_invalidation_for_type(
                level, level_type, regime
            )
            candidates.append(
                MagnetCandidate(
                    level=level,
                    level_type=level_type,
                    score=score,
                    confidence=confidence,
                    invalidation_level=invalidation,
                    invalidation_reason=inv_reason,
                )
            )

        # Pin magnet — highest priority when pin_risk > 65
        if (pin.pin_risk or 0) > 65 and pin.magnet_strike:
            add(pin.magnet_strike, "pin_magnet_strike")

        # Core levels
        add(regime.gamma_flip, "gamma_flip")
        add(regime.call_wall, "call_wall")
        add(regime.put_wall, "put_wall")

        # Max pain — higher weight near expiry
        if regime.max_pain:
            add(regime.max_pain, "max_pain_expiry" if is_0dte else "max_pain")

        return candidates

    def _score_level(
        self,
        level: float,
        level_type: str,
        current_nq: float,
        regime_sign: str,
        flow_direction: str,
        pin_risk: float,
        oi_confidence: float,
        is_0dte: bool,
    ) -> float:
        """Compute composite score for a candidate level."""
        base = LEVEL_TYPE_WEIGHTS.get(level_type, 0.5)

        # Distance relevance: levels within 200pts score higher (inverse distance)
        dist = abs(level - current_nq)
        if dist < 1:
            dist_score = 1.0
        elif dist > 500:
            dist_score = 0.1
        else:
            dist_score = max(0.1, 1.0 - dist / 500.0)

        # Regime alignment: call_wall bullish in positive GEX, put_wall bullish in negative
        regime_score = 1.0
        if regime_sign == "positive":
            if level_type == "call_wall" and level > current_nq:
                regime_score = 1.0  # call wall is cap in long gamma
            elif level_type == "put_wall" and level < current_nq:
                regime_score = 1.0  # put wall is floor in long gamma
            elif level_type == "gamma_flip":
                regime_score = 0.9
        else:  # negative GEX
            if level_type in ("call_wall", "put_wall"):
                regime_score = 0.7  # walls less reliable in short gamma
            elif level_type == "gamma_flip":
                regime_score = 1.0  # flip is THE level in negative gamma

        # Flow amplifies conviction
        flow_mult = (
            1.1
            if flow_direction == "amplifying"
            else (0.9 if flow_direction == "dampening" else 1.0)
        )

        # Pin boost
        pin_boost = (
            1.2 if (level_type == "pin_magnet_strike" and pin_risk > 65) else 1.0
        )

        # OI confidence modifier (low confidence = less trustworthy)
        conf_mod = max(0.5, oi_confidence)

        score = base * dist_score * regime_score * flow_mult * pin_boost * conf_mod
        return round(min(score, 1.0), 4)

    def _compute_invalidation(
        self, candidate: MagnetCandidate, snapshot: FlashAlphaSnapshot
    ) -> tuple[float | None, str]:
        return self._compute_invalidation_for_type(
            candidate.level, candidate.level_type, snapshot.regime
        )

    def _compute_invalidation_for_type(
        self, level: float, level_type: str, regime: FARegime
    ) -> tuple[float | None, str]:
        """Compute invalidation level for a given magnet type."""
        flip = regime.gamma_flip

        if level_type == "gamma_flip":
            # Invalidated if price breaks gamma flip and accepts on opposite side
            inv = level + 10 if regime.gex_sign == "positive" else level - 10
            return inv, "Break and acceptance beyond gamma flip level"

        if level_type == "call_wall":
            # Invalidated by sustained break above call wall
            inv = level + 15
            return inv, "Sustained acceptance above call wall; wall loses cap function"

        if level_type == "put_wall":
            # Invalidated by sustained break below put wall
            inv = level - 15
            return inv, "Sustained break below put wall; floor loses support function"

        if level_type in ("max_pain", "max_pain_expiry"):
            # Invalidated by regime flip
            return flip, "Regime flip invalidates max-pain pin magnetism"

        if level_type == "pin_magnet_strike":
            return flip, "Regime flip or catalyst break invalidates pin magnet"

        return None, "No invalidation defined"
