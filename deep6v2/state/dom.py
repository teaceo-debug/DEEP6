from __future__ import annotations

import array
from datetime import UTC, datetime

from deep6v2.types.dom import DOMLevel, DOMSnapshot


class DOMState:
    """Zero-allocation DOM state backed by pre-allocated arrays."""

    TICK_SIZE = 0.25
    SNAPSHOT_LEVELS = 40

    def __init__(self, base_price: float = 20000.0, num_levels: int = 4000):
        self._base_price = base_price
        self._num_levels = num_levels
        self._bid_sizes = array.array("l", [0]) * num_levels
        self._ask_sizes = array.array("l", [0]) * num_levels
        self._best_bid_idx = -1
        self._best_ask_idx = num_levels

    def _price_to_idx(self, price: float) -> int:
        return int(round((price - self._base_price) / self.TICK_SIZE))

    def _idx_to_price(self, idx: int) -> float:
        return self._base_price + (idx * self.TICK_SIZE)

    def update_level(self, side: str, price: float, size: int) -> None:
        idx = self._price_to_idx(price)
        if idx < 0 or idx >= self._num_levels:
            return

        if side == "bid":
            self._bid_sizes[idx] = size
            if size > 0:
                if idx > self._best_bid_idx:
                    self._best_bid_idx = idx
            elif idx == self._best_bid_idx:
                self._best_bid_idx = self._scan_best_bid(idx - 1)
            return

        if side == "ask":
            self._ask_sizes[idx] = size
            if size > 0:
                if idx < self._best_ask_idx:
                    self._best_ask_idx = idx
            elif idx == self._best_ask_idx:
                self._best_ask_idx = self._scan_best_ask(idx + 1)

    def _scan_best_bid(self, start_idx: int) -> int:
        for idx in range(start_idx, -1, -1):
            if self._bid_sizes[idx] > 0:
                return idx
        return -1

    def _scan_best_ask(self, start_idx: int) -> int:
        for idx in range(start_idx, self._num_levels):
            if self._ask_sizes[idx] > 0:
                return idx
        return self._num_levels

    def get_best_bid(self) -> float | None:
        if self._best_bid_idx < 0:
            return None
        return self._idx_to_price(self._best_bid_idx)

    def get_best_ask(self) -> float | None:
        if self._best_ask_idx >= self._num_levels:
            return None
        return self._idx_to_price(self._best_ask_idx)

    def depth_imbalance(self, levels: int = 5) -> float:
        bid_total = 0
        ask_total = 0

        if self._best_bid_idx >= 0:
            count = 0
            for idx in range(self._best_bid_idx, -1, -1):
                size = self._bid_sizes[idx]
                if size <= 0:
                    continue
                bid_total += size
                count += 1
                if count >= levels:
                    break

        if self._best_ask_idx < self._num_levels:
            count = 0
            for idx in range(self._best_ask_idx, self._num_levels):
                size = self._ask_sizes[idx]
                if size <= 0:
                    continue
                ask_total += size
                count += 1
                if count >= levels:
                    break

        if ask_total == 0:
            return 1.0
        return bid_total / ask_total

    def snapshot(self, timestamp: datetime | None = None) -> DOMSnapshot:
        bids: list[DOMLevel] = []
        asks: list[DOMLevel] = []

        if self._best_bid_idx >= 0:
            count = 0
            for idx in range(self._best_bid_idx, -1, -1):
                size = self._bid_sizes[idx]
                if size <= 0:
                    continue
                bids.append(DOMLevel(price=self._idx_to_price(idx), volume=size))
                count += 1
                if count >= self.SNAPSHOT_LEVELS:
                    break

        if self._best_ask_idx < self._num_levels:
            count = 0
            for idx in range(self._best_ask_idx, self._num_levels):
                size = self._ask_sizes[idx]
                if size <= 0:
                    continue
                asks.append(DOMLevel(price=self._idx_to_price(idx), volume=size))
                count += 1
                if count >= self.SNAPSHOT_LEVELS:
                    break

        return DOMSnapshot(
            timestamp=timestamp or datetime.now(UTC),
            bids=bids,
            asks=asks,
        )

    def reset(self) -> None:
        for idx in range(self._num_levels):
            self._bid_sizes[idx] = 0
            self._ask_sizes[idx] = 0

        self._best_bid_idx = -1
        self._best_ask_idx = self._num_levels


__all__ = ["DOMState"]
