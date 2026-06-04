"""Async multi-symbol intermarket feed backed by async-rithmic tick/BBO data."""
from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Callable
from enum import IntFlag
from typing import Any, Optional

try:
    from async_rithmic import DataType, ReconnectionSettings, RithmicClient
except ImportError:  # pragma: no cover - allows unit tests without vendor package
    class DataType(IntFlag):
        LAST_TRADE = 1
        BBO = 2

    class ReconnectionSettings:  # type: ignore[no-redef]
        def __init__(self, **_: Any) -> None:
            pass

    class RithmicClient:  # type: ignore[no-redef]
        pass

from deep6.config import Config
from deep6.engines.intermarket_registry import InstrumentSpec, IntermarketRegistry
from deep6.engines.ohlcv_accumulator import OHLCVAccumulator, OHLCVBar

log = logging.getLogger(__name__)

BarCallback = Callable[[str, OHLCVBar], Any]


class IntermarketFeed:
    def __init__(
        self,
        registry: IntermarketRegistry,
        bar_interval_sec: int = 60,
        on_bar: Optional[BarCallback] = None,
        *,
        config: Config | None = None,
        client_factory: Callable[..., RithmicClient] | None = None,
    ):
        self._registry = registry
        self._bar_interval_sec = bar_interval_sec
        self._accumulators: dict[str, OHLCVAccumulator] = {}
        self._on_bar = on_bar
        self._config = config or Config.from_env()
        self._client_factory = client_factory or RithmicClient
        self._client: RithmicClient | None = None
        self._running = False
        self._subscription_tasks: dict[str, asyncio.Task[None]] = {}
        self._subscriptions: dict[str, tuple[str, str, DataType]] = {}
        self._security_to_symbol: dict[str, str] = {}
        self._disconnect_event = asyncio.Event()
        self._reconnect_lock = asyncio.Lock()
        self._callback_tasks: set[asyncio.Task[Any]] = set()

    async def start(self, symbols: list[str]) -> None:
        """Connect to Rithmic and subscribe to tick/BBO data for all symbols."""
        if self._running:
            return

        self._running = True
        self._disconnect_event.clear()
        await self._ensure_connected()

        for symbol in symbols:
            if symbol in self._subscription_tasks:
                continue
            spec = self._registry.get_state(symbol)
            interval = self._bar_interval_sec if spec is None else spec.spec.bar_interval_sec
            self._accumulators.setdefault(symbol, OHLCVAccumulator(symbol, interval_sec=interval))
            self._subscription_tasks[symbol] = asyncio.create_task(
                self._subscribe_symbol(symbol),
                name=f"intermarket_subscribe_{symbol}",
            )

    async def stop(self) -> None:
        """Graceful shutdown: unsubscribe, cancel workers, flush partial bars."""
        if not self._running:
            return

        self._running = False
        self._disconnect_event.set()

        tasks = list(self._subscription_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._subscription_tasks.clear()

        await self._unsubscribe_all()

        for symbol, accumulator in self._accumulators.items():
            bar = accumulator.flush()
            if bar is not None:
                await self._emit_bar(symbol, bar)

        if self._callback_tasks:
            await asyncio.gather(*tuple(self._callback_tasks), return_exceptions=True)

        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                log.warning("intermarket_feed.disconnect_failed", exc_info=True)
            finally:
                self._client = None

    async def _subscribe_symbol(self, symbol: str) -> None:
        """Subscribe one symbol with reconnect/backoff on failure."""
        state = self._registry.get_state(symbol)
        if state is None:
            log.warning("intermarket_feed.unknown_symbol", extra={"symbol": symbol})
            return

        backoff = 1.0
        while self._running:
            try:
                await self._ensure_connected()
                client = self._require_client()
                security_code = await self._resolve_security_code(client, state.spec)
                data_type = DataType.LAST_TRADE | DataType.BBO
                await client.subscribe_to_market_data(security_code, state.spec.exchange, data_type)

                self._subscriptions[symbol] = (security_code, state.spec.exchange, data_type)
                self._security_to_symbol[security_code] = symbol
                state.is_connected = True
                backoff = 1.0

                while self._running and symbol in self._subscriptions and not self._disconnect_event.is_set():
                    await asyncio.sleep(0.25)

                if self._disconnect_event.is_set():
                    raise ConnectionError("Rithmic disconnected")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                state.is_connected = False
                self._subscriptions.pop(symbol, None)
                log.warning(
                    "intermarket_feed.subscribe_failed",
                    extra={"symbol": symbol, "error": str(exc), "backoff": backoff},
                )
                if not self._running:
                    return
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 30.0)

    def _on_tick(self, symbol: str, price: float, volume: float, ts: float) -> None:
        """Feed accumulator and refresh registry staleness on each tick."""
        accumulator = self._accumulators.get(symbol)
        if accumulator is None:
            accumulator = OHLCVAccumulator(symbol, interval_sec=self._bar_interval_sec)
            self._accumulators[symbol] = accumulator

        self._registry.update(symbol, price, ts)
        completed_bar = accumulator.feed_tick(price, volume, ts)
        if completed_bar is not None:
            self._dispatch_bar(symbol, completed_bar)

    async def _ensure_connected(self) -> None:
        async with self._reconnect_lock:
            if not self._running:
                return
            if self._client is None:
                self._client = self._build_client()
                self._register_callbacks(self._client)
                await self._client.connect()
                await asyncio.sleep(0.5)
                self._disconnect_event.clear()
                return
            if not self._disconnect_event.is_set():
                return
            await self._client.connect()
            await asyncio.sleep(0.5)
            self._disconnect_event.clear()

    def _build_client(self) -> RithmicClient:
        return self._client_factory(
            user=self._config.rithmic_user,
            password=self._config.rithmic_password,
            system_name=self._config.rithmic_system_name,
            app_name="migo:DEEP6",
            app_version="2.0.0",
            url=self._config.rithmic_uri,
            reconnection_settings=ReconnectionSettings(
                max_retries=10,
                backoff_type="exponential",
                interval=1.0,
                max_delay=60.0,
                jitter_range=(0.5, 1.5),
            ),
        )

    def _register_callbacks(self, client: RithmicClient) -> None:
        client.on_tick += self._handle_tick
        client.on_connected += self._handle_connected
        client.on_disconnected += self._handle_disconnected

    async def _handle_tick(self, tick: Any) -> None:
        if not self._running:
            return

        symbol = self._extract_symbol(tick)
        if symbol is None:
            return

        payload = self._extract_payload(tick)
        if payload is None:
            return

        price, volume, ts = payload
        self._on_tick(symbol, price, volume, ts)

    def _handle_connected(self) -> None:
        self._disconnect_event.clear()

    def _handle_disconnected(self) -> None:
        self._disconnect_event.set()
        for symbol in list(self._subscriptions):
            self._subscriptions.pop(symbol, None)
        for state in self._registry._states.values():
            state.is_connected = False

    async def _unsubscribe_all(self) -> None:
        if self._client is None:
            self._subscriptions.clear()
            return

        pending = list(self._subscriptions.items())
        self._subscriptions.clear()
        for symbol, (security_code, exchange, data_type) in pending:
            try:
                await self._client.unsubscribe_from_market_data(security_code, exchange, data_type)
            except Exception:
                log.warning(
                    "intermarket_feed.unsubscribe_failed",
                    extra={"symbol": symbol, "security_code": security_code},
                    exc_info=True,
                )

    async def _resolve_security_code(self, client: RithmicClient, spec: InstrumentSpec) -> str:
        if spec.rithmic_symbol.endswith("_FUT"):
            return await client.get_front_month_contract(spec.symbol, spec.exchange)
        return spec.rithmic_symbol

    def _extract_symbol(self, tick: Any) -> str | None:
        raw_symbol = self._value_from(tick, "symbol", "security_code")
        if raw_symbol is None:
            last_trade = self._value_from(tick, "last_trade")
            raw_symbol = self._value_from(last_trade, "symbol", "security_code")
        if raw_symbol is None:
            return None
        raw_symbol = str(raw_symbol)
        return self._security_to_symbol.get(raw_symbol, raw_symbol if self._registry.get_state(raw_symbol) else None)

    def _extract_payload(self, tick: Any) -> tuple[float, float, float] | None:
        data_type = self._value_from(tick, "data_type")
        if data_type == DataType.LAST_TRADE or str(data_type).endswith("LAST_TRADE"):
            return self._extract_trade_payload(tick)
        if data_type == DataType.BBO or str(data_type).endswith("BBO"):
            return self._extract_bbo_payload(tick)
        return None

    def _extract_trade_payload(self, tick: Any) -> tuple[float, float, float] | None:
        last_trade = self._value_from(tick, "last_trade")
        price = self._value_from(last_trade, "price", "last_trade_price")
        if price is None:
            price = self._value_from(tick, "last_trade_price")
        volume = self._value_from(last_trade, "size", "quantity", "last_trade_quantity")
        if volume is None:
            volume = self._value_from(tick, "last_trade_quantity", "size")
        if price is None or volume is None:
            return None
        ts = self._coerce_timestamp(
            self._value_from(last_trade, "timestamp", "time", "last_trade_time")
            or self._value_from(tick, "last_trade_time", "timestamp", "ts")
        )
        return float(price), float(volume), ts

    def _extract_bbo_payload(self, tick: Any) -> tuple[float, float, float] | None:
        price = self._value_from(tick, "last_trade_price")
        if price is None:
            bid = self._value_from(tick, "bid_price")
            ask = self._value_from(tick, "ask_price")
            if bid is not None and ask is not None:
                price = (float(bid) + float(ask)) / 2.0
            elif bid is not None:
                price = bid
            elif ask is not None:
                price = ask
        if price is None:
            return None
        volume = self._value_from(tick, "last_trade_quantity", "bid_quantity", "ask_quantity")
        ts = self._coerce_timestamp(
            self._value_from(tick, "last_trade_time", "timestamp", "ts")
        )
        return float(price), float(volume or 0.0), ts

    def _dispatch_bar(self, symbol: str, bar: OHLCVBar) -> None:
        if self._on_bar is None:
            return
        result = self._on_bar(symbol, bar)
        if inspect.isawaitable(result):
            task = asyncio.create_task(result)
            self._callback_tasks.add(task)
            task.add_done_callback(self._callback_tasks.discard)

    async def _emit_bar(self, symbol: str, bar: OHLCVBar) -> None:
        if self._on_bar is None:
            return
        result = self._on_bar(symbol, bar)
        if inspect.isawaitable(result):
            await result

    def _require_client(self) -> RithmicClient:
        if self._client is None:
            raise RuntimeError("IntermarketFeed client not connected")
        return self._client

    @staticmethod
    def _value_from(payload: Any, *keys: str) -> Any:
        if payload is None:
            return None
        for key in keys:
            if isinstance(payload, dict) and key in payload:
                return payload[key]
            if hasattr(payload, key):
                return getattr(payload, key)
        return None

    @staticmethod
    def _coerce_timestamp(value: Any) -> float:
        if value is None:
            return time.time()
        ts = float(value)
        if ts > 1_000_000_000_000_000:
            return ts / 1_000_000_000.0
        if ts > 1_000_000_000_000:
            return ts / 1_000.0
        return ts


__all__ = ["IntermarketFeed"]
