"""E10 is PURELY ADVISORY — sets flags on ScorerResult, does NOT modify final_score."""
from __future__ import annotations

from deep6v2.kronos.pipeline import E10Prediction
from deep6v2.types.signal import Direction


class E10BiasAdvisor:
    """Consults E10 prediction and produces advisory flags for ScorerResult."""

    def evaluate(self, prediction: E10Prediction | None, signal_direction: Direction) -> tuple[bool | None, bool]:
        """Return ``(e10_agreement, e10_caution)`` advisory flags."""
        if prediction is None or prediction.stale or prediction.direction == Direction.NEUTRAL:
            return None, False
        if prediction.direction == signal_direction:
            return True, False
        return False, True


__all__ = ["E10BiasAdvisor"]
