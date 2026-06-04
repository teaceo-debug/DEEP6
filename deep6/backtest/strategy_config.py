"""Frozen strategy config models for backtest/search orchestration.

This module represents strategy intent as structured config only — not code.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from deep6v2.types.signal import SignalId


class LevelTarget(str, Enum):
    LVN = "LVN"
    HVN = "HVN"
    VPOC = "VPOC"
    GENUINE_WALL = "GENUINE_WALL"
    ICEBERG_WALL = "ICEBERG_WALL"
    ANY_WALL = "ANY_WALL"


class ApproachDirection(str, Enum):
    ABOVE = "ABOVE"
    BELOW = "BELOW"
    EITHER = "EITHER"


class TimingFilter(str, Enum):
    RTH_OPEN = "RTH_OPEN"
    LONDON = "LONDON"
    NY_AM = "NY_AM"
    NY_PM = "NY_PM"
    MIDDAY_BLOCK_EXCLUDED = "MIDDAY_BLOCK_EXCLUDED"
    ANY = "ANY"


class ExitType(str, Enum):
    BRACKET = "BRACKET"
    LEVEL = "LEVEL"
    TIME = "TIME"


class ConfirmationSignal(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal_id: str
    threshold: float
    operator: Literal["gt", "lt", "active"]

    @field_validator("signal_id")
    @classmethod
    def _validate_signal_id(cls, value: str) -> str:
        if value not in SignalId.__members__:
            raise ValueError(f"Unknown SignalId name: {value}")
        return value


class BracketExit(BaseModel):
    model_config = ConfigDict(frozen=True)

    stop_ticks: int
    target_ticks: int
    rr_ratio: float


class LevelExit(BaseModel):
    model_config = ConfigDict(frozen=True)

    exit_at_next_zone: bool
    trail_to_zone_boundary: bool


class TimeExit(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_bars_in_trade: int = 30
    session_end_flatten: bool = True


class StrategyConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    level_target: LevelTarget = LevelTarget.LVN
    approach_direction: ApproachDirection = ApproachDirection.EITHER
    timing_filter: TimingFilter = TimingFilter.ANY
    confirmation_signals: list[ConfirmationSignal] = Field(default_factory=list)
    multi_level_distance_ticks: int = 10
    require_multi_level: bool = False
    bracket_exit: Optional[BracketExit] = Field(
        default_factory=lambda: BracketExit(stop_ticks=20, target_ticks=40, rr_ratio=2.0)
    )
    level_exit: Optional[LevelExit] = None
    time_exit: TimeExit = Field(default_factory=TimeExit)
    generation: int = 0
    parent_hash: Optional[str] = None
    mutation_type: Optional[str] = None

    def config_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude_none=False)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "ApproachDirection",
    "BracketExit",
    "ConfirmationSignal",
    "ExitType",
    "LevelExit",
    "LevelTarget",
    "StrategyConfig",
    "TimeExit",
    "TimingFilter",
]
