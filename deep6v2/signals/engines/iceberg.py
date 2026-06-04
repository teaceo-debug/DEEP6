from __future__ import annotations

from deep6v2.config.signals import SignalConfig
from deep6v2.types.bar import FootprintBar
from deep6v2.types.dom import DOMSnapshot
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult


class IcebergDetector:
    """ENG-04 hidden liquidity detector."""

    _ZONE_TOLERANCE = 0.25

    def __init__(self, config: SignalConfig | None = None) -> None:
        self._config = config or SignalConfig()
        self._last_snapshot: DOMSnapshot | None = None
        self._absorption_zones: list[tuple[float, Direction, float]] = []

    def on_depth(self, snapshot: DOMSnapshot) -> None:
        self._last_snapshot = snapshot

    def mark_absorption_zone(self, price: float, direction: Direction, strength: float) -> None:
        self._absorption_zones.append((price, direction, strength))
        self._absorption_zones = self._absorption_zones[-20:]

    def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]:
        del ctx
        if self._last_snapshot is None:
            return []

        best: SignalResult | None = None
        for price, fill_vol in bar.bid_volumes.items():
            candidate = self._candidate(price, fill_vol, self._last_snapshot.bids, Direction.BULLISH)
            best = self._stronger(best, candidate)
        for price, fill_vol in bar.ask_volumes.items():
            candidate = self._candidate(price, fill_vol, self._last_snapshot.asks, Direction.BEARISH)
            best = self._stronger(best, candidate)
        return [best] if best is not None else []

    def _candidate(
        self,
        price: float,
        fill_vol: int,
        levels: list,
        fill_direction: Direction,
    ) -> SignalResult | None:
        displayed = next((level.volume for level in levels if level.price == price), 0)
        if displayed <= 0 or fill_vol <= displayed * 2:
            return None

        zone = self._nearest_zone(price)
        direction = zone[1] if zone is not None else fill_direction
        strength = min(fill_vol / (2 * displayed), 1.0)
        if zone is not None:
            strength = min(strength * (1.0 + (zone[2] * 0.25)), 1.0)
        return SignalResult(
            signal_id=SignalId.ENG_04,
            direction=direction,
            strength=strength,
            detail=f"Iceberg at {price}: fill={fill_vol}, displayed={displayed}",
            price=price,
            flag_bit=SignalFlagBits.ENG_04,
        )

    def _nearest_zone(self, price: float) -> tuple[float, Direction, float] | None:
        for zone in reversed(self._absorption_zones):
            if abs(zone[0] - price) <= self._ZONE_TOLERANCE:
                return zone
        return None

    @staticmethod
    def _stronger(current: SignalResult | None, candidate: SignalResult | None) -> SignalResult | None:
        if candidate is None:
            return current
        if current is None or candidate.strength > current.strength:
            return candidate
        return current


__all__ = ["IcebergDetector"]
