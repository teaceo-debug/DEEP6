from __future__ import annotations

from typing import Any, Mapping, Sequence

from deep6v2.types.signal import SIGNAL_TO_CATEGORY, Direction, SignalCategory, SignalResult

_REVERSAL_CATEGORIES = frozenset(
    {
        SignalCategory.ABSORPTION,
        SignalCategory.EXHAUSTION,
        SignalCategory.TRAPPED,
    }
)
_BREAKOUT_CATEGORIES = frozenset(
    {
        SignalCategory.IMBALANCE,
        SignalCategory.DELTA,
        SignalCategory.AUCTION,
    }
)
WallSignalModifier = dict[str, object]


class WallIntentDetector:
    """Optional wall-context modifier fed by MBOWallEngine / DepthRadar wall classifications.

    This detector does not emit standalone trade signals. It converts nearby active
    walls into lightweight confidence modifiers that can be layered onto an
    existing signal set later in the scoring pipeline.

    Modifier rules:
    - SPOOF_LIKE within 4 ticks -> suppressor (-0.15)
    - PASSIVE_REAL + DEFENDING within 4 ticks -> confirmer (+0.10)
    - RESERVE_REFRESH within 4 ticks -> strong confirmer (+0.15)
    - BOUNCE interaction -> boost reversal signals in the wall's defending direction
    - BREAK interaction -> boost breakout signals in the wall's failure direction

    If no wall data is supplied, the detector stays inert and returns empty results.
    """

    class ContextResult:
        def __init__(self, modifiers: Sequence[dict[str, object]] | None = None) -> None:
            self.modifiers = tuple(modifiers or ())
            self.nearby_wall_count = len(self.modifiers)
            self.details = tuple(str(modifier.get("reason", "")) for modifier in self.modifiers if modifier.get("reason"))

        def apply(self, signals: Sequence[SignalResult]) -> list[SignalResult]:
            if not self.modifiers:
                return list(signals)

            delta_by_index: dict[int, float] = {}
            for modifier in self.modifiers:
                signal_index = modifier.get("signal_index")
                magnitude = modifier.get("magnitude")
                if not isinstance(signal_index, int):
                    continue
                if not isinstance(magnitude, int | float):
                    continue
                delta_by_index[signal_index] = delta_by_index.get(signal_index, 0.0) + float(magnitude)

            adjusted: list[SignalResult] = []
            for index, signal in enumerate(signals):
                delta = delta_by_index.get(index, 0.0)
                if delta == 0.0:
                    adjusted.append(signal)
                    continue
                adjusted.append(signal.model_copy(update={"strength": max(0.0, min(signal.strength + delta, 1.0))}))
            return adjusted

    def __init__(
        self,
        *,
        proximity_ticks: int = 4,
        spoof_penalty: float = -0.15,
        passive_real_defending_boost: float = 0.10,
        reserve_refresh_boost: float = 0.15,
        bounce_boost: float = 0.10,
        break_boost: float = 0.10,
    ) -> None:
        self._proximity_ticks = proximity_ticks
        self._spoof_penalty = spoof_penalty
        self._passive_real_defending_boost = passive_real_defending_boost
        self._reserve_refresh_boost = reserve_refresh_boost
        self._bounce_boost = bounce_boost
        self._break_boost = break_boost
        self._mid_price = 0.0
        self._tick_size = 0.25
        self._modifiers: list[WallSignalModifier] = []

    def update(self, walls: list[dict], mid_price: float, tick_size: float = 0.25) -> None:
        self._mid_price = float(mid_price)
        self._tick_size = float(tick_size) if tick_size > 0 else 0.25
        self._modifiers = []

        if not walls or self._mid_price <= 0:
            return

        for wall in walls:
            wall_price = self._to_float(wall.get("price"))
            if wall_price <= 0 or not self._is_within_range(wall_price):
                continue

            side = self._normalized_text(wall.get("side"))
            if side not in {"BID", "ASK"}:
                continue

            intent = self._resolve_intent(wall)
            state = self._normalized_text(wall.get("state"))
            interaction = self._normalized_text(wall.get("interaction"))
            distance_ticks = abs(self._mid_price - wall_price) / self._tick_size
            defended_direction = Direction.BULLISH if side == "BID" else Direction.BEARISH
            broken_direction = Direction.BEARISH if side == "BID" else Direction.BULLISH

            if intent == "SPOOF_LIKE":
                self._modifiers.append(
                    self._modifier(
                        modifier_type="suppressor",
                        direction=Direction.NEUTRAL,
                        magnitude=self._spoof_penalty,
                        reason=f"spoof_like_{side.lower()}_{distance_ticks:.1f}t",
                    )
                )

            if intent == "PASSIVE_REAL" and state == "DEFENDING":
                self._modifiers.append(
                    self._modifier(
                        modifier_type="confirmer",
                        direction=defended_direction,
                        magnitude=self._passive_real_defending_boost,
                        reason=f"passive_real_defending_{side.lower()}_{distance_ticks:.1f}t",
                    )
                )

            if intent == "RESERVE_REFRESH":
                self._modifiers.append(
                    self._modifier(
                        modifier_type="strong_confirmer",
                        direction=defended_direction,
                        magnitude=self._reserve_refresh_boost,
                        reason=f"reserve_refresh_{side.lower()}_{distance_ticks:.1f}t",
                    )
                )

            if interaction == "BOUNCE":
                self._modifiers.append(
                    self._modifier(
                        modifier_type="reversal",
                        direction=defended_direction,
                        magnitude=self._bounce_boost,
                        reason=f"bounce_bias_{side.lower()}_{distance_ticks:.1f}t",
                    )
                )

            if interaction == "BREAK":
                self._modifiers.append(
                    self._modifier(
                        modifier_type="breakout",
                        direction=broken_direction,
                        magnitude=self._break_boost,
                        reason=f"break_bias_{side.lower()}_{distance_ticks:.1f}t",
                    )
                )

    def get_modifiers(self) -> list[dict[str, object]]:
        return [dict(modifier) for modifier in self._modifiers]

    def evaluate(
        self,
        active_walls: Sequence[Mapping[str, Any]] | None,
        *,
        current_price: float,
        signals: Sequence[SignalResult],
    ) -> ContextResult:
        self.update(walls=[dict(wall) for wall in active_walls] if active_walls else [], mid_price=current_price)
        if not signals:
            return self.ContextResult()

        applied: list[dict[str, object]] = []
        for index, signal in enumerate(signals):
            category = SIGNAL_TO_CATEGORY.get(signal.signal_id)
            if category is None:
                continue

            for modifier in self._modifiers:
                if self._applies_to_signal(modifier, signal.direction, category):
                    applied.append({**modifier, "signal_index": index, "signal_id": signal.signal_id.value})

        return self.ContextResult(applied)

    def _applies_to_signal(
        self,
        modifier: Mapping[str, object],
        direction: Direction,
        category: SignalCategory,
    ) -> bool:
        modifier_type = str(modifier.get("type", ""))
        modifier_direction = modifier.get("direction")

        if modifier_type == "suppressor":
            return direction is not Direction.NEUTRAL

        if modifier_direction is not direction:
            return False

        if modifier_type in {"confirmer", "strong_confirmer", "reversal"}:
            return category in _REVERSAL_CATEGORIES

        if modifier_type == "breakout":
            return category in _BREAKOUT_CATEGORIES

        return False

    def _is_within_range(self, wall_price: float) -> bool:
        return abs(self._mid_price - wall_price) <= self._proximity_ticks * self._tick_size

    @staticmethod
    def _modifier(
        *,
        modifier_type: str,
        direction: Direction,
        magnitude: float,
        reason: str,
    ) -> dict[str, object]:
        return {
            "type": modifier_type,
            "direction": direction,
            "magnitude": magnitude,
            "reason": reason,
        }

    @staticmethod
    def _resolve_intent(wall: Mapping[str, Any]) -> str:
        intent = WallIntentDetector._normalized_text(wall.get("intent"))
        if intent:
            return intent

        classification = WallIntentDetector._normalized_text(wall.get("classification"))
        return {
            "GENUINE": "PASSIVE_REAL",
            "SPOOF": "SPOOF_LIKE",
            "ICEBERG": "RESERVE_REFRESH",
        }.get(classification, classification)

    @staticmethod
    def _normalized_text(value: Any) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0


WallContextResult = WallIntentDetector.ContextResult

__all__ = ["WallContextResult", "WallIntentDetector", "WallSignalModifier"]
