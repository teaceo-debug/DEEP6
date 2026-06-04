from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol
from uuid import uuid4

from deep6v2.config.rithmic import RithmicConfig
from deep6v2.types.execution import OrderSide, OrderType

FillCallback = Callable[["Fill"], Awaitable[None] | None]


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: OrderSide
    order_type: OrderType
    size: int
    price: float | None = None


@dataclass(frozen=True)
class Fill:
    order_id: str
    symbol: str
    side: OrderSide
    size: int
    price: float
    timestamp: float


@dataclass(frozen=True)
class Position:
    symbol: str
    size: int
    avg_price: float
    unrealized_pnl: float


class IBroker(Protocol):
    async def submit_order(self, request: OrderRequest) -> str: ...

    async def cancel_order(self, order_id: str) -> bool: ...

    async def query_position(self, symbol: str) -> Position: ...

    async def get_fills(self, since: float | None = None) -> list[Fill]: ...

    def on_fill(self, callback: FillCallback) -> None: ...


@dataclass
class _PendingOrder:
    request: OrderRequest
    triggered: bool = False


@dataclass
class _PositionState:
    size: int = 0
    avg_price: float = 0.0


class MockBroker:
    """In-memory broker simulator for deterministic unit tests."""

    def __init__(
        self,
        *,
        slippage: float = 0.25,
        initial_prices: dict[str, float] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.slippage = slippage
        self._clock = clock or time.time
        self._market_prices: dict[str, float] = dict(initial_prices or {})
        self._positions: dict[str, _PositionState] = {}
        self._orders: dict[str, _PendingOrder] = {}
        self._fills: list[Fill] = []
        self._callbacks: list[FillCallback] = []
        self._callback_queue: asyncio.Queue[Fill] = asyncio.Queue()

    def on_fill(self, callback: FillCallback) -> None:
        self._callbacks.append(callback)

    def update_market_price(self, symbol: str, price: float) -> None:
        self._market_prices[symbol] = price
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self._evaluate_open_orders(symbol=symbol))
        else:
            loop.create_task(self._evaluate_open_orders(symbol=symbol))

    async def submit_order(self, request: OrderRequest) -> str:
        order_id = str(uuid4())
        self._validate_request(request)

        if request.order_type is OrderType.MARKET:
            fill_price = self._market_fill_price(request.symbol, request.side)
            await self._apply_fill(
                Fill(
                    order_id=order_id,
                    symbol=request.symbol,
                    side=request.side,
                    size=request.size,
                    price=fill_price,
                    timestamp=self._clock(),
                )
            )
            return order_id

        self._orders[order_id] = _PendingOrder(request=request)
        await self._evaluate_open_orders(symbol=request.symbol)
        return order_id

    async def cancel_order(self, order_id: str) -> bool:
        return self._orders.pop(order_id, None) is not None

    async def query_position(self, symbol: str) -> Position:
        state = self._positions.get(symbol, _PositionState())
        market_price = self._market_prices.get(symbol, state.avg_price)
        unrealized = (market_price - state.avg_price) * state.size if state.size else 0.0
        return Position(
            symbol=symbol,
            size=state.size,
            avg_price=state.avg_price,
            unrealized_pnl=unrealized,
        )

    async def get_fills(self, since: float | None = None) -> list[Fill]:
        if since is None:
            return list(self._fills)
        return [fill for fill in self._fills if fill.timestamp >= since]

    async def _evaluate_open_orders(self, symbol: str | None = None) -> None:
        if symbol is None:
            candidates = list(self._orders.items())
        else:
            candidates = [
                (order_id, pending)
                for order_id, pending in self._orders.items()
                if pending.request.symbol == symbol
            ]

        for order_id, pending in candidates:
            market_price = self._market_prices.get(pending.request.symbol)
            if market_price is None:
                continue

            fill = self._maybe_fill_order(order_id=order_id, pending=pending, market_price=market_price)
            if fill is None:
                continue

            self._orders.pop(order_id, None)
            await self._apply_fill(fill)

    def _maybe_fill_order(self, *, order_id: str, pending: _PendingOrder, market_price: float) -> Fill | None:
        request = pending.request
        timestamp = self._clock()

        if request.order_type is OrderType.LIMIT and request.price is not None:
            if request.side is OrderSide.BUY and market_price <= request.price:
                return Fill(order_id, request.symbol, request.side, request.size, request.price, timestamp)
            if request.side is OrderSide.SELL and market_price >= request.price:
                return Fill(order_id, request.symbol, request.side, request.size, request.price, timestamp)

        if request.order_type is OrderType.STOP and request.price is not None:
            triggered = pending.triggered
            if request.side is OrderSide.BUY and market_price >= request.price:
                triggered = True
            if request.side is OrderSide.SELL and market_price <= request.price:
                triggered = True

            if triggered:
                pending.triggered = True
                fill_price = self._market_fill_price(request.symbol, request.side)
                return Fill(order_id, request.symbol, request.side, request.size, fill_price, timestamp)

        return None

    def _market_fill_price(self, symbol: str, side: OrderSide) -> float:
        market_price = self._market_prices.get(symbol)
        if market_price is None:
            raise ValueError(f"No market price available for symbol={symbol!r}")

        if side is OrderSide.BUY:
            return market_price + self.slippage
        return market_price - self.slippage

    async def _apply_fill(self, fill: Fill) -> None:
        self._fills.append(fill)
        self._market_prices[fill.symbol] = fill.price
        self._update_position(fill)
        self._callback_queue.put_nowait(fill)
        await self._drain_callbacks()

    async def _drain_callbacks(self) -> None:
        while not self._callback_queue.empty():
            fill = await self._callback_queue.get()
            for callback in self._callbacks:
                result = callback(fill)
                if inspect.isawaitable(result):
                    await result

    def _update_position(self, fill: Fill) -> None:
        signed_fill_size = fill.size if fill.side is OrderSide.BUY else -fill.size
        state = self._positions.setdefault(fill.symbol, _PositionState())

        if state.size == 0:
            state.size = signed_fill_size
            state.avg_price = fill.price
            return

        if state.size > 0 and signed_fill_size > 0:
            new_size = state.size + signed_fill_size
            state.avg_price = ((state.avg_price * state.size) + (fill.price * signed_fill_size)) / new_size
            state.size = new_size
            return

        if state.size < 0 and signed_fill_size < 0:
            existing_size = abs(state.size)
            added_size = abs(signed_fill_size)
            new_size = existing_size + added_size
            state.avg_price = ((state.avg_price * existing_size) + (fill.price * added_size)) / new_size
            state.size = -new_size
            return

        remaining = state.size + signed_fill_size
        if remaining == 0:
            state.size = 0
            state.avg_price = 0.0
            return

        if state.size > 0 > remaining:
            state.size = remaining
            state.avg_price = fill.price
            return

        if state.size < 0 < remaining:
            state.size = remaining
            state.avg_price = fill.price
            return

        state.size = remaining

    @staticmethod
    def _validate_request(request: OrderRequest) -> None:
        if request.size <= 0:
            raise ValueError("Order size must be positive")
        if request.order_type is not OrderType.MARKET and request.price is None:
            raise ValueError("Limit and stop orders require a price")


