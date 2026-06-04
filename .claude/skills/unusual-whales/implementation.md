# Unusual Whales Python Integration — DEEP6 Async Pipeline

## Official Python SDK

Two packages exist. Pick based on your needs:

**Option A: Official SDK (alpha)**
```bash
pip install --pre unusualwhales-python
```
- Version: `0.1.0a6` (alpha, official from Unusual Whales)
- Transport: `httpx` (async-native, HTTP/2 capable)
- Sync class: `Unusualwhales`
- Async class: `AsyncUnusualwhales`
- Minimal surface area, still evolving

**Option B: OpenAPI-generated client (more complete)**
```bash
pip install unusualwhales-python-client
```
- Version: `5.0.1`
- Generated from the full OpenAPI spec
- Dependencies: `httpx`, `attrs`, `python-dateutil`
- More endpoints covered, but generated code is verbose

For DEEP6, neither is ideal. The custom async client below gives you rate limiting, circuit breaking, and retry logic that production use requires.

---

## Custom Async Client (Recommended for DEEP6)

This is the production-grade wrapper. It pools connections, enforces rate limits, and handles transient failures without manual intervention.

```python
import httpx
import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum

# --- Rate Limiter ---

@dataclass
class RateLimiter:
    max_per_minute: int = 120
    _timestamps: list = field(default_factory=list)

    async def acquire(self):
        now = time.monotonic()
        self._timestamps = [t for t in self._timestamps if now - t < 60]
        if len(self._timestamps) >= self.max_per_minute:
            sleep_time = 60 - (now - self._timestamps[0])
            await asyncio.sleep(sleep_time)
        self._timestamps.append(time.monotonic())


# --- Circuit Breaker ---

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 30.0, success_threshold: int = 2):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.success_threshold = success_threshold
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at: float | None = None

    def record_success(self):
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self):
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            self._success_count = 0
        elif self._state == CircuitState.CLOSED:
            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()

    def is_open(self) -> bool:
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - (self._opened_at or 0)
            if elapsed >= self.cooldown_seconds:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                return False
            return True
        return False


# --- Main Client ---

class UnusualWhalesClient:
    def __init__(self, api_key: str, rate_limit_per_minute: int = 120, max_retries: int = 3):
        self.base_url = "https://api.unusualwhales.com"
        self.max_retries = max_retries
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "UW-CLIENT-API-ID": "100001",
            "Accept": "application/json",
        }
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=30.0,
        )
        self._rate_limiter = RateLimiter(max_per_minute=rate_limit_per_minute)
        self._circuit_breaker = CircuitBreaker()
        self._last_usage: dict = {}

    async def _get(self, path: str, **params) -> dict:
        if self._circuit_breaker.is_open():
            raise RuntimeError("Circuit breaker is open — UW API unavailable, retrying after cooldown")

        await self._rate_limiter.acquire()

        backoff_delays = [1.0, 2.0, 4.0, 8.0]
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.get(f"/api{path}", params={k: v for k, v in params.items() if v is not None})
                self._last_usage = self._extract_usage(response)
                response.raise_for_status()
                self._circuit_breaker.record_success()
                return response.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    reset_ms = int(exc.response.headers.get("x-uw-req-per-minute-reset", 60000))
                    await asyncio.sleep(reset_ms / 1000)
                    last_exc = exc
                    continue
                self._circuit_breaker.record_failure()
                raise
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                self._circuit_breaker.record_failure()
                last_exc = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(backoff_delays[min(attempt, len(backoff_delays) - 1)])
                    continue
                raise

        raise last_exc  # type: ignore

    @staticmethod
    def _extract_usage(response: httpx.Response) -> dict:
        h = response.headers
        return {
            "daily_limit": h.get("x-uw-token-req-limit"),
            "daily_used": h.get("x-uw-daily-req-count"),
            "minute_remaining": h.get("x-uw-req-per-minute-remaining"),
            "minute_used": h.get("x-uw-minute-req-counter"),
            "minute_reset_ms": h.get("x-uw-req-per-minute-reset"),
        }

    def get_api_usage(self) -> dict:
        """Returns usage stats extracted from the last response headers."""
        return self._last_usage

    # --- Dark Pool ---

    async def get_darkpool_ticker(self, ticker: str, **kwargs):
        """Dark pool prints for a specific ticker."""
        return await self._get(f"/darkpool/{ticker}", **kwargs)

    async def get_darkpool_recent(self, **kwargs):
        """Most recent dark pool prints across all tickers."""
        return await self._get("/darkpool/recent", **kwargs)

    # --- Options Flow ---

    async def get_flow_alerts(self, **kwargs):
        """Real-time options flow alerts. Filter by ticker_symbol, min_premium, etc."""
        return await self._get("/option-trades/flow-alerts", **kwargs)

    # --- GEX ---

    async def get_spot_gex(self, ticker: str):
        """Spot GEX by strike for a ticker. Use QQQ/NDX as NQ proxy."""
        return await self._get(f"/stock/{ticker}/spot-exposures/strike")

    # --- Market Tide ---

    async def get_market_tide(self, **kwargs):
        """Aggregate options market tide (call vs put premium flow)."""
        return await self._get("/market/market-tide", **kwargs)

    # --- Dark Pool S/R Levels ---

    async def get_price_levels(self, ticker: str, **kwargs):
        """Off-lit and lit price levels — dark pool support/resistance clusters."""
        return await self._get(f"/stock/{ticker}/stock-volume-price-levels", **kwargs)

    async def close(self):
        await self._client.aclose()
```

