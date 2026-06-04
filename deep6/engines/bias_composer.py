"""Bias composition for v3 market bias engine."""
from __future__ import annotations

from deep6.engines.bias_contracts import BiasComponentState, BiasMode, BiasState, DomainScore


class BiasComposer:
    """Compose four domain scores into a raw bias component state."""

    def compose(
        self,
        ict: DomainScore,
        macro: DomainScore,
        flow: DomainScore,
        kronos: DomainScore,
        gex: DomainScore | None = None,
        session_quality: bool = False,
        proximity_bonus: bool = False,
        flow_clean: bool = False,
        rvol_bonus: bool = False,
    ) -> BiasComponentState:
        domains = (ict, macro, flow, kronos) if gex is None else (ict, macro, flow, kronos, gex)
        active_domains = [domain for domain in domains if domain.available and not domain.stale]
        stale_count = sum(1 for domain in domains if domain.stale)

        domain_scores = {
            domain.domain: domain.score if domain.available and not domain.stale else 0
            for domain in domains
        }
        # Max score: ICT(4) + Macro(3) + Flow(2) + Kronos(3) + GEX(3) = 15
        # Clamp to ±12 to keep scoring proportional
        max_clamp = 12 if gex is not None else 9
        total_score = self._clamp(sum(domain_scores.values()), low=-max_clamp, high=max_clamp)

        confidence = abs(total_score) / max_clamp
        if self._has_heavy_disagreement(active_domains):
            confidence *= 0.5
        for _ in range(stale_count):
            confidence *= 0.9
        if len(active_domains) < 2:
            confidence *= 0.5
        confidence = max(0.0, min(1.0, confidence))

        setup_quality = self._setup_quality(
            active_domains=active_domains,
            session_quality=session_quality,
            proximity_bonus=proximity_bonus,
            flow_clean=flow_clean,
            rvol_bonus=rvol_bonus,
        )

        return BiasComponentState(
            ict_score=domain_scores.get("ict", 0),
            macro_score=domain_scores.get("macro", 0),
            flow_score=domain_scores.get("flow", 0),
            kronos_score=domain_scores.get("kronos", 0),
            gex_score=domain_scores.get("gex", 0),
            total_score=total_score,
            confidence=confidence,
            setup_quality=setup_quality,
            bias_state=BiasState.NEUTRAL,
            mode=BiasMode.CAUTION.value,
            reason="Pending hysteresis and kill switch",
        )

    @staticmethod
    def _clamp(value: int, low: int, high: int) -> int:
        return max(low, min(high, value))

    def _has_heavy_disagreement(self, domains: list[DomainScore]) -> bool:
        positives = [domain.score for domain in domains if domain.score > 0]
        negatives = [abs(domain.score) for domain in domains if domain.score < 0]
        if not positives or not negatives:
            return False
        return max(positives) + max(negatives) > 5

    def _setup_quality(
        self,
        *,
        active_domains: list[DomainScore],
        session_quality: bool,
        proximity_bonus: bool,
        flow_clean: bool,
        rvol_bonus: bool,
    ) -> int:
        quality = 0
        if self._has_domain_agreement(active_domains):
            quality += 1
        quality += int(session_quality)
        quality += int(proximity_bonus)
        quality += int(flow_clean)
        quality += int(rvol_bonus)
        return self._clamp(quality, low=0, high=5)

    def _has_domain_agreement(self, domains: list[DomainScore]) -> bool:
        non_zero_scores = [domain.score for domain in domains if domain.score != 0]
        if len(non_zero_scores) < 2:
            return False
        signs = {1 if score > 0 else -1 for score in non_zero_scores}
        return len(signs) == 1


__all__ = ["BiasComposer"]
