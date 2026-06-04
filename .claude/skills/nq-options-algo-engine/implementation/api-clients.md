# API Clients: Massive.com and FlashAlpha

Async HTTP and WebSocket client patterns for both options data providers. All I/O is
non-blocking. Both clients share a common `RateLimiter` and retry decorator.

Companion files:
- `../data-shapes.md` — typed dataclasses returned by these clients
- `async-pipeline.md` — how these clients plug into `OptionsPipeline`
- `../flashalpha-reference.md` — full FlashAlpha endpoint catalog

---

## Shared Utilities

### RateLimiter (Token Bucket)

```python
import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    """
    Token bucket rate limiter. Thread-safe within a single event loop.

    Usage:
        limiter = RateLimiter(tokens_per_second=1.67, max_burst=10)  # 100/min
        await limiter.acquire()
        response = await session.get(url)
    """
    tokens_per_second: float
    max_burst: float
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)
    _lock: asyncio.Lock = field(init=False)

    def __post_init__(self):
        self._tokens = self.max_burst
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self.max_burst,
                self._tokens + elapsed * self.tokens_per_second,
            )
            self._last_refill = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                return

            # Not enough tokens — wait for refill
            wait_time = (tokens - self._tokens) / self.tokens_per_second
            self._tokens = 0
            await asyncio.sleep(wait_time)
```

### Retry Decorator

```python
import functools
import logging
from collections.abc import Callable, Awaitable
from typing import TypeVar

logger = logging.getLogger("deep6.options.clients")
T = TypeVar("T")


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_status: tuple[int, ...] = (429, 500, 502, 503, 504),
):
    """
    Decorator for async methods. Retries on network errors and retryable HTTP status codes.
    Raises the last exception if all attempts fail.

    Usage:
        @with_retry(max_attempts=3, base_delay=1.0)
        async def get_data(self, symbol: str) -> dict:
            ...
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exc = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except aiohttp.ClientResponseError as exc:
                    if exc.status not in retryable_status:
                        # 4xx (except 429) — don't retry
                        logger.warning(
                            "http.non_retryable",
                            extra={"status": exc.status, "url": str(exc.request_info.url)},
                        )
                        raise
                    last_exc = exc
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(
                        "http.retry",
                        extra={
                            "status": exc.status,
                            "attempt": attempt + 1,
                            "max_attempts": max_attempts,
                            "delay": delay,
                        },
                    )
                    await asyncio.sleep(delay)
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    last_exc = exc
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(
                        "http.network_error",
                        extra={"error": str(exc), "attempt": attempt + 1, "delay": delay},
                    )
                    await asyncio.sleep(delay)
            raise last_exc
        return wrapper
    return decorator
```

---

## MassiveClient

Massive.com provides real-time options quotes via WebSocket and historical/snapshot data
via REST. The client manages both connections independently.

