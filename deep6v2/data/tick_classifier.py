from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from deep6v2.state.dom import DOMState


class AggressorSide(Enum):
    BUY = "BUY"
    SELL = "SELL"
    UNSPECIFIED = "UNSPECIFIED"


@dataclass(frozen=True, slots=True)
class ClassifiedTick:
    price: float
    size: int
    timestamp: datetime
    aggressor: AggressorSide


class TickClassifier:
    """Classify raw Rithmic trade ticks as BUY, SELL, or UNSPECIFIED aggressor.

    Algorithm (D-03 gate):
    - price >= best_ask → BUY aggressor (buyer lifting the offer)
    - price <= best_bid → SELL aggressor (seller hitting the bid)
    - best_bid < price < best_ask → UNSPECIFIED (inside spread)
    - No BBO (empty DOM) → UNSPECIFIED
    """

    def __init__(self, dom_state: DOMState) -> None:
        self._dom = dom_state

    def classify(self, price: float, size: int, timestamp: datetime) -> ClassifiedTick:
        """Classify a trade tick based on current BBO."""
        best_bid = self._dom.get_best_bid()
        best_ask = self._dom.get_best_ask()

        if best_bid is None or best_ask is None:
            aggressor = AggressorSide.UNSPECIFIED
        elif price >= best_ask:
            aggressor = AggressorSide.BUY
        elif price <= best_bid:
            aggressor = AggressorSide.SELL
        else:
            aggressor = AggressorSide.UNSPECIFIED

        return ClassifiedTick(
            price=price,
            size=size,
            timestamp=timestamp,
            aggressor=aggressor,
        )

    def is_buy_aggressor(self, classified: ClassifiedTick) -> bool:
        return classified.aggressor == AggressorSide.BUY

    def is_sell_aggressor(self, classified: ClassifiedTick) -> bool:
        return classified.aggressor == AggressorSide.SELL

    def is_unspecified(self, classified: ClassifiedTick) -> bool:
        return classified.aggressor == AggressorSide.UNSPECIFIED


__all__ = ["AggressorSide", "ClassifiedTick", "TickClassifier"]
