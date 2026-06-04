"""Per-order lifecycle tracking for MBO events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(slots=True)
class LifecycleRecord:
    order_id: str
    price: float
    size: int
    side: str
    add_time_ns: int
    cancel_time_ns: Optional[int] = None
    trade_time_ns: Optional[int] = None
    fills: List[int] = field(default_factory=list)
    modify_count: int = 0

    @property
    def life_ms(self) -> Optional[float]:
        if self.cancel_time_ns is not None:
            return (self.cancel_time_ns - self.add_time_ns) / 1e6
        return None

    @property
    def fill_ratio(self) -> float:
        if self.size == 0:
            return 0.0
        return sum(self.fills) / self.size

    @property
    def was_filled(self) -> bool:
        return sum(self.fills) > 0

    @property
    def total_filled(self) -> int:
        return sum(self.fills)


class OrderLifecycleTracker:
    def __init__(self) -> None:
        self._records: Dict[str, LifecycleRecord] = {}

    def on_add(self, order_id: str, price: float, size: int, side: str, ts_ns: int) -> None:
        self._records[order_id] = LifecycleRecord(
            order_id=order_id,
            price=price,
            size=size,
            side=side,
            add_time_ns=ts_ns,
        )

    def on_cancel(self, order_id: str, ts_ns: int) -> Optional[LifecycleRecord]:
        record = self._records.get(order_id)
        if record is not None:
            record.cancel_time_ns = ts_ns
        return record

    def on_trade(self, order_id: str, fill_size: int, ts_ns: int) -> None:
        record = self._records.get(order_id)
        if record is not None:
            record.fills.append(fill_size)
            if record.trade_time_ns is None:
                record.trade_time_ns = ts_ns

    def on_modify(self, order_id: str, new_size: int) -> None:
        record = self._records.get(order_id)
        if record is not None:
            record.size = new_size
            record.modify_count += 1

    def get(self, order_id: str) -> Optional[LifecycleRecord]:
        return self._records.get(order_id)

    def get_cancelled_unfilled(self, min_size: int = 0) -> List[LifecycleRecord]:
        return [
            record
            for record in self._records.values()
            if record.cancel_time_ns is not None and not record.was_filled and record.size >= min_size
        ]
