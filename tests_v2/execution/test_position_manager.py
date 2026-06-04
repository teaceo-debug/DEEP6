from __future__ import annotations

from deep6v2.execution.position_manager import PositionManager
from deep6v2.types.execution import OrderSide


def test_buy_then_sell_transitions_long_to_flat() -> None:
    manager = PositionManager()

    manager.on_fill(OrderSide.BUY, size=1, price=21000.0)
    assert manager.is_flat is False
    assert manager.current_size == 1
    assert manager.avg_price == 21000.0

    manager.on_fill(OrderSide.SELL, size=1, price=21001.0)

    assert manager.is_flat is True
    assert manager.current_size == 0
    assert manager.avg_price == 0.0


def test_unrealized_pnl_calculation() -> None:
    manager = PositionManager()

    manager.on_fill(OrderSide.BUY, size=2, price=21000.0)
    unrealized = manager.update_mark(21001.5)

    assert unrealized == 60.0


def test_record_close_returns_realized_pnl() -> None:
    manager = PositionManager()

    manager.on_fill(OrderSide.BUY, size=1, price=21000.0)
    realized = manager.record_close(21002.0)

    assert realized == 40.0
    assert manager.is_flat is True
    assert manager.trade_count == 1
    assert manager.total_pnl == 40.0


def test_win_rate_calculation() -> None:
    manager = PositionManager()

    manager.on_fill(OrderSide.BUY, size=1, price=21000.0)
    manager.record_close(21001.0)
    manager.on_fill(OrderSide.BUY, size=1, price=21000.0)
    manager.record_close(20999.0)

    assert manager.win_rate == 0.5
