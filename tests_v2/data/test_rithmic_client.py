from __future__ import annotations

import asyncio

from deep6v2.config.rithmic import RithmicConfig
from deep6v2.types.dom import DOMUpdate
from deep6v2.types.execution import OrderSide


def _make_config() -> RithmicConfig:
    return RithmicConfig(reconnect_attempts=5, reconnect_backoff_base=0.5)


def _make_update() -> DOMUpdate:
    return DOMUpdate(side=OrderSide.BUY, level=0, price=21000.25, volume=12)


class FakeAsyncRithmicClient:
    def __init__(self, **_: object) -> None:
        self.connect_calls = 0
        self.disconnect_calls = 0

    async def connect(self) -> None:
        self.connect_calls += 1

    async def disconnect(self) -> None:
        self.disconnect_calls += 1


def test_initial_state_disconnected():
    from deep6v2.data.rithmic_client import ConnectionState, RithmicClient

    client = RithmicClient(config=_make_config(), client_factory=FakeAsyncRithmicClient)

    assert client.state is ConnectionState.DISCONNECTED


def test_connect_transitions_to_connected():
    from deep6v2.data.rithmic_client import ConnectionState, RithmicClient

    client = RithmicClient(config=_make_config(), client_factory=FakeAsyncRithmicClient)

    asyncio.run(client.connect())

    assert client.state is ConnectionState.CONNECTED


def test_freeze_on_disconnect():
    from deep6v2.data.rithmic_client import ConnectionState, RithmicClient

    client = RithmicClient(config=_make_config(), client_factory=FakeAsyncRithmicClient)
    asyncio.run(client.connect())

    client.freeze()

    assert client.state is ConnectionState.FROZEN
    assert client.is_frozen() is True


def test_dom_update_rejected_when_frozen():
    from deep6v2.data.rithmic_client import RithmicClient

    received: list[DOMUpdate] = []
    client = RithmicClient(
        config=_make_config(),
        on_dom_update=received.append,
        client_factory=FakeAsyncRithmicClient,
    )
    asyncio.run(client.connect())
    client.freeze()

    client.handle_dom_update(_make_update())

    assert received == []


def test_dom_update_processed_when_connected():
    from deep6v2.data.rithmic_client import RithmicClient

    received: list[DOMUpdate] = []
    client = RithmicClient(
        config=_make_config(),
        on_dom_update=received.append,
        client_factory=FakeAsyncRithmicClient,
    )
    asyncio.run(client.connect())
    update = _make_update()

    client.handle_dom_update(update)

    assert received == [update]


def test_unfreeze_requires_reconciliation():
    from deep6v2.data.rithmic_client import ConnectionState, RithmicClient

    client = RithmicClient(config=_make_config(), client_factory=FakeAsyncRithmicClient)
    asyncio.run(client.connect())
    client.freeze()

    assert client.state is ConnectionState.FROZEN

    asyncio.run(client.reconcile_position())

    assert client.state is ConnectionState.CONNECTED
    assert client.is_frozen() is False


def test_reconnect_backoff_delays(monkeypatch):
    from deep6v2.data.rithmic_client import ConnectionState, RithmicClient

    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("deep6v2.data.rithmic_client.asyncio.sleep", fake_sleep)

    attempts = {"count": 0}

    class FlakyClient(RithmicClient):
        async def connect(self) -> None:
            self.state = ConnectionState.CONNECTING
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RuntimeError("transient failure")
            self.state = ConnectionState.CONNECTED
            self._reconnect_attempt = 0

    client = FlakyClient(config=_make_config(), client_factory=FakeAsyncRithmicClient)
    client.state = ConnectionState.CONNECTED
    client.freeze()

    asyncio.run(client.reconnect_loop())

    assert delays == [0.5, 1.0, 2.0]
    assert attempts["count"] == 3
    assert client.state is ConnectionState.CONNECTED


def test_disconnect_sets_disconnected():
    from deep6v2.data.rithmic_client import ConnectionState, RithmicClient

    client = RithmicClient(config=_make_config(), client_factory=FakeAsyncRithmicClient)
    asyncio.run(client.connect())

    asyncio.run(client.disconnect())

    assert client.state is ConnectionState.DISCONNECTED
