"""WebSocket ConnectionManager + /ws endpoint.

Per D-04: Native WebSocket API (no Socket.io).
Per D-17: /ws endpoint pushes signal/bar/position events to dashboard.
Per D-23: Bearer token auth — token from ?token= query param or Authorization header.
Per T-10-01: Close code 1008 on auth mismatch.
Per T-10-04: Broadcast catches SendError and disconnects dead sockets silently.

WS_TOKEN defaults to "deep6-dev" for local development without .env setup.
"""
from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections with broadcast support.

    Thread-safety: All methods run in the asyncio event loop.
    Dead connections are silently removed on broadcast failure (T-10-04).
    """

    def __init__(self) -> None:
        self.active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        """Accept and register a WebSocket connection."""
        await ws.accept()
        self.active.add(ws)
        log.debug("ws.connected", extra={"total": len(self.active)})

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a connection from the active set (no-op if not present)."""
        self.active.discard(ws)
        log.debug("ws.disconnected", extra={"total": len(self.active)})

    async def broadcast(self, data: dict) -> None:
        """Broadcast JSON data to all active connections.

        Per T-10-04: Any send error silently disconnects the dead socket
        without interrupting delivery to healthy connections.
        """
        message = json.dumps(data)
        dead: set[WebSocket] = set()

        for ws in list(self.active):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)

        for ws in dead:
            self.disconnect(ws)


# Module-level singleton — imported by events.py for broadcast wiring
ws_manager = ConnectionManager()

router = APIRouter(tags=["ws"])


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str | None = None) -> None:
    """WebSocket endpoint for real-time dashboard push.

    Auth: token from ?token= query param or Authorization header.
    Expected token: WS_TOKEN env var (default "deep6-dev").
    Rejects with close code 1008 on mismatch (T-10-01).

    Protocol:
    - Sends "pong" in response to "ping" messages (keepalive).
    - All other messages are ignored (server-push only model).
    """
    expected_token = os.environ.get("WS_TOKEN", "deep6-dev")

    # Check Authorization header if query param not provided
    if token is None:
        auth_header = ws.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer "):]

    if token != expected_token:
        await ws.close(code=1008)
        return

    await ws_manager.connect(ws)
    try:
        while True:
            text = await ws.receive_text()
            if text == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        ws_manager.disconnect(ws)
