# Unusual Whales GEX & Greeks — Gamma Exposure for NQ Trading

## Overview

Unusual Whales provides two distinct GEX data types: **static** (OI-based snapshots) and **spot** (real-time, trade-by-trade updates). For intraday NQ trading, spot GEX is the primary signal. Static GEX sets the structural context at session open.

QQQ and NDX are the NQ proxies. QQQ = NDX / 40 (approximately). All GEX endpoints below work with `QQQ` as the ticker for NQ gamma analysis.

Base URL: `https://api.unusualwhales.com`
Auth: `Authorization: Bearer {UW_API_TOKEN}` on every request.

---

## GEX & Greeks Endpoints

### Overall Greek Exposure

```
GET /api/stock/{ticker}/greek-exposure
```

Returns aggregate delta, gamma, vega, theta, and charm across all strikes and expiries. Use for a top-level read on net dealer positioning.

---

### Greek Exposure by Expiry

```
GET /api/stock/{ticker}/greek-exposure/expiry
```

Breaks down aggregate Greeks by expiration date. Reveals which expiry is driving the most gamma. Heavy 0DTE gamma on QQQ means dealers are pinned and will hedge aggressively intraday.

---

### Static GEX by Strike

```
GET /api/stock/{ticker}/greek-exposure/strike
```

OI-based gamma exposure per strike. This is the traditional GEX calculation: dealer gamma from existing open interest. Updates once per day (after settlement). Use for structural levels that persist across sessions.

---

### Static GEX by Strike and Expiry

```
GET /api/stock/{ticker}/greek-exposure/strike-expiry
```

Same as above but cross-referenced by both strike and expiry. Useful for isolating which expiry is responsible for a gamma wall at a given strike.

---

### Spot GEX by Strike (Real-Time)

```
GET /api/stock/{ticker}/spot-exposures/strike
```

Real-time gamma exposure per strike, updated from live trade flow. This is the most actionable GEX endpoint for intraday trading.

**Response fields per strike:**

| Field | Description |
|-------|-------------|
| `strike` | Strike price |
| `call_gamma_oi` | Call gamma from open interest (static component) |
| `call_gamma_bid` | Call gamma from bid-side fills (closing/selling pressure) |
| `call_gamma_ask` | Call gamma from ask-side fills (opening/buying pressure) |
| `put_gamma_oi` | Put gamma from open interest |
| `put_gamma_bid` | Put gamma from bid-side fills |
| `put_gamma_ask` | Put gamma from ask-side fills |

Net dealer gamma at a strike = `(call_gamma_oi + call_gamma_ask - call_gamma_bid) - (put_gamma_oi + put_gamma_ask - put_gamma_bid)`. Positive = dealers are long gamma (stabilizing). Negative = dealers are short gamma (amplifying).

---

### Spot GEX by Strike and Expiry

```
GET /api/stock/{ticker}/spot-exposures/strike-expiry
```

Real-time GEX cross-referenced by strike and expiry. Use when you need to know whether a gamma wall is driven by 0DTE or weekly options.

---

### Per-Minute Spot GEX

```
GET /api/stock/{ticker}/spot-exposures/one-minute
```

Returns GEX snapshots at one-minute resolution. The most granular GEX feed UW provides. Poll this during RTH for real-time gamma regime tracking. Combine with NQ price to detect when price approaches or crosses a gamma wall.

---

### Greek Flow (Directional Delta/Vega from Trades)

```
GET /api/stock/{ticker}/greek-flow
```

Aggregates the Greeks from actual trade flow, not just OI. Shows the net directional delta and vega being bought or sold.

**Response fields:**

| Field | Description |
|-------|-------------|
| `call_delta` | Aggregate delta from call trades |
| `put_delta` | Aggregate delta from put trades |
| `dir_delta_flow` | Net directional delta flow (calls minus puts, signed) |
| `dir_vega_flow` | Net directional vega flow |
| `call_fill_delta` | Delta from call fills specifically |
| `charm` | CEX (charm exposure) per 1% move in underlying |

`dir_delta_flow` is the cleanest single number for directional bias from options flow. Positive = net call delta being bought. Negative = net put delta being bought.

---

### Greek Flow by Expiry

```
GET /api/stock/{ticker}/greek-flow-expiry
```

Same Greek flow data broken down by expiration. Useful for separating 0DTE gamma scalping activity from longer-dated directional positioning.

---

### Group-Level Greek Flow

```
GET /api/group-flow/greek-flow
```

Greek flow aggregated across a group of tickers (e.g., all tech, all ETFs). Use for sector-level bias when individual QQQ flow is ambiguous.

