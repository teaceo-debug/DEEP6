from __future__ import annotations

from dataclasses import dataclass

from deep6v2.types.execution import OrderSide


@dataclass
class TradeRecord:
    entry_price: float
    exit_price: float | None = None
    size: int = 1
    side: str = "BUY"
    pnl: float = 0.0
    closed: bool = False


class PositionManager:
    def __init__(self) -> None:
        self._current_size: int = 0
        self._avg_price: float = 0.0
        self._trades: list[TradeRecord] = []
        self._unrealized_pnl: float = 0.0

    @property
    def is_flat(self) -> bool:
        return self._current_size == 0

    @property
    def current_size(self) -> int:
        return self._current_size

    @property
    def avg_price(self) -> float:
        return self._avg_price

    def on_fill(self, side: OrderSide, size: int, price: float) -> None:
        """Process fill. Update position."""
        if side is OrderSide.BUY:
            self._current_size += size
        else:
            self._current_size -= size
        self._avg_price = price
        if self._current_size == 0:
            self._avg_price = 0.0

    def update_mark(self, current_price: float) -> float:
        """Update unrealized P&L. Returns unrealized."""
        if self._current_size == 0:
            self._unrealized_pnl = 0.0
        else:
            self._unrealized_pnl = (current_price - self._avg_price) * self._current_size * 20.0
        return self._unrealized_pnl

    def record_close(self, exit_price: float) -> float:
        """Close position, return realized P&L."""
        pnl = (exit_price - self._avg_price) * self._current_size * 20.0
        self._trades.append(
            TradeRecord(
                entry_price=self._avg_price,
                exit_price=exit_price,
                size=abs(self._current_size),
                side="BUY" if self._current_size >= 0 else "SELL",
                pnl=pnl,
                closed=True,
            )
        )
        self._current_size = 0
        self._avg_price = 0.0
        self._unrealized_pnl = 0.0
        return pnl

    @property
    def trade_count(self) -> int:
        return len(self._trades)

    @property
    def win_rate(self) -> float:
        closed = [t for t in self._trades if t.closed]
        if not closed:
            return 0.0
        return sum(1 for t in closed if t.pnl > 0) / len(closed)

    @property
    def total_pnl(self) -> float:
        return sum(t.pnl for t in self._trades if t.closed)


__all__ = ["PositionManager", "TradeRecord"]
