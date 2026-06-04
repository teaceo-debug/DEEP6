from __future__ import annotations

import math

from deep6v2.types.dom import DOMLevel, DOMSnapshot
from deep6v2.types.dom_intelligence import DOMIntelligenceEvent, DetectorTier, ReplaySafety
from deep6v2.types.signal import Direction, SignalId


def _top_n_total(levels: list[DOMLevel], depth_levels: int) -> int:
    return sum(level.volume for level in levels[:depth_levels] if level.volume > 0)


def _timestamp_ns(snapshot: DOMSnapshot) -> int:
    return int(snapshot.timestamp.timestamp() * 1_000_000_000)


def _reference_price(snapshot: DOMSnapshot, direction: Direction) -> float:
    if direction is Direction.BULLISH:
        if snapshot.bids:
            return snapshot.bids[0].price
        if snapshot.asks:
            return snapshot.asks[0].price
        return 0.0

    if direction is Direction.BEARISH:
        if snapshot.asks:
            return snapshot.asks[0].price
        if snapshot.bids:
            return snapshot.bids[0].price
        return 0.0

    if snapshot.bids:
        return snapshot.bids[0].price
    if snapshot.asks:
        return snapshot.asks[0].price
    return 0.0


class OrderBookImbalanceDetector:
    """Detects directional top-of-book volume imbalance from DOMSnapshot."""

    detector_id = "dom.imbalance.v1"
    tier = DetectorTier.MECHANICAL
    replay_safety = ReplaySafety.REPLAY_SAFE
    signal_id = SignalId.IMB_01

    def __init__(
        self,
        *,
        min_imbalance_ratio: float = 2.0,
        depth_levels: int = 5,
        min_total_volume: int = 50,
    ) -> None:
        self.min_imbalance_ratio = min_imbalance_ratio
        self.depth_levels = depth_levels
        self.min_total_volume = min_total_volume

    def on_depth(self, snapshot: DOMSnapshot) -> list[DOMIntelligenceEvent]:
        bid_total = _top_n_total(snapshot.bids, self.depth_levels)
        ask_total = _top_n_total(snapshot.asks, self.depth_levels)
        total_volume = bid_total + ask_total
        if total_volume < self.min_total_volume:
            return []

        bullish_ratio = math.inf if ask_total == 0 and bid_total > 0 else (bid_total / ask_total if ask_total > 0 else 1.0)
        bearish_ratio = math.inf if bid_total == 0 and ask_total > 0 else (ask_total / bid_total if bid_total > 0 else 1.0)

        direction = Direction.NEUTRAL
        imbalance_ratio = 1.0
        if bullish_ratio >= self.min_imbalance_ratio:
            direction = Direction.BULLISH
            imbalance_ratio = bullish_ratio
        elif bearish_ratio >= self.min_imbalance_ratio:
            direction = Direction.BEARISH
            imbalance_ratio = bearish_ratio

        if direction is Direction.NEUTRAL:
            return []

        confidence = 0.5 if math.isinf(imbalance_ratio) else min(1.0, imbalance_ratio / (self.min_imbalance_ratio * 2.0))
        return [
            DOMIntelligenceEvent(
                signal_id=self.signal_id,
                tier=self.tier,
                replay_safety=self.replay_safety,
                direction=direction,
                confidence=confidence,
                price=_reference_price(snapshot, direction),
                timestamp_ns=_timestamp_ns(snapshot),
                detector_id=self.detector_id,
                metadata={
                    "depth_levels": self.depth_levels,
                    "min_total_volume": self.min_total_volume,
                    "bid_volume": bid_total,
                    "ask_volume": ask_total,
                    "imbalance_ratio": imbalance_ratio,
                    "dominant_side": "bid" if direction is Direction.BULLISH else "ask",
                },
                dom_state_snapshot=snapshot,
            )
        ]


class LiquidityThinnessDetector:
    """Detects globally thin or one-sided-thin DOM liquidity conditions."""

    detector_id = "dom.thinness.v1"
    tier = DetectorTier.MECHANICAL
    replay_safety = ReplaySafety.REPLAY_SAFE
    signal_id = SignalId.IMB_02
    depth_levels = 5

    def __init__(
        self,
        *,
        thin_threshold: int = 100,
        asymmetry_ratio: float = 3.0,
    ) -> None:
        self.thin_threshold = thin_threshold
        self.asymmetry_ratio = asymmetry_ratio

    def on_depth(self, snapshot: DOMSnapshot) -> list[DOMIntelligenceEvent]:
        bid_total = _top_n_total(snapshot.bids, self.depth_levels)
        ask_total = _top_n_total(snapshot.asks, self.depth_levels)
        total_volume = bid_total + ask_total

        if total_volume <= 0:
            return []

        globally_thin = total_volume < self.thin_threshold
        bullish_asymmetry = ask_total > 0 and bid_total > (ask_total * self.asymmetry_ratio)
        bearish_asymmetry = bid_total > 0 and ask_total > (bid_total * self.asymmetry_ratio)
        empty_bid_vs_liquid_ask = bid_total == 0 and ask_total >= self.thin_threshold
        empty_ask_vs_liquid_bid = ask_total == 0 and bid_total >= self.thin_threshold

        if not any(
            (
                globally_thin,
                bullish_asymmetry,
                bearish_asymmetry,
                empty_bid_vs_liquid_ask,
                empty_ask_vs_liquid_bid,
            )
        ):
            return []

        if empty_ask_vs_liquid_bid or bullish_asymmetry:
            direction = Direction.BULLISH
        elif empty_bid_vs_liquid_ask or bearish_asymmetry:
            direction = Direction.BEARISH
        elif bid_total > ask_total:
            direction = Direction.BULLISH
        elif ask_total > bid_total:
            direction = Direction.BEARISH
        else:
            direction = Direction.NEUTRAL

        if globally_thin:
            confidence = min(1.0, max(0.0, 1.0 - (total_volume / self.thin_threshold)))
            condition = "global_thinness"
        else:
            dominant = max(bid_total, ask_total)
            weak = min(bid_total, ask_total)
            ratio = math.inf if weak == 0 else dominant / weak
            confidence = 1.0 if math.isinf(ratio) else min(1.0, ratio / (self.asymmetry_ratio * 2.0))
            condition = "asymmetric_thinness"

        return [
            DOMIntelligenceEvent(
                signal_id=self.signal_id,
                tier=self.tier,
                replay_safety=self.replay_safety,
                direction=direction,
                confidence=confidence,
                price=_reference_price(snapshot, direction),
                timestamp_ns=_timestamp_ns(snapshot),
                detector_id=self.detector_id,
                metadata={
                    "depth_levels": self.depth_levels,
                    "thin_threshold": self.thin_threshold,
                    "asymmetry_ratio": self.asymmetry_ratio,
                    "bid_volume": bid_total,
                    "ask_volume": ask_total,
                    "total_volume": total_volume,
                    "condition": condition,
                },
                dom_state_snapshot=snapshot,
            )
        ]


__all__ = ["LiquidityThinnessDetector", "OrderBookImbalanceDetector"]
