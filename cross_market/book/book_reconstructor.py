"""MBO event stream orchestrator for book reconstruction."""

from __future__ import annotations

from cross_market.book.mbo_order_book import MBOOrderBook
from cross_market.book.order_lifecycle_tracker import OrderLifecycleTracker
from cross_market.types.mbo_event import MBOAction, MBOEvent


class BookReconstructor:
    """Orchestrates MBOEvent stream -> book state + lifecycle tracking."""

    def __init__(self) -> None:
        self.book = MBOOrderBook()
        self.tracker = OrderLifecycleTracker()
        self._last_sequence = -1

    def process(self, event: MBOEvent) -> dict:
        result = {"action": event.action.value, "order_id": event.order_id}

        if event.action == MBOAction.ADD:
            self.book.on_add(
                event.order_id,
                event.price,
                event.size,
                event.side.value,
                event.timestamp_exchange_ns,
                event.priority or 0,
            )
            self.tracker.on_add(
                event.order_id,
                event.price,
                event.size,
                event.side.value,
                event.timestamp_exchange_ns,
            )
        elif event.action == MBOAction.CANCEL:
            self.book.on_cancel(event.order_id, event.timestamp_exchange_ns)
            self.tracker.on_cancel(event.order_id, event.timestamp_exchange_ns)
        elif event.action == MBOAction.MODIFY:
            self.book.on_modify(event.order_id, event.size, event.timestamp_exchange_ns)
            self.tracker.on_modify(event.order_id, event.size)
        elif event.action in (MBOAction.TRADE, MBOAction.FILL):
            self.book.on_trade(event.order_id, event.size, event.timestamp_exchange_ns)
            self.tracker.on_trade(event.order_id, event.size, event.timestamp_exchange_ns)
        elif event.action == MBOAction.CLEAR:
            self.book = MBOOrderBook()

        self._last_sequence = event.sequence_id
        result["sequence_id"] = self._last_sequence
        return result

    @property
    def best_bid(self) -> float | None:
        return self.book.best_bid()

    @property
    def best_ask(self) -> float | None:
        return self.book.best_ask()

    @property
    def microprice(self) -> float | None:
        return self.book.microprice()
