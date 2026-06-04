from __future__ import annotations

import math

from deep6v2.config.signals import SignalConfig
from deep6v2.types.bar import FootprintBar
from deep6v2.types.dom import DOMSnapshot
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult


class TrespassDetector:
    """ENG-02 DOM queue imbalance detector."""

    _LEVELS = 5
    _THRESHOLD = 0.6
    _LOGISTIC_K = 5.0

    def __init__(self, config: SignalConfig | None = None) -> None:
        self._config = config or SignalConfig()
        self._last_snapshot: DOMSnapshot | None = None

    def on_depth(self, snapshot: DOMSnapshot) -> None:
        self._last_snapshot = snapshot

    def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]:
        del bar, ctx
        if self._last_snapshot is None:
            return []

        imbalance = self._depth_imbalance(self._last_snapshot)
        if abs(imbalance) <= self._THRESHOLD:
            return []

        direction = Direction.BULLISH if imbalance > 0 else Direction.BEARISH
        strength = self._logistic(abs(imbalance))
        return [
            SignalResult(
                signal_id=SignalId.ENG_02,
                direction=direction,
                strength=strength,
                detail=f"Top-{self._LEVELS} DOM imbalance={imbalance:.3f}",
                price=self._reference_price(self._last_snapshot, direction),
                flag_bit=SignalFlagBits.ENG_02,
            )
        ]

    def _depth_imbalance(self, snapshot: DOMSnapshot) -> float:
        bid_vol = sum(level.volume for level in snapshot.bids[: self._LEVELS])
        ask_vol = sum(level.volume for level in snapshot.asks[: self._LEVELS])
        total = bid_vol + ask_vol
        if total <= 0:
            return 0.0
        return (bid_vol - ask_vol) / total

    def _logistic(self, value: float) -> float:
        return 1.0 / (1.0 + math.exp(-(self._LOGISTIC_K * value)))

    @staticmethod
    def _reference_price(snapshot: DOMSnapshot, direction: Direction) -> float:
        side = snapshot.bids if direction is Direction.BULLISH else snapshot.asks
        if side:
            return side[0].price
        other_side = snapshot.asks if direction is Direction.BULLISH else snapshot.bids
        return other_side[0].price if other_side else 0.0


__all__ = ["TrespassDetector"]
