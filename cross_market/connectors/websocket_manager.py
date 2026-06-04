"""Generic async WebSocket manager with reconnect."""
from __future__ import annotations

import asyncio
import logging
from enum import Enum, auto
from typing import Callable, Awaitable

log = logging.getLogger(__name__)


class ConnectionState(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    RECONNECTING = auto()


class WebSocketManager:
    def __init__(
        self,
        url: str,
        on_message: Callable[[bytes], Awaitable[None]],
        max_retries: int = 10,
        base_delay_s: float = 1.0,
    ):
        self.url = url
        self._on_message = on_message
        self._max_retries = max_retries
        self._base_delay = base_delay_s
        self.state = ConnectionState.DISCONNECTED
        self._ws = None
        self._retries = 0

    async def connect(self) -> None:
        """Connect with exponential backoff."""
        import websockets

        self.state = ConnectionState.CONNECTING
        delay = self._base_delay
        while self._retries < self._max_retries:
            try:
                self._ws = await websockets.connect(self.url)
                self.state = ConnectionState.CONNECTED
                self._retries = 0
                log.info(f"Connected to {self.url}")
                await self._recv_loop()
            except Exception as e:
                self.state = ConnectionState.RECONNECTING
                self._retries += 1
                log.warning(
                    f"Connection failed ({self._retries}/{self._max_retries}): {e}"
                )
                await asyncio.sleep(min(delay, 60.0))
                delay *= 2  # exponential backoff
        self.state = ConnectionState.DISCONNECTED
        raise RuntimeError(f"Max retries exceeded for {self.url}")

    async def _recv_loop(self) -> None:
        try:
            async for msg in self._ws:
                await self._on_message(
                    msg if isinstance(msg, bytes) else msg.encode()
                )
        except Exception as e:
            log.error(f"Recv loop error: {e}")
            raise
