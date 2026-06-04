from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from deep6v2.types.signal import SignalId


class TradeState(str, Enum):
    IDLE = "IDLE"
    WATCHING = "WATCHING"
    ARMED = "ARMED"
    PENDING_ENTRY = "PENDING_ENTRY"
    IN_POSITION = "IN_POSITION"
    EXITING = "EXITING"
    CLOSED = "CLOSED"


class TradeTransition(str, Enum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"
    T5 = "T5"
    T6 = "T6"
    T7 = "T7"
    T8 = "T8"
    T9 = "T9"
    T10 = "T10"
    T11 = "T11"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class TradeSetup(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: TradeState
    transition: TradeTransition
    side: OrderSide
    order_type: OrderType
    entry_price: float
    stop_price: float
    target_price: float
    confidence: float
    signal_ids: list[SignalId]
    bar_index: int


__all__ = [
    "OrderSide",
    "OrderType",
    "TradeSetup",
    "TradeState",
    "TradeTransition",
]