class RithmicBroker:
    """Best-effort async-rithmic ORDER_PLANT wrapper."""

    def __init__(
        self,
        config: RithmicConfig,
        *,
        exchange: str = "CME",
        client: Any | None = None,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config
        self.exchange = exchange
        self._client = client
        self._client_factory = client_factory or self._default_client_factory
        self._callbacks: list[FillCallback] = []
        self._fills: list[Fill] = []
        self._connected = False
        self._registered_notification_handler = False

    def on_fill(self, callback: FillCallback) -> None:
        self._callbacks.append(callback)

    async def connect(self) -> None:
        if self._connected:
            return

        if self._client is None:
            self._client = self._client_factory(
                user=self.config.username,
                password=self.config.password,
                system_name=self.config.system_name,
                app_name=self.config.app_name,
                app_version="2.0.0",
                url=self.config.uri,
            )

        try:
            from async_rithmic.enums import SysInfraType

            await self._client.connect(plants=[SysInfraType.ORDER_PLANT, SysInfraType.PNL_PLANT])
        except TypeError:
            await self._client.connect()

        self._register_notification_handlers()
        self._connected = True

    async def disconnect(self) -> None:
        if self._client is None:
            return
        if hasattr(self._client, "disconnect"):
            await self._client.disconnect()
        self._connected = False

    async def submit_order(self, request: OrderRequest) -> str:
        await self.connect()
        order_id = str(uuid4())

        kwargs: dict[str, Any] = {}
        if request.order_type is OrderType.LIMIT:
            kwargs["price"] = request.price
        elif request.order_type is OrderType.STOP:
            kwargs["trigger_price"] = request.price

        responses = await self._client.submit_order(
            order_id=order_id,
            symbol=request.symbol,
            exchange=self.exchange,
            qty=request.size,
            transaction_type=self._map_side(request.side),
            order_type=self._map_order_type(request.order_type),
            **kwargs,
        )

        # TODO: tighten response parsing against a real paper-trading session capture.
        if responses:
            response = responses[0]
            broker_order_id = getattr(response, "user_tag", None) or getattr(response, "order_id", None)
            if broker_order_id:
                return str(broker_order_id)
        return order_id

    async def cancel_order(self, order_id: str) -> bool:
        await self.connect()
        try:
            responses = await self._client.cancel_order(order_id=order_id)
        except Exception:
            return False

        return bool(responses)

    async def query_position(self, symbol: str) -> Position:
        await self.connect()
        positions = await self._client.list_positions()
        for raw in positions:
            raw_symbol = getattr(raw, "symbol", getattr(raw, "symbol_name", None))
            if raw_symbol != symbol:
                continue

            size = self._coerce_int(
                getattr(raw, "net_quantity", None)
                or getattr(raw, "quantity", None)
                or getattr(raw, "position", None)
                or 0
            )
            avg_price = self._coerce_float(
                getattr(raw, "avg_price", None)
                or getattr(raw, "average_price", None)
                or getattr(raw, "price", None)
                or 0.0
            )
            unrealized_pnl = self._coerce_float(
                getattr(raw, "open_pnl", None)
                or getattr(raw, "unrealized_pnl", None)
                or getattr(raw, "pnl", None)
                or 0.0
            )
            return Position(
                symbol=symbol,
                size=size,
                avg_price=avg_price,
                unrealized_pnl=unrealized_pnl,
            )

        return Position(symbol=symbol, size=0, avg_price=0.0, unrealized_pnl=0.0)

    async def get_fills(self, since: float | None = None) -> list[Fill]:
        if since is None:
            return list(self._fills)
        return [fill for fill in self._fills if fill.timestamp >= since]

    def _register_notification_handlers(self) -> None:
        if self._client is None or self._registered_notification_handler:
            return

        notification = getattr(self._client, "on_exchange_order_notification", None)
        if notification is None:
            return

        notification += self._handle_exchange_notification
        self._registered_notification_handler = True

    async def _handle_exchange_notification(self, raw: Any) -> None:
        fill = self._parse_fill(raw)
        if fill is None:
            return

        self._fills.append(fill)
        for callback in self._callbacks:
            result = callback(fill)
            if inspect.isawaitable(result):
                await result

    def _parse_fill(self, raw: Any) -> Fill | None:
        quantity = getattr(raw, "fill_size", None) or getattr(raw, "fill_quantity", None) or getattr(raw, "quantity", None)
        price = getattr(raw, "fill_price", None) or getattr(raw, "price", None)
        side = getattr(raw, "transaction_type", None) or getattr(raw, "side", None)
        symbol = getattr(raw, "symbol", None) or getattr(raw, "symbol_name", None)
        order_id = getattr(raw, "user_tag", None) or getattr(raw, "order_id", None) or getattr(raw, "basket_id", None)

        if quantity in (None, "", 0, "0") or price in (None, "") or symbol is None or order_id is None:
            return None

        return Fill(
            order_id=str(order_id),
            symbol=str(symbol),
            side=self._parse_side(side),
            size=self._coerce_int(quantity),
            price=self._coerce_float(price),
            timestamp=time.time(),
        )

    @staticmethod
    def _map_side(side: OrderSide) -> Any:
        from async_rithmic.enums import TransactionType

        return TransactionType.Value(side.value)

    @staticmethod
    def _map_order_type(order_type: OrderType) -> Any:
        from async_rithmic.enums import OrderType as RithmicOrderType

        if order_type is OrderType.MARKET:
            return RithmicOrderType.Value("MARKET")
        if order_type is OrderType.LIMIT:
            return RithmicOrderType.Value("LIMIT")
        return RithmicOrderType.Value("STOP_MARKET")

    @staticmethod
    def _parse_side(side: Any) -> OrderSide:
        if str(side).upper().endswith("SELL") or side == 2:
            return OrderSide.SELL
        return OrderSide.BUY

    @staticmethod
    def _coerce_int(value: Any) -> int:
        return int(float(value))

    @staticmethod
    def _coerce_float(value: Any) -> float:
        return float(value)

    @staticmethod
    def _default_client_factory(**kwargs: Any) -> Any:
        from async_rithmic import RithmicClient as AsyncRithmicClient

        return AsyncRithmicClient(**kwargs)
__all__ = [
    "Fill",
    "FillCallback",
    "IBroker",
    "MockBroker",
    "OrderRequest",
    "Position",
    "RithmicBroker",
]
