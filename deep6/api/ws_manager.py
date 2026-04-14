"""WSManager — WebSocket connection set + broadcast fan-out.

Per D-10: ONE WebSocket multiplexes all streams. All clients receive a mix of
LiveBarMessage / LiveSignalMessage / LiveScoreMessage / LiveStatusMessage,
discriminated by the 'type' field.

Per T-11-03: stale sockets are discovered and removed on the next broadcast
attempt (send raises an exception); no unbounded growth beyond live connections.

Per Phase 11.3-r3 observability additions:
- Tracks last_sent_ts per client so the frontend can detect stale connections.
- broadcast_status() builds a LiveStatusMessage from internal counters and fans
  it out to all clients.
- Periodic keepalive: every 30 s a status snapshot is broadcast to all clients.
- New clients receive an initial status snapshot within 100 ms of connecting.

Singleton pattern: the app lifespan sets ``app.state.ws_manager = WSManager()``
and route handlers reach it via ``request.app.state.ws_manager``.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import WebSocket
from pydantic import BaseModel

log = logging.getLogger(__name__)

# How often (seconds) to push a keepalive status to all clients.
_KEEPALIVE_INTERVAL = 30.0


class WSManager:
    """Connection set + broadcast fan-out singleton.

    Thread-safety: All methods are coroutines running in the asyncio event loop.
    The internal ``_lock`` prevents race conditions on connect/disconnect vs
    broadcast snapshot operations.

    Observability state (updated by callers / lifespan):
        session_start_ts  — epoch when the session was started
        bars_received     — total bars counted since start
        signals_fired     — total signals counted since start
        last_signal_tier  — tier string of most recent signal
        process_start_ts  — epoch when this WSManager was created (proxy for uptime)
    """

    def __init__(self) -> None:
        self.active: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        # Per-client last-sent timestamp {ws: epoch_float}
        self._last_sent: dict[int, float] = {}  # keyed by id(ws)

        # Observability counters (updated externally or via helpers)
        self.session_start_ts: float = time.time()
        self.bars_received: int = 0
        self.signals_fired: int = 0
        self.last_signal_tier: str = ""
        self.process_start_ts: float = time.time()

        # Keepalive task handle — started lazily on first connect
        self._keepalive_task: asyncio.Task | None = None  # type: ignore[type-arg]

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, ws: WebSocket) -> None:
        """Accept the WebSocket handshake, register the connection, and
        schedule an initial status snapshot to be sent within 100 ms."""
        await ws.accept()
        async with self._lock:
            self.active.add(ws)
            self._last_sent[id(ws)] = time.time()
        log.debug("ws.connected total=%d", len(self.active))

        # Ensure keepalive loop is running
        if self._keepalive_task is None or self._keepalive_task.done():
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())

        # Push initial status snapshot to just this client (≤ 100 ms)
        asyncio.create_task(self._send_initial_status(ws))

    async def disconnect(self, ws: WebSocket) -> None:
        """Remove a connection from the active set (no-op if not present)."""
        async with self._lock:
            self.active.discard(ws)
            self._last_sent.pop(id(ws), None)
        log.debug("ws.disconnected total=%d", len(self.active))

    # ------------------------------------------------------------------
    # Broadcast helpers
    # ------------------------------------------------------------------

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

        now = time.time()
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(payload)
                self._last_sent[id(ws)] = now
            except Exception as exc:  # noqa: BLE001 — per-socket failure must not abort broadcast
                log.warning("ws.send_failed: %s", exc)
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self.active.discard(ws)
                    self._last_sent.pop(id(ws), None)

    async def broadcast_status(
        self,
        *,
        connected: bool = True,
        pnl: float = 0.0,
        circuit_breaker_active: bool = False,
        feed_stale: bool = False,
    ) -> None:
        """Build a LiveStatusMessage from internal counters and broadcast it.

        Callers can override the per-call fields (connected, pnl, etc.);
        the observability counters are always sourced from ``self``.
        """
        # Import here to avoid circular import at module load time.
        from deep6.api.schemas import LiveStatusMessage  # noqa: PLC0415

        msg = LiveStatusMessage(
            connected=connected,
            pnl=pnl,
            circuit_breaker_active=circuit_breaker_active,
            feed_stale=feed_stale,
            ts=time.time(),
            session_start_ts=self.session_start_ts,
            bars_received=self.bars_received,
            signals_fired=self.signals_fired,
            last_signal_tier=self.last_signal_tier,
            uptime_seconds=int(time.time() - self.process_start_ts),
            active_clients=len(self.active),
        )
        await self.broadcast(msg)

    def status_snapshot(
        self,
        *,
        connected: bool = True,
        pnl: float = 0.0,
        circuit_breaker_active: bool = False,
        feed_stale: bool = False,
    ) -> dict[str, Any]:
        """Return the current status as a plain dict (for HTTP GET responses)."""
        return {
            "type": "status",
            "connected": connected,
            "pnl": pnl,
            "circuit_breaker_active": circuit_breaker_active,
            "feed_stale": feed_stale,
            "ts": time.time(),
            "session_start_ts": self.session_start_ts,
            "bars_received": self.bars_received,
            "signals_fired": self.signals_fired,
            "last_signal_tier": self.last_signal_tier,
            "uptime_seconds": int(time.time() - self.process_start_ts),
            "active_clients": len(self.active),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send_initial_status(self, ws: WebSocket) -> None:
        """Send one status snapshot to a single newly-connected client."""
        # Small yield so the caller's connect() can return first.
        await asyncio.sleep(0.05)
        from deep6.api.schemas import LiveStatusMessage  # noqa: PLC0415

        msg = LiveStatusMessage(
            connected=True,
            pnl=0.0,
            ts=time.time(),
            session_start_ts=self.session_start_ts,
            bars_received=self.bars_received,
            signals_fired=self.signals_fired,
            last_signal_tier=self.last_signal_tier,
            uptime_seconds=int(time.time() - self.process_start_ts),
            active_clients=len(self.active),
        )
        try:
            await ws.send_json(msg.model_dump())
            self._last_sent[id(ws)] = time.time()
        except Exception as exc:  # noqa: BLE001
            log.debug("ws._send_initial_status failed: %s", exc)

    async def _keepalive_loop(self) -> None:
        """Periodically broadcast a status keepalive to all connected clients."""
        while True:
            await asyncio.sleep(_KEEPALIVE_INTERVAL)
            async with self._lock:
                if not self.active:
                    # No clients — stop the loop; it restarts on next connect.
                    self._keepalive_task = None
                    return
            try:
                await self.broadcast_status()
                log.debug("ws.keepalive sent to %d clients", len(self.active))
            except Exception as exc:  # noqa: BLE001
                log.warning("ws.keepalive error: %s", exc)