```python
import asyncio
import json
import logging
import time
from collections.abc import Callable, Awaitable
from dataclasses import dataclass
from typing import Optional

import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from .data_shapes import MassiveChainSnapshot, MassiveTrade, MassiveQuote
from .rate_limiter import RateLimiter
from .retry import with_retry

logger = logging.getLogger("deep6.options.massive")

MASSIVE_REST_BASE = "https://api.massive.com/v1"
MASSIVE_WS_BASE = "wss://stream.massive.com/v1"
MASSIVE_RATE_LIMIT = RateLimiter(tokens_per_second=1.67, max_burst=20)  # 100 req/min


@dataclass
class MassiveConfig:
    api_key: str
    connection_limit: int = 10
    request_timeout_seconds: float = 10.0
    ws_heartbeat_interval: float = 30.0
    ws_ping_timeout: float = 10.0


class MassiveClient:
    """
    Async client for Massive.com options data.

    REST methods return typed dataclasses.
    WebSocket subscription runs until cancelled or connection permanently fails.

    Usage:
        async with MassiveClient(config) as client:
            chain = await client.get_option_chain("QQQ")
            await client.subscribe_quotes(["QQQ"], callback=my_handler)
    """

    def __init__(self, config: MassiveConfig):
        self._config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._metrics = {
            "rest_request_count": 0,
            "rest_error_count": 0,
            "ws_message_count": 0,
            "ws_reconnect_count": 0,
        }

    async def __aenter__(self) -> "MassiveClient":
        connector = aiohttp.TCPConnector(limit=self._config.connection_limit)
        self._session = aiohttp.ClientSession(
            connector=connector,
            headers={"Authorization": f"Bearer {self._config.api_key}"},
            timeout=aiohttp.ClientTimeout(total=self._config.request_timeout_seconds),
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._session:
            await self._session.close()
        if self._ws:
            await self._ws.close()

    # -------------------------------------------------------------------------
    # REST Methods
    # -------------------------------------------------------------------------

    @with_retry(max_attempts=3, base_delay=1.0)
    async def get_option_chain(self, symbol: str) -> MassiveChainSnapshot:
        """
        Fetch full option chain snapshot for a symbol.
        Returns all strikes and expirations with bid/ask/IV/OI/volume.
        """
        await MASSIVE_RATE_LIMIT.acquire()
        url = f"{MASSIVE_REST_BASE}/chains/{symbol}"

        async with self._session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json()
            self._metrics["rest_request_count"] += 1

        logger.debug(
            "massive.chain_ok",
            extra={"symbol": symbol, "strikes": len(data.get("strikes", []))},
        )
        return MassiveChainSnapshot.from_dict(data)

    @with_retry(max_attempts=3, base_delay=1.0)
    async def get_trades(self, ticker: str, limit: int = 100) -> list[MassiveTrade]:
        """
        Fetch recent options trades (tape) for a ticker.
        Useful for unusual flow detection.
        """
        await MASSIVE_RATE_LIMIT.acquire()
        url = f"{MASSIVE_REST_BASE}/trades/{ticker}"
        params = {"limit": limit}

        async with self._session.get(url, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
            self._metrics["rest_request_count"] += 1

        trades = [MassiveTrade.from_dict(t) for t in data.get("trades", [])]
        logger.debug("massive.trades_ok", extra={"ticker": ticker, "count": len(trades)})
        return trades

    # -------------------------------------------------------------------------
    # WebSocket Subscription
    # -------------------------------------------------------------------------

    async def subscribe_quotes(
        self,
        symbols: list[str],
        callback: Callable[[MassiveQuote], Awaitable[None]],
    ) -> None:
        """
        Subscribe to real-time quote updates for symbols.
        Blocks until connection is permanently closed or task is cancelled.
        Reconnects automatically on transient failures.

        The callback receives a MassiveQuote for each update.
        """
        ws_url = f"{MASSIVE_WS_BASE}/quotes"
        headers = {"Authorization": f"Bearer {self._config.api_key}"}

        while True:
            try:
                async with websockets.connect(
                    ws_url,
                    extra_headers=headers,
                    ping_interval=self._config.ws_heartbeat_interval,
                    ping_timeout=self._config.ws_ping_timeout,
                ) as ws:
                    self._ws = ws
                    logger.info("massive.ws_connected", extra={"symbols": symbols})

                    # Send subscription message
                    await ws.send(json.dumps({
                        "action": "subscribe",
                        "symbols": symbols,
                        "channels": ["quotes"],
                    }))

                    async for raw_message in ws:
                        self._metrics["ws_message_count"] += 1
                        try:
                            data = json.loads(raw_message)
                            quote = MassiveQuote.from_dict(data)
                            await callback(quote)
                        except (json.JSONDecodeError, KeyError, ValueError) as exc:
                            logger.warning(
                                "massive.parse_error",
                                extra={"error": str(exc), "raw": raw_message[:200]},
                            )

            except asyncio.CancelledError:
                logger.info("massive.ws_cancelled")
                raise

            except (ConnectionClosed, WebSocketException) as exc:
                self._metrics["ws_reconnect_count"] += 1
                logger.warning("massive.ws_disconnected", extra={"error": str(exc)})
                # Reconnection is handled by the caller (OptionsPipeline._run_massive_ws)
                raise

    @property
    def metrics(self) -> dict:
        return dict(self._metrics)
```

