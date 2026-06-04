from __future__ import annotations

from deep6v2.config.signals import SignalConfig
from deep6v2.types.bar import FootprintBar
from deep6v2.types.dom import DOMSnapshot
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult


class CounterSpoofDetector:
    """ENG-03 DOM spoofing detector using snapshot displacement and cancel rate."""

    _DISTANCE_THRESHOLD = 5000
    _CANCEL_THRESHOLD = 0.6

    def __init__(self, config: SignalConfig | None = None) -> None:
        self._config = config or SignalConfig()
        self._prev_snapshot: DOMSnapshot | None = None
        self._last_snapshot: DOMSnapshot | None = None
        self._spoof_detected = False
        self._last_distance = 0.0
        self._last_cancel_rate = 0.0

    def on_depth(self, snapshot: DOMSnapshot) -> None:
        self._prev_snapshot = self._last_snapshot
        self._last_snapshot = snapshot
        self._spoof_detected = self._check_spoof()

    def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]:
        del bar, ctx
        if not self._spoof_detected:
            return []
        price = 0.0
        if self._last_snapshot and self._last_snapshot.asks:
            price = self._last_snapshot.asks[0].price
        return [
            SignalResult(
                signal_id=SignalId.SPOOF_VETO,
                direction=Direction.NEUTRAL,
                strength=min(max(self._last_cancel_rate, 0.0), 1.0),
                detail=(
                    f"Spoof veto: distance={self._last_distance:.0f}, "
                    f"cancel_rate={self._last_cancel_rate:.2f}"
                ),
                price=price,
                flag_bit=SignalFlagBits.ENG_03,
            )
        ]

    def _check_spoof(self) -> bool:
        if self._prev_snapshot is None or self._last_snapshot is None:
            self._last_distance = 0.0
            self._last_cancel_rate = 0.0
            return False

        prev_map = self._snapshot_map(self._prev_snapshot)
        curr_map = self._snapshot_map(self._last_snapshot)
        keys = set(prev_map) | set(curr_map)

        self._last_distance = sum(abs(prev_map.get(key, 0) - curr_map.get(key, 0)) for key in keys)
        prev_total = sum(prev_map.values())
        disappeared = sum(max(prev_map.get(key, 0) - curr_map.get(key, 0), 0) for key in prev_map)
        self._last_cancel_rate = disappeared / prev_total if prev_total > 0 else 0.0
        return self._last_distance > self._DISTANCE_THRESHOLD and self._last_cancel_rate > self._CANCEL_THRESHOLD

    @staticmethod
    def _snapshot_map(snapshot: DOMSnapshot) -> dict[tuple[str, float], int]:
        result: dict[tuple[str, float], int] = {}
        for level in snapshot.bids:
            result[("bid", level.price)] = level.volume
        for level in snapshot.asks:
            result[("ask", level.price)] = level.volume
        return result


__all__ = ["CounterSpoofDetector"]
