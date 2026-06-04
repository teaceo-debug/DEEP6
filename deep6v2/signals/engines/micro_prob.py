from __future__ import annotations

from deep6v2.config.signals import SignalConfig
from deep6v2.types.bar import FootprintBar
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import (
    SIGNAL_TO_CATEGORY,
    Direction,
    SignalCategory,
    SignalFlagBits,
    SignalId,
    SignalResult,
)


class MicroProbDetector:
    """ENG-05 meta-detector combining prior signal categories with Naive Bayes."""

    _PRIORS: dict[SignalCategory, float] = {
        SignalCategory.ABSORPTION: 0.65,
        SignalCategory.EXHAUSTION: 0.60,
        SignalCategory.IMBALANCE: 0.55,
        SignalCategory.DELTA: 0.50,
        SignalCategory.VOLUME_PROFILE: 0.50,
        SignalCategory.AUCTION: 0.55,
        SignalCategory.POC: 0.50,
        SignalCategory.TRAPPED: 0.55,
    }

    def __init__(self, config: SignalConfig | None = None) -> None:
        self._config = config or SignalConfig()

    def evaluate(self, bar: FootprintBar, ctx: SessionContext, signals: list[SignalResult]) -> list[SignalResult]:
        del ctx
        priors: list[float] = []
        bullish = 0
        bearish = 0

        for signal in signals:
            category = SIGNAL_TO_CATEGORY.get(signal.signal_id)
            if category is None:
                continue
            prior = self._PRIORS.get(category)
            if prior is None:
                continue
            priors.append(prior)
            if signal.direction is Direction.BULLISH:
                bullish += 1
            elif signal.direction is Direction.BEARISH:
                bearish += 1

        if not priors:
            return []

        positive = 1.0
        negative = 1.0
        for prior in priors:
            positive *= prior
            negative *= 1.0 - prior
        combined = positive / (positive + negative) if (positive + negative) > 0 else 0.0

        direction = Direction.NEUTRAL
        if bullish > bearish:
            direction = Direction.BULLISH
        elif bearish > bullish:
            direction = Direction.BEARISH

        return [
            SignalResult(
                signal_id=SignalId.ENG_05,
                direction=direction,
                strength=combined,
                detail=f"Naive Bayes from {len(priors)} categorized signals",
                price=bar.close,
                flag_bit=SignalFlagBits.ENG_05,
            )
        ]


__all__ = ["MicroProbDetector"]
