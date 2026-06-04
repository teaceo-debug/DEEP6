"""Rithmic NQ futures price feed — provides real-time NQ price for GEX Doctor."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

NQ_SYMBOL = "NQ"
NQ_EXCHANGE = "CME"
_STALE_AFTER_SEC = 60.0


class RithmicNQFeed:
    """Lightweight async NQ price feed from Rithmic.

    Tracks only last-trade price and exposes a simple stale-safe getter so the
    orchestrator can prefer real NQ spot over QQQ-derived estimation.
    """

    def __init__(
        self,
        user: str,
        password: str,
        system_name: str = "Rithmic Paper Trading",
        uri: str = "wss://rprotocol.rithmic.com:443",
        app_name: str = "migo:DEEP6-sim",
        app_version: str = "2.0.0",
        reconnect_interval_sec: float = 10.0,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._user = user
        self._password = password
        self._system_name = system_name
        self._uri = uri
        self._app_name = app_name
        self._app_version = app_version
        self._reconnect_interval_sec = max(1.0, reconnect_interval_sec)
        self._client_factory = client_factory
        self._client: Any | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._connected = False
        self._last_price: float | None = None
        self._last_update: float = 0.0

    async def start(self) -> None:
        """Start the background price feed. Non-blocking."""
        if self._task is not None:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="rithmic_nq_feed")
        logger.info("Rithmic NQ feed starting")

    async def stop(self) -> None:
        """Stop the feed gracefully."""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._disconnect_client()
        self._connected = False
        logger.info("Rithmic NQ feed stopped")

    @property
    def price(self) -> float | None:
        return self._last_price

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def last_update(self) -> float | None:
        return self._last_update if self._last_update > 0 else None

    @property
    def age_seconds(self) -> float:
        if self._last_update <= 0:
            return float("inf")
        return time.time() - self._last_update

    def get_nq_price(self) -> float | None:
        if not self._connected:
            return None
        if self._last_price is None or self.age_seconds > _STALE_AFTER_SEC:
            return None
        return self._last_price

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._connect_and_subscribe()
                await self._stop_event.wait()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._connected = False
                logger.warning("Rithmic NQ feed error: %s", exc)
                await self._disconnect_client()
                if not self._stop_event.is_set():
                    await asyncio.sleep(self._reconnect_interval_sec)

    async def _connect_and_subscribe(self) -> None:
        client = self._build_client()
        self._client = client

        async def on_tick(tick: dict[str, Any]) -> None:
            price = tick.get("trade_price") or tick.get("price")
            if isinstance(price, (int, float)) and price > 0:
                self._last_price = float(price)
                self._last_update = time.time()

        def on_connected(*_: Any) -> None:
            self._connected = True
            logger.info("Rithmic NQ feed connected")

        def on_disconnected(*_: Any) -> None:
            self._connected = False
            logger.warning("Rithmic NQ feed disconnected")

        client.on_tick += on_tick
        if hasattr(client, "on_connected"):
            client.on_connected += on_connected
        if hasattr(client, "on_disconnected"):
            client.on_disconnected += on_disconnected

        try:
            from async_rithmic import DataType, SysInfraType
        except ImportError as exc:
            raise RuntimeError("async-rithmic not installed") from exc

        await client.connect(plants=[SysInfraType.TICKER_PLANT])
        await asyncio.sleep(0.5)
        await client.subscribe_to_market_data(NQ_SYMBOL, NQ_EXCHANGE, DataType.LAST_TRADE)
        self._connected = True
        logger.info("Rithmic NQ feed subscribed symbol=%s exchange=%s", NQ_SYMBOL, NQ_EXCHANGE)

    def _build_client(self) -> Any:
        if self._client_factory is not None:
            return self._client_factory(
                user=self._user,
                password=self._password,
                system_name=self._system_name,
                app_name=self._app_name,
                app_version=self._app_version,
                url=self._uri,
            )

        try:
            from async_rithmic import ReconnectionSettings, RithmicClient
        except ImportError as exc:
            raise RuntimeError("async-rithmic not installed") from exc

        return RithmicClient(
            user=self._user,
            password=self._password,
            system_name=self._system_name,
            app_name=self._app_name,
            app_version=self._app_version,
            url=self._uri,
            reconnection_settings=ReconnectionSettings(
                max_retries=20,
                backoff_type="exponential",
                interval=1.0,
                max_delay=60.0,
                jitter_range=(0.5, 1.5),
            ),
        )

    async def _disconnect_client(self) -> None:
        client = self._client
        self._client = None
        if client is None:
            return
        try:
            await client.disconnect()
        except Exception:
            logger.debug("Rithmic NQ feed disconnect cleanup failed", exc_info=True)


__all__ = ["RithmicNQFeed", "NQ_SYMBOL", "NQ_EXCHANGE"]
