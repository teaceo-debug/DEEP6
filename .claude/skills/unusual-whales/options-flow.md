# Unusual Whales Options Flow — Screening & Signal Detection

## Overview

Unusual Whales (UW) provides institutional-grade options flow data via REST API. The core value for DEEP6 is detecting large, directional, opening trades in QQQ/NDX as a proxy for NQ directional bias. Flow alerts surface sweeps, floor trades, and repeat-hit patterns that precede significant moves.

Base URL: `https://api.unusualwhales.com`
Auth: `Authorization: Bearer {UW_API_TOKEN}` header on every request.

---

## Flow Alerts Endpoint

```
GET /api/option-trades/flow-alerts
```

The primary screening endpoint. Returns filtered flow alerts across all tickers or a specific one.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `ticker_symbol` | string | Filter to a single ticker (e.g., `QQQ`, `NDX`) |
| `min_premium` | number | Minimum total premium in dollars (e.g., `100000` for $100K+) |
| `size_greater_oi` | boolean | Only return trades where size > open interest (strong opening signal) |
| `is_call` | boolean | Calls only |
| `is_put` | boolean | Puts only |
| `is_otm` | boolean | Out-of-the-money contracts only |
| `limit` | integer | Max results, capped at **200** |
| `is_ask_side` | boolean | Trades executed at or above ask (aggressive buyers) |
| `is_bid_side` | boolean | Trades executed at or below bid (aggressive sellers) |
| `min_dte` | integer | Minimum days to expiry |
| `max_dte` | integer | Maximum days to expiry |
| `rule_name[]` | string[] | Filter by specific alert rule names (see rules below) |
| `all_opening` | boolean | Only return opening trades |
| `min_open_interest` | number | Minimum existing open interest |
| `max_open_interest` | number | Maximum existing open interest |
| `min_size` | number | Minimum contract size |
| `max_size` | number | Maximum contract size |

---

## Flow Alert Rules

UW classifies each alert into one of these named rule categories:

| Rule Name | What It Means |
|-----------|---------------|
| `RepeatedHits` | Same contract hit multiple times in a short window — accumulation pattern |
| `RepeatedHitsAscendingFill` | Repeated hits with each fill at a higher price — urgency, chasing |
| `RepeatedHitsDescendingFill` | Repeated hits with each fill at a lower price — possible distribution |
| `SweepsFollowedByFloor` | Electronic sweeps followed by a large floor block — institutional confirmation |
| `OTMEarningsFloor` | Large OTM floor trade near an earnings event |
| `LowHistoricVolumeFloor` | Floor trade in a contract with historically low volume — unusual activity |
| `SmallCapFloorTrade` | Large floor block in a small-cap name |
| `MidCapFloorTrade` | Large floor block in a mid-cap name |

For NQ/QQQ bias, prioritize: `RepeatedHitsAscendingFill`, `SweepsFollowedByFloor`, and `RepeatedHits` on QQQ/NDX.

---

## 6-Component Flow Scoring System

UW assigns each flow alert a score from 0 to 100 using six weighted components. Understanding this scoring lets you replicate or extend it in DEEP6.

### Component Breakdown

**1. Premium Score** (weight: 1.0)
Log-normalized, capped at $10M.
- $1M premium → score ~0.86
- $100K premium → score ~0.71
- Formula: `log(premium) / log(10_000_000)`, clamped to [0, 1]

**2. Size vs Open Interest** (weight: 1.0)
Ratio of trade size to existing OI, capped at 1.0.
- Size = OI → 1.0 (strong opening signal)
- Size = 10% of OI → 0.10

**3. Aggressor Strength** (weight: 0.8)
NBBO-aware fill location:
- At or above ask → ~1.0 (aggressive buyer)
- At midpoint → ~0.5
- Below midpoint → low score (passive or closing)

**4. Sweep Structure** (weight: 1.0)
- Coalesced sweep (multi-venue, multi-fill) → 1.0
- Singleton block (single large fill) → 0.55
- Sub-block (small single fill) → 0.20

**5. Opening Bias** (weight: 1.2, highest weight)
- Opening trade → 1.0
- Closing trade → 0.3
- Unknown → 0.5
- Multiplied by OI confidence factor (~0.43 when OI data is stale or unavailable)

**6. Tenor (DTE)** (weight: 0.6)
- 0DTE → 1.0 (maximum urgency)
- 22 DTE → ~0.51
- 45+ DTE → 0.0 (long-dated, less directional urgency)

### Final Score

```
raw = sum(component_i * weight_i)
score = int((raw / 5.6) * 100)   # 5.6 = sum of all weights
```

Score range: 0-100. Scores above 70 are high-conviction. Above 85 are rare and worth immediate attention.

---

## Recent Ticker Flow

```
GET /api/stock/{ticker}/flow-recent
```

Returns the most recent flow alerts for a specific ticker.

| Parameter | Type | Description |
|-----------|------|-------------|
| `side` | string | `ASK`, `BID`, or `MID` |
| `min_premium` | number | Minimum premium filter |
| `limit` | integer | Max results, capped at **500** |

Use this for real-time QQQ monitoring during the trading session.

---

## Flow Per Strike

```
GET /api/stock/{ticker}/flow-per-strike
```

Aggregates flow by strike price. Shows where premium is concentrating across the options chain. Useful for identifying which strikes are seeing the most institutional activity.

