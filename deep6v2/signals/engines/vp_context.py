from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from deep6v2.config.signals import SignalConfig
from deep6v2.types.bar import FootprintBar
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult


class LVNZoneState(str, Enum):
    CREATED = "CREATED"
    DEFENDED = "DEFENDED"
    BROKEN = "BROKEN"
    FLIPPED = "FLIPPED"
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True)
class LVNZone:
    price: float
    state: LVNZoneState = LVNZoneState.CREATED


class VPContextDetector:
    """ENG-06 value-area/POC context detector with LVN FSM scaffold."""

    _TICK_SIZE = 0.25
    _NEAR_TICKS = 2.0

    def __init__(self, config: SignalConfig | None = None) -> None:
        self._config = config or SignalConfig()
        self._lvn_zones: list[LVNZone] = []

    def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]:
        candidates = [
            ("VAH", ctx.vah, Direction.BEARISH),
            ("VAL", ctx.val, Direction.BULLISH),
            ("POC", ctx.poc, Direction.NEUTRAL),
        ]
        best: tuple[str, float, Direction, float] | None = None
        for label, level, direction in candidates:
            ticks = abs(bar.close - level) / self._TICK_SIZE
            if ticks > self._NEAR_TICKS:
                continue
            strength = max(0.0, min(1.0, 1.0 - (ticks / self._NEAR_TICKS)))
            if best is None or strength > best[3]:
                best = (label, level, direction, strength)

        if best is None:
            return []

        label, level, direction, strength = best
        return [
            SignalResult(
                signal_id=SignalId.ENG_06,
                direction=direction,
                strength=strength,
                detail=f"Price near {label}={level:.2f}",
                price=level,
                flag_bit=SignalFlagBits.ENG_06,
            )
        ]


__all__ = ["LVNZone", "LVNZoneState", "VPContextDetector"]
