from __future__ import annotations

import asyncio

from deep6v2.execution.rithmic_broker import Fill, MockBroker, OrderRequest
from deep6v2.types.execution import OrderSide, OrderType


def test_mock_broker_market_order_immediate_fill() -> None:
    broker = MockBroker(initial_prices={"NQ": 21000.0})

    order_id = asyncio.run(
        broker.submit_order(
            OrderRequest(symbol="NQ", side=OrderSide.BUY, order_type=OrderType.MARKET, size=1)
        )
    )

    fills = asyncio.run(broker.get_fills())

    assert order_id == fills[0].order_id
    assert fills[0].price == 21000.25
    assert fills[0].side is OrderSide.BUY


def test_mock_broker_position_tracking_buy_to_flat() -> None:
    broker = MockBroker(initial_prices={"NQ": 21000.0})

    asyncio.run(
        broker.submit_order(
            OrderRequest(symbol="NQ", side=OrderSide.BUY, order_type=OrderType.MARKET, size=1)
        )
    )
    broker.update_market_price("NQ", 21001.0)
    long_position = asyncio.run(broker.query_position("NQ"))

    broker.update_market_price("NQ", 21001.0)
    asyncio.run(
        broker.submit_order(
            OrderRequest(symbol="NQ", side=OrderSide.SELL, order_type=OrderType.MARKET, size=1)
        )
    )
    flat_position = asyncio.run(broker.query_position("NQ"))

    assert long_position.size == 1
    assert long_position.avg_price == 21000.25
    assert long_position.unrealized_pnl == 0.75
    assert flat_position.size == 0
    assert flat_position.avg_price == 0.0


def test_mock_broker_limit_order_fills_when_price_crosses() -> None:
    broker = MockBroker(initial_prices={"NQ": 21005.0})

    order_id = asyncio.run(
        broker.submit_order(
            OrderRequest(symbol="NQ", side=OrderSide.BUY, order_type=OrderType.LIMIT, size=2, price=21000.0)
        )
    )

    assert asyncio.run(broker.get_fills()) == []

    broker.update_market_price("NQ", 21000.0)
    asyncio.run(broker._evaluate_open_orders("NQ"))
    fills = asyncio.run(broker.get_fills())
    position = asyncio.run(broker.query_position("NQ"))

    assert fills == [
        Fill(
            order_id=order_id,
            symbol="NQ",
            side=OrderSide.BUY,
            size=2,
            price=21000.0,
            timestamp=fills[0].timestamp,
        )
    ]
    assert position.size == 2
    assert position.avg_price == 21000.0


def test_mock_broker_cancel_order_removes_pending_order() -> None:
    broker = MockBroker(initial_prices={"NQ": 21005.0})

    order_id = asyncio.run(
        broker.submit_order(
            OrderRequest(symbol="NQ", side=OrderSide.SELL, order_type=OrderType.LIMIT, size=1, price=21010.0)
        )
    )

    cancelled = asyncio.run(broker.cancel_order(order_id))
    broker.update_market_price("NQ", 21010.0)
    asyncio.run(broker._evaluate_open_orders("NQ"))

    assert cancelled is True
    assert asyncio.run(broker.get_fills()) == []


def test_mock_broker_fill_callback_fires_on_fill() -> None:
    broker = MockBroker(initial_prices={"NQ": 21000.0})
    seen: list[Fill] = []

    async def callback(fill: Fill) -> None:
        seen.append(fill)

    broker.on_fill(callback)

    asyncio.run(
        broker.submit_order(
            OrderRequest(symbol="NQ", side=OrderSide.SELL, order_type=OrderType.MARKET, size=1)
        )
    )

    fills = asyncio.run(broker.get_fills())

    assert seen == fills