---

## Flow Per Expiry

```
GET /api/stock/{ticker}/flow-per-expiry
```

Aggregates flow by expiration date. Reveals whether activity is concentrated in 0DTE, weekly, or monthly expirations. Heavy 0DTE flow on QQQ often precedes intraday NQ moves.

---

## Options Screener

```
GET /api/screener/option-contracts
```

Broader contract-level screener for finding unusual activity across the market.

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | integer | Max results |
| `min_premium` | number | Minimum premium |
| `type` | string | `Calls` or `Puts` |
| `is_otm` | boolean | OTM only |
| `issue_types[]` | string[] | Filter by issue type (e.g., ETF, stock) |
| `min_volume_oi_ratio` | number | Minimum volume-to-OI ratio |
| `max_multileg_volume_ratio` | number | Cap on multileg (spread) volume as fraction of total |
| `min_ask_perc` | number | Minimum percentage of fills at ask |
| `vol_greater_oi` | boolean | Only contracts where today's volume exceeds OI |

---

## Key Concepts

**Sweeps vs Floor Trades**

Sweeps are urgent, multi-venue executions. When a buyer needs size immediately, they sweep through multiple exchanges simultaneously, leaving a trail of small fills at or above ask across venues. This signals urgency and directional conviction.

Floor trades are large single blocks negotiated on the exchange floor. They're slower, often pre-arranged, and represent institutional positioning rather than reactive urgency. Both matter, but sweeps are more predictive of short-term moves.

**Opening vs Closing**

An opening trade creates new positions (size > existing OI or OI increases after the trade). A closing trade reduces existing positions. Opening trades carry far more directional signal. The UW scoring system weights opening bias at 1.2, the highest of all six components.

**Ask-Side vs Bid-Side**

Ask-side fills (at or above ask) indicate aggressive buyers willing to pay up. Bid-side fills indicate aggressive sellers. For NQ bullish bias, look for ask-side call sweeps on QQQ. For bearish bias, look for ask-side put sweeps.

---

## Python Example: QQQ Flow Alerts

```python
import httpx
import os
from typing import Optional

UW_TOKEN = os.environ["UW_API_TOKEN"]
BASE_URL = "https://api.unusualwhales.com"

HEADERS = {
    "Authorization": f"Bearer {UW_TOKEN}",
    "Accept": "application/json",
}


async def fetch_qqq_flow(
    min_premium: int = 500_000,
    calls_only: bool = False,
    puts_only: bool = False,
    max_dte: Optional[int] = 5,
) -> list[dict]:
    """Fetch high-conviction QQQ flow alerts for NQ directional bias."""
    params = {
        "ticker_symbol": "QQQ",
        "min_premium": min_premium,
        "is_ask_side": True,       # aggressive fills only
        "all_opening": True,       # opening trades only
        "limit": 200,
    }
    if calls_only:
        params["is_call"] = True
    if puts_only:
        params["is_put"] = True
    if max_dte is not None:
        params["max_dte"] = max_dte

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BASE_URL}/api/option-trades/flow-alerts",
            headers=HEADERS,
            params=params,
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()

    alerts = data.get("data", [])
    # Sort by UW score descending
    return sorted(alerts, key=lambda x: x.get("score", 0), reverse=True)


def classify_bias(alerts: list[dict]) -> str:
    """
    Derive directional bias from QQQ flow.
    Returns 'BULLISH', 'BEARISH', or 'NEUTRAL'.
    """
    call_premium = sum(
        float(a.get("premium", 0))
        for a in alerts
        if a.get("type", "").upper() == "CALL"
    )
    put_premium = sum(
        float(a.get("premium", 0))
        for a in alerts
        if a.get("type", "").upper() == "PUT"
    )

    total = call_premium + put_premium
    if total == 0:
        return "NEUTRAL"

    call_ratio = call_premium / total
    if call_ratio > 0.65:
        return "BULLISH"
    elif call_ratio < 0.35:
        return "BEARISH"
    return "NEUTRAL"
```

---

## NQ Trading Application

QQQ and NDX options are the primary proxy for NQ gamma exposure and directional flow. The relationship is tight: QQQ tracks NDX at 1/40th the price, and NQ futures track NDX tick-for-tick.

**Workflow for NQ bias from UW flow:**

1. Fetch QQQ flow alerts every 5 minutes during RTH (9:30-16:00 ET)
2. Filter: `min_premium=$500K`, `all_opening=True`, `is_ask_side=True`, `max_dte=5`
3. Compute call/put premium ratio from high-score alerts (score > 65)
4. Combine with GEX regime from `/api/stock/QQQ/spot-exposures/strike` (see `gex-greeks.md`)
5. Use as one input into DEEP6's composite signal engine

**High-conviction signal pattern:**
- 3+ `RepeatedHitsAscendingFill` alerts on QQQ calls within 15 minutes
- All ask-side, all opening, score > 75
- Combined premium > $2M
- DTE < 3

This pattern precedes NQ moves of 20-50 points within 30-60 minutes with meaningful frequency. Always confirm with GEX regime and order flow absorption before acting.

---

## Rate Limits

UW API enforces per-minute rate limits. For real-time monitoring, poll `/flow-recent` at 30-60 second intervals rather than hammering `/flow-alerts`. Cache responses and diff against last fetch to detect new alerts.
