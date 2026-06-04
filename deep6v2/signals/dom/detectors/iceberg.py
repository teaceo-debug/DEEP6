"""Iceberg/refill detector for the DEEP6 SuperDOM Intelligence Layer.

Detects hidden liquidity (iceberg orders) by monitoring repeated depletion + refill
cycles at the same price level across consecutive DOM snapshots.

Adapted from V1 IcebergEngine's synthetic detection logic for DOMSnapshot-based
operation.  Does NOT import V1 — adapts the pattern for snapshot-only input.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from deep6v2.types.dom import DOMSnapshot
from deep6v2.types.dom_intelligence import (
    DOMIntelligenceEvent,
    DetectorTier,
    ReplaySafety,
)
from deep6v2.types.signal import Direction, SignalId

_MAX_TRACKED_LEVELS: int = 20


@dataclass
class _TrackedLevel:
    """Per-price-level refill cycle state."""

    depleted: bool = False
    depletion_snap: int = 0
    refill_count: int = 0


class IcebergRefillDetector:
    """DOM-snapshot iceberg/refill detector.

    detector_id : ``"dom.iceberg.v1"``
    tier        : ``MECHANICAL``
    replay_safety : ``REPLAY_SAFE``
    signal_id   : ``SignalId.ENG_04``

    Iceberg = hidden large order that repeatedly refreshes displayed size.

    Detection (adapted from V1 IcebergEngine for DOMSnapshot):

    * A price level trades (volume decreases by >= *min_trade_size*).
    * Volume at that **same** price replenishes (increases by >=
      *min_refill_size*) within *max_refill_window* snapshots.
    * Replenishment count at the same level reaches *confirmation_count*
      → iceberg confirmed → ``DOMIntelligenceEvent`` emitted.

    Thresholds
    ----------
    min_trade_size : int
        Minimum volume decrease per snapshot to count as a trade (default 30).
    min_refill_size : int
        Minimum volume increase to count as a refill (default 25).
    confirmation_count : int
        Refills at the same level required before confirmation (default 2).
    max_refill_window : int
        Maximum snapshots between depletion and refill (default 4).
    """

    DETECTOR_ID: str = "dom.iceberg.v1"
    TIER: DetectorTier = DetectorTier.MECHANICAL
    REPLAY_SAFETY: ReplaySafety = ReplaySafety.REPLAY_SAFE
    SIGNAL_ID: SignalId = SignalId.ENG_04

    def __init__(
        self,
        min_trade_size: int = 30,
        min_refill_size: int = 25,
        confirmation_count: int = 2,
        max_refill_window: int = 4,
    ) -> None:
        self._min_trade_size = min_trade_size
        self._min_refill_size = min_refill_size
        self._confirmation_count = confirmation_count
        self._max_refill_window = max_refill_window

        self._prior_bids: dict[float, int] = {}
        self._prior_asks: dict[float, int] = {}
        self._tracked: dict[float, _TrackedLevel] = {}
        self._snapshot_idx: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_depth(self, snapshot: DOMSnapshot) -> list[DOMIntelligenceEvent]:
        """Process a DOM snapshot; return iceberg events (if any)."""
        self._snapshot_idx += 1

        curr_bids = {lvl.price: lvl.volume for lvl in snapshot.bids}
        curr_asks = {lvl.price: lvl.volume for lvl in snapshot.asks}

        ts_ns = int(snapshot.timestamp.timestamp() * 1_000_000_000)

        events: list[DOMIntelligenceEvent] = []
        events.extend(
            self._check_side(curr_bids, self._prior_bids, Direction.BULLISH, ts_ns, snapshot),
        )
        events.extend(
            self._check_side(curr_asks, self._prior_asks, Direction.BEARISH, ts_ns, snapshot),
        )

        self._prior_bids = curr_bids
        self._prior_asks = curr_asks
        return events

    def reset(self) -> None:
        """Clear all internal state for session boundaries or test teardown."""
        self._prior_bids.clear()
        self._prior_asks.clear()
        self._tracked.clear()
        self._snapshot_idx = 0

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_side(
        self,
        current: dict[float, int],
        prior: dict[float, int],
        direction: Direction,
        timestamp_ns: int,
        snapshot: DOMSnapshot,
    ) -> list[DOMIntelligenceEvent]:
        events: list[DOMIntelligenceEvent] = []

        for price, volume in current.items():
            prior_vol = prior.get(price)
            if prior_vol is None:
                # First time seeing this level — need a baseline first.
                continue

            delta = volume - prior_vol
            tracked = self._tracked.get(price)

            if tracked is None:
                # Level not tracked yet — start tracking on depletion.
                if delta <= -self._min_trade_size:
                    self._ensure_capacity()
                    self._tracked[price] = _TrackedLevel(
                        depleted=True,
                        depletion_snap=self._snapshot_idx,
                    )
            elif tracked.depleted:
                if self._snapshot_idx - tracked.depletion_snap > self._max_refill_window:
                    # Window expired — abandon this depletion cycle.
                    tracked.depleted = False
                elif delta >= self._min_refill_size:
                    # Refill confirmed within window.
                    tracked.refill_count += 1
                    tracked.depleted = False  # Ready for next depletion cycle.

                    if tracked.refill_count >= self._confirmation_count:
                        confidence = min(0.3 + 0.2 * tracked.refill_count, 1.0)
                        events.append(
                            DOMIntelligenceEvent(
                                signal_id=self.SIGNAL_ID,
                                tier=self.TIER,
                                replay_safety=self.REPLAY_SAFETY,
                                direction=direction,
                                confidence=confidence,
                                price=price,
                                timestamp_ns=timestamp_ns,
                                detector_id=self.DETECTOR_ID,
                                metadata={
                                    "refill_count": tracked.refill_count,
                                    "volume": volume,
                                    "prior_volume": prior_vol,
                                },
                            ),
                        )
                        # Reset count after firing — allows re-detection.
                        tracked.refill_count = 0
            else:
                # Not depleted — watch for new depletion.
                if delta <= -self._min_trade_size:
                    tracked.depleted = True
                    tracked.depletion_snap = self._snapshot_idx

        return events

    def _ensure_capacity(self) -> None:
        """Evict the least-valuable tracked level when at capacity."""
        while len(self._tracked) >= _MAX_TRACKED_LEVELS:
            worst = min(
                self._tracked,
                key=lambda p: (
                    self._tracked[p].refill_count,
                    -self._tracked[p].depletion_snap,
                ),
            )
            del self._tracked[worst]


__all__ = ["IcebergRefillDetector"]
