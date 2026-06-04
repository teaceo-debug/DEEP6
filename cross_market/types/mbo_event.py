"""Core MBO event types for synthetic and live order book processing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MBOSide(str, Enum):
    """Normalized side representation used by the cross_market package."""

    BID = "B"
    ASK = "A"
    BUY = "BUY"
    SELL = "SELL"
    UNKNOWN = "UNKNOWN"


class MBOAction(str, Enum):
    """Normalized MBO action codes."""

    ADD = "add"
    CANCEL = "cancel"
    MODIFY = "modify"
    TRADE = "trade"
    FILL = "fill"
    CLEAR = "clear"


@dataclass(slots=True)
class MBOEvent:
    """Synthetic/live MBO event consumed by the reconstructor.

    This is a temporary local implementation for Task 10 because the shared types
    module referenced by the plan is not present yet in the workspace.
    """

    action: MBOAction
    side: MBOSide
    price: float
    size: int
    order_id: str
    timestamp_exchange_ns: int
    sequence_id: int
    timestamp_receive_ns: int = 0
    symbol: str = "NQ"
    priority: int | None = None
