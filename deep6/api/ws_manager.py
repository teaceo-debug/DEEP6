"""WSManager — WebSocket connection set + broadcast fan-out.

Per D-10: ONE WebSocket multiplexes all streams. All clients receive a mix of
LiveBarMessage / LiveSignalMessage / LiveScoreMessage / LiveStatusMessage,
discriminated by the 'type' field.

Per T-11-03: stale sockets are discovered and removed on the next broadcast
attempt (send raises an exception); no unbounded growth beyond live connections.

Singleton pattern: the app lifespan sets ``app.state.ws_manager = WSManager()``
and route handlers reach it via ``request.app.state.ws_manager``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket
from pydantic import BaseModel

log = logging.getLogger(__name__)


class WSManager:
    """Connection set + broadcast fan-out singleton.

    Thread-safety: All methods are coroutines running in the asyncio event loop.
    The internal ``_lock`` prevents race conditions on connect/disconnect vs
    broadcast snapshot operations.
    """

    def __init__(self) -> None:
        self.active: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        """Accept the WebSocket handshake and register the connection."""
        await ws.accept()
        async with self._lock:
            self.active.add(ws)
        log.debug("ws.connected total=%d", len(self.active))

    async def disconnect(self, ws: WebSocket) -> None:
        """Remove a connection from the active set (no-op if not present)."""
        async with self._lock:
            self.active.discard(ws)
        log.debug("ws.disconnected total=%d", len(self.active))

    async def broadcast(self, message: BaseModel | dict[str, Any]) -> None:
        """Fan-out one message to all active connections.

        Accepts a Pydantic model (serialized via model_dump) or a plain dict.

        Per T-11-03: individual send failures do not block delivery to other
        recipients. Failing sockets are removed from the active set so they
        do not accumulate across subsequent broadcasts.
        """
        payload = message.model_dump() if isinstance(message, BaseModel) else message

        # Snapshot the active set under lock, then send without holding the lock
        # (sending could block; we must not hold the lock while blocked on I/O).
        async with self._lock:
            targets = list(self.active)

        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception as exc:  # noqa: BLE001 — per-socket failure must not abort broadcast
                log.warning("ws.send_failed: %s", exc)
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self.active.discard(ws)
