"""Aggregated MBP view derived from MBO state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from cross_market.book.mbo_order_book import MBOOrderBook, TICK_SIZE


@dataclass(slots=True)
class MBPLevel:
    price: float
    size: int
    order_count: int


class MBPOrderBook:
    """Aggregated view derived from MBO book. Not a primary data source."""

    def __init__(self, mbo_book: MBOOrderBook, n_levels: int = 40) -> None:
        self._mbo = mbo_book
        self._n = n_levels

    @property
    def bids(self) -> List[MBPLevel]:
        levels = sorted(self._mbo.bids.keys(), reverse=True)[: self._n]
        return [
            MBPLevel(
                price=tick * TICK_SIZE,
                size=self._mbo.bids[tick].total_size,
                order_count=self._mbo.bids[tick].order_count,
            )
            for tick in levels
        ]

    @property
    def asks(self) -> List[MBPLevel]:
        levels = sorted(self._mbo.asks.keys())[: self._n]
        return [
            MBPLevel(
                price=tick * TICK_SIZE,
                size=self._mbo.asks[tick].total_size,
                order_count=self._mbo.asks[tick].order_count,
            )
            for tick in levels
        ]

    @property
    def best_bid(self) -> float | None:
        return self._mbo.best_bid()

    @property
    def best_ask(self) -> float | None:
        return self._mbo.best_ask()

    @property
    def spread_ticks(self) -> float | None:
        best_bid = self.best_bid
        best_ask = self.best_ask
        if best_bid is None or best_ask is None:
            return None
        return (best_ask - best_bid) / TICK_SIZE
