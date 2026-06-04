"""Heuristic micro-feature detectors for the SuperDOM Intelligence Layer.

These detectors emit DOMIntelligenceEvent when heuristic thresholds are exceeded.
They are tier=HEURISTIC, replay_safety=REPLAY_DEGRADED — not scored signal IDs.
SignalId.REGIME_CHANGE is used as a placeholder for heuristic-only events.
"""

from __future__ import annotations

from collections import deque

from deep6v2.types.dom import DOMSnapshot
from deep6v2.types.dom_intelligence import DOMIntelligenceEvent, DetectorTier, ReplaySafety
from deep6v2.types.signal import Direction, SignalId


def _timestamp_ns(snapshot: DOMSnapshot) -> int:
    return int(snapshot.timestamp.timestamp() * 1_000_000_000)


def _mid_price(snapshot: DOMSnapshot) -> float | None:
    if not snapshot.bids or not snapshot.asks:
        return None
    return (snapshot.bids[0].price + snapshot.asks[0].price) / 2.0


def _reference_price(snapshot: DOMSnapshot) -> float:
    if snapshot.bids:
        return snapshot.bids[0].price
    if snapshot.asks:
        return snapshot.asks[0].price
    return 0.0


class MicroMomentumDetector:
    """Tracks mid-price velocity over last N snapshots.

    detector_id: "dom.micro_momentum.v1"
    tier: HEURISTIC, replay_safety: REPLAY_DEGRADED

    Computes velocity = (current_mid - oldest_mid) / window_size.
    Emits when abs(velocity) exceeds momentum_threshold.
    """

    detector_id = "dom.micro_momentum.v1"
    tier = DetectorTier.HEURISTIC
    replay_safety = ReplaySafety.REPLAY_DEGRADED
    signal_id = SignalId.REGIME_CHANGE

    def __init__(
        self,
        *,
        window_size: int = 5,
        momentum_threshold: float = 0.50,
    ) -> None:
        if window_size < 2:
            raise ValueError("window_size must be >= 2")
        self.window_size = window_size
        self.momentum_threshold = momentum_threshold
        self._mid_prices: deque[float] = deque(maxlen=window_size)

    def on_depth(self, snapshot: DOMSnapshot) -> list[DOMIntelligenceEvent]:
        mid = _mid_price(snapshot)
        if mid is None:
            return []

        self._mid_prices.append(mid)

        if len(self._mid_prices) < self.window_size:
            return []

        oldest = self._mid_prices[0]
        velocity = (mid - oldest) / self.window_size

        if abs(velocity) < self.momentum_threshold:
            return []

        direction = Direction.BULLISH if velocity > 0 else Direction.BEARISH
        confidence = min(1.0, abs(velocity) / (self.momentum_threshold * 2.0))

        return [
            DOMIntelligenceEvent(
                signal_id=self.signal_id,
                tier=self.tier,
                replay_safety=self.replay_safety,
                direction=direction,
                confidence=confidence,
                price=_reference_price(snapshot),
                timestamp_ns=_timestamp_ns(snapshot),
                detector_id=self.detector_id,
                metadata={
                    "velocity": velocity,
                    "mid_price": mid,
                    "oldest_mid": oldest,
                    "window_size": self.window_size,
                    "momentum_threshold": self.momentum_threshold,
                },
                dom_state_snapshot=snapshot,
            )
        ]

    def reset(self) -> None:
        self._mid_prices.clear()


class TPSIntensityDetector:
    """Tracks trades-per-snapshot as a proxy for TPS intensity.

    detector_id: "dom.tps.v1"
    tier: HEURISTIC, replay_safety: REPLAY_DEGRADED

    update_trade(volume, is_buy) is called per trade within a snapshot window.
    on_depth() finalises the current snapshot, rolls the window, and checks threshold.
    Emits when rolling average trades/snapshot > tps_threshold.
    """

    detector_id = "dom.tps.v1"
    tier = DetectorTier.HEURISTIC
    replay_safety = ReplaySafety.REPLAY_DEGRADED
    signal_id = SignalId.REGIME_CHANGE

    def __init__(
        self,
        *,
        window_size: int = 5,
        tps_threshold: float = 10.0,
    ) -> None:
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        self.window_size = window_size
        self.tps_threshold = tps_threshold
        self._trade_counts: deque[int] = deque(maxlen=window_size)
        self._buy_volume: deque[int] = deque(maxlen=window_size)
        self._sell_volume: deque[int] = deque(maxlen=window_size)
        self._current_count: int = 0
        self._current_buy_vol: int = 0
        self._current_sell_vol: int = 0

    def update_trade(self, volume: int, is_buy: bool) -> None:
        """Register a trade that occurred before the next on_depth call."""
        self._current_count += 1
        if is_buy:
            self._current_buy_vol += volume
        else:
            self._current_sell_vol += volume

    def on_depth(self, snapshot: DOMSnapshot) -> list[DOMIntelligenceEvent]:
        self._trade_counts.append(self._current_count)
        self._buy_volume.append(self._current_buy_vol)
        self._sell_volume.append(self._current_sell_vol)
        self._current_count = 0
        self._current_buy_vol = 0
        self._current_sell_vol = 0

        if len(self._trade_counts) < self.window_size:
            return []

        avg_tps = sum(self._trade_counts) / len(self._trade_counts)
        if avg_tps < self.tps_threshold:
            return []

        total_buy = sum(self._buy_volume)
        total_sell = sum(self._sell_volume)
        if total_buy > total_sell:
            direction = Direction.BULLISH
        elif total_sell > total_buy:
            direction = Direction.BEARISH
        else:
            direction = Direction.NEUTRAL

        confidence = min(1.0, avg_tps / (self.tps_threshold * 2.0))

        return [
            DOMIntelligenceEvent(
                signal_id=self.signal_id,
                tier=self.tier,
                replay_safety=self.replay_safety,
                direction=direction,
                confidence=confidence,
                price=_reference_price(snapshot),
                timestamp_ns=_timestamp_ns(snapshot),
                detector_id=self.detector_id,
                metadata={
                    "avg_tps": avg_tps,
                    "tps_threshold": self.tps_threshold,
                    "window_size": self.window_size,
                    "total_buy_volume": total_buy,
                    "total_sell_volume": total_sell,
                },
                dom_state_snapshot=snapshot,
            )
        ]

    def reset(self) -> None:
        self._trade_counts.clear()
        self._buy_volume.clear()
        self._sell_volume.clear()
        self._current_count = 0
        self._current_buy_vol = 0
        self._current_sell_vol = 0