---

## Volatility Endpoints

### IV Rank

```
GET /api/stock/{ticker}/iv-rank
```

Current implied volatility rank (0-100) relative to the past year. IV rank above 50 means options are expensive relative to history. Relevant for sizing and for interpreting whether flow is hedging or speculating.

---

### Interpolated IV

```
GET /api/stock/{ticker}/interpolated-iv
```

Smooth IV curve interpolated across strikes and expiries. More useful than raw chain IV for vol surface analysis.

---

### Realized Volatility

```
GET /api/stock/{ticker}/realized-volatility
```

Historical realized volatility at multiple lookback windows. Compare against IV to assess vol premium or discount.

---

### Volatility Stats

```
GET /api/stock/{ticker}/volatility-stats
```

Summary statistics: current IV, IV rank, IV percentile, HV, and the IV/HV ratio.

---

### Implied Volatility Term Structure

```
GET /api/stock/{ticker}/implied-volatility-term-structure
```

IV across expiration dates. A normal (contango) term structure shows rising IV with time. An inverted structure (near-term IV > far-term) signals near-term event risk or panic.

---

### Historical Risk Reversal Skew

```
GET /api/stock/{ticker}/historical-risk-reversal-skew
```

25-delta risk reversal over time. Negative skew (puts more expensive than calls) is the normal state for equity indices. A sharp move toward zero or positive skew signals unusual call demand, often preceding rallies.

---

## Options Chain & OI Endpoints

### Full Options Chain

```
GET /api/stock/{ticker}/option-chains
```

Complete options chain with strikes, expiries, bid/ask, IV, Greeks, OI, and volume.

---

### ATM Chains

```
GET /api/stock/{ticker}/atm-chains
```

At-the-money contracts only. Faster to fetch and sufficient for most intraday gamma calculations.

---

### Max Pain

```
GET /api/stock/{ticker}/max-pain
```

The strike price where total option value (calls + puts) is minimized at expiry. Dealers and market makers benefit when price pins to max pain. Useful as a gravitational level near expiry.

---

### OI Per Strike

```
GET /api/stock/{ticker}/oi-per-strike
```

Open interest distribution across strikes. Shows where the most contracts are outstanding. Large OI concentrations create gamma walls.

---

### OI Per Expiry

```
GET /api/stock/{ticker}/oi-per-expiry
```

Open interest by expiration date. Reveals which expiry is the most crowded.

---

### OI Change

```
GET /api/stock/{ticker}/oi-change
```

Change in open interest from the prior session. Rising OI at a strike = new positions being opened. Falling OI = positions being closed or expiring.

---

### NOPE (Net Options Positioning Effect)

```
GET /api/stock/{ticker}/nope
```

NOPE measures the net delta exposure from options relative to underlying volume. Originally developed by Lily Francus. High positive NOPE = options market is net long delta, which can amplify upside moves. High negative NOPE = net short delta, amplifies downside.

---

## Static vs Spot GEX

| | Static GEX | Spot GEX |
|--|-----------|----------|
| Source | Open interest (OI) | Live trade flow |
| Update frequency | Once daily (post-settlement) | Real-time, per trade |
| Use case | Structural levels, session planning | Intraday gamma walls, regime shifts |
| Endpoints | `/greek-exposure/strike`, `/greek-exposure/strike-expiry` | `/spot-exposures/strike`, `/spot-exposures/strike-expiry`, `/spot-exposures/one-minute` |
| Responsiveness | Lags intraday activity | Reflects current positioning |

For DEEP6 intraday NQ trading, use spot GEX as the primary signal and static GEX as the structural backdrop. When spot GEX diverges significantly from static GEX at a key strike, it means intraday flow is reshaping the gamma landscape.

---

## Comparison with FlashAlpha

| Feature | Unusual Whales | FlashAlpha |
|---------|---------------|------------|
| GEX by strike | Yes (static + spot) | Yes |
| Per-minute GEX updates | Yes (`/spot-exposures/one-minute`) | No |
| Greek flow (delta/vega from trades) | Yes | No |
| Flow alerts with scoring | Yes | No |
| NQ proxy | QQQ, NDX | QQQ, NDX |
| Cost | Subscription | $49/mo |
| Cross-validation value | High | High |

Use both sources. When UW spot GEX and FlashAlpha GEX agree on a gamma wall location, the level has higher confidence. When they diverge, investigate why before acting.

---

## Python Example: QQQ Gamma Walls

