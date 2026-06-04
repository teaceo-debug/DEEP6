# Massive.com API Reference for NQ Options Algo

Massive.com (Polygon.io's options data arm) provides tick-level options data, minute aggregates,
real-time quotes, and bulk flat files for all US-listed options. For NQ algo work, the primary
symbols are `QQQ` (liquid, tight spreads, 0DTE every day) and `SPXW`-adjacent NDX options.

This file covers integration patterns only. For theory on what GEX/vanna/charm mean, see
`options-bias-engine/domains/`.

---

## 1. Authentication and Setup

All requests require an API key. Two delivery methods:

```python
# Header (preferred for REST)
headers = {"Authorization": "Bearer YOUR_API_KEY"}

# Query param (acceptable, avoid in logs)
params = {"apiKey": "YOUR_API_KEY"}
```

Base URLs:
- REST: `https://api.polygon.io`
- WebSocket: `wss://socket.polygon.io`
- Flat files: `https://files.polygon.io` (S3-compatible)

```python
import os
import aiohttp
import asyncio

POLYGON_API_KEY = os.environ["POLYGON_API_KEY"]
BASE_URL = "https://api.polygon.io"
WS_URL = "wss://socket.polygon.io"

def auth_headers() -> dict:
    return {"Authorization": f"Bearer {POLYGON_API_KEY}"}

async def get(session: aiohttp.ClientSession, path: str, params: dict = None) -> dict:
    url = f"{BASE_URL}{path}"
    async with session.get(url, headers=auth_headers(), params=params or {}) as resp:
        resp.raise_for_status()
        return await resp.json()
```

### Tier access summary

| Tier | Price | Options access |
|------|-------|---------------|
| Basic | Free | Contract reference data, 2yr delayed |
| Starter | $29/mo | Minute aggregates, 15-min delayed quotes |
| Developer | $79/mo | Trades + quotes, delayed |
| Advanced | $199/mo | Real-time trades + quotes |
| Business | $399/mo | + Fair Market Value (FMV) feed |

For NQ algo work, **Advanced** is the minimum viable tier for live signal generation.
Developer is sufficient for backtesting and strategy development.

---

## 2. REST Endpoints

### 2.1 Option Chain Snapshot

Fetches the full option chain for an underlying with Greeks, IV, OI, bid/ask, and VWAP.
This is the highest-value single call for building an `OptionsState`.

```
GET /v3/snapshot/options/{underlyingAsset}
```

**Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `underlyingAsset` | path | Ticker, e.g. `QQQ` or `NDX` |
| `strike_price.gte` | query | Min strike filter |
| `strike_price.lte` | query | Max strike filter |
| `expiration_date.gte` | query | Min expiry (YYYY-MM-DD) |
| `expiration_date.lte` | query | Max expiry |
| `contract_type` | query | `call` or `put` |
| `limit` | query | Max results (default 250, max 250) |
| `cursor` | query | Pagination cursor from prior response |

**Python example — fetch ATM QQQ chain for 0DTE:**

```python
from datetime import date
import aiohttp

async def fetch_qqq_0dte_chain(
    session: aiohttp.ClientSession,
    spot: float,
    width_pct: float = 0.03,
) -> list[dict]:
    """Fetch QQQ options within 3% of spot expiring today."""
    today = date.today().isoformat()
    lo = round(spot * (1 - width_pct), 2)
    hi = round(spot * (1 + width_pct), 2)

    results = []
    cursor = None

    while True:
        params = {
            "expiration_date.gte": today,
            "expiration_date.lte": today,
            "strike_price.gte": lo,
            "strike_price.lte": hi,
            "limit": 250,
        }
        if cursor:
            params["cursor"] = cursor

        data = await get(session, f"/v3/snapshot/options/QQQ", params)

        results.extend(data.get("results", []))

        # Polygon paginates via next_url cursor
        next_url = data.get("next_url")
        if not next_url:
            break
        # Extract cursor from next_url
        cursor = next_url.split("cursor=")[-1].split("&")[0]

    return results
```

**Response shape (single contract):**

```json
{
  "break_even_price": 487.23,
  "day": {
    "change": 1.45,
    "change_percent": 3.2,
    "close": 4.65,
    "high": 5.10,
    "last_updated": 1716912000000000000,
    "low": 3.20,
    "open": 3.80,
    "previous_close": 3.20,
    "volume": 48320,
    "vwap": 4.41
  },
  "details": {
    "contract_type": "call",
    "exercise_style": "american",
    "expiration_date": "2026-05-25",
    "shares_per_contract": 100,
    "strike_price": 487.0,
    "ticker": "O:QQQ260525C00487000"
  },
  "greeks": {
    "delta": 0.52,
    "gamma": 0.089,
    "theta": -0.31,
    "vega": 0.18
  },
  "implied_volatility": 0.1842,
  "open_interest": 12450,
  "last_quote": {
    "ask": 4.70,
    "ask_size": 120,
    "bid": 4.60,
    "bid_size": 85,
    "last_updated": 1716912001000000000,
    "midpoint": 4.65,
    "timeframe": "REAL-TIME"
  },
  "last_trade": {
    "conditions": [14],
    "exchange": 4,
    "price": 4.65,
    "sip_timestamp": 1716912000500000000,
    "size": 10
  },
  "underlying_asset": {
    "change_to_break_even": 0.23,
    "last_updated": 1716912001000000000,
    "price": 486.77,
    "ticker": "QQQ",
    "timeframe": "REAL-TIME"
  }
}
```

**Key fields for NQ algo:**
- `greeks.gamma` + `open_interest` → GEX contribution per strike
- `implied_volatility` → IV surface construction
- `last_quote.midpoint` → fair value for flow analysis
- `details.strike_price` + `details.expiration_date` → level mapping

---

### 2.2 Tick-Level Options Trades

Individual trade prints with exchange, conditions, and nanosecond timestamps.

```
GET /v3/trades/{optionsTicker}
```

**Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `optionsTicker` | path | OCC symbol, e.g. `O:QQQ260525C00487000` |
| `timestamp.gte` | query | Unix nanoseconds or ISO datetime |
| `timestamp.lte` | query | Upper bound |
| `limit` | query | Max 50,000 |
| `order` | query | `asc` or `desc` |
| `sort` | query | `timestamp` |

**Python example — stream recent QQQ 487C trades:**

```python
async def fetch_option_trades(
    session: aiohttp.ClientSession,
    ticker: str,  # e.g. "O:QQQ260525C00487000"
    since_ns: int,  # unix nanoseconds
) -> list[dict]:
    params = {
        "timestamp.gte": since_ns,
        "limit": 1000,
        "order": "asc",
        "sort": "timestamp",
    }
    data = await get(session, f"/v3/trades/{ticker}", params)
    return data.get("results", [])
```

**Response shape:**

```json
{
  "conditions": [14, 41],
  "correction": 0,
  "exchange": 4,
  "id": "4",
  "participant_timestamp": 1716912000123456789,
  "price": 4.65,
  "sequence_number": 1234567,
  "sip_timestamp": 1716912000234567890,
  "size": 25,
  "trf_timestamp": 0
}
```

**Condition codes relevant to flow analysis:**
- `14` = Regular sale
- `41` = Intermarket sweep (aggressive, directional)
- `37` = Opening print
- `15` = Form T (extended hours)

Sweeps (condition 41) are the highest-signal trades for directional flow detection.

---

### 2.3 Per-Minute OHLC Aggregates

```
GET /v2/aggs/ticker/{optionsTicker}/prev
```

Returns the previous day's OHLC for a single contract. For intraday minute bars, use:

```
GET /v2/aggs/ticker/{optionsTicker}/range/1/minute/{from}/{to}
```

**Python example — fetch today's minute bars for QQQ 487C:**

```python
from datetime import date

async def fetch_option_minute_bars(
    session: aiohttp.ClientSession,
    ticker: str,
    from_date: str,  # YYYY-MM-DD
    to_date: str,
) -> list[dict]:
    path = f"/v2/aggs/ticker/{ticker}/range/1/minute/{from_date}/{to_date}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000}
    data = await get(session, path, params)
    return data.get("results", [])
```

**Response shape:**

```json
{
  "c": 4.65,
  "h": 4.80,
  "l": 4.50,
  "n": 142,
  "o": 4.55,
  "otc": false,
  "t": 1716912000000,
  "v": 3420.0,
  "vw": 4.61
}
```

Fields: `o/h/l/c` = OHLC, `v` = volume, `vw` = VWAP, `n` = trade count, `t` = unix ms.

---

### 2.4 Contract Reference Data

Fetch contract specs: expiry, strike, style, underlying multiplier.

```
GET /v3/reference/options/contracts/{options_ticker}
```

**Python example:**

```python
async def fetch_contract_ref(
    session: aiohttp.ClientSession,
    ticker: str,  # "O:QQQ260525C00487000"
) -> dict:
    data = await get(session, f"/v3/reference/options/contracts/{ticker}")
    return data.get("results", {})
```

**Response shape:**

```json
{
  "additional_underlyings": [],
  "cfi": "OCAFPS",
  "contract_type": "call",
  "correction": 0,
  "exercise_style": "american",
  "expiration_date": "2026-05-25",
  "primary_exchange": "BATO",
  "shares_per_contract": 100,
  "strike_price": 487.0,
  "ticker": "O:QQQ260525C00487000",
  "underlying_ticker": "QQQ"
}
```

**NDX note:** NDX options use European exercise style (`exercise_style: "european"`).
QQQ uses American. This matters for early assignment risk but not for GEX computation.

---

## 3. WebSocket Feeds

All WebSocket connections authenticate via a JSON auth message after connecting.

```python
import json
import websockets
import asyncio

async def ws_connect(feed: str) -> websockets.WebSocketClientProtocol:
    """Connect and authenticate to a Polygon WebSocket feed."""
    uri = f"{WS_URL}/{feed}"
    ws = await websockets.connect(uri)

    # Wait for connected message
    msg = json.loads(await ws.recv())
    assert msg[0]["status"] == "connected"

    # Authenticate
    await ws.send(json.dumps({"action": "auth", "params": POLYGON_API_KEY}))
    auth_msg = json.loads(await ws.recv())
    assert auth_msg[0]["status"] == "auth_success", f"Auth failed: {auth_msg}"

    return ws
```

### 3.1 Minute Aggregates Feed

```
WS /options/AM
```

Fires once per minute per subscribed contract with OHLCV.

```python
async def stream_qqq_minute_aggs(contracts: list[str]):
    """Stream minute aggregates for a list of QQQ option tickers."""
    ws = await ws_connect("options")

    # Subscribe — use wildcard for all QQQ options
    sub_params = ",".join(f"AM.{t}" for t in contracts)
    await ws.send(json.dumps({"action": "subscribe", "params": sub_params}))

    async for raw in ws:
        msgs = json.loads(raw)
        for msg in msgs:
            if msg.get("ev") == "AM":
                yield {
                    "ticker": msg["sym"],
                    "open": msg["o"],
                    "high": msg["h"],
                    "low": msg["l"],
                    "close": msg["c"],
                    "volume": msg["v"],
                    "vwap": msg["vw"],
                    "timestamp_ms": msg["e"],  # end of minute
                }
```

**Message shape:**

```json
{
  "ev": "AM",
  "sym": "O:QQQ260525C00487000",
  "v": 3420,
  "av": 18200,
  "op": 4.55,
  "vw": 4.61,
  "o": 4.55,
  "c": 4.65,
  "h": 4.80,
  "l": 4.50,
  "a": 4.58,
  "z": 142,
  "s": 1716912000000,
  "e": 1716912060000
}
```

**Subscription limit:** 1,000 contracts per connection. For full QQQ chain (typically 2,000+ contracts on 0DTE), open two connections.

---

### 3.2 Quote Updates Feed

```
WS /options/Q
```

Real-time NBBO updates. Fires on every quote change.

```python
async def stream_qqq_quotes(contracts: list[str]):
    """Stream real-time quotes for QQQ options."""
    ws = await ws_connect("options")

    sub_params = ",".join(f"Q.{t}" for t in contracts)
    await ws.send(json.dumps({"action": "subscribe", "params": sub_params}))

    async for raw in ws:
        msgs = json.loads(raw)
        for msg in msgs:
            if msg.get("ev") == "Q":
                yield {
                    "ticker": msg["sym"],
                    "bid": msg["bp"],
                    "bid_size": msg["bs"],
                    "ask": msg["ap"],
                    "ask_size": msg["as"],
                    "midpoint": (msg["bp"] + msg["ap"]) / 2,
                    "timestamp_ns": msg["t"],
                    "exchange": msg["x"],
                }
```

**Message shape:**

```json
{
  "ev": "Q",
  "sym": "O:QQQ260525C00487000",
  "bx": 4,
  "bp": 4.60,
  "bs": 85,
  "ax": 12,
  "ap": 4.70,
  "as": 120,
  "c": 0,
  "t": 1716912001234567890,
  "x": 4,
  "q": 987654321
}
```

**Volume warning:** QQQ 0DTE generates 50,000+ quote updates per minute across the full chain.
Subscribe only to strikes within 2% of spot for real-time signal work.

---

### 3.3 Fair Market Value Feed (Business Tier)

```
WS /business/options/FMV
```

Polygon's proprietary fair value model. Fires when their model updates the theoretical price.
Useful for detecting when market price diverges from model (flow signal).

```python
async def stream_fmv(contracts: list[str]):
    ws = await ws_connect("business/options")

    sub_params = ",".join(f"FMV.{t}" for t in contracts)
    await ws.send(json.dumps({"action": "subscribe", "params": sub_params}))

    async for raw in ws:
        msgs = json.loads(raw)
        for msg in msgs:
            if msg.get("ev") == "FMV":
                yield {
                    "ticker": msg["sym"],
                    "fmv": msg["fmv"],
                    "timestamp_ns": msg["t"],
                }
```

**FMV divergence signal:** When `last_trade.price > fmv * 1.05`, aggressive buying above fair value.
When `last_trade.price < fmv * 0.95`, aggressive selling below fair value.

---

## 4. Flat File Access

Polygon stores bulk historical data in S3-compatible flat files. Useful for backtesting
and building historical IV surfaces.

### 4.1 File structure

```
https://files.polygon.io/flatfiles/options/
  minute_aggs/
    YYYY/MM/DD/
      {YYYY-MM-DD}.csv.gz          # All options, minute OHLCV
  trades/
    YYYY/MM/DD/
      {YYYY-MM-DD}.csv.gz          # All options trades, nanosecond timestamps
  quotes/
    YYYY/MM/DD/
      {YYYY-MM-DD}.csv.gz          # All options quotes
  day_aggs/
    YYYY/MM/DD/
      {YYYY-MM-DD}.csv.gz          # Daily OHLCV + OI
```

### 4.2 Download pattern

```python
import aiohttp
import gzip
import csv
import io
from datetime import date

async def download_qqq_minute_aggs(
    session: aiohttp.ClientSession,
    target_date: date,
) -> list[dict]:
    """Download and filter QQQ options minute aggs for a given date."""
    date_str = target_date.strftime("%Y-%m-%d")
    year = target_date.strftime("%Y")
    month = target_date.strftime("%m")
    day = target_date.strftime("%d")

    url = f"https://files.polygon.io/flatfiles/options/minute_aggs/{year}/{month}/{day}/{date_str}.csv.gz"

    async with session.get(url, headers=auth_headers()) as resp:
        resp.raise_for_status()
        compressed = await resp.read()

    # Decompress and filter for QQQ
    with gzip.open(io.BytesIO(compressed), "rt") as f:
        reader = csv.DictReader(f)
        return [
            row for row in reader
            if row.get("ticker", "").startswith("O:QQQ")
        ]
```

### 4.3 Trades flat file schema

```
ticker,conditions,correction,exchange,id,participant_timestamp,price,
sequence_number,sip_timestamp,size,trf_timestamp
O:QQQ260525C00487000,"[14]",0,4,abc123,1716912000123456789,4.65,
1234567,1716912000234567890,25,0
```

**Nanosecond timestamps** allow sub-millisecond sequencing for replay. Convert to Python datetime:

```python
from datetime import datetime, timezone

def ns_to_dt(ns: int) -> datetime:
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)
```

---

## 5. Rate Limits and Error Handling

### Rate limits by tier

| Tier | Requests/min | WebSocket connections |
|------|-------------|----------------------|
| Basic | 5 | 0 |
| Starter | 100 | 1 |
| Developer | 1,000 | 5 |
| Advanced | 10,000 | 10 |
| Business | Unlimited | Unlimited |

### Retry pattern with exponential backoff

```python
import asyncio
import aiohttp
from typing import Any

class PolygonClient:
    def __init__(self, api_key: str, max_retries: int = 5):
        self.api_key = api_key
        self.max_retries = max_retries
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args):
        await self._session.close()

    async def get(self, path: str, params: dict = None) -> dict:
        url = f"{BASE_URL}{path}"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        for attempt in range(self.max_retries):
            try:
                async with self._session.get(
                    url, headers=headers, params=params or {}
                ) as resp:
                    if resp.status == 429:
                        # Rate limited — back off
                        retry_after = int(resp.headers.get("Retry-After", 60))
                        await asyncio.sleep(retry_after)
                        continue
                    if resp.status == 403:
                        raise PermissionError(f"Tier restriction: {path}")
                    if resp.status == 404:
                        return {"results": []}  # Contract not found, not an error
                    resp.raise_for_status()
                    return await resp.json()

            except aiohttp.ClientConnectorError:
                wait = 2 ** attempt
                await asyncio.sleep(wait)

        raise RuntimeError(f"Failed after {self.max_retries} attempts: {path}")
```

### Common error codes

| HTTP | Meaning | Action |
|------|---------|--------|
| 200 | OK | Process normally |
| 400 | Bad request | Log params, fix query |
| 403 | Tier restriction | Upgrade or skip endpoint |
| 404 | Not found | Contract may not exist yet |
| 429 | Rate limited | Respect `Retry-After` header |
| 500 | Server error | Retry with backoff |

---

## 6. QQQ/NDX-Specific Query Patterns for NQ Algo

### 6.1 OCC ticker construction

```python
def build_occ_ticker(
    underlying: str,  # "QQQ" or "NDX"
    expiry: date,
    contract_type: str,  # "C" or "P"
    strike: float,
) -> str:
    """Build OCC option ticker format: O:QQQ260525C00487000"""
    exp_str = expiry.strftime("%y%m%d")
    strike_int = int(strike * 1000)  # Strike in thousandths
    return f"O:{underlying}{exp_str}{contract_type}{strike_int:08d}"

# Examples
# QQQ 487 call expiring 2026-05-25 -> "O:QQQ260525C00487000"
# QQQ 480 put expiring 2026-05-25  -> "O:QQQ260525P00480000"
# NDX 21000 call expiring 2026-05-30 -> "O:NDX260530C21000000"
```

### 6.2 Fetching the full 0DTE chain for GEX computation

```python
async def fetch_0dte_gex_inputs(
    session: aiohttp.ClientSession,
    spot_qqq: float,
) -> dict[float, dict]:
    """
    Returns dict keyed by strike with {call_gamma, put_gamma, call_oi, put_oi}.
    Used to compute GEX per strike for dealer positioning map.
    """
    today = date.today().isoformat()
    lo = round(spot_qqq * 0.95, 0)
    hi = round(spot_qqq * 1.05, 0)

    chain = await fetch_qqq_0dte_chain(session, spot_qqq, width_pct=0.05)

    strikes: dict[float, dict] = {}
    for contract in chain:
        details = contract["details"]
        greeks = contract.get("greeks", {})
        strike = details["strike_price"]
        ctype = details["contract_type"]
        oi = contract.get("open_interest", 0)
        gamma = greeks.get("gamma", 0.0)

        if strike not in strikes:
            strikes[strike] = {
                "call_gamma": 0.0, "put_gamma": 0.0,
                "call_oi": 0, "put_oi": 0,
            }

        if ctype == "call":
            strikes[strike]["call_gamma"] = gamma
            strikes[strike]["call_oi"] = oi
        else:
            strikes[strike]["put_gamma"] = gamma
            strikes[strike]["put_oi"] = oi

    return strikes
```

### 6.3 NDX vs QQQ selection guide

| Use case | Symbol | Reason |
|----------|--------|--------|
| 0DTE flow analysis | QQQ | 10x more volume, tighter spreads |
| Weekly GEX levels | QQQ | Dominant OI concentration |
| Monthly expiry levels | NDX | Institutional hedges live here |
| IV surface construction | QQQ | More strikes, better interpolation |
| Index-level accuracy | NDX | No tracking error vs NQ |

For NQ proxy conversion, always use QQQ levels scaled by the NQ/QQQ ratio.
See `nq-proxy-pipeline.md` for the conversion math.

### 6.4 Polling cadence for live algo

```python
import asyncio
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class MassivePoller:
    client: PolygonClient
    spot_qqq: float = 0.0
    chain_cache: dict = field(default_factory=dict)
    last_chain_fetch: datetime | None = None

    async def run(self):
        """Main polling loop. Runs concurrently with signal engine."""
        await asyncio.gather(
            self._poll_chain(),      # Every 30s — full chain snapshot
            self._poll_quotes(),     # Continuous — WebSocket
        )

    async def _poll_chain(self):
        async with PolygonClient(POLYGON_API_KEY) as client:
            while True:
                try:
                    self.chain_cache = await fetch_0dte_gex_inputs(
                        client._session, self.spot_qqq
                    )
                    self.last_chain_fetch = datetime.utcnow()
                except Exception as e:
                    print(f"Chain fetch error: {e}")
                await asyncio.sleep(30)

    async def _poll_quotes(self):
        # Build contract list from current chain
        contracts = list(self.chain_cache.keys())[:500]  # Top 500 by OI
        async for quote in stream_qqq_quotes(contracts):
            # Update midpoint in chain cache
            strike = self._ticker_to_strike(quote["ticker"])
            if strike in self.chain_cache:
                self.chain_cache[strike]["midpoint"] = quote["midpoint"]
```
