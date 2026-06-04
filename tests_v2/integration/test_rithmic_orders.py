"""Paper-trading integration coverage for broker order flow.

These tests are opt-in and intentionally guarded to avoid accidental live routing.
They document the expected async-rithmic usage behind ``RithmicBroker``.
"""

from __future__ import annotations

import os

import pytest

from deep6v2.config.rithmic import RithmicConfig
from deep6v2.execution.rithmic_broker import OrderRequest, RithmicBroker
from deep6v2.types.execution import OrderSide, OrderType

pytestmark = pytest.mark.integration


def _integration_guard() -> None:
    if not os.environ.get("RITHMIC_USER"):
        pytest.skip("RITHMIC_USER not configured")

    if os.environ.get("RITHMIC_ALLOW_ORDER_TESTS") != "1":
        pytest.skip("Set RITHMIC_ALLOW_ORDER_TESTS=1 to enable paper-order integration tests")

    system_name = os.environ.get("RITHMIC_SYSTEM_NAME", "")
    if "paper" not in system_name.lower():
        pytest.skip("Integration order tests are restricted to paper-trading environments")


def _build_config() -> RithmicConfig:
    return RithmicConfig(
        uri=os.environ.get("RITHMIC_URI", "wss://rituz00100.rithmic.com"),
        username=os.environ["RITHMIC_USER"],
        password=os.environ["RITHMIC_PASSWORD"],
        system_name=os.environ["RITHMIC_SYSTEM_NAME"],
        app_name=os.environ.get("RITHMIC_APP_NAME", "deep6v2"),
    )


@pytest.mark.asyncio
async def test_market_order_lifecycle() -> None:
    """Submit a paper market order and assert the broker records a fill callback."""
    _integration_guard()

    broker = RithmicBroker(config=_build_config(), exchange=os.environ.get("RITHMIC_EXCHANGE", "CME"))

    try:
        seen = []
        broker.on_fill(lambda fill: seen.append(fill))

        order_id = await broker.submit_order(
            OrderRequest(symbol=os.environ.get("RITHMIC_SYMBOL", "NQ"), side=OrderSide.BUY, order_type=OrderType.MARKET, size=1)
        )

        fills = await broker.get_fills()

        assert order_id
        assert all(fill.order_id for fill in fills)
        assert seen == fills
    finally:
        await broker.disconnect()


@pytest.mark.asyncio
async def test_limit_order_submit_and_cancel() -> None:
    """Submit a distant paper limit order, then cancel it through the broker abstraction."""
    _integration_guard()

    broker = RithmicBroker(config=_build_config(), exchange=os.environ.get("RITHMIC_EXCHANGE", "CME"))

    try:
        order_id = await broker.submit_order(
            OrderRequest(
                symbol=os.environ.get("RITHMIC_SYMBOL", "NQ"),
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                size=1,
                price=float(os.environ.get("RITHMIC_TEST_LIMIT_PRICE", "1.0")),
            )
        )

        assert order_id
        assert await broker.cancel_order(order_id) is True
    finally:
        await broker.disconnect()
