"""Tests for DEEP6 v2 FastAPI endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from deep6v2.api.app import app, state


@pytest.fixture()
def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    """Reset shared state between tests."""
    state.system_status = "idle"
    state.rithmic_connected = False
    state.bars_processed = 0
    state.last_position = {
        "symbol": "NQ",
        "size": 0,
        "avg_price": 0.0,
        "unrealized_pnl": 0.0,
    }
    state.signal_subscribers.clear()
    state.score_subscribers.clear()
    state.bar_connections.clear()


@pytest.mark.asyncio()
async def test_health(client: AsyncClient) -> None:
    async with client:
        r = await client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["system_status"] == "idle"
        assert data["rithmic_connected"] is False
        assert data["bars_processed"] == 0


@pytest.mark.asyncio()
async def test_position(client: AsyncClient) -> None:
    async with client:
        r = await client.get("/position")
        assert r.status_code == 200
        data = r.json()
        assert data["symbol"] == "NQ"
        assert data["size"] == 0


@pytest.mark.asyncio()
async def test_config(client: AsyncClient) -> None:
    async with client:
        r = await client.get("/config")
        assert r.status_code == 200
        data = r.json()
        assert data["scoring"]["type_a"] == 80
        assert data["execution"]["dry_run"] is True


@pytest.mark.asyncio()
async def test_kill_switch(client: AsyncClient) -> None:
    async with client:
        r = await client.post("/kill-switch")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "killed"
        assert data["message"] == "Kill switch activated"
        assert state.system_status == "killed"


@pytest.mark.asyncio()
async def test_kill_switch_persists(client: AsyncClient) -> None:
    """After kill switch, health reports killed status."""
    async with client:
        await client.post("/kill-switch")
        r = await client.get("/health")
        assert r.json()["system_status"] == "killed"