### MassiveQuote Parsing

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class MassiveQuote:
    symbol: str
    timestamp: datetime
    atm_iv: Optional[float]
    put_call_ratio: Optional[float]
    total_volume: Optional[int]
    unusual_flow_score: Optional[float]  # 0-100, computed by Massive

    @classmethod
    def from_dict(cls, data: dict) -> "MassiveQuote":
        return cls(
            symbol=data["symbol"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            atm_iv=data.get("atm_iv"),
            put_call_ratio=data.get("put_call_ratio"),
            total_volume=data.get("total_volume"),
            unusual_flow_score=data.get("unusual_flow_score"),
        )


@dataclass(frozen=True)
class MassiveChainSnapshot:
    symbol: str
    timestamp: datetime
    expiration_dates: list[str]
    strikes: list[dict]  # raw strike data — parse as needed per signal

    @classmethod
    def from_dict(cls, data: dict) -> "MassiveChainSnapshot":
        return cls(
            symbol=data["symbol"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            expiration_dates=data.get("expiration_dates", []),
            strikes=data.get("strikes", []),
        )
```

---

## FlashAlphaClient

FlashAlpha is REST-only. The client runs a polling scheduler with configurable intervals
per endpoint group. Historical mode swaps the host and adds a timestamp parameter.

```python
import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

import aiohttp

from .data_shapes import (
    FAExposureLevels, FAGexByStrike, FAZeroDTE,
    FAVolatility, FAExposureSummary,
)
from .rate_limiter import RateLimiter
from .retry import with_retry

logger = logging.getLogger("deep6.options.flashalpha")

FA_LIVE_HOST = "https://lab.flashalpha.com"
FA_HISTORICAL_HOST = "https://historical.flashalpha.com"

# FlashAlpha rate limits are not published — use conservative 60 req/min
FA_RATE_LIMIT = RateLimiter(tokens_per_second=1.0, max_burst=10)


@dataclass
class FAConfig:
    api_key: str
    historical_mode: bool = False
    historical_at: Optional[datetime] = None  # required if historical_mode=True
    request_timeout_seconds: float = 15.0
    connection_limit: int = 5

    @property
    def base_url(self) -> str:
        return FA_HISTORICAL_HOST if self.historical_mode else FA_LIVE_HOST

    def build_params(self, extra: Optional[dict] = None) -> dict:
        params = {"apiKey": self._sanitized_key()}
        if self.historical_mode and self.historical_at:
            params["at"] = self.historical_at.strftime("%Y-%m-%dT%H:%M:%S")
        if extra:
            params.update(extra)
        return params

    def _sanitized_key(self) -> str:
        return self.api_key  # used in params, not logged


class FlashAlphaClient:
    """
    Async REST client for FlashAlpha options analytics.

    Supports live polling and historical replay (Alpha tier).
    All methods return typed dataclasses.

    Usage (live):
        async with FlashAlphaClient(FAConfig(api_key="...")) as fa:
            levels = await fa.get_exposure_levels("QQQ")
            gex = await fa.get_gex("QQQ")

    Usage (historical):
        config = FAConfig(
            api_key="...",
            historical_mode=True,
            historical_at=datetime(2026, 3, 15, 10, 30, 0),
        )
        async with FlashAlphaClient(config) as fa:
            levels = await fa.get_exposure_levels("QQQ")
    """

    def __init__(self, config: FAConfig):
        self._config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: dict[str, tuple[float, object]] = {}  # key -> (timestamp, value)
        self._metrics = {
            "request_count": 0,
            "cache_hit_count": 0,
            "error_count": 0,
        }

    async def __aenter__(self) -> "FlashAlphaClient":
        connector = aiohttp.TCPConnector(limit=self._config.connection_limit)
        self._session = aiohttp.ClientSession(
            connector=connector,
            headers={"X-Api-Key": self._config.api_key},
            timeout=aiohttp.ClientTimeout(total=self._config.request_timeout_seconds),
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._session:
            await self._session.close()

    # -------------------------------------------------------------------------
    # Core Request Method
    # -------------------------------------------------------------------------

    @with_retry(max_attempts=3, base_delay=2.0, max_delay=30.0)
    async def _get(self, path: str, cache_ttl: float = 0.0, extra_params: Optional[dict] = None) -> dict:
        """
        Internal GET with rate limiting, caching, and structured logging.
        cache_ttl=0 disables caching.
        """
        cache_key = f"{path}:{extra_params}"

        if cache_ttl > 0 and cache_key in self._cache:
            cached_at, cached_value = self._cache[cache_key]
            if time.monotonic() - cached_at < cache_ttl:
                self._metrics["cache_hit_count"] += 1
                return cached_value

        await FA_RATE_LIMIT.acquire()
        url = f"{self._config.base_url}{path}"
        params = self._config.build_params(extra_params)

        # Log without API key
        safe_params = {k: v for k, v in params.items() if k != "apiKey"}
        logger.debug("fa.request", extra={"path": path, "params": safe_params})

        async with self._session.get(url, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
            self._metrics["request_count"] += 1

        if cache_ttl > 0:
            self._cache[cache_key] = (time.monotonic(), data)

        return data

    # -------------------------------------------------------------------------
    # Endpoint Methods
    # -------------------------------------------------------------------------

    async def get_exposure_levels(self, symbol: str) -> FAExposureLevels:
        """
        Gamma flip, call wall, put wall. Free tier.
        Cache for 30s — these levels don't change frequently.
        """
        data = await self._get(f"/exposure/levels/{symbol}", cache_ttl=30.0)
        return FAExposureLevels.from_dict(data)

    async def get_gex(self, symbol: str) -> FAGexByStrike:
        """
        GEX by strike. Growth tier.
        Cache for 60s.
        """
        data = await self._get(f"/exposure/gex/{symbol}", cache_ttl=60.0)
        return FAGexByStrike.from_dict(data)

    async def get_zero_dte(self, symbol: str) -> FAZeroDTE:
        """
        0DTE analytics: expected move, pin score, charm regime. Growth tier.
        Cache for 30s — updates frequently during market hours.
        """
        data = await self._get(f"/zero-dte/{symbol}", cache_ttl=30.0)
        return FAZeroDTE.from_dict(data)

    async def get_volatility(self, symbol: str) -> FAVolatility:
        """
        IV, VRP, skew, term structure. Growth tier.
        Cache for 60s.
        """
        data = await self._get(f"/volatility/{symbol}", cache_ttl=60.0)
        return FAVolatility.from_dict(data)

    async def get_exposure_summary(self, symbol: str) -> FAExposureSummary:
        """
        Full exposure summary with regime + interpretations. Growth tier.
        Cache for 30s.
        """
        data = await self._get(f"/exposure/summary/{symbol}", cache_ttl=30.0)
        return FAExposureSummary.from_dict(data)

    async def get_full_snapshot(self, symbol: str) -> "FASnapshot":
        """
        Convenience method: fetches all relevant endpoints in parallel.
        Returns a merged FASnapshot for the fusion engine.
        """
        levels_task = asyncio.create_task(self.get_exposure_levels(symbol))
        zte_task = asyncio.create_task(self.get_zero_dte(symbol))
        vol_task = asyncio.create_task(self.get_volatility(symbol))

        levels, zte, vol = await asyncio.gather(
            levels_task, zte_task, vol_task,
            return_exceptions=True,
        )

        # Partial success: use whatever succeeded
        def safe(result, default=None):
            return result if not isinstance(result, Exception) else default

        return FASnapshot(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            gamma_flip=safe(levels).gamma_flip if safe(levels) else None,
            call_wall=safe(levels).call_wall if safe(levels) else None,
            put_wall=safe(levels).put_wall if safe(levels) else None,
            net_gex=safe(levels).net_gex if safe(levels) else None,
            regime=safe(levels).regime if safe(levels) else None,
            zero_dte_expected_move=safe(zte).expected_move if safe(zte) else None,
            zero_dte_pin_score=safe(zte).pin_score if safe(zte) else None,
            atm_iv=safe(vol).atm_iv if safe(vol) else None,
            vrp=safe(vol).vrp if safe(vol) else None,
        )

    @property
    def metrics(self) -> dict:
        return dict(self._metrics)
```

### FlashAlpha Typed Dataclasses

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class FAExposureLevels:
    symbol: str
    gamma_flip: Optional[float]
    call_wall: Optional[float]
    put_wall: Optional[float]
    net_gex: Optional[float]
    net_dex: Optional[float]
    regime: Optional[str]  # "positive" | "negative"

    @classmethod
    def from_dict(cls, data: dict) -> "FAExposureLevels":
        return cls(
            symbol=data.get("symbol", ""),
            gamma_flip=data.get("gamma_flip"),
            call_wall=data.get("call_wall"),
            put_wall=data.get("put_wall"),
            net_gex=data.get("net_gex"),
            net_dex=data.get("net_dex"),
            regime=data.get("regime"),
        )


@dataclass(frozen=True)
class FAZeroDTE:
    symbol: str
    expected_move: Optional[float]
    expected_move_upper: Optional[float]
    expected_move_lower: Optional[float]
    pin_score: Optional[float]       # 0-100; > 70 = strong pin
    magnet_strike: Optional[float]
    charm_regime: Optional[str]      # "dealers_buy" | "dealers_sell"
    gamma_acceleration: Optional[float]

    @classmethod
    def from_dict(cls, data: dict) -> "FAZeroDTE":
        return cls(
            symbol=data.get("symbol", ""),
            expected_move=data.get("expected_move"),
            expected_move_upper=data.get("upper_bound"),
            expected_move_lower=data.get("lower_bound"),
            pin_score=data.get("pin_score"),
            magnet_strike=data.get("magnet_strike"),
            charm_regime=data.get("charm_regime"),
            gamma_acceleration=data.get("gamma_acceleration"),
        )


@dataclass(frozen=True)
class FAVolatility:
    symbol: str
    atm_iv: Optional[float]
    vrp: Optional[float]             # implied - realized
    iv_rank: Optional[float]         # 0-100
    iv_percentile: Optional[float]   # 0-100
    skew_25d: Optional[float]        # 25-delta risk reversal

    @classmethod
    def from_dict(cls, data: dict) -> "FAVolatility":
        return cls(
            symbol=data.get("symbol", ""),
            atm_iv=data.get("atm_iv"),
            vrp=data.get("vrp"),
            iv_rank=data.get("iv_rank"),
            iv_percentile=data.get("iv_percentile"),
            skew_25d=data.get("skew_25d"),
        )


@dataclass
class FASnapshot:
    """Merged snapshot from multiple FA endpoints. Used by fusion engine."""
    symbol: str
    timestamp: datetime
    gamma_flip: Optional[float]
    call_wall: Optional[float]
    put_wall: Optional[float]
    net_gex: Optional[float]
    regime: Optional[str]
    zero_dte_expected_move: Optional[float]
    zero_dte_pin_score: Optional[float]
    atm_iv: Optional[float]
    vrp: Optional[float]
```

---

## Polling Scheduler

For endpoints that need different poll intervals, use a scheduler task per group:

```python
class FAPollingScheduler:
    """
    Runs multiple FA endpoint groups at different intervals.
    Writes results to a shared queue.

    Endpoint groups:
    - fast (30s): exposure_levels, zero_dte — change frequently during market hours
    - medium (60s): gex, volatility — change on each options print
    - slow (300s): exposure_summary — regime rarely changes intraday
    """

    def __init__(self, fa_client: FlashAlphaClient, symbol: str, output_q: asyncio.Queue):
        self._fa = fa_client
        self._symbol = symbol
        self._q = output_q
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._poll_fast(), name="fa_poll_fast"),
            asyncio.create_task(self._poll_medium(), name="fa_poll_medium"),
        ]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _poll_fast(self) -> None:
        while True:
            try:
                snapshot = await self._fa.get_full_snapshot(self._symbol)
                await self._q.put(snapshot)
            except Exception as exc:
                logger.warning("fa_scheduler.fast_error", extra={"error": str(exc)})
            await asyncio.sleep(30.0)

    async def _poll_medium(self) -> None:
        while True:
            try:
                vol = await self._fa.get_volatility(self._symbol)
                await self._q.put(vol)
            except Exception as exc:
                logger.warning("fa_scheduler.medium_error", extra={"error": str(exc)})
            await asyncio.sleep(60.0)
```

---

## Health Check Endpoints

Both clients expose a `health_check()` method for monitoring:

```python
class MassiveClient:
    async def health_check(self) -> dict:
        """Returns health status. Safe to call from monitoring loop."""
        try:
            # Lightweight endpoint — just verify auth and connectivity
            await self._get("/health")
            return {"status": "ok", "metrics": self.metrics}
        except Exception as exc:
            return {"status": "error", "error": str(exc), "metrics": self.metrics}


class FlashAlphaClient:
    async def health_check(self) -> dict:
        try:
            # Use a free-tier endpoint to verify connectivity
            await self.get_exposure_levels("QQQ")
            return {"status": "ok", "metrics": self.metrics}
        except Exception as exc:
            return {"status": "error", "error": str(exc), "metrics": self.metrics}
```

---

## Testing Patterns

### Mock Server for Integration Tests

```python
import pytest
from aiohttp import web


@pytest.fixture
async def mock_flashalpha_server():
    """
    Spins up a local aiohttp server that mimics FlashAlpha responses.
    Use in integration tests to avoid hitting the real API.
    """
    async def handle_exposure_levels(request: web.Request) -> web.Response:
        symbol = request.match_info["symbol"]
        return web.json_response({
            "symbol": symbol,
            "gamma_flip": 480.0,
            "call_wall": 490.0,
            "put_wall": 470.0,
            "net_gex": 1_500_000_000,
            "net_dex": -200_000_000,
            "regime": "positive",
        })

    app = web.Application()
    app.router.add_get("/exposure/levels/{symbol}", handle_exposure_levels)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 8765)
    await site.start()

    yield "http://localhost:8765"

    await runner.cleanup()


async def test_fa_client_exposure_levels(mock_flashalpha_server):
    config = FAConfig(api_key="test_key")
    # Override base URL to point at mock server
    config._base_url_override = mock_flashalpha_server

    async with FlashAlphaClient(config) as fa:
        levels = await fa.get_exposure_levels("QQQ")

    assert levels.gamma_flip == 480.0
    assert levels.regime == "positive"
```

### Recorded Response Replay for Unit Tests

```python
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch


def load_fixture(name: str) -> dict:
    """Load a recorded API response from tests/fixtures/."""
    fixture_path = Path(__file__).parent / "fixtures" / f"{name}.json"
    return json.loads(fixture_path.read_text())


async def test_fa_zero_dte_parsing():
    fixture = load_fixture("fa_zero_dte_qqq")

    with patch.object(FlashAlphaClient, "_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = fixture

        config = FAConfig(api_key="test")
        async with FlashAlphaClient(config) as fa:
            zte = await fa.get_zero_dte("QQQ")

    assert zte.pin_score is not None
    assert 0 <= zte.pin_score <= 100
    assert zte.charm_regime in ("dealers_buy", "dealers_sell", None)
```

---

## Graceful Shutdown

Both clients must drain pending requests before the event loop closes:

```python
async def shutdown_clients(
    fa_client: FlashAlphaClient,
    massive_client: MassiveClient,
    timeout: float = 5.0,
) -> None:
    """
    Close both clients gracefully. Called during DEEP6 shutdown sequence.
    aiohttp sessions close their connection pool on __aexit__.
    """
    logger.info("clients.shutdown_start")

    shutdown_tasks = [
        asyncio.create_task(fa_client.__aexit__(None, None, None)),
        asyncio.create_task(massive_client.__aexit__(None, None, None)),
    ]

    try:
        await asyncio.wait_for(
            asyncio.gather(*shutdown_tasks, return_exceptions=True),
            timeout=timeout,
        )
        logger.info("clients.shutdown_ok")
    except asyncio.TimeoutError:
        logger.warning("clients.shutdown_timeout", extra={"timeout": timeout})
```
