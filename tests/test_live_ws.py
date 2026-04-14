"""Tests for WSManager + /ws/live WebSocket endpoint.

TDD — RED phase: these tests must fail before Task 2 implementation.

Covers:
  1. WSManager.connect/disconnect tracks active set size
  2. broadcast() sends JSON to all connected mock sockets exactly once
  3. broadcast() continues to remaining sockets when one raises; removes dead socket
  4. POST /api/live/test-broadcast triggers broadcast to connected WS clients
  5. WS /ws/live sends initial LiveStatusMessage(connected=True) on connect

Per T-11-01: test-broadcast validates against LiveMessage TypeAdapter before broadcast.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_app():
    from deep6.api.app import app
    return app


def _make_mock_ws():
    """Return a MagicMock websocket with async send_json."""
    ws = MagicMock()
    ws.send_json = AsyncMock()
    ws.accept = AsyncMock()
    return ws


# ---------------------------------------------------------------------------
# Test 1: connect/disconnect tracks active set
# ---------------------------------------------------------------------------

def test_ws_manager_connect_disconnect():
    async def run():
        from deep6.api.ws_manager import WSManager
        manager = WSManager()
        ws1 = _make_mock_ws()
        ws2 = _make_mock_ws()

        await manager.connect(ws1)
        await manager.connect(ws2)
        assert len(manager.active) == 2

        await manager.disconnect(ws1)
        assert len(manager.active) == 1
        assert ws2 in manager.active

        await manager.disconnect(ws2)
        assert len(manager.active) == 0

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 2: broadcast sends to all connected sockets exactly once
# ---------------------------------------------------------------------------

def test_ws_manager_broadcast_sends_to_all():
    async def run():
        from deep6.api.ws_manager import WSManager
        from deep6.api.schemas import LiveStatusMessage

        manager = WSManager()
        ws1 = _make_mock_ws()
        ws2 = _make_mock_ws()
        ws3 = _make_mock_ws()

        await manager.connect(ws1)
        await manager.connect(ws2)
        await manager.connect(ws3)

        msg = LiveStatusMessage(connected=True, ts=time.time())
        await manager.broadcast(msg)

        ws1.send_json.assert_called_once()
        ws2.send_json.assert_called_once()
        ws3.send_json.assert_called_once()

        # Payload should be the model_dump dict
        payload = ws1.send_json.call_args[0][0]
        assert payload["type"] == "status"
        assert payload["connected"] is True

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 3: broadcast continues after individual failure; removes dead socket
# ---------------------------------------------------------------------------

def test_ws_manager_broadcast_tolerates_failures():
    async def run():
        from deep6.api.ws_manager import WSManager

        manager = WSManager()
        good_ws = _make_mock_ws()
        bad_ws = _make_mock_ws()
        bad_ws.send_json = AsyncMock(side_effect=RuntimeError("connection broken"))

        await manager.connect(good_ws)
        await manager.connect(bad_ws)

        await manager.broadcast({"type": "status", "connected": True, "ts": 0})

        # Good socket received the message
        good_ws.send_json.assert_called_once()
        # Bad socket removed from active
        assert bad_ws not in manager.active
        assert good_ws in manager.active

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 4: POST /api/live/test-broadcast triggers fan-out (integration)
# ---------------------------------------------------------------------------

def test_test_broadcast_endpoint_fans_out():
    app = _get_app()
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as ws:
            # Drain the initial status message
            _initial = ws.receive_json()
            assert _initial["type"] == "status"

            # POST the test-broadcast helper
            payload = {
                "type": "status",
                "connected": True,
                "pnl": 42.0,
                "circuit_breaker_active": False,
                "feed_stale": False,
                "ts": 0.0,
            }
            resp = client.post("/api/live/test-broadcast", json=payload)
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "broadcast"

            # WS client should receive the broadcast
            msg = ws.receive_json()
            assert msg["type"] == "status"
            assert msg["pnl"] == pytest.approx(42.0)


# ---------------------------------------------------------------------------
# Test 5: /ws/live sends initial LiveStatusMessage(connected=True) on connect
# ---------------------------------------------------------------------------

def test_ws_live_sends_initial_status():
    app = _get_app()
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "status"
            assert msg["connected"] is True
            assert "ts" in msg


# ---------------------------------------------------------------------------
# Test 6: T-11-01 — test-broadcast rejects invalid payload with 422
# ---------------------------------------------------------------------------

def test_test_broadcast_rejects_invalid_payload():
    """POST /api/live/test-broadcast with invalid type field returns 422."""
    app = _get_app()
    with TestClient(app) as client:
        resp = client.post("/api/live/test-broadcast", json={"type": "not_a_real_type", "foo": "bar"})
        assert resp.status_code == 422
