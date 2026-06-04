from __future__ import annotations

from deep6v2.config.scoring import ScoringConfig
from deep6v2.types.scoring import ScorerResult, SignalTier
from deep6v2.types.signal import SignalCategory, SignalResult, SIGNAL_TO_CATEGORY

try:
    from deep6v2.signals.engines.wall_intent import WallContextResult, WallIntentDetector
except Exception:  # pragma: no cover - optional integration guard
    WallContextResult = None  # type: ignore[assignment]
    WallIntentDetector = None  # type: ignore[assignment]


class ConfluenceScorer:
    def __init__(self, config: ScoringConfig | None = None) -> None:
        self._config = config or ScoringConfig()
        self._wall_intent = WallIntentDetector() if WallIntentDetector is not None else None
        self._category_weights = {
            SignalCategory.ABSORPTION: self._config.absorption_weight,
            SignalCategory.EXHAUSTION: self._config.exhaustion_weight,
            SignalCategory.IMBALANCE: self._config.imbalance_weight,
            SignalCategory.DELTA: self._config.delta_weight,
            SignalCategory.VOLUME_PROFILE: self._config.volume_profile_weight,
            SignalCategory.AUCTION: self._config.auction_weight,
            SignalCategory.TRAPPED: self._config.trapped_weight,
            SignalCategory.POC: self._config.poc_weight,
        }

    def score(
        self,
        signals: list[SignalResult],
        bar_index: int,
        *,
        zone_bonus: float = 0.0,
        gex_mult: float = 1.0,
        vpin_mult: float = 1.0,
        current_price: float | None = None,
        active_walls: list[dict[str, object]] | None = None,
    ) -> ScorerResult:
        wall_context = self._evaluate_wall_context(signals, current_price=current_price, active_walls=active_walls)
        scored_signals = wall_context.apply(signals) if wall_context is not None else list(signals)
        best_by_category: dict[SignalCategory, SignalResult] = {}

        for signal in scored_signals:
            category = SIGNAL_TO_CATEGORY.get(signal.signal_id)
            if category is None:
                continue

            current = best_by_category.get(category)
            if current is None or signal.strength > current.strength:
                best_by_category[category] = signal

        category_scores = {
            category.value: signal.strength * self._category_weights[category]
            for category, signal in best_by_category.items()
        }
        raw_score = sum(category_scores.values())
        category_count = len(best_by_category)

        category_directions = {signal.direction for signal in best_by_category.values()}
        confluence_mult = (
            self._config.confluence_multiplier
            if category_count >= 5 and len(category_directions) == 1
            else 1.0
        )

        active_directions = {signal.direction for signal in scored_signals}
        agreement_mult = self._config.confluence_multiplier if scored_signals and len(active_directions) == 1 else 1.0
        ib_mult = self._config.ib_multiplier if bar_index < self._config.midday_block_start_bar else 1.0

        score = raw_score
        score *= confluence_mult
        score += zone_bonus
        score *= gex_mult
        score *= agreement_mult
        score *= ib_mult
        score *= vpin_mult
        final_score = max(0.0, min(score, 100.0))

        midday_blocked = self._config.midday_block_start_bar <= bar_index <= self._config.midday_block_end_bar
        tier = self._classify_tier(final_score)
        veto_reasons: list[str] = []
        if midday_blocked:
            tier = SignalTier.QUIET
            veto_reasons.append(
                f"midday_block_{self._config.midday_block_start_bar}_{self._config.midday_block_end_bar}"
            )

        return ScorerResult(
            tier=tier,
            raw_score=raw_score,
            final_score=final_score,
            category_scores=category_scores,
            category_count=category_count,
            confluence_mult=confluence_mult,
            zone_bonus=zone_bonus,
            gex_mult=gex_mult,
            agreement_mult=agreement_mult,
            ib_mult=ib_mult,
            vpin_mult=vpin_mult,
            midday_blocked=midday_blocked,
            active_signals=signals,
            veto_reasons=veto_reasons,
            e10_agreement=None,
            e10_caution=False,
            wall_context_applied=wall_context is not None and bool(wall_context.modifiers),
            wall_context_details=list(wall_context.details) if wall_context is not None else [],
        )

    def _classify_tier(self, final_score: float) -> SignalTier:
        if final_score >= self._config.type_a_threshold:
            return SignalTier.TYPE_A
        if final_score >= self._config.type_b_threshold:
            return SignalTier.TYPE_B
        if final_score >= self._config.type_c_threshold:
            return SignalTier.TYPE_C
        return SignalTier.QUIET

    def _evaluate_wall_context(
        self,
        signals: list[SignalResult],
        *,
        current_price: float | None,
        active_walls: list[dict[str, object]] | None,
    ) -> WallContextResult | None:
        if self._wall_intent is None or not signals or not active_walls or current_price is None:
            return None
        try:
            return self._wall_intent.evaluate(active_walls, current_price=current_price, signals=signals)
        except Exception:
            return None


__all__ = ["ConfluenceScorer"]
