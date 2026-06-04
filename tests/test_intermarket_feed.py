from __future__ import annotations

import asyncio
import types
from typing import Any
from unittest.mock import AsyncMock

import pytest

from deep6.engines.intermarket_feed import DataType, IntermarketFeed
from deep6.engines.intermarket_registry import IntermarketRegistry


class EventHook:
    def __init__(self) -> None:
        self._callbacks: list[Any] = []

    def __iadd__(self, callback: Any):
        self._callbacks.append(callback)
        return self

    async def fire(self, *args: Any, **kwargs: Any) -> None:
        for callback in list(self._callbacks):
            result = callback(*args, **kwargs)
            if hasattr(result, "__await__"):
                await result


class FakeClient:
    def __init__(self) -> None:
        self.on_tick = EventHook()
        self.on_connected = EventHook()
        self.on_disconnected = EventHook()
        self.connect = AsyncMock(side_effect=self._connect)
        self.disconnect = AsyncMock()
        self.get_front_month_contract = AsyncMock(side_effect=self._front_month)
        self.subscribe_to_market_data = AsyncMock(side_effect=self._subscribe)
        self.unsubscribe_from_market_data = AsyncMock()
        self.front_months = {("ZN", "CME"): "ZNM6", ("RTY", "CME"): "RTYM6"}
        self.fail_symbols: set[str] = set()
        self.subscriptions: list[tuple[str, str, DataType]] = []

    async def _connect(self) -> None:
        await self.on_connected.fire()

    async def _front_month(self, symbol: str, exchange: str) -> str:
        return self.front_months[(symbol, exchange)]

    async def _subscribe(self, security_code: str, exchange: str, data_type: DataType) -> None:
        if security_code in self.fail_symbols:
            raise RuntimeError(f"cannot subscribe {security_code}")
        self.subscriptions.append((security_code, exchange, data_type))

    async def emit_trade(self, symbol: str, price: float, size: float, ts: float) -> None:
        tick = types.SimpleNamespace(
            data_type=DataType.LAST_TRADE,
            symbol=symbol,
            last_trade=types.SimpleNamespace(price=price, size=size, time=ts),
        )
        await self.on_tick.fire(tick)


@pytest.fixture(autouse=True)
def fast_intermarket_sleep(monkeypatch: pytest.MonkeyPatch):
    real_sleep = asyncio.sleep

    async def _sleep(_: float) -> None:
        await real_sleep(0)

    monkeypatch.setattr("deep6.engines.intermarket_feed.asyncio.sleep", _sleep)


@pytest.fixture
def config() -> Any:
    return types.SimpleNamespace(
        rithmic_user="user",
        rithmic_password="secret",
        rithmic_system_name="Rithmic Test",
        rithmic_uri="wss://rituz00100.rithmic.com:443",
    )
@pytest.mark.asyncio
async def test_bar_callback_fires_when_tick_crosses_interval(config: Any) -> None:
    registry = IntermarketRegistry()
    client = FakeClient()
    bars = []
    feed = IntermarketFeed(
        registry,
        on_bar=lambda symbol, bar: bars.append((symbol, bar)),
        config=config,
        client_factory=lambda **_: client,
    )

    await feed.start(["ZN"])
    await asyncio.sleep(0)
    await client.emit_trade("ZNM6", 100.0, 2.0, 120.0)
    await client.emit_trade("ZNM6", 101.0, 3.0, 180.0)

    assert len(bars) == 1
    symbol, bar = bars[0]
    assert symbol == "ZN"
    assert bar.open == 100.0
    assert bar.close == 100.0
    assert bar.volume == 2.0
    assert bar.bar_start_ts == 120.0
    assert bar.bar_end_ts == 180.0

    await feed.stop()


@pytest.mark.asyncio
async def test_registry_updated_on_tick(config: Any) -> None:
    registry = IntermarketRegistry()
    client = FakeClient()
    feed = IntermarketFeed(
        registry,
        config=config,
        client_factory=lambda **_: client,
    )

    await feed.start(["ZN"])
    await asyncio.sleep(0)
    await client.emit_trade("ZNM6", 4321.25, 1.0, 250.0)

    state = registry.get_state("ZN")
    assert state is not None
    assert state.last_value == 4321.25
    assert state.last_update_ts == 250.0
    assert state.is_connected is True

    await feed.stop()


@pytest.mark.asyncio
async def test_gracefully_handles_symbol_subscription_failure(config: Any) -> None:
    registry = IntermarketRegistry()
    client = FakeClient()
    client.fail_symbols.add("DXY")
    feed = IntermarketFeed(
        registry,
        config=config,
        client_factory=lambda **_: client,
    )

    await feed.start(["DXY"])
    await asyncio.sleep(0)

    assert registry.get_state("DXY").is_connected is False
    assert feed._running is True

    await feed.stop()


@pytest.mark.asyncio
async def test_partial_symbol_failure_does_not_kill_feed(config: Any) -> None:
    registry = IntermarketRegistry()
    client = FakeClient()
    client.fail_symbols.add("DXY")
    feed = IntermarketFeed(
        registry,
        config=config,
        client_factory=lambda **_: client,
    )

    await feed.start(["ZN", "DXY"])
    await asyncio.sleep(0)
    await client.emit_trade("ZNM6", 99.5, 4.0, 300.0)

    zn_state = registry.get_state("ZN")
    dxy_state = registry.get_state("DXY")
    assert zn_state is not None and zn_state.last_value == 99.5
    assert dxy_state is not None and dxy_state.is_connected is False
    assert feed._running is True

    await feed.stop()


@pytest.mark.asyncio
async def test_stop_flushes_partial_bars(config: Any) -> None:
    registry = IntermarketRegistry()
    client = FakeClient()
    bars = []
    feed = IntermarketFeed(
        registry,
        on_bar=lambda symbol, bar: bars.append((symbol, bar)),
        config=config,
        client_factory=lambda **_: client,
    )

    await feed.start(["ZN"])
    await asyncio.sleep(0)
    await client.emit_trade("ZNM6", 100.5, 7.0, 120.0)
    await feed.stop()

    assert len(bars) == 1
    symbol, bar = bars[0]
    assert symbol == "ZN"
    assert bar.open == 100.5
    assert bar.close == 100.5
    assert bar.volume == 7.0
    assert bar.tick_count == 1
