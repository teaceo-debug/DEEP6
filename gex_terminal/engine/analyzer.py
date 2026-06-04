"""GEX Terminal analysis engine — synthesizes adapter outputs into BiasVerdict."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from gex_terminal.engine.adapters.flashalpha import FlashAlphaResult
from gex_terminal.engine.adapters.massive import MassiveResult
from gex_terminal.engine.conviction import ConvictionScorer
from gex_terminal.schemas import (
    BiasVerdict,
    DealerPositioning,
    FlowSummary,
    GEXLevels,
    SourceHealth,
    VannaCharmState,
    ZeroDTEState,
)

logger = logging.getLogger(__name__)

DEFAULT_NQ_QQQ_RATIO = 41.16  # NQ ~30500 / QQQ ~741 (June 2026)
_DEFAULT_BASE_CONFIDENCE = {"positive": 80.0, "negative": 80.0, "neutral": 45.0}
_DEFAULT_REGIME_NAMES = {
    "positive": "Positive Gamma",
    "negative": "Negative Gamma",
    "neutral": "Neutral / Transition",
}
_EASTERN_TZ = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class AnalyzerWeights:
    """Relative weights for agreement inputs."""

    flip: float = 0.5
    call_wall: float = 0.25
    put_wall: float = 0.25


@dataclass(frozen=True)
class AnalysisResult:
    """Complete analysis output from all adapter data."""

    bias: BiasVerdict
    levels: GEXLevels
    dealer: DealerPositioning
    flow: FlowSummary
    vanna_charm: VannaCharmState
    zero_dte: ZeroDTEState
    material_change: bool
    nq_qqq_ratio: float
    vix: Optional[float] = None
    conviction_grade: str = "C"
    conviction_rivers: int = 0
    po3_state: str = "UNKNOWN"


_NQ_LEVELS_CACHE_PATH = Path.home() / ".deep6" / "nq_levels_cache.json"


class GEXAnalyzer:
    """Synthesizes FlashAlpha + Massive data into a unified directional verdict."""

    def __init__(
        self,
        nq_qqq_ratio: float = DEFAULT_NQ_QQQ_RATIO,
        weights: AnalyzerWeights | None = None,
    ) -> None:
        self._nq_qqq_ratio = nq_qqq_ratio
        self._weights = weights or AnalyzerWeights()
        self._conviction = ConvictionScorer()
        self._last_regime: Optional[str] = None
        self._last_flip: Optional[float] = None
        self._last_levels: Optional[GEXLevels] = self._load_nq_levels_cache()
        self._last_spot_nq: Optional[float] = None

    @staticmethod
    def _load_nq_levels_cache() -> Optional[GEXLevels]:
        """Load last known good NQ-space levels from disk (survives restarts)."""
        try:
            if _NQ_LEVELS_CACHE_PATH.exists():
                data = json.loads(_NQ_LEVELS_CACHE_PATH.read_text(encoding="utf-8-sig"))
                age_hours = (time.time() - data.get("cached_at", 0)) / 3600
                if age_hours > 24:
                    return None
                levels = GEXLevels(
                    gamma_flip=data.get("gamma_flip"),
                    call_wall=data.get("call_wall"),
                    put_wall=data.get("put_wall"),
                    hvl=data.get("hvl"),
                    zero_dte_magnet=data.get("zero_dte_magnet"),
                )
                logger.info("Analyzer: loaded cached NQ levels (%.1fh old): flip=%s cw=%s pw=%s",
                            age_hours, levels.gamma_flip, levels.call_wall, levels.put_wall)
                return levels
        except Exception as exc:
            logger.debug("Analyzer: NQ level cache load failed: %s", exc)
        return None

    def _save_nq_levels_cache(self, levels: GEXLevels) -> None:
        """Persist good NQ levels to disk."""
        try:
            _NQ_LEVELS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _NQ_LEVELS_CACHE_PATH.write_text(json.dumps({
                "gamma_flip": levels.gamma_flip,
                "call_wall": levels.call_wall,
                "put_wall": levels.put_wall,
                "hvl": levels.hvl,
                "zero_dte_magnet": levels.zero_dte_magnet,
                "cached_at": time.time(),
            }, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.debug("Analyzer: NQ level cache save failed: %s", exc)

    @staticmethod
    def _has_real_nq_levels(levels: GEXLevels) -> bool:
        """True if at least gamma_flip or one wall is a realistic NQ price."""
        for val in (levels.gamma_flip, levels.call_wall, levels.put_wall):
            if val is not None and 10_000 < val < 50_000:
                return True
        return False

    @staticmethod
    def _levels_are_fresh(levels: GEXLevels, spot_nq: Optional[float]) -> bool:
        """True if levels are plausibly near current NQ spot (not stale QQQ conversions).

        If no spot available, assume fresh to avoid blocking valid data.
        """
        if spot_nq is None or spot_nq <= 0:
            return True  # can't verify — accept them
        ref = levels.gamma_flip or levels.call_wall or levels.put_wall
        if ref is None:
            return False
        # Levels should be within 15% of current NQ spot
        return abs(ref - spot_nq) / spot_nq < 0.15

    def analyze(
        self,
        fa_result: FlashAlphaResult,
        massive_result: MassiveResult,
        *,
        vix: Optional[float] = None,
        nq_spot: Optional[float] = None,
        qqq_spot: Optional[float] = None,
        flow_z_score: float = 0.0,
        flow_direction_raw: str = "neutral",
        vanna_charm_net: str = "neutral",
        hmm_state: str = "UNKNOWN",
        dark_pool_direction: str = "neutral",
        dp_levels_nq: Optional[list[float]] = None,
        po3_direction: str = "UNKNOWN",
    ) -> AnalysisResult:
        """Synthesize adapter outputs into a regime-aware analysis result."""
        if nq_spot is None:
            nq_spot = self._extract_nq_spot(fa_result)
        if qqq_spot is None:
            qqq_spot = self._extract_qqq_spot(massive_result)
        self.update_ratio(nq_spot, qqq_spot)

        regime = self._resolve_regime(fa_result, massive_result)
        source_agreement = self._compute_source_agreement(
            fa_result.levels,
            massive_result.levels,
        )
        health_multiplier = self._compute_health_multiplier(
            fa_result.source_health,
            massive_result.source_health,
        )
        freshness_multiplier = self._compute_freshness_multiplier(
            fa_result.source_health,
            massive_result.source_health,
        )
        confidence = self._compute_confidence(
            regime=regime,
            source_agreement=source_agreement,
            health_multiplier=health_multiplier,
            freshness_multiplier=freshness_multiplier,
        )

        flow_result = massive_result.flow_result
        has_real_flow = False
        if flow_result is not None:
            has_real_flow = True
            flow_z_score = float(flow_result.z_score)
            flow_direction_raw = self._flow_direction_label(flow_result.net_direction)
            flow_intensity = self._flow_intensity(flow_result)
        else:
            has_real_flow = flow_direction_raw != "neutral" or abs(flow_z_score) > 0.0
            flow_intensity = self._flow_intensity_from_zscore(flow_z_score, flow_direction_raw)

        confidence = self._apply_vix_modifier(confidence, vix)
        confidence = self._apply_vanna_charm_modifier(
            confidence,
            fa_result.dealer.net_vex,
            fa_result.dealer.net_chex,
        )
        confidence = self._apply_zero_dte_modifier(
            confidence,
            regime=regime,
            zero_dte_pct=fa_result.zero_dte.gex_pct_of_total,
            pin_risk=fa_result.zero_dte.pin_risk,
        )
        confidence = self._apply_zero_dte_divergence_modifier(
            confidence,
            regime=regime,
            by_expiry=self._by_expiry_buckets(massive_result),
        )
        confidence = self._apply_near_expiry_charm_modifier(
            confidence,
            regime=regime,
            net_chex=fa_result.dealer.net_chex,
            zero_dte_pct=fa_result.zero_dte.gex_pct_of_total,
            by_expiry=self._by_expiry_buckets(massive_result),
        )
        if has_real_flow:
            confidence = self._apply_flow_regime_interaction(
                confidence,
                regime,
                flow_direction_raw,
                flow_z_score,
            )
        direction = self._regime_to_direction(regime, confidence)
        nq_levels = self._merge_and_convert_levels(fa_result.levels, massive_result.levels)
        confidence = self._apply_dark_pool_modifier(
            confidence,
            direction,
            dark_pool_direction,
            dp_levels_nq or [],
            nq_levels,
        )
        confidence = self._apply_hmm_tradability_gate(confidence, hmm_state)
        direction = self._regime_to_direction(regime, confidence)
        confidence = self._apply_po3_modifier(confidence, direction, po3_direction)
        direction = self._regime_to_direction(regime, confidence)

        dealer = self._resolve_dealer_positioning(fa_result.dealer, regime)

        vanna_charm = self._build_vanna_charm_state(dealer)
        conviction_input = vanna_charm_net if vanna_charm_net != "neutral" else vanna_charm.net_hedge_direction
        conviction = self._conviction.score(
            gex_direction=self._regime_to_direction(regime, 100),
            flow_direction=flow_direction_raw,
            vanna_charm_direction=conviction_input,
            dark_pool_direction=dark_pool_direction,
            hmm_state=hmm_state,
            overall_direction=direction,
        )
        if conviction.stand_aside and direction != "NEUTRAL":
            confidence = max(0, confidence - 15)
        direction = self._regime_to_direction(regime, confidence)
        grade = "F" if conviction.stand_aside else conviction.grade
        if direction == "NEUTRAL" and not conviction.stand_aside:
            grade = self._confidence_to_grade(confidence)
        if hmm_state == "CHAOTIC" and confidence < 40:
            grade = "F"

        nq_levels = self._merge_and_convert_levels(fa_result.levels, massive_result.levels)
        flow = self._build_flow_summary(
            regime,
            source_agreement,
            flow_direction_raw=flow_direction_raw,
            flow_z_score=flow_z_score,
            flow_intensity=flow_intensity,
        )
        zero_dte = self._build_zero_dte_state(fa_result.zero_dte)
        current_spot_nq = self._resolve_spot_nq(massive_result, nq_spot=nq_spot)
        material_change = self._detect_material_change(
            regime=regime,
            flip=fa_result.levels.gamma_flip,
            levels=nq_levels,
            current_spot_nq=current_spot_nq,
        )

        bias = BiasVerdict(
            direction=direction,
            confidence=confidence,
            grade=grade,
            regime_name=_DEFAULT_REGIME_NAMES.get(regime, "Unknown"),
        )

        self._last_regime = regime
        self._last_flip = fa_result.levels.gamma_flip

        # NQ level caching strategy:
        # 1. If fresh levels are verified against NQ spot → save and use
        # 2. If fresh levels conflict with cached levels AND no spot to verify → prefer cache
        # 3. If no fresh levels at all → use cache
        fresh_valid = self._has_real_nq_levels(nq_levels)
        spot_verifiable = current_spot_nq is not None and current_spot_nq > 0
        cache_exists = self._last_levels is not None and self._has_real_nq_levels(self._last_levels)

        if fresh_valid and spot_verifiable and self._levels_are_fresh(nq_levels, current_spot_nq):
            # Verified live levels — save
            self._last_levels = nq_levels
            self._save_nq_levels_cache(nq_levels)
        elif fresh_valid and not spot_verifiable and cache_exists:
            # Can't verify fresh levels — check if they diverge >10% from cache
            cache_ref = self._last_levels.gamma_flip or self._last_levels.call_wall
            fresh_ref = nq_levels.gamma_flip or nq_levels.call_wall
            if cache_ref and fresh_ref and abs(cache_ref - fresh_ref) / cache_ref > 0.10:
                # Stale QQQ conversion diverges from cached NQ levels — prefer cache
                nq_levels = self._last_levels
                logger.info("Analyzer: fresh levels (%.0f) diverge >10%% from cache (%.0f) — using cache",
                            fresh_ref, cache_ref)
            else:
                self._last_levels = nq_levels
                self._save_nq_levels_cache(nq_levels)
        elif fresh_valid and not cache_exists:
            # No cache at all — accept whatever we have
            self._last_levels = nq_levels
            self._save_nq_levels_cache(nq_levels)
        elif not fresh_valid and cache_exists:
            # No fresh levels — use cache
            nq_levels = self._last_levels
            logger.info("Analyzer: no live levels — using cached NQ (flip=%s cw=%s pw=%s)",
                        nq_levels.gamma_flip, nq_levels.call_wall, nq_levels.put_wall)

        self._last_spot_nq = current_spot_nq

        return AnalysisResult(
            bias=bias,
            levels=nq_levels,
            dealer=dealer,
            flow=flow,
            vanna_charm=vanna_charm,
            zero_dte=zero_dte,
            material_change=material_change,
            nq_qqq_ratio=self._nq_qqq_ratio,
            vix=vix,
            conviction_grade=grade,
            conviction_rivers=conviction.rivers_agreeing,
            po3_state=self._normalize_po3_state(po3_direction),
        )

    def update_ratio(self, nq_spot: Optional[float], qqq_spot: Optional[float]) -> None:
        """Update NQ/QQQ ratio from live spot prices."""
        if nq_spot and qqq_spot and qqq_spot > 0:
            new_ratio = round(nq_spot / qqq_spot, 4)
            if 30.0 <= new_ratio <= 55.0:
                self._nq_qqq_ratio = new_ratio
                logger.debug(
                    "NQ/QQQ ratio updated: %.4f (NQ=%.2f, QQQ=%.2f)",
                    new_ratio,
                    nq_spot,
                    qqq_spot,
                )

    def _extract_nq_spot(self, fa_result: FlashAlphaResult) -> Optional[float]:
        summary = fa_result.raw.get("summary") if isinstance(fa_result.raw, dict) else None
        if not isinstance(summary, dict):
            return None
        for key in ("spot", "price", "underlying_price", "underlyingPrice"):
            value = summary.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return float(value)
        return None

    def _extract_qqq_spot(self, massive_result: MassiveResult) -> Optional[float]:
        raw_gex = massive_result.raw_gex_result
        spot = getattr(raw_gex, "spot", None)
        if isinstance(spot, (int, float)) and spot > 0:
            return float(spot)
        return None

    def _resolve_regime(self, fa_result: FlashAlphaResult, massive_result: MassiveResult) -> str:
        fa_status = (fa_result.source_health.status or "").lower()
        massive_status = (massive_result.source_health.status or "").lower()

        if fa_status not in {"error", "stale"} and fa_result.dealer.regime:
            return fa_result.dealer.regime

        massive_regime_sign = getattr(massive_result.raw_gex_result, "regime_sign", None)
        if massive_status != "error" and isinstance(massive_regime_sign, int):
            return self._regime_from_sign(massive_regime_sign)

        return fa_result.dealer.regime or "neutral"

    def _resolve_dealer_positioning(self, dealer: DealerPositioning, regime: str) -> DealerPositioning:
        hedge_direction = dealer.hedge_direction
        if hedge_direction == "neutral" and regime in {"positive", "negative"}:
            hedge_direction = "buying" if regime == "positive" else "selling"
        return dealer.model_copy(update={"regime": regime, "hedge_direction": hedge_direction})

    def _compute_source_agreement(self, fa_levels: GEXLevels, massive_levels: GEXLevels) -> float:
        comparisons = (
            (self._weights.flip, self._compare_levels(fa_levels.gamma_flip, massive_levels.gamma_flip)),
            (self._weights.call_wall, self._compare_levels(fa_levels.call_wall, massive_levels.call_wall)),
            (self._weights.put_wall, self._compare_levels(fa_levels.put_wall, massive_levels.put_wall)),
        )
        total_weight = sum(weight for weight, score in comparisons if score is not None)
        if total_weight <= 0:
            return 0.75
        weighted_score = sum(weight * score for weight, score in comparisons if score is not None)
        return round(weighted_score / total_weight, 4)

    def _compare_levels(self, left: Optional[float], right: Optional[float]) -> Optional[float]:
        if left is None and right is None:
            return None
        if left is None or right is None:
            return 0.75

        diff = abs((left - right) * self._nq_qqq_ratio)
        if diff < 50:
            return 1.0
        if diff < 150:
            return 0.85
        if diff < 300:
            return 0.7
        return 0.55

    def _compute_confidence(
        self,
        *,
        regime: str,
        source_agreement: float,
        health_multiplier: float,
        freshness_multiplier: float,
    ) -> int:
        base_confidence = _DEFAULT_BASE_CONFIDENCE.get(regime, 45.0)
        bonus = max(0.0, min(10.0, (source_agreement - 0.55) / 0.45 * 10.0))
        raw_confidence = (
            base_confidence * source_agreement * health_multiplier * freshness_multiplier
        ) + bonus
        return int(round(max(0.0, min(100.0, raw_confidence))))

    def _apply_vix_modifier(self, confidence: int, vix: Optional[float]) -> int:
        if vix is None:
            return confidence
        if vix < 15:
            return min(100, confidence + 5)
        if vix > 35:
            return max(0, confidence - 20)
        if vix > 25:
            return max(0, confidence - 10)
        return confidence

    def _apply_vanna_charm_modifier(
        self,
        confidence: int,
        net_vex: Optional[float],
        net_chex: Optional[float],
    ) -> int:
        """Apply VEX/CHEX alignment bonus/penalty."""
        if net_vex is None or net_chex is None:
            return confidence
        if (net_vex > 0 and net_chex > 0) or (net_vex < 0 and net_chex < 0):
            return min(100, confidence + 5)
        if (net_vex > 0 and net_chex < 0) or (net_vex < 0 and net_chex > 0):
            return max(0, confidence - 5)
        return confidence

    def _apply_zero_dte_modifier(
        self,
        confidence: int,
        regime: str,
        zero_dte_pct: Optional[float],
        pin_risk: str,
    ) -> int:
        """Apply 0DTE pin risk modifier to confidence."""
        if zero_dte_pct is not None and zero_dte_pct > 0.5:
            confidence = max(0, confidence - 10)
        if pin_risk == "high":
            confidence = max(0, confidence - 8)
        elif pin_risk == "medium":
            confidence = max(0, confidence - 4)
        return confidence

    def _apply_zero_dte_divergence_modifier(
        self,
        confidence: int,
        regime: str,
        by_expiry: dict[str, float],
    ) -> int:
        """Penalize confidence when 0DTE GEX fights the broader regime."""
        regime_sign = self._regime_sign(regime)
        zero_dte_gex = float(by_expiry.get("0DTE", 0.0))
        if regime_sign == 0 or zero_dte_gex == 0.0:
            return confidence
        if zero_dte_gex * regime_sign < 0:
            return max(0, confidence - 7)
        return confidence

    def _apply_near_expiry_charm_modifier(
        self,
        confidence: int,
        regime: str,
        net_chex: Optional[float],
        zero_dte_pct: Optional[float],
        by_expiry: dict[str, float],
    ) -> int:
        """Adjust confidence for last-hour charm drift on meaningful 0DTE sessions."""
        if net_chex is None or net_chex == 0 or not self._is_last_hour_of_session():
            return confidence

        zero_dte_share = zero_dte_pct
        if zero_dte_share is None:
            zero_dte_share = self._zero_dte_share_from_buckets(by_expiry)
        if zero_dte_share is None or zero_dte_share < 0.2:
            return confidence

        regime_sign = self._regime_sign(regime)
        charm_sign = 1 if net_chex > 0 else -1
        if regime_sign == 0:
            return confidence
        if charm_sign == regime_sign:
            return min(100, confidence + 4)
        return max(0, confidence - 4)

    def _apply_flow_regime_interaction(
        self,
        confidence: int,
        regime: str,
        flow_direction: str,
        flow_z_score: float,
    ) -> int:
        """Apply flow-regime interaction scoring."""
        if regime == "positive":
            if flow_direction == "bullish":
                confidence = min(100, confidence + 10)
            elif flow_direction == "bearish":
                confidence = max(0, confidence - 15)
        elif regime == "negative":
            if flow_direction == "bearish":
                confidence = min(100, confidence + 10)
            elif flow_direction == "bullish":
                confidence = max(0, confidence - 15)

        if abs(flow_z_score) > 2.0:
            confidence = min(100, confidence + 5)
        elif abs(flow_z_score) < 0.5:
            confidence = max(0, confidence - 5)

        return confidence

    def _apply_dark_pool_modifier(
        self,
        confidence: int,
        direction: str,
        dp_institutional_bias: str,
        dp_levels_nq: list[float],
        gex_levels: GEXLevels,
    ) -> int:
        """Apply dark pool institutional bias and level-confluence modifier.

        - Bias confirmation: +5 if DP bias confirms regime direction, -5 if contradicts.
        - Level confluence: +3 per DP level within 100 NQ points of a GEX key level.
        """
        if dp_institutional_bias == "neutral" and not dp_levels_nq:
            return confidence

        # Institutional bias confirmation/contradiction
        if dp_institutional_bias == "bullish" and direction == "BULLISH":
            confidence = min(100, confidence + 5)
        elif dp_institutional_bias == "bearish" and direction == "BEARISH":
            confidence = min(100, confidence + 5)
        elif dp_institutional_bias in ("bullish", "bearish"):
            expected = "BULLISH" if dp_institutional_bias == "bullish" else "BEARISH"
            if direction != "NEUTRAL" and direction != expected:
                confidence = max(0, confidence - 5)

        # Level confluence: DP levels within 100 NQ pts of GEX key levels
        if dp_levels_nq:
            gex_key = [
                lvl
                for lvl in [gex_levels.gamma_flip, gex_levels.call_wall, gex_levels.put_wall]
                if lvl is not None and lvl > 0
            ]
            confluence_count = 0
            for dp_level in dp_levels_nq:
                for gex_level in gex_key:
                    if abs(dp_level - gex_level) <= 100:
                        confluence_count += 1
                        break
            confidence = min(100, confidence + (confluence_count * 3))

        return confidence

    def _apply_hmm_tradability_gate(self, confidence: int, hmm_state: str) -> int:
        if hmm_state == "TRENDING":
            return max(0, int(confidence * 0.85))
        if hmm_state == "CHAOTIC":
            return max(0, int(confidence * 0.75))
        return confidence

    def _apply_po3_modifier(self, confidence: int, direction: str, po3_direction: str) -> int:
        po3_state = self._normalize_po3_state(po3_direction)
        if po3_state == "UNKNOWN" or direction == "NEUTRAL":
            return confidence
        if po3_state == direction:
            return min(100, confidence + 5)
        if po3_state in {"BULLISH", "BEARISH"}:
            return max(0, confidence - 10)
        return confidence

    def _compute_health_multiplier(self, *sources: SourceHealth) -> float:
        scores = [self._source_status_score(source.status) for source in sources]
        return sum(scores) / len(scores) if scores else 1.0

    def _compute_freshness_multiplier(self, *sources: SourceHealth) -> float:
        now = time.time()
        scores: list[float] = []
        for source in sources:
            if source.last_update is None or source.ttl_sec <= 0:
                scores.append(0.9)
                continue
            age = max(0.0, now - source.last_update)
            if age <= source.ttl_sec:
                scores.append(1.0)
            elif age <= source.ttl_sec * 2:
                scores.append(0.85)
            else:
                scores.append(0.7)
        return sum(scores) / len(scores) if scores else 1.0

    def _source_status_score(self, status: str) -> float:
        return {
            "ok": 1.0,
            "stale": 0.85,
            "pending": 0.8,
            "error": 0.7,
        }.get(status, 0.75)

    def _regime_to_direction(self, regime: str, confidence: int) -> str:
        if confidence < 50:
            return "NEUTRAL"
        return {
            "positive": "BULLISH",
            "negative": "BEARISH",
            "neutral": "NEUTRAL",
        }.get(regime, "NEUTRAL")

    def _confidence_to_grade(self, confidence: int) -> str:
        if confidence >= 85:
            return "A+"
        if confidence >= 75:
            return "A"
        if confidence >= 65:
            return "B"
        if confidence >= 50:
            return "C"
        return "F"

    def _normalize_po3_state(self, po3_direction: str) -> str:
        value = str(po3_direction or "").upper()
        if "BULL" in value:
            return "BULLISH"
        if "BEAR" in value:
            return "BEARISH"
        if value == "NEUTRAL":
            return "NEUTRAL"
        return "UNKNOWN"

    def _merge_and_convert_levels(self, fa_levels: GEXLevels, massive_levels: GEXLevels) -> GEXLevels:
        def convert(level: Optional[float]) -> Optional[float]:
            return round(level * self._nq_qqq_ratio, 2) if level is not None else None

        def merge(primary: Optional[float], secondary: Optional[float]) -> Optional[float]:
            if primary is None:
                return secondary
            if secondary is None:
                return primary
            agreement = self._compare_levels(primary, secondary)
            if agreement is not None and agreement >= 0.85:
                return round((primary + secondary) / 2.0, 4)
            return primary

        return GEXLevels(
            gamma_flip=convert(merge(fa_levels.gamma_flip, massive_levels.gamma_flip)),
            call_wall=convert(merge(fa_levels.call_wall, massive_levels.call_wall)),
            put_wall=convert(merge(fa_levels.put_wall, massive_levels.put_wall)),
            hvl=convert(fa_levels.hvl),
            zero_dte_magnet=convert(fa_levels.zero_dte_magnet),
            expected_move_up=convert(fa_levels.expected_move_up),
            expected_move_down=convert(fa_levels.expected_move_down),
        )

    def _build_flow_summary(
        self,
        regime: str,
        source_agreement: float,
        *,
        flow_direction_raw: str = "neutral",
        flow_z_score: float = 0.0,
        flow_intensity: float = 0.5,
    ) -> FlowSummary:
        has_real_flow = (
            flow_direction_raw != "neutral" or abs(flow_z_score) > 0.0 or flow_intensity != 0.5
        )
        if has_real_flow:
            direction = flow_direction_raw if flow_intensity > 0 else "neutral"
            intensity = flow_intensity
        else:
            direction = {
                "positive": "bullish",
                "negative": "bearish",
                "neutral": "neutral",
            }.get(regime, "neutral")
            if source_agreement < 0.65:
                direction = "neutral"
            intensity = source_agreement

        return FlowSummary(
            direction=direction,
            intensity=round(max(0.0, min(1.0, intensity)), 4),
            z_score=round(flow_z_score, 4),
            raw_direction=flow_direction_raw,
        )

    def _flow_direction_label(self, net_direction: int) -> str:
        if net_direction > 0:
            return "bullish"
        if net_direction < 0:
            return "bearish"
        return "neutral"

    def _flow_intensity(self, flow_result) -> float:
        premium_scale = min(1.0, abs(float(flow_result.signed_premium_5m)) / 1_000_000.0)
        z_scale = min(1.0, abs(float(flow_result.z_score)) / 3.0)
        base = max(premium_scale, z_scale)
        if flow_result.net_direction != 0 and base == 0.0:
            return 0.2
        return round(base, 4)

    def _flow_intensity_from_zscore(self, flow_z_score: float, flow_direction_raw: str) -> float:
        if flow_direction_raw == "neutral" and abs(flow_z_score) == 0.0:
            return 0.5
        return round(min(1.0, max(0.2, abs(flow_z_score) / 3.0)), 4)

    def _build_vanna_charm_state(self, dealer: DealerPositioning) -> VannaCharmState:
        net_hedge_direction = "neutral"
        exposures = [value for value in (dealer.net_vex, dealer.net_chex) if value is not None]
        if exposures:
            total = sum(exposures)
            if total > 0:
                net_hedge_direction = "tailwind"
            elif total < 0:
                net_hedge_direction = "headwind"
        return VannaCharmState(
            vanna_exposure=dealer.net_vex,
            charm_exposure=dealer.net_chex,
            net_hedge_direction=net_hedge_direction,
        )

    def _build_zero_dte_state(self, zero_dte: ZeroDTEState) -> ZeroDTEState:
        return ZeroDTEState(
            gex_pct_of_total=zero_dte.gex_pct_of_total,
            pin_risk=zero_dte.pin_risk,
            pin_risk_score=self._pin_risk_score(zero_dte),
            gamma_acceleration=zero_dte.gamma_acceleration,
        )

    def _pin_risk_score(self, zero_dte: ZeroDTEState) -> int:
        score = {
            "low": 25,
            "medium": 60,
            "high": 85,
        }.get(zero_dte.pin_risk, 25)
        if zero_dte.gex_pct_of_total is not None:
            score = max(score, int(round(max(0.0, min(1.0, zero_dte.gex_pct_of_total)) * 100)))
        if zero_dte.gamma_acceleration is not None:
            accel_bonus = int(round(max(0.0, min(1.0, zero_dte.gamma_acceleration)) * 10))
            score = min(100, score + accel_bonus)
        return max(0, min(100, score))

    def _by_expiry_buckets(self, massive_result: MassiveResult) -> dict[str, float]:
        raw_gex_result = massive_result.raw_gex_result
        by_expiry = getattr(raw_gex_result, "by_expiry", None)
        return by_expiry if isinstance(by_expiry, dict) else {}

    def _zero_dte_share_from_buckets(self, by_expiry: dict[str, float]) -> Optional[float]:
        if not by_expiry:
            return None
        total = sum(abs(float(value)) for value in by_expiry.values())
        if total <= 0:
            return None
        return abs(float(by_expiry.get("0DTE", 0.0))) / total

    def _regime_sign(self, regime: str) -> int:
        return {
            "positive": 1,
            "negative": -1,
            "neutral": 0,
        }.get(regime, 0)

    def _regime_from_sign(self, regime_sign: int) -> str:
        if regime_sign > 0:
            return "positive"
        if regime_sign < 0:
            return "negative"
        return "neutral"

    def _is_last_hour_of_session(self) -> bool:
        now = self._session_time_et()
        return now.weekday() < 5 and now.hour == 15

    def _session_time_et(self) -> datetime:
        return datetime.now(_EASTERN_TZ)

    def _resolve_spot_nq(self, massive_result: MassiveResult, *, nq_spot: Optional[float] = None) -> Optional[float]:
        if isinstance(nq_spot, (int, float)) and nq_spot > 0:
            return round(float(nq_spot), 2)
        if massive_result.raw_gex_result is None or massive_result.raw_gex_result.spot <= 0:
            return None
        return round(massive_result.raw_gex_result.spot * self._nq_qqq_ratio, 2)

    def _detect_material_change(
        self,
        *,
        regime: str,
        flip: Optional[float],
        levels: GEXLevels,
        current_spot_nq: Optional[float],
    ) -> bool:
        if self._last_regime is None:
            return True

        regime_changed = regime != self._last_regime
        flip_moved = False
        if flip is not None and self._last_flip is not None:
            flip_moved = abs((flip - self._last_flip) * self._nq_qqq_ratio) > 100

        wall_breached = False
        if (
            current_spot_nq is not None
            and self._last_spot_nq is not None
            and self._last_levels is not None
        ):
            if self._last_levels.call_wall is not None and levels.call_wall is not None:
                wall_breached = wall_breached or (
                    self._last_spot_nq <= self._last_levels.call_wall and current_spot_nq > levels.call_wall
                )
            if self._last_levels.put_wall is not None and levels.put_wall is not None:
                wall_breached = wall_breached or (
                    self._last_spot_nq >= self._last_levels.put_wall and current_spot_nq < levels.put_wall
                )

        return regime_changed or flip_moved or wall_breached


__all__ = ["AnalysisResult", "AnalyzerWeights", "GEXAnalyzer"]
