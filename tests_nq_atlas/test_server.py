"""Test FastAPI endpoints via ASGI transport."""
import pytest
import httpx
from httpx import ASGITransport
from nq_atlas.server import app


@pytest.mark.asyncio
async def test_health_endpoint():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert data["status"] in ("ok", "degraded")


@pytest.mark.asyncio
async def test_bias_endpoint_returns_neutral_when_empty():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/bias")
        assert r.status_code == 200
        data = r.json()
        assert "direction" in data
        assert "conviction" in data


@pytest.mark.asyncio
async def test_state_endpoint():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/state")
        assert r.status_code == 200
        data = r.json()
        assert "spots" in data


@pytest.mark.asyncio
async def test_dashboard_endpoint_returns_html():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/dashboard")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
