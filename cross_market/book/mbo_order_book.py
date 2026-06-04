"""Full MBO order book reconstructed from individual order events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


TICK_SIZE = 0.25


@dataclass(slots=True)
class OrderState:
    order_id: str
    price: float
    size: int
    side: str
    add_time_ns: int
    modify_count: int = 0
    priority: int = 0
    fills: List[int] = field(default_factory=list)


@dataclass(slots=True)
class PriceLevelState:
    price: float
    total_size: int = 0
    order_count: int = 0
    orders: Dict[str, OrderState] = field(default_factory=dict)


class MBOOrderBook:
    """Full MBO order book with live order and price-level state."""

    def __init__(self) -> None:
        self.orders: Dict[str, OrderState] = {}
        self.bids: Dict[int, PriceLevelState] = {}
        self.asks: Dict[int, PriceLevelState] = {}
        self.lifecycle: Dict[str, dict] = {}

    @staticmethod
    def price_to_tick(price: float) -> int:
        return round(price / TICK_SIZE)

    def on_add(
        self,
        order_id: str,
        price: float,
        size: int,
        side: str,
        ts_ns: int,
        priority: int,
    ) -> None:
        if size <= 0:
            raise ValueError("order size must be positive on add")
        if side not in {"B", "A"}:
            raise ValueError("side must be 'B' or 'A'")
        if order_id in self.orders:
            self.on_cancel(order_id, ts_ns)

        tick = self.price_to_tick(price)
        order = OrderState(
            order_id=order_id,
            price=price,
            size=size,
            side=side,
            add_time_ns=ts_ns,
            priority=priority,
        )
        self.orders[order_id] = order

        levels = self.bids if side == "B" else self.asks
        level = levels.setdefault(tick, PriceLevelState(price=price))
        level.total_size += size
        level.order_count += 1
        level.orders[order_id] = order

        self.lifecycle[order_id] = {
            "add_time": ts_ns,
            "price": price,
            "size": size,
            "side": side,
            "fills": [],
            "cancel_time": None,
            "fill_ratio": 0.0,
        }

    def on_cancel(self, order_id: str, ts_ns: int) -> Optional[OrderState]:
        order = self.orders.pop(order_id, None)
        if order is None:
            return None

        self._remove_from_level(order, order.size)

        if order_id in self.lifecycle:
            lifecycle = self.lifecycle[order_id]
            lifecycle["cancel_time"] = ts_ns
            lifecycle["life_ms"] = (ts_ns - lifecycle["add_time"]) / 1e6
            filled = sum(lifecycle["fills"])
            lifecycle["fill_ratio"] = filled / lifecycle["size"] if lifecycle["size"] > 0 else 0.0
        return order

    def on_modify(self, order_id: str, new_size: int, ts_ns: int) -> None:
        if new_size < 0:
            raise ValueError("order size cannot become negative")

        order = self.orders.get(order_id)
        if order is None:
            return
        if new_size == 0:
            self.on_cancel(order_id, ts_ns)
            return

        delta = new_size - order.size
        order.size = new_size
        order.modify_count += 1

        tick = self.price_to_tick(order.price)
        levels = self.bids if order.side == "B" else self.asks
        level = levels.get(tick)
        if level is not None:
            level.total_size += delta
            if level.total_size < 0:
                raise ValueError("price level size cannot become negative")

        if order_id in self.lifecycle:
            self.lifecycle[order_id]["size"] = new_size

    def on_trade(self, order_id: str, fill_size: int, ts_ns: int) -> None:
        if fill_size <= 0:
            raise ValueError("fill size must be positive")
        if order_id in self.lifecycle:
            self.lifecycle[order_id]["fills"].append(fill_size)
            self.lifecycle[order_id].setdefault("first_fill_time", ts_ns)

        order = self.orders.get(order_id)
        if order is None:
            return

        actual_fill = min(fill_size, order.size)
        order.fills.append(actual_fill)
        order.size -= actual_fill
        if order.size < 0:
            raise ValueError("order size cannot become negative")

        tick = self.price_to_tick(order.price)
        levels = self.bids if order.side == "B" else self.asks
        level = levels.get(tick)
        if level is not None:
            level.total_size -= actual_fill
            if level.total_size < 0:
                raise ValueError("price level size cannot become negative")

        if order.size == 0:
            self.orders.pop(order_id, None)
            if level is not None:
                level.order_count -= 1
                level.orders.pop(order_id, None)
                if level.order_count <= 0 or level.total_size <= 0:
                    levels.pop(tick, None)

        if order_id in self.lifecycle:
            lifecycle = self.lifecycle[order_id]
            filled = sum(lifecycle["fills"])
            lifecycle["fill_ratio"] = filled / lifecycle["size"] if lifecycle["size"] > 0 else 0.0

    def best_bid(self) -> Optional[float]:
        return max(self.bids) * TICK_SIZE if self.bids else None

    def best_ask(self) -> Optional[float]:
        return min(self.asks) * TICK_SIZE if self.asks else None

    def mid(self) -> Optional[float]:
        best_bid = self.best_bid()
        best_ask = self.best_ask()
        if best_bid is None or best_ask is None:
            return None
        return (best_bid + best_ask) / 2.0

    def microprice(self) -> Optional[float]:
        best_bid_tick = max(self.bids) if self.bids else None
        best_ask_tick = min(self.asks) if self.asks else None
        if best_bid_tick is None or best_ask_tick is None:
            return None

        bid_size = self.bids[best_bid_tick].total_size
        ask_size = self.asks[best_ask_tick].total_size
        total = bid_size + ask_size
        if total == 0:
            return None
        return (best_ask_tick * TICK_SIZE * bid_size + best_bid_tick * TICK_SIZE * ask_size) / total

    def get_depth(self, n_levels: int = 10) -> tuple[list[tuple[float, int, int]], list[tuple[float, int, int]]]:
        bid_levels = [
            (tick * TICK_SIZE, self.bids[tick].total_size, self.bids[tick].order_count)
            for tick in sorted(self.bids, reverse=True)[:n_levels]
        ]
        ask_levels = [
            (tick * TICK_SIZE, self.asks[tick].total_size, self.asks[tick].order_count)
            for tick in sorted(self.asks)[:n_levels]
        ]
        return bid_levels, ask_levels

    def _remove_from_level(self, order: OrderState, remove_size: int) -> None:
        tick = self.price_to_tick(order.price)
        levels = self.bids if order.side == "B" else self.asks
        level = levels.get(tick)
        if level is None:
            return

        level.total_size -= remove_size
        level.order_count -= 1
        level.orders.pop(order.order_id, None)
        if level.total_size < 0:
            raise ValueError("price level size cannot become negative")
        if level.order_count <= 0 or level.total_size <= 0:
            levels.pop(tick, None)
