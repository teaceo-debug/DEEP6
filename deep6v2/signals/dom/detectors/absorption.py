from __future__ import annotations

from collections.abc import Iterable

from deep6v2.types.dom import DOMLevel, DOMSnapshot
from deep6v2.types.dom_intelligence import DOMIntelligenceEvent, DetectorTier, ReplaySafety
from deep6v2.types.signal import Direction, SignalId


class AbsorptionDOMDetector:
    """Detect resting liquidity absorption from consecutive DOM snapshots."""

    detector_id = "dom.absorption.v1"
    tier = DetectorTier.MECHANICAL
    replay_safety = ReplaySafety.REPLAY_SAFE
    signal_id = SignalId.ABS_01

    def __init__(
        self,
        wall_threshold: int = 200,
        aggression_threshold: int = 50,
        absorption_count: int = 3,
    ) -> None:
        self._wall_threshold = wall_threshold
        self._aggression_threshold = aggression_threshold
        self._absorption_count = absorption_count
        self._hit_counts: dict[float, int] = {}
        self._prev_snapshot: DOMSnapshot | None = None

    def on_depth(self, snapshot: DOMSnapshot) -> list[DOMIntelligenceEvent]:
        """Process new DOM snapshot, return absorption events if detected."""
        if self._prev_snapshot is None:
            self._prev_snapshot = snapshot
            return []

        curr_bids = {level.price: level.volume for level in snapshot.bids}
        curr_asks = {level.price: level.volume for level in snapshot.asks}

        surviving_prices: set[float] = set()
        events: list[DOMIntelligenceEvent] = []

        events.extend(
            self._detect_side(
                previous_levels=self._prev_snapshot.bids,
                current_lookup=curr_bids,
                best_price=self._best_price(snapshot.bids, is_bid=True),
                direction=Direction.BULLISH,
                timestamp_ns=self._to_timestamp_ns(snapshot),
                snapshot=snapshot,
                surviving_prices=surviving_prices,
            )
        )
        events.extend(
            self._detect_side(
                previous_levels=self._prev_snapshot.asks,
                current_lookup=curr_asks,
                best_price=self._best_price(snapshot.asks, is_bid=False),
                direction=Direction.BEARISH,
                timestamp_ns=self._to_timestamp_ns(snapshot),
                snapshot=snapshot,
                surviving_prices=surviving_prices,
            )
        )

        for price in set(self._hit_counts) - surviving_prices:
            self._hit_counts.pop(price, None)

        self._prev_snapshot = snapshot
        return events

    def reset(self) -> None:
        """Clear state for session rollover."""
        self._hit_counts.clear()
        self._prev_snapshot = None

    def _detect_side(
        self,
        *,
        previous_levels: Iterable[DOMLevel],
        current_lookup: dict[float, int],
        best_price: float | None,
        direction: Direction,
        timestamp_ns: int,
        snapshot: DOMSnapshot,
        surviving_prices: set[float],
    ) -> list[DOMIntelligenceEvent]:
        events: list[DOMIntelligenceEvent] = []

        for level in previous_levels:
            price = level.price
            previous_volume = level.volume
            current_volume = current_lookup.get(price)

            if current_volume is None:
                self._hit_counts.pop(price, None)
                continue

            if previous_volume < self._wall_threshold or current_volume < self._wall_threshold:
                self._hit_counts.pop(price, None)
                continue

            aggressive_flow = previous_volume - current_volume
            if aggressive_flow < self._aggression_threshold:
                self._hit_counts.pop(price, None)
                continue

            if best_price is None or not self._price_held(best_price, price, direction):
                self._hit_counts.pop(price, None)
                continue

            surviving_prices.add(price)
            hit_count = self._hit_counts.get(price, 0) + 1
            self._hit_counts[price] = hit_count

            if hit_count == self._absorption_count:
                events.append(
                    DOMIntelligenceEvent(
                        signal_id=self.signal_id,
                        tier=self.tier,
                        replay_safety=self.replay_safety,
                        direction=direction,
                        confidence=min(hit_count / self._absorption_count, 1.0),
                        price=price,
                        timestamp_ns=timestamp_ns,
                        detector_id=self.detector_id,
                        metadata={
                            "wall_threshold": self._wall_threshold,
                            "aggression_threshold": self._aggression_threshold,
                            "absorption_count": self._absorption_count,
                            "hit_count": hit_count,
                            "resting_volume": current_volume,
                            "aggressive_flow": aggressive_flow,
                        },
                        dom_state_snapshot=snapshot,
                    )
                )

        return events

    @staticmethod
    def _best_price(levels: Iterable[DOMLevel], *, is_bid: bool) -> float | None:
        prices = [level.price for level in levels]
        if not prices:
            return None
        return max(prices) if is_bid else min(prices)

    @staticmethod
    def _price_held(best_price: float, wall_price: float, direction: Direction) -> bool:
        if direction is Direction.BULLISH:
            return best_price >= wall_price
        return best_price <= wall_price

    @staticmethod
    def _to_timestamp_ns(snapshot: DOMSnapshot) -> int:
        return int(snapshot.timestamp.timestamp() * 1_000_000_000)


__all__ = ["AbsorptionDOMDetector"]
