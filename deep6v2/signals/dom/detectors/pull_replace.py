from __future__ import annotations

from dataclasses import dataclass

from deep6v2.types.dom import DOMLevel, DOMSnapshot
from deep6v2.types.dom_intelligence import DOMIntelligenceEvent, DetectorTier, ReplaySafety
from deep6v2.types.signal import Direction, SignalId


@dataclass(slots=True)
class _PendingPull:
    side: str
    from_price: float
    pulled_volume: int
    snapshot_index: int


class PullReplaceTrapDetector:
    """Detect nearby pull/replace liquidity behavior across consecutive DOM snapshots."""

    detector_id = "dom.pull_replace.v1"
    tier = DetectorTier.HEURISTIC
    replay_safety = ReplaySafety.REPLAY_DEGRADED
    signal_id = SignalId.REGIME_CHANGE

    def __init__(
        self,
        *,
        cancel_threshold: int = 50,
        price_range: float = 1.0,
        look_ahead: int = 2,
        confirmation_threshold: int = 2,
        ratio_tolerance: float = 0.35,
    ) -> None:
        if cancel_threshold <= 0:
            raise ValueError("cancel_threshold must be positive")
        if price_range <= 0.0:
            raise ValueError("price_range must be positive")
        if look_ahead < 1:
            raise ValueError("look_ahead must be at least 1")
        if confirmation_threshold < 1:
            raise ValueError("confirmation_threshold must be at least 1")
        if not 0.0 < ratio_tolerance < 1.0:
            raise ValueError("ratio_tolerance must be between 0.0 and 1.0")

        self.cancel_threshold = cancel_threshold
        self.price_range = price_range
        self.look_ahead = look_ahead
        self.confirmation_threshold = confirmation_threshold
        self.ratio_tolerance = ratio_tolerance
        self._snapshot_index = 0
        self._previous_snapshot: DOMSnapshot | None = None
        self._pending_pulls: list[_PendingPull] = []
        self._repeat_counts: dict[tuple[str, float, float], int] = {}

    def on_depth(self, snapshot: DOMSnapshot) -> list[DOMIntelligenceEvent]:
        self._snapshot_index += 1
        self._expire_old_pulls()

        if self._previous_snapshot is None:
            self._previous_snapshot = snapshot
            return []

        events: list[DOMIntelligenceEvent] = []
        previous_snapshot = self._previous_snapshot

        events.extend(self._process_side(snapshot=snapshot, previous_levels=previous_snapshot.bids, current_levels=snapshot.bids, side="bid"))
        events.extend(self._process_side(snapshot=snapshot, previous_levels=previous_snapshot.asks, current_levels=snapshot.asks, side="ask"))

        self._previous_snapshot = snapshot
        return events

    def _process_side(
        self,
        *,
        snapshot: DOMSnapshot,
        previous_levels: list[DOMLevel],
        current_levels: list[DOMLevel],
        side: str,
    ) -> list[DOMIntelligenceEvent]:
        current_lookup = {level.price: level.volume for level in current_levels}
        current_pulls = [
            _PendingPull(
                side=side,
                from_price=level.price,
                pulled_volume=level.volume - current_lookup.get(level.price, 0),
                snapshot_index=self._snapshot_index,
            )
            for level in previous_levels
            if level.volume - current_lookup.get(level.price, 0) >= self.cancel_threshold
        ]
        increases = [
            (level.price, current_lookup.get(level.price, 0) - level.volume)
            for level in previous_levels
            if current_lookup.get(level.price, 0) - level.volume >= self.cancel_threshold
        ]
        previous_prices = {level.price for level in previous_levels}
        increases.extend(
            (level.price, level.volume)
            for level in current_levels
            if level.price not in previous_prices and level.volume >= self.cancel_threshold
        )

        events: list[DOMIntelligenceEvent] = []
        matched_pull_ids: set[int] = set()

        for pull_index, pull in enumerate(self._pending_pulls):
            if pull.side != side:
                continue
            if self._snapshot_index - pull.snapshot_index > self.look_ahead:
                continue

            best_candidate = self._best_replacement_candidate(pull=pull, increases=increases)
            if best_candidate is None:
                continue

            matched_pull_ids.add(pull_index)
            replacement_price, replacement_volume = best_candidate
            repeat_key = (side, pull.from_price, replacement_price)
            repeat_count = self._repeat_counts.get(repeat_key, 0) + 1
            self._repeat_counts[repeat_key] = repeat_count
            if repeat_count >= self.confirmation_threshold:
                events.append(
                    self._build_event(
                        snapshot=snapshot,
                        pull=pull,
                        replacement_price=replacement_price,
                        replacement_volume=replacement_volume,
                        repeat_count=repeat_count,
                    )
                )
                self._repeat_counts[repeat_key] = 0

        self._pending_pulls = [pull for index, pull in enumerate(self._pending_pulls) if index not in matched_pull_ids]

        unmatched_current_pulls: list[_PendingPull] = []
        for pull in current_pulls:
            best_candidate = self._best_replacement_candidate(pull=pull, increases=increases)
            if best_candidate is None:
                unmatched_current_pulls.append(pull)
                continue

            replacement_price, replacement_volume = best_candidate
            repeat_key = (side, pull.from_price, replacement_price)
            repeat_count = self._repeat_counts.get(repeat_key, 0) + 1
            self._repeat_counts[repeat_key] = repeat_count
            if repeat_count >= self.confirmation_threshold:
                events.append(
                    self._build_event(
                        snapshot=snapshot,
                        pull=pull,
                        replacement_price=replacement_price,
                        replacement_volume=replacement_volume,
                        repeat_count=repeat_count,
                    )
                )
                self._repeat_counts[repeat_key] = 0

        self._pending_pulls.extend(unmatched_current_pulls)

        return events

    def _best_replacement_candidate(
        self,
        *,
        pull: _PendingPull,
        increases: list[tuple[float, int]],
    ) -> tuple[float, int] | None:
        best_candidate: tuple[float, int] | None = None
        best_score: float | None = None

        for price, increased_volume in increases:
            if price == pull.from_price:
                continue
            if abs(price - pull.from_price) > self.price_range:
                continue

            pull_ratio = increased_volume / pull.pulled_volume
            if abs(1.0 - pull_ratio) > self.ratio_tolerance:
                continue

            score = abs(1.0 - pull_ratio)
            if best_score is None or score < best_score:
                best_score = score
                best_candidate = (price, increased_volume)

        return best_candidate

    def _build_event(
        self,
        *,
        snapshot: DOMSnapshot,
        pull: _PendingPull,
        replacement_price: float,
        replacement_volume: int,
        repeat_count: int,
    ) -> DOMIntelligenceEvent:
        pull_ratio = replacement_volume / max(pull.pulled_volume, 1)
        replacement_speed = max(1, self._snapshot_index - pull.snapshot_index)
        return DOMIntelligenceEvent(
            signal_id=self.signal_id,
            tier=self.tier,
            replay_safety=self.replay_safety,
            direction=self._direction_for(side=pull.side, from_price=pull.from_price, replacement_price=replacement_price),
            confidence=min(1.0, 0.5 + ((repeat_count - 1) / max(self.confirmation_threshold, 1)) * 0.5),
            price=replacement_price,
            timestamp_ns=int(snapshot.timestamp.timestamp() * 1_000_000_000),
            detector_id=self.detector_id,
            metadata={
                "side": pull.side,
                "pull_price": pull.from_price,
                "replacement_price": replacement_price,
                "pulled_volume": pull.pulled_volume,
                "replacement_volume": replacement_volume,
                "pull_ratio": pull_ratio,
                "replacement_speed": replacement_speed,
                "cancel_threshold": self.cancel_threshold,
                "price_range": self.price_range,
                "look_ahead": self.look_ahead,
                "confirmation_threshold": self.confirmation_threshold,
                "repeat_count": repeat_count,
            },
            dom_state_snapshot=snapshot,
        )

    def _expire_old_pulls(self) -> None:
        self._pending_pulls = [
            pull for pull in self._pending_pulls if self._snapshot_index - pull.snapshot_index <= self.look_ahead
        ]

    @staticmethod
    def _direction_for(*, side: str, from_price: float, replacement_price: float) -> Direction:
        if side == "bid":
            return Direction.BULLISH if replacement_price > from_price else Direction.BEARISH
        return Direction.BEARISH if replacement_price < from_price else Direction.BULLISH


__all__ = ["PullReplaceTrapDetector"]
