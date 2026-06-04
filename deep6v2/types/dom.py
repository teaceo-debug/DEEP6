from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from deep6v2.types.execution import OrderSide


class DOMLevel(BaseModel):
    model_config = ConfigDict(frozen=True)

    price: float
    volume: int


class DOMSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    bids: list[DOMLevel]
    asks: list[DOMLevel]


class DOMUpdate(BaseModel):
    model_config = ConfigDict(frozen=True)

    side: OrderSide
    level: int
    price: float
    volume: int


__all__ = ["DOMLevel", "DOMSnapshot", "DOMUpdate"]
