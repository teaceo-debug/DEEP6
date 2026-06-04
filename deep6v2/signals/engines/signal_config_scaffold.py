from __future__ import annotations

from statistics import fmean

from deep6v2.config.signals import SignalConfig
from deep6v2.types.bar import FootprintBar
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult


class RegimeDetector:
    """ENG-07 regime classifier emitting only on regime transitions."""

    def __init__(self, config: SignalConfig | None = None) -> None:
        self._config = config or SignalConfig()
        self._current_regime = "UNKNOWN"

    def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]:
        regime, confidence = self._classify(bar, ctx)
        previous = self._current_regime
        self._current_regime = regime
        if previous == "UNKNOWN" or regime == previous:
            return []
        return [
            SignalResult(
                signal_id=SignalId.REGIME_CHANGE,
                direction=Direction.NEUTRAL,
                strength=confidence,
                detail=f"Regime changed: {previous} -> {regime}",
                price=bar.close,
                flag_bit=SignalFlagBits.ENG_07,
            )
        ]

    def _classify(self, bar: FootprintBar, ctx: SessionContext) -> tuple[str, float]:
        prices = list(ctx.price_history)
        prices.append(bar.close)
        deltas = list(ctx.delta_history)
        deltas.append(bar.delta)
        if not prices:
            return self._current_regime, 0.0

        atr = ctx.atr if ctx.atr > 0 else max(bar.high - bar.low, 0.25)
        span = max(prices) - min(prices)
        span_ratio = span / atr if atr > 0 else 0.0
        delta_signs = [1 if delta > 0 else -1 if delta < 0 else 0 for delta in deltas]
        directional_bias = abs(sum(delta_signs)) / len(delta_signs) if delta_signs else 0.0
        delta_flip_rate = self._flip_rate(delta_signs)
        avg_abs_delta = fmean(abs(delta) for delta in deltas) if deltas else 0.0
        delta_variance_proxy = min(avg_abs_delta / max(bar.total_volume, 1), 1.0)

        if span_ratio >= 1.0 and directional_bias >= 0.6:
            return "TRENDING", min(1.0, 0.55 + (0.25 * min(span_ratio, 1.0)) + (0.20 * directional_bias))
        if span_ratio <= 0.7:
            confidence = max(0.0, min(1.0, 1.0 - (span_ratio / 0.7)))
            confidence *= 1.0 - min(delta_variance_proxy, 0.4)
            return "RANGING", confidence
        if span_ratio > 0.7 and delta_flip_rate >= 0.5:
            confidence = min(1.0, 0.45 + 0.30 * min(span_ratio, 1.0) + 0.25 * delta_flip_rate)
            return "VOLATILE", confidence
        return self._current_regime if self._current_regime != "UNKNOWN" else "RANGING", 0.25

    @staticmethod
    def _flip_rate(signs: list[int]) -> float:
        filtered = [sign for sign in signs if sign != 0]
        if len(filtered) < 2:
            return 0.0
        flips = sum(1 for left, right in zip(filtered, filtered[1:], strict=False) if left != right)
        return flips / (len(filtered) - 1)


__all__ = ["RegimeDetector"]