---

## Usage Monitoring

Every response from the UW API includes rate limit headers. The client captures them automatically after each request.

| Header | Meaning |
|--------|---------|
| `x-uw-token-req-limit` | Your daily request cap |
| `x-uw-daily-req-count` | Requests used today (resets 8 PM ET) |
| `x-uw-req-per-minute-remaining` | Remaining in the current minute window |
| `x-uw-minute-req-counter` | Requests used in the current minute |
| `x-uw-req-per-minute-reset` | Milliseconds until the minute counter resets |

```python
client = UnusualWhalesClient(api_key=os.environ["UW_API_KEY"])
await client.get_flow_alerts(ticker_symbol="QQQ")

usage = client.get_api_usage()
print(f"Daily: {usage['daily_used']} / {usage['daily_limit']}")
print(f"This minute: {usage['minute_used']} used, {usage['minute_remaining']} remaining")
print(f"Resets in: {usage['minute_reset_ms']}ms")
```

---

## DEEP6 Integration Pattern

The UW client slots into the existing async pipeline alongside Rithmic. Both run concurrently in the same event loop.

```python
import os
import asyncio
from deep6.uw_client import UnusualWhalesClient
from deep6.signals import compute_signals
from deep6.darkpool import cluster_dark_pool_prints
from deep6.gex import find_gamma_walls


async def nq_signal_pipeline():
    uw = UnusualWhalesClient(api_key=os.environ["UW_API_KEY"])

    try:
        # Fetch all UW data concurrently — one round-trip latency instead of four
        darkpool, flow, gex, tide = await asyncio.gather(
            uw.get_darkpool_ticker("QQQ", min_size=10000),
            uw.get_flow_alerts(ticker_symbol="QQQ", min_premium=50000),
            uw.get_spot_gex("QQQ"),
            uw.get_market_tide(),
        )

        # Extract dark pool S/R clusters
        dp_levels = cluster_dark_pool_prints(darkpool["data"])

        # Extract GEX walls from strike exposure
        gex_walls = find_gamma_walls(gex["data"])

        # Feed into the 44-signal engine
        signals = compute_signals(dp_levels, flow["data"], gex_walls, tide["data"])

        return signals

    finally:
        await uw.close()
```

For long-running processes, keep the client alive across bar updates rather than recreating it each cycle. The connection pool is the expensive part.

```python
# In your main service class
class DEEP6Service:
    def __init__(self):
        self.uw = UnusualWhalesClient(api_key=os.environ["UW_API_KEY"])

    async def on_bar_close(self, bar):
        # Reuse the same client — no reconnect overhead
        gex = await self.uw.get_spot_gex("QQQ")
        ...

    async def shutdown(self):
        await self.uw.close()
```

---

## Error Handling

| Status | Cause | Fix |
|--------|-------|-----|
| `401` | Invalid or expired token | Regenerate at https://unusualwhales.com/settings/developer-settings |
| `403` | Endpoint not in your subscription tier | Check plan at https://unusualwhales.com/settings/account |
| `429` | Rate limit hit | Wait `x-uw-req-per-minute-reset` ms. The client handles this automatically. |
| `404` | Endpoint doesn't exist | Cross-check against `api-reference.md`. Don't trust hallucinated paths. |

The client raises `httpx.HTTPStatusError` for 4xx/5xx responses after exhausting retries. Catch it at the pipeline level:

```python
try:
    data = await uw.get_flow_alerts(ticker_symbol="QQQ")
except httpx.HTTPStatusError as exc:
    if exc.response.status_code == 403:
        logger.error("UW tier insufficient for flow alerts — check subscription")
    elif exc.response.status_code == 401:
        logger.error("UW token invalid — rotate key at unusualwhales.com/settings/developer-settings")
    raise
except RuntimeError as exc:
    # Circuit breaker open
    logger.warning(str(exc))
```

---

## MCP Server Integration

The Unusual Whales API exposes an MCP server endpoint. This lets Claude Code query UW data directly during analysis sessions.

**Claude Code (CLI):**
```bash
claude mcp add --transport http unusualwhales https://api.unusualwhales.com/api/mcp \
  --header "Authorization: Bearer YOUR_KEY"
```

**OpenCode (`opencode.json`):**
```json
{
  "mcpServers": {
    "unusualwhales": {
      "type": "http",
      "url": "https://api.unusualwhales.com/api/mcp",
      "headers": {
        "Authorization": "Bearer ${UW_API_KEY}"
      }
    }
  }
}
```

Use `${UW_API_KEY}` to pull from the environment rather than hardcoding the token.

---

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `UW_API_KEY` | API token (required) | None |
| `UW_RATE_LIMIT_PER_MINUTE` | Override the sliding window cap | `120` |
| `UW_MAX_RETRIES` | Override retry count on transient failures | `3` |

Load them in your service entrypoint:

```python
import os

client = UnusualWhalesClient(
    api_key=os.environ["UW_API_KEY"],
    rate_limit_per_minute=int(os.environ.get("UW_RATE_LIMIT_PER_MINUTE", 120)),
    max_retries=int(os.environ.get("UW_MAX_RETRIES", 3)),
)
```

Never hardcode the API key. Never commit it to git. Add `UW_API_KEY` to `.env` and `.gitignore`.
