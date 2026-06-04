from __future__ import annotations

import pytest

from deep6v2.execution.paper_trader import PaperTrader
from deep6v2.types.execution import OrderSide


@pytest.fixture
def trader() -> PaperTrader:
    return PaperTrader(slippage_ticks=1.0)


class TestPaperTraderExecution:
    @pytest.mark.asyncio
    async def test_execute_entry_returns_order_id(self, trader: PaperTrader) -> None:
        trader._broker.update_market_price("NQ", 20000.0)
        order_id = await trader.execute_entry("NQ", OrderSide.BUY, 1, 20000.0)
        assert isinstance(order_id, str)
        assert len(order_id) > 0

    @pytest.mark.asyncio
    async def test_execute_exit_returns_order_id(self, trader: PaperTrader) -> None:
        trader._broker.update_market_price("NQ", 20000.0)
        await trader.execute_entry("NQ", OrderSide.BUY, 1, 20000.0)
        order_id = await trader.execute_exit("NQ", OrderSide.SELL, 1)
        assert isinstance(order_id, str)
        assert len(order_id) > 0

    @pytest.mark.asyncio
    async def test_execute_entry_creates_fill(self, trader: PaperTrader) -> None:
        trader._broker.update_market_price("NQ", 20000.0)
        await trader.execute_entry("NQ", OrderSide.BUY, 1, 20000.0)
        fills = await trader._broker.get_fills()
        assert len(fills) == 1
        assert fills[0].side == OrderSide.BUY
        assert fills[0].size == 1

    @pytest.mark.asyncio
    async def test_execute_entry_applies_slippage(self, trader: PaperTrader) -> None:
        trader._broker.update_market_price("NQ", 20000.0)
        await trader.execute_entry("NQ", OrderSide.BUY, 1, 20000.0)
        fills = await trader._broker.get_fills()
        # slippage_ticks=1.0 -> slippage=0.25; BUY fills at market + slippage
        assert fills[0].price == 20000.25


class TestPaperTraderRecording:
    def test_record_result_tracks_pnl(self, trader: PaperTrader) -> None:
        trader.record_result(100.0)
        trader.record_result(-50.0)
        assert trader.trade_count == 2
        assert trader.total_pnl == pytest.approx(50.0)

    def test_win_rate_calculation(self, trader: PaperTrader) -> None:
        trader.record_result(100.0)
        trader.record_result(-50.0)
        trader.record_result(200.0)
        trader.record_result(75.0)
        assert trader.win_rate == pytest.approx(0.75)

    def test_win_rate_empty(self, trader: PaperTrader) -> None:
        assert trader.win_rate == 0.0

    def test_max_drawdown_tracking(self, trader: PaperTrader) -> None:
        trader.record_result(100.0)   # daily=100, peak=100, dd=0
        trader.record_result(50.0)    # daily=150, peak=150, dd=0
        trader.record_result(-200.0)  # daily=-50, peak=150, dd=-200
        trader.record_result(-100.0)  # daily=-150, peak=150, dd=-300
        trader.record_result(400.0)   # daily=250, peak=250, dd=-300 (max dd unchanged)
        assert trader.max_drawdown == pytest.approx(-300.0)

    def test_max_drawdown_starts_at_zero(self, trader: PaperTrader) -> None:
        assert trader.max_drawdown == 0.0

    def test_trade_count_increments(self, trader: PaperTrader) -> None:
        assert trader.trade_count == 0
        trader.record_result(10.0)
        assert trader.trade_count == 1
        trader.record_result(-5.0)
        assert trader.trade_count == 2
