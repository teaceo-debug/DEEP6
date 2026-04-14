"""Tests for WebSocket ConnectionManager + /ws endpoint.

TDD: Task 1 — ws.py tests
Tests cover ConnectionManager behavior and /ws auth gating.
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import TestClient as StarletteTestClient


# ---------------------------------------------------------------------------
# ConnectionManager unit tests (pure async)
# ---------------------------------------------------------------------------

class TestConnectionManager:
    """Unit tests for ConnectionManager.broadcast() and disconnect()."""

    def test_broadcast_sends_to_all_active_connections(self):
        """broadcast() sends message to all active WebSocket connections."""
        from deep6.api.routes.ws import ConnectionManager

        manager = ConnectionManager()

        ws1 = AsyncMock()
        ws2 = AsyncMock()

        asyncio.run(manager.connect(ws1))
        asyncio.run(manager.connect(ws2))

        asyncio.run(manager.broadcast({"type": "signal", "score": 75.0}))

        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

    def test_disconnect_removes_connection_from_active_set(self):
        """disconnect() removes connection without raising errors."""
        from deep6.api.routes.ws import ConnectionManager

        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        asyncio.run(manager.connect(ws1))
        asyncio.run(manager.connect(ws2))
        assert len(manager.active) == 2

        manager.disconnect(ws1)
        assert len(manager.active) == 1
        assert ws1 not in manager.active
        assert ws2 in manager.active

    def test_disconnect_nonexistent_connection_no_error(self):
        """disconnect() on unknown connection does not raise."""
        from deep6.api.routes.ws import ConnectionManager

        manager = ConnectionManager()
        ws = AsyncMock()
        # Should not raise even though ws was never connected
        manager.disconnect(ws)

    def test_broadcast_handles_send_error_silently(self):
        """broadcast() catches WebSocketDisconnect/error and disconnects dead socket."""
        from deep6.api.routes.ws import ConnectionManager

        manager = ConnectionManager()

        ws_good = AsyncMock()
        ws_bad = AsyncMock()
        ws_bad.send_text.side_effect = RuntimeError("disconnected")

        asyncio.run(manager.connect(ws_good))
        asyncio.run(manager.connect(ws_bad))

        # Should not raise
        asyncio.run(manager.broadcast({"type": "ping"}))

        # Good connection still received message
        ws_good.send_text.assert_called_once()
        # Bad connection should be removed
        assert ws_bad not in manager.active


# ---------------------------------------------------------------------------
# /ws endpoint integration tests (via TestClient)
# ---------------------------------------------------------------------------

class TestWebSocketEndpoint:
    """Integration tests for /ws endpoint auth gating."""

    def setup_method(self):
        # Set token to known value for tests
        os.environ["WS_TOKEN"] = "test-secret-token"

    def teardown_method(self):
        # Clean up env
        os.environ.pop("WS_TOKEN", None)

    def _get_app(self):
        """Return fresh app instance."""
        from deep6.api.app import app
        return app

    def test_ws_rejects_connection_without_token(self):
        """WS endpoint closes with 1008 when no token provided."""
        app = self._get_app()
        with TestClient(app) as client:
            with pytest.raises(Exception):
                # No token — should get closed/rejected
                with client.websocket_connect("/ws") as ws:
                    ws.receive_text()  # Should fail

    def test_ws_rejects_connection_with_wrong_token(self):
        """WS endpoint closes with 1008 when wrong token provided."""
        app = self._get_app()
        with TestClient(app) as client:
            with pytest.raises(Exception):
                with client.websocket_connect("/ws?token=wrong-token") as ws:
                    ws.receive_text()

    def test_ws_accepts_connection_with_correct_token(self):
        """WS endpoint accepts connection with correct token and responds to ping."""
        app = self._get_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws?token=test-secret-token") as ws:
                ws.send_text("ping")
                response = ws.receive_text()
                assert response == "pong"

    def test_ws_responds_to_ping_with_pong(self):
        """WS endpoint echoes pong in response to ping message."""
        app = self._get_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws?token=test-secret-token") as ws:
                ws.send_text("ping")
                msg = ws.receive_text()
                assert msg == "pong"
