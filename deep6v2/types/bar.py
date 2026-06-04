from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class SessionType(str, Enum):
    RTH = "RTH"
    ETH = "ETH"


class FootprintBar(BaseModel):
    model_config = ConfigDict(frozen=True)

    open: float
    high: float
    low: float
    close: float
    delta: int
    total_volume: int
    bid_volumes: dict[float, int]
    ask_volumes: dict[float, int]
    poc_price: float
    poc_volume: int
    vah: float
    val: float
    cvd: float
    bar_index: int
    timestamp: datetime
    session_type: SessionType


__all__ = ["FootprintBar", "SessionType"]
