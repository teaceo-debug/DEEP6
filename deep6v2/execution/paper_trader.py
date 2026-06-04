from __future__ import annotations

from deep6v2.execution.rithmic_broker import MockBroker


class PaperTrader:
    """Simulated execution for paper trading validation."""

    def __init__(self, slippage_ticks: float = 1.0) -> None:
        self._broker = MockBroker(slippage=slippage_ticks * 0.25)
        self._trades: list[dict] = []
        self._daily_pnl: float = 0.0
        self._max_drawdown: float = 0.0
        self._peak_pnl: float = 0.0

    async def execute_entry(self, symbol: str, side, size: int, price: float) -> str:
        from deep6v2.execution.rithmic_broker import OrderRequest
        from deep6v2.types.execution import OrderType

        req = OrderRequest(symbol=symbol, side=side, order_type=OrderType.MARKET, size=size)
        return await self._broker.submit_order(req)

    async def execute_exit(self, symbol: str, side, size: int) -> str:
        from deep6v2.execution.rithmic_broker import OrderRequest
        from deep6v2.types.execution import OrderType

        req = OrderRequest(symbol=symbol, side=side, order_type=OrderType.MARKET, size=size)
        return await self._broker.submit_order(req)

    def record_result(self, pnl: float) -> None:
        self._trades.append({"pnl": pnl})
        self._daily_pnl += pnl
        self._peak_pnl = max(self._peak_pnl, self._daily_pnl)
        self._max_drawdown = min(self._max_drawdown, self._daily_pnl - self._peak_pnl)

    @property
    def trade_count(self) -> int:
        return len(self._trades)

    @property
    def win_rate(self) -> float:
        if not self._trades:
            return 0.0
        return sum(1 for t in self._trades if t["pnl"] > 0) / len(self._trades)

    @property
    def total_pnl(self) -> float:
        return sum(t["pnl"] for t in self._trades)

    @property
    def max_drawdown(self) -> float:
        return self._max_drawdown


__all__ = ["PaperTrader"]