```python
import httpx
import os
import numpy as np
from typing import Optional

UW_TOKEN = os.environ["UW_API_TOKEN"]
BASE_URL = "https://api.unusualwhales.com"

HEADERS = {
    "Authorization": f"Bearer {UW_TOKEN}",
    "Accept": "application/json",
}


async def fetch_spot_gex(ticker: str = "QQQ") -> list[dict]:
    """Fetch real-time spot GEX by strike."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BASE_URL}/api/stock/{ticker}/spot-exposures/strike",
            headers=HEADERS,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])


def compute_net_gamma(row: dict) -> float:
    """
    Net dealer gamma at a strike.
    Positive = dealers long gamma (stabilizing).
    Negative = dealers short gamma (amplifying).
    """
    call_net = (
        float(row.get("call_gamma_oi", 0))
        + float(row.get("call_gamma_ask", 0))
        - float(row.get("call_gamma_bid", 0))
    )
    put_net = (
        float(row.get("put_gamma_oi", 0))
        + float(row.get("put_gamma_ask", 0))
        - float(row.get("put_gamma_bid", 0))
    )
    return call_net - put_net


def find_gamma_walls(
    gex_data: list[dict],
    current_price: float,
    top_n: int = 5,
) -> dict:
    """
    Identify gamma walls above and below current price.
    Returns top call walls (resistance) and put walls (support).
    """
    strikes = []
    for row in gex_data:
        strike = float(row.get("strike", 0))
        net_gamma = compute_net_gamma(row)
        strikes.append({"strike": strike, "net_gamma": net_gamma})

    above = [s for s in strikes if s["strike"] > current_price]
    below = [s for s in strikes if s["strike"] < current_price]

    # Call walls = large positive gamma above price (resistance)
    call_walls = sorted(above, key=lambda x: x["net_gamma"], reverse=True)[:top_n]

    # Put walls = large negative gamma below price (support from dealer hedging)
    put_walls = sorted(below, key=lambda x: x["net_gamma"])[:top_n]

    # Gamma flip = strike where net gamma crosses zero
    all_sorted = sorted(strikes, key=lambda x: x["strike"])
    flip_strike = None
    for i in range(len(all_sorted) - 1):
        if all_sorted[i]["net_gamma"] <= 0 < all_sorted[i + 1]["net_gamma"]:
            flip_strike = (all_sorted[i]["strike"] + all_sorted[i + 1]["strike"]) / 2
            break

    return {
        "call_walls": call_walls,
        "put_walls": put_walls,
        "gamma_flip": flip_strike,
        "regime": "positive" if flip_strike and current_price > flip_strike else "negative",
    }


async def get_greek_flow_bias(ticker: str = "QQQ") -> dict:
    """Fetch directional delta/vega flow for bias signal."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BASE_URL}/api/stock/{ticker}/greek-flow",
            headers=HEADERS,
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})

    dir_delta = float(data.get("dir_delta_flow", 0))
    dir_vega = float(data.get("dir_vega_flow", 0))

    return {
        "dir_delta_flow": dir_delta,
        "dir_vega_flow": dir_vega,
        "bias": "BULLISH" if dir_delta > 0 else "BEARISH" if dir_delta < 0 else "NEUTRAL",
    }
```

---

## WebSocket Channel

UW provides a real-time WebSocket feed for GEX updates:

**Channel:** `gex`

Connect to the UW WebSocket endpoint and subscribe to the `gex` channel for streaming gamma exposure updates. This avoids polling `/spot-exposures/one-minute` and reduces latency for intraday gamma wall tracking.

Refer to UW WebSocket documentation for authentication and subscription message format.

---

## NQ Trading Application

**Session planning (pre-market):**
1. Fetch static GEX via `/greek-exposure/strike` for QQQ
2. Identify the top 3 call walls (resistance) and put walls (support)
3. Convert QQQ strikes to NQ price: `NQ_level ≈ QQQ_strike * 40`
4. Note the gamma flip level and whether overnight price is above or below it

**Intraday (RTH):**
1. Poll `/spot-exposures/one-minute` every minute
2. Track when spot GEX walls shift (new walls forming, old walls dissolving)
3. Monitor `dir_delta_flow` from `/greek-flow` for directional bias confirmation
4. When NQ approaches a gamma wall identified from QQQ GEX, look for absorption or exhaustion signals in the order flow engine

**Regime classification:**
- Price above gamma flip + positive `dir_delta_flow` = positive gamma regime, mean-reverting, fade extremes
- Price below gamma flip + negative `dir_delta_flow` = negative gamma regime, trending, follow breakouts
- Gamma flip crossing intraday = regime change, high-volatility transition, reduce size until confirmed
