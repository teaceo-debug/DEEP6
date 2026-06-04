"""Wall episode data model for DepthRadar V4 causal labeling."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd


class WallIntent(str, Enum):
    """Resolved retrospective intent label for a wall episode."""

    PASSIVE_REAL = "PASSIVE_REAL"
    SPOOF_LIKE = "SPOOF_LIKE"
    RESERVE_REFRESH = "RESERVE_REFRESH"
    MIGRATORY = "MIGRATORY"


class WallState(str, Enum):
    """Observed lifecycle state for a wall episode."""

    FRESH = "FRESH"
    ESTABLISHED = "ESTABLISHED"
    UNDER_ATTACK = "UNDER_ATTACK"
    DEFENDING = "DEFENDING"
    EXHAUSTED = "EXHAUSTED"
    STALE = "STALE"
    PULLED = "PULLED"
    CONSUMED = "CONSUMED"


class InteractionOutcome(str, Enum):
    """Resolved price interaction outcome at a touched wall."""

    BOUNCE = "BOUNCE"
    BREAK = "BREAK"
    CHURN = "CHURN"


@dataclass(slots=True)
class SnapshotEvent:
    """One causal observation of a wall at a specific time."""

    timestamp: pd.Timestamp
    wall_price: float
    mid_price: float
    wall_size: int
    state: WallState
    features: dict[str, float] = field(default_factory=dict)

    def to_row(self, episode_id: str) -> dict[str, Any]:
        row: dict[str, Any] = {
            "episode_id": episode_id,
            "timestamp": self.timestamp,
            "wall_price": self.wall_price,
            "mid_price": self.mid_price,
            "wall_size": self.wall_size,
            "state": self.state.value,
        }
        row.update(self.features)
        return row


@dataclass(slots=True)
class TouchEvent:
    """One price approach / touch event for an active wall episode."""

    timestamp: pd.Timestamp
    mid_price: float
    wall_price: float
    wall_size: int
    features: dict[str, float] = field(default_factory=dict)
    outcome: InteractionOutcome | None = None
    resolution_time: pd.Timestamp | None = None

    def to_row(self, episode_id: str) -> dict[str, Any]:
        row: dict[str, Any] = {
            "episode_id": episode_id,
            "timestamp": self.timestamp,
            "mid_price": self.mid_price,
            "wall_price": self.wall_price,
            "wall_size": self.wall_size,
            "outcome": self.outcome.value if self.outcome is not None else None,
            "resolution_time": self.resolution_time,
        }
        row.update(self.features)
        return row


@dataclass(slots=True)
class WallEpisode:
    """Complete lifecycle of a significant wall stored as causal snapshots."""

    episode_id: str
    session_date: str
    side: str
    price: float
    first_seen: pd.Timestamp
    snapshots: list[SnapshotEvent] = field(default_factory=list)
    touches: list[TouchEvent] = field(default_factory=list)
    intent_label: WallIntent | None = None
    final_state: WallState | None = None
    retirement_time: pd.Timestamp | None = None
    retirement_reason: str | None = None

    def add_snapshot(
        self,
        timestamp: pd.Timestamp,
        wall_price: float,
        mid_price: float,
        wall_size: int,
        state: WallState,
        features: dict[str, float],
    ) -> SnapshotEvent:
        snapshot = SnapshotEvent(
            timestamp=timestamp,
            wall_price=float(wall_price),
            mid_price=float(mid_price),
            wall_size=int(wall_size),
            state=state,
            features={str(k): float(v) for k, v in features.items()},
        )
        self.snapshots.append(snapshot)
        return snapshot

    def add_touch(
        self,
        timestamp: pd.Timestamp,
        mid_price: float,
        wall_price: float,
        wall_size: int,
        features: dict[str, float],
    ) -> int:
        touch = TouchEvent(
            timestamp=timestamp,
            mid_price=float(mid_price),
            wall_price=float(wall_price),
            wall_size=int(wall_size),
            features={str(k): float(v) for k, v in features.items()},
        )
        self.touches.append(touch)
        return len(self.touches) - 1

    def resolve_touch(
        self,
        touch_index: int,
        outcome: InteractionOutcome,
        resolution_time: pd.Timestamp | None = None,
    ) -> None:
        self.touches[touch_index].outcome = outcome
        self.touches[touch_index].resolution_time = resolution_time

    def retire(
        self,
        timestamp: pd.Timestamp,
        final_state: WallState,
        reason: str,
        intent_label: WallIntent | None = None,
    ) -> None:
        self.retirement_time = timestamp
        self.final_state = final_state
        self.retirement_reason = reason
        if intent_label is not None:
            self.intent_label = intent_label

    def to_parquet_rows(self) -> dict[str, Any]:
        last_snapshot = self.snapshots[-1] if self.snapshots else None
        episode_row: dict[str, Any] = {
            "episode_id": self.episode_id,
            "session_date": self.session_date,
            "side": self.side,
            "price": self.price,
            "first_seen": self.first_seen,
            "retirement_time": self.retirement_time,
            "retirement_reason": self.retirement_reason,
            "intent_label": self.intent_label.value if self.intent_label is not None else None,
            "final_state": self.final_state.value if self.final_state is not None else None,
            "snapshot_count": len(self.snapshots),
            "touch_count": len(self.touches),
            "duration_sec": (
                max((self.retirement_time - self.first_seen).total_seconds(), 0.0)
                if self.retirement_time is not None
                else (
                    max((last_snapshot.timestamp - self.first_seen).total_seconds(), 0.0)
                    if last_snapshot is not None
                    else 0.0
                )
            ),
            "last_wall_price": last_snapshot.wall_price if last_snapshot is not None else self.price,
            "last_wall_size": last_snapshot.wall_size if last_snapshot is not None else None,
            "last_mid_price": last_snapshot.mid_price if last_snapshot is not None else None,
            "max_wall_size": max((snapshot.wall_size for snapshot in self.snapshots), default=0),
        }
        snapshot_rows = [snapshot.to_row(self.episode_id) for snapshot in self.snapshots]
        touch_rows = [touch.to_row(self.episode_id) for touch in self.touches]
        return {
            "episode": episode_row,
            "snapshots": snapshot_rows,
            "touches": touch_rows,
        }


__all__ = [
    "InteractionOutcome",
    "SnapshotEvent",
    "TouchEvent",
    "WallEpisode",
    "WallIntent",
    "WallState",
]
