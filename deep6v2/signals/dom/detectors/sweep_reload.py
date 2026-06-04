from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Literal

from deep6v2.types.dom import DOMSnapshot
from deep6v2.types.dom_intelligence import DOMIntelligenceEvent, DetectorTier, ReplaySafety
from deep6v2.types.signal import Direction, SignalId

Side = Literal["bid", "ask"]
LevelKey = tuple[Side, float]


@dataclass(slots=True)
class _LevelState:
    side: Side
    price: float
    last_volume: int
    swept_at_snapshot: int | None = None
    swept_volume: int | None = None

    @property
    def is_swept(self) -> bool:
        return self.swept_at_snapshot is not None


class SweepReloadDetector:
    """Detects sweep-through liquidity that immediately reloads.

    detector_id: "dom.sweep_reload.v1"
    tier: MECHANICAL
    replay_safety: REPLAY_SAFE
    signal_id: SignalId.ABS_02

    Sweep + Reload = a price level is swept (drops to near-zero volume) then
    immediately reloads (refills to > threshold). Signals institutional layering.

    States per level: NORMAL -> SWEPT -> RELOADED
    """

    detector_id = "dom.sweep_reload.v1"
    tier = DetectorTier.MECHANICAL
    replay_safety = ReplaySafety.REPLAY_SAFE
    signal_id = SignalId.ABS_02
    max_tracked_levels = 20

    def __init__(
        self,
        *,
        sweep_threshold: int = 20,
        reload_threshold: int = 150,
        max_reload_snapshots: int = 3,
    ) -> None:
        if sweep_threshold < 0:
            raise ValueError("sweep_threshold must be non-negative")
        if reload_threshold <= sweep_threshold:
            raise ValueError("reload_threshold must be greater than sweep_threshold")
        if max_reload_snapshots < 1:
            raise ValueError("max_reload_snapshots must be at least 1")

        self.sweep_threshold = sweep_threshold
        self.reload_threshold = reload_threshold
        self.max_reload_snapshots = max_reload_snapshots
        self._snapshot_index = 0
        self._levels: OrderedDict[LevelKey, _LevelState] = OrderedDict()

    def on_depth(self, snapshot: DOMSnapshot) -> list[DOMIntelligenceEvent]:
        """Track level states across snapshots and emit on SWEPT->RELOADED."""
        self._snapshot_index += 1
        self._expire_timed_out_sweeps()

        events: list[DOMIntelligenceEvent] = []
        tracked_levels = [
            *(("bid", level) for level in snapshot.bids[: self.max_tracked_levels // 2]),
            *(("ask", level) for level in snapshot.asks[: self.max_tracked_levels // 2]),
        ]

        for side, level in tracked_levels:
            key = (side, level.price)
            state = self._touch_state(key=key, side=side, price=level.price, volume=level.volume)

            if state.is_swept:
                if self._reloaded_within_window(state, level.volume):
                    events.append(self._build_event(snapshot=snapshot, state=state, reloaded_volume=level.volume))
                    state.swept_at_snapshot = None
                    state.swept_volume = None
            elif self._is_sweep(state.last_volume, level.volume):
                state.swept_at_snapshot = self._snapshot_index
                state.swept_volume = level.volume

            state.last_volume = level.volume

        self._trim_levels()
        return events

    def _touch_state(self, *, key: LevelKey, side: Side, price: float, volume: int) -> _LevelState:
        state = self._levels.get(key)
        if state is None:
            state = _LevelState(side=side, price=price, last_volume=volume)
            self._levels[key] = state
            return state

        self._levels.move_to_end(key)
        return state

    def _expire_timed_out_sweeps(self) -> None:
        for key, state in list(self._levels.items()):
            if not state.is_swept:
                continue
            assert state.swept_at_snapshot is not None
            if self._snapshot_index - state.swept_at_snapshot > self.max_reload_snapshots:
                state.swept_at_snapshot = None
                state.swept_volume = None
                self._levels[key] = state

    def _is_sweep(self, previous_volume: int, current_volume: int) -> bool:
        return previous_volume >= self.reload_threshold and current_volume < self.sweep_threshold

    def _reloaded_within_window(self, state: _LevelState, current_volume: int) -> bool:
        assert state.swept_at_snapshot is not None
        return (
            current_volume >= self.reload_threshold
            and self._snapshot_index - state.swept_at_snapshot <= self.max_reload_snapshots
        )

    def _build_event(
        self,
        *,
        snapshot: DOMSnapshot,
        state: _LevelState,
        reloaded_volume: int,
    ) -> DOMIntelligenceEvent:
        timestamp_ns = int(snapshot.timestamp.timestamp() * 1_000_000_000)
        swept_at_snapshot = state.swept_at_snapshot or self._snapshot_index
        swept_volume = state.swept_volume if state.swept_volume is not None else state.last_volume
        snapshots_to_reload = self._snapshot_index - swept_at_snapshot
        return DOMIntelligenceEvent(
            signal_id=self.signal_id,
            tier=self.tier,
            replay_safety=self.replay_safety,
            direction=Direction.BULLISH if state.side == "bid" else Direction.BEARISH,
            confidence=min(1.0, reloaded_volume / max(self.reload_threshold, 1)),
            price=state.price,
            timestamp_ns=timestamp_ns,
            detector_id=self.detector_id,
            metadata={
                "side": state.side,
                "state_path": ["NORMAL", "SWEPT", "RELOADED"],
                "sweep_threshold": self.sweep_threshold,
                "reload_threshold": self.reload_threshold,
                "max_reload_snapshots": self.max_reload_snapshots,
                "swept_volume": swept_volume,
                "reloaded_volume": reloaded_volume,
                "snapshots_to_reload": snapshots_to_reload,
            },
            dom_state_snapshot=snapshot,
        )

    def _trim_levels(self) -> None:
        while len(self._levels) > self.max_tracked_levels:
            removable_key = next((key for key, state in self._levels.items() if not state.is_swept), None)
            if removable_key is None:
                removable_key = next(iter(self._levels))
            self._levels.pop(removable_key)


__all__ = ["SweepReloadDetector"]
