"""WebSocket ConnectionManager + /ws endpoint.

Per D-04: Native WebSocket API (no Socket.io).
Per D-17: /ws endpoint pushes signal/bar/position events to dashboard.
Per D-23: Bearer token auth — token via Sec-WebSocket-Protocol subprotocol
or first-message handshake. Query-param tokens are rejected (they leak into
access logs and browser histories).
Per T-10-01: Close code 1008 on auth mismatch. Error payload includes the
marker "AUTH_FAILED_NO_RECONNECT" so the dashboard client can distinguish
policy-violation closes from transient network failures and avoid an
infinite reconnect loop.
Per T-10-04: Broadcast catches SendError and disconnects dead sockets silently.

WS_TOKEN must be set in the environment — there is no default fallback. When
the env var is unset or empty, every connection is rejected with 1008.
"""
from __future__ import annotations

import asyncio
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


_AUTH_FAIL_REASON = "AUTH_FAILED_NO_RECONNECT"


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """WebSocket endpoint for real-time dashboard push.

    Auth: token MUST be presented via one of:
      1. ``Sec-WebSocket-Protocol`` header — either the raw token, or a
         two-value list ``["bearer", "<token>"]``. The accepted subprotocol
         is echoed back so the browser's WebSocket handshake completes.
      2. First client message (JSON or raw text) sent within a short timeout
         after the socket is accepted. Format: ``{"type":"auth","token":"…"}``
         or a bare string matching the token.

    Query-param tokens are intentionally NOT supported — they are logged by
    proxies and stored in browser history. Authorization headers are not
    available on the browser WebSocket API, so Sec-WebSocket-Protocol is the
    canonical channel.

    Expected token: ``WS_TOKEN`` env var. When unset/empty, every connection
    is rejected (fail closed — no dev default).

    Rejects with close code 1008 on mismatch (T-10-01). The close reason
    contains ``AUTH_FAILED_NO_RECONNECT`` so clients can break out of a
    reconnect loop on policy-violation closes.

    Protocol after auth:
    - Sends "pong" in response to "ping" messages (keepalive).
    - All other messages are ignored (server-push only model).
    """
    expected_token = os.environ.get("WS_TOKEN", "")

    if not expected_token:
        # Fail closed — never run with a default token.
        await ws.close(code=1008, reason=_AUTH_FAIL_REASON)
        return

    # --- Phase 1: Sec-WebSocket-Protocol subprotocol auth ----------------
    subprotocol_header = ws.headers.get("sec-websocket-protocol", "")
    offered = [p.strip() for p in subprotocol_header.split(",") if p.strip()]
    token: str | None = None
    accept_subprotocol: str | None = None

    if offered:
        # Two common patterns: ["bearer", "<token>"] or just ["<token>"].
        if len(offered) >= 2 and offered[0].lower() == "bearer":
            token = offered[1]
            accept_subprotocol = offered[0]
        else:
            token = offered[0]
            accept_subprotocol = offered[0]

    if token is not None:
        if token != expected_token:
            await ws.close(code=1008, reason=_AUTH_FAIL_REASON)
            return
        await ws.accept(subprotocol=accept_subprotocol)
    else:
        # --- Phase 2: first-message handshake auth -----------------------
        await ws.accept()
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=5.0)
        except (asyncio.TimeoutError, WebSocketDisconnect, Exception):
            await ws.close(code=1008, reason=_AUTH_FAIL_REASON)
            return

        handshake_token: str | None = None
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict) and payload.get("type") == "auth":
                handshake_token = payload.get("token")
        except (ValueError, TypeError):
            handshake_token = raw.strip() or None

        if handshake_token != expected_token:
            await ws.close(code=1008, reason=_AUTH_FAIL_REASON)
            return

    # Already accepted above — register and move to the ping/pong loop.
    ws_manager.active.add(ws)
    log.debug("ws.connected", extra={"total": len(ws_manager.active)})
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
