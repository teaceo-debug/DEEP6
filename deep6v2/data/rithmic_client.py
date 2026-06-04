from __future__ import annotations

import asyncio
import logging
from enum import Enum, auto
from typing import Any, Callable

from deep6v2.config.rithmic import RithmicConfig
from deep6v2.types.dom import DOMUpdate

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    FROZEN = auto()
    RECONNECTING = auto()


class RithmicClient:
    """Manage async-rithmic lifecycle with a FreezeGuard safety gate."""

    def __init__(
        self,
        config: RithmicConfig,
        on_dom_update: Callable[[DOMUpdate], None] | None = None,
        on_tick: Callable[[dict[str, Any]], None] | None = None,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config
        self.state = ConnectionState.DISCONNECTED
        self._on_dom_update = on_dom_update
        self._on_tick = on_tick
        self._client_factory = client_factory or self._default_client_factory
        self._client: Any | None = None
        self._reconnect_attempt = 0
        self._position_reconciled = False
        self._freeze_lock = asyncio.Event()
        self._freeze_lock.set()

    async def connect(self) -> None:
        """Connect to Rithmic and clear FreezeGuard on success."""
        self.state = ConnectionState.CONNECTING
        client = self._client_factory(
            user=self.config.username,
            password=self.config.password,
            system_name=self.config.system_name,
            app_name=self.config.app_name,
            app_version="2.0.0",
            url=self.config.uri,
        )

        await client.connect()

        self._client = client
        self.state = ConnectionState.CONNECTED
        self._reconnect_attempt = 0

    async def disconnect(self) -> None:
        """Graceful shutdown."""
        client = self._client
        self._client = None

        if client is not None and hasattr(client, "disconnect"):
            await client.disconnect()

        self.state = ConnectionState.DISCONNECTED
        self._freeze_lock.set()

    def freeze(self) -> None:
        """Freeze processing after connectivity loss."""
        if self.state in (ConnectionState.CONNECTED, ConnectionState.RECONNECTING):
            self.state = ConnectionState.FROZEN
            self._freeze_lock.clear()
            self._position_reconciled = False

    def is_frozen(self) -> bool:
        return self.state == ConnectionState.FROZEN

    async def reconcile_position(self) -> None:
        """Mark live position as reconciled before resuming processing."""
        self._position_reconciled = True
        await self._maybe_unfreeze()

    async def _maybe_unfreeze(self) -> None:
        if self._position_reconciled and self.state == ConnectionState.FROZEN:
            self.state = ConnectionState.CONNECTED
            self._freeze_lock.set()

    def handle_dom_update(self, update: DOMUpdate) -> None:
        """Drop DOM updates while frozen; otherwise forward to callback."""
        if self.is_frozen():
            return

        if self._on_dom_update is not None:
            self._on_dom_update(update)

    def handle_tick(self, tick: dict[str, Any]) -> None:
        """Drop ticks while frozen; otherwise forward to callback."""
        if self.is_frozen():
            return

        if self._on_tick is not None:
            self._on_tick(tick)

    async def reconnect_loop(self) -> None:
        """Reconnect with exponential backoff until success or attempts exhausted."""
        while self.state in (ConnectionState.FROZEN, ConnectionState.RECONNECTING):
            if self._reconnect_attempt >= self.config.reconnect_attempts:
                logger.error("Rithmic reconnect attempts exhausted")
                break

            self.state = ConnectionState.RECONNECTING
            wait = self.config.reconnect_backoff_base * (2**self._reconnect_attempt)
            await asyncio.sleep(wait)
            self._reconnect_attempt += 1

            try:
                await self.connect()
            except Exception:
                logger.exception("Rithmic reconnect attempt failed")
                self.state = ConnectionState.FROZEN
            else:
                break

    @staticmethod
    def _default_client_factory(**kwargs: Any) -> Any:
        from async_rithmic import RithmicClient as AsyncRithmicClient

        return AsyncRithmicClient(**kwargs)


__all__ = ["ConnectionState", "RithmicClient"]
