"""Tests for DEEP6 v2 session replay API endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from deep6v2.api.app import app


@pytest.fixture()
def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# -- /replay/sessions -------------------------------------------------------


@pytest.mark.asyncio()
async def test_list_sessions(client: AsyncClient) -> None:
    async with client:
        r = await client.get("/replay/sessions")
        assert r.status_code == 200
        data = r.json()
        assert "sessions" in data
        assert "total" in data
        assert isinstance(data["sessions"], list)


@pytest.mark.asyncio()
async def test_list_sessions_with_limit(client: AsyncClient) -> None:
    async with client:
        r = await client.get("/replay/sessions", params={"limit": 10})
        assert r.status_code == 200


@pytest.mark.asyncio()
async def test_list_sessions_invalid_limit(client: AsyncClient) -> None:
    async with client:
        r = await client.get("/replay/sessions", params={"limit": 0})
        assert r.status_code == 422  # Validation error


# -- /replay/{session_id}/bars ----------------------------------------------


@pytest.mark.asyncio()
async def test_get_bars(client: AsyncClient) -> None:
    async with client:
        r = await client.get("/replay/test-session/bars")
        assert r.status_code == 200
        data = r.json()
        assert "bars" in data
        assert data["session_id"] == "test-session"
        assert data["total"] == 0


@pytest.mark.asyncio()
async def test_get_bars_pagination(client: AsyncClient) -> None:
    async with client:
        r = await client.get("/replay/test-session/bars", params={"offset": 10, "limit": 50})
        assert r.status_code == 200
        data = r.json()
        assert data["offset"] == 10
        assert data["limit"] == 50


# -- /replay/{session_id}/signals -------------------------------------------


@pytest.mark.asyncio()
async def test_get_signals(client: AsyncClient) -> None:
    async with client:
        r = await client.get("/replay/test-session/signals")
        assert r.status_code == 200
        data = r.json()
        assert "signals" in data
        assert data["session_id"] == "test-session"


@pytest.mark.asyncio()
async def test_get_signals_pagination(client: AsyncClient) -> None:
    async with client:
        r = await client.get("/replay/test-session/signals", params={"offset": 5, "limit": 25})
        assert r.status_code == 200
        data = r.json()
        assert data["offset"] == 5
        assert data["limit"] == 25


# -- /replay/{session_id}/scores -------------------------------------------


@pytest.mark.asyncio()
async def test_get_scores(client: AsyncClient) -> None:
    async with client:
        r = await client.get("/replay/test-session/scores")
        assert r.status_code == 200
        data = r.json()
        assert "scores" in data
        assert data["session_id"] == "test-session"
        assert data["total"] == 0


# -- /replay/{session_id}/trades -------------------------------------------


@pytest.mark.asyncio()
async def test_get_trades(client: AsyncClient) -> None:
    async with client:
        r = await client.get("/replay/test-session/trades")
        assert r.status_code == 200
        data = r.json()
        assert "trades" in data
        assert data["session_id"] == "test-session"
        assert data["total"] == 0