class LargeTradeBurstDetector:
    """Detects concentrated bursts of large trade activity within a window.

    detector_id: "dom.large_burst.v1"
    tier: HEURISTIC, replay_safety: REPLAY_DEGRADED

    A large trade is any single trade with volume > large_trade_size.
    update_trade(volume, is_buy) is called per trade.
    on_depth() finalises the snapshot and checks whether burst_count large trades
    appeared within the last burst_window snapshots.
    """

    detector_id = "dom.large_burst.v1"
    tier = DetectorTier.HEURISTIC
    replay_safety = ReplaySafety.REPLAY_DEGRADED
    signal_id = SignalId.REGIME_CHANGE

    def __init__(
        self,
        *,
        large_trade_size: int = 20,
        burst_count: int = 3,
        burst_window: int = 5,
    ) -> None:
        if burst_window < 1:
            raise ValueError("burst_window must be >= 1")
        if burst_count < 1:
            raise ValueError("burst_count must be >= 1")
        self.large_trade_size = large_trade_size
        self.burst_count = burst_count
        self.burst_window = burst_window
        self._large_counts: deque[int] = deque(maxlen=burst_window)
        self._large_buy_vol: deque[int] = deque(maxlen=burst_window)
        self._large_sell_vol: deque[int] = deque(maxlen=burst_window)
        self._current_large: int = 0
        self._current_buy_vol: int = 0
        self._current_sell_vol: int = 0

    def update_trade(self, volume: int, is_buy: bool) -> None:
        """Register a trade; only trades > large_trade_size are tracked."""
        if volume > self.large_trade_size:
            self._current_large += 1
            if is_buy:
                self._current_buy_vol += volume
            else:
                self._current_sell_vol += volume

    def on_depth(self, snapshot: DOMSnapshot) -> list[DOMIntelligenceEvent]:
        self._large_counts.append(self._current_large)
        self._large_buy_vol.append(self._current_buy_vol)
        self._large_sell_vol.append(self._current_sell_vol)
        self._current_large = 0
        self._current_buy_vol = 0
        self._current_sell_vol = 0

        if len(self._large_counts) < self.burst_window:
            return []

        total_large = sum(self._large_counts)
        if total_large < self.burst_count:
            return []

        total_buy = sum(self._large_buy_vol)
        total_sell = sum(self._large_sell_vol)
        if total_buy > total_sell:
            direction = Direction.BULLISH
        elif total_sell > total_buy:
            direction = Direction.BEARISH
        else:
            direction = Direction.NEUTRAL

        confidence = min(1.0, total_large / (self.burst_count * 2.0))

        return [
            DOMIntelligenceEvent(
                signal_id=self.signal_id,
                tier=self.tier,
                replay_safety=self.replay_safety,
                direction=direction,
                confidence=confidence,
                price=_reference_price(snapshot),
                timestamp_ns=_timestamp_ns(snapshot),
                detector_id=self.detector_id,
                metadata={
                    "total_large_trades": total_large,
                    "burst_count_threshold": self.burst_count,
                    "burst_window": self.burst_window,
                    "large_trade_size": self.large_trade_size,
                    "large_buy_volume": total_buy,
                    "large_sell_volume": total_sell,
                },
                dom_state_snapshot=snapshot,
            )
        ]

    def reset(self) -> None:
        self._large_counts.clear()
        self._large_buy_vol.clear()
        self._large_sell_vol.clear()
        self._current_large = 0
        self._current_buy_vol = 0
        self._current_sell_vol = 0


__all__ = [
    "LargeTradeBurstDetector",
    "MicroMomentumDetector",
    "TPSIntensityDetector",
]
