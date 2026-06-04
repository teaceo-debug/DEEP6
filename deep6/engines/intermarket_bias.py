"""Macro intermarket bias scoring for NQ context."""
from __future__ import annotations

from deep6.engines.bias_contracts import DomainScore
from deep6.engines.intermarket_registry import IntermarketRegistry
from deep6.engines.ohlcv_accumulator import OHLCVBar
from deep6.engines.signal_config import IntermarketBiasConfig


class MacroIntermarketDomain:
    """Scores NQ bias from ZN, DXY, and VIX cross-market inputs."""

    MAX_RANGE = 3
    DOMAIN = "macro"

    def __init__(self, config: IntermarketBiasConfig | None = None) -> None:
        self._config = config or IntermarketBiasConfig()

    def compute(
        self,
        bars: dict[str, OHLCVBar],
        registry: IntermarketRegistry,
    ) -> DomainScore:
        components = {
            "ZN": self._score_zn,
            "DXY": self._score_dxy,
            "VIX": self._score_vix,
        }
        detail: dict[str, object] = {"components": {}}
        score = 0
        available_components = 0

        for symbol, scorer in components.items():
            bar = bars.get(symbol)
            is_stale = bar is None or registry.is_stale(symbol)
            if is_stale:
                detail["components"][symbol] = {
                    "available": False,
                    "stale": True,
                    "score": 0,
                    "reason": "missing_or_stale",
                }
                continue

            component_score = scorer(bar)
            available_components += 1
            score += component_score
            detail["components"][symbol] = {
                "available": True,
                "stale": False,
                "score": component_score,
                "open": bar.open,
                "close": bar.close,
            }

        available = available_components > 0
        detail["available_components"] = available_components
        detail["excluded_components"] = self.MAX_RANGE - available_components

        return DomainScore(
            domain=self.DOMAIN,
            score=score,
            max_range=available_components,
            available=available,
            stale=not available,
            detail=detail,
        )

    @staticmethod
    def _score_zn(bar: OHLCVBar) -> int:
        if bar.close > bar.open:
            return 1
        if bar.close < bar.open:
            return -1
        return 0

    @staticmethod
    def _score_dxy(bar: OHLCVBar) -> int:
        if bar.close < bar.open:
            return 1
        if bar.close > bar.open:
            return -1
        return 0

    def _score_vix(self, bar: OHLCVBar) -> int:
        if bar.close < self._config.vix_low_threshold:
            return 1
        if bar.close > self._config.vix_high_threshold:
            return -1
        return 0


__all__ = ["MacroIntermarketDomain"]
