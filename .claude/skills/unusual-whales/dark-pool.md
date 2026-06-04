# Unusual Whales Dark Pool — NQ Trading via Institutional Levels

## What Dark Pool Data Provides

Dark pools are off-exchange trading venues where institutional orders execute away from lit markets. Unusual Whales aggregates these prints from FINRA TRF (Trade Reporting Facilities) and provides them in near-real-time with full trade metadata.

Dark pool data tells you *where* institutions transacted, not *why*. A print at 19,850 NQ-equivalent doesn't mean a hedge fund is bullish — it means significant size changed hands at that price. The level becomes meaningful when multiple prints cluster there over days or weeks, suggesting that price is institutionally significant.

Used alone, dark pool levels have a 30-45% false positive rate. Combined with GEX walls, options flow, and order flow confirmation, accuracy rises to 55-70%.

---

## Data Fields Per Trade

Each dark pool print from the Unusual Whales API contains:

| Field | Description |
|-------|-------------|
| `executed_at` | Timestamp of execution |
| `price` | Execution price |
| `size` | Number of shares |
| `premium` | Dollar value of the print (price × size) |
| `nbbo_bid` | National Best Bid at time of execution |
| `nbbo_ask` | National Best Ask at time of execution |
| `nbbo_bid_quantity` | Bid size at NBBO |
| `nbbo_ask_quantity` | Ask size at NBBO |
| `market_center` | Venue where the trade was reported |
| `trade_code` | Trade condition code |
| `sale_cond_codes` | Sale condition flags |
| `trf_executed_at` | TRF reporting timestamp |
| `tracking_id` | Unique print identifier |
| `canceled` | Whether the trade was later canceled |
| `volume` | Cumulative volume context |
| `ticker` | Symbol |
| `ext_hour_sold_codes` | Extended hours flags |
| `trade_settlement` | Settlement type |

---

## API Endpoints

### Market-Wide Recent Prints
```
GET /api/darkpool/recent
```
Params: `limit` (max 200), `date`, `min_premium`, `max_premium`, `min_size`, `max_size`

### Ticker-Specific Prints
```
GET /api/darkpool/{ticker}
```
Params: `date`, `newer_than`, `older_than`, `min_premium`, `max_premium`, `min_size`, `max_size`, `limit` (max 500)

### Off/Lit Price Levels
```
GET /api/stock/{ticker}/stock-volume-price-levels
```
Returns aggregated volume by price level: `{price, lit_vol, off_vol}`

This endpoint is the most useful for S/R identification — it shows you the full distribution of where off-exchange volume has concentrated, not just individual prints.

### Real-Time WebSocket
```
channel: off-lit-trades
```
Streams dark pool prints as they're reported. Latency is 15-60 seconds behind actual execution due to TRF reporting requirements.

---

## NQ Proxy Strategy

NQ futures don't trade on dark pools directly. The proxy approach uses QQQ and top NQ components.

### QQQ as Primary Proxy

QQQ tracks the Nasdaq-100 with ~99.8% correlation to NQ. Dark pool prints in QQQ represent institutional positioning in the same underlying index. A cluster of QQQ dark pool prints at $485 translates directly to an NQ level via the multiplier:

```
NQ_equivalent = QQQ_price × (NQ_price / QQQ_price)
```

In practice, just track QQQ levels and overlay them on the NQ chart scaled by the current ratio.

### Top-5 Component Aggregation

The five largest NQ components represent approximately 45% of index weight:

| Ticker | Approx NQ Weight | Why It Matters |
|--------|-----------------|----------------|
| AAPL | ~9% | Largest single component; dark pool prints move NQ |
| MSFT | ~8% | Second largest; institutional accumulation visible |
| NVDA | ~8% | High volatility; dark pool prints often precede moves |
| GOOGL | ~5% | Dual-class structure means large blocks go dark |
| AMZN | ~5% | Frequent dark pool activity around earnings cycles |

When 3+ of these show dark pool accumulation at similar price levels (converted to NQ-equivalent), the confluence signal is strong.

```python
# Component weight mapping for NQ proxy
NQ_COMPONENTS = {
    "QQQ":  {"weight": 1.0,  "type": "etf"},      # primary proxy
    "AAPL": {"weight": 0.09, "type": "component"},
    "MSFT": {"weight": 0.08, "type": "component"},
    "NVDA": {"weight": 0.08, "type": "component"},
    "GOOGL": {"weight": 0.05, "type": "component"},
    "AMZN": {"weight": 0.05, "type": "component"},
}
```

---

## Clustering Methodology

Individual prints are noise. Clusters are signal.

### Why Prints Cluster

**Order splitting**: A $500M institutional order can't execute in one block without moving price. Algorithms split it into hundreds of smaller dark pool prints over hours or days, all near the same target price.

**VWAP execution**: Institutions executing against VWAP naturally concentrate prints around the day's VWAP, which tends to be near significant price levels.

**Psychological levels**: Round numbers (QQQ $480, $490, $500) attract institutional limit orders. Dark pool prints cluster at these levels because that's where the orders sit.

**Gamma walls**: When a large gamma wall exists at a strike, market makers hedge near that level. Their hedging activity shows up as dark pool prints because they route through dark venues to minimize market impact.

### Clustering Algorithm

```python
import numpy as np
from collections import defaultdict

def cluster_dark_pool_prints(prints: list[dict], 
                              cluster_pct: float = 0.005) -> list[dict]:
    """
    Cluster dark pool prints by price proximity.
    cluster_pct: price range to consider same level (0.5% default)
    """
    if not prints:
        return []
    
    # Sort by price
    sorted_prints = sorted(prints, key=lambda x: x["price"])
    
    clusters = []
    current_cluster = [sorted_prints[0]]
    
    for print_data in sorted_prints[1:]:
        ref_price = current_cluster[0]["price"]
        if abs(print_data["price"] - ref_price) / ref_price <= cluster_pct:
            current_cluster.append(print_data)
        else:
            clusters.append(current_cluster)
            current_cluster = [print_data]
    
    if current_cluster:
        clusters.append(current_cluster)
    
    # Summarize each cluster
    result = []
    for cluster in clusters:
        prices = [p["price"] for p in cluster]
        premiums = [p["premium"] for p in cluster]
        result.append({
            "level": np.average(prices, weights=premiums),  # premium-weighted center
            "total_premium": sum(premiums),
            "print_count": len(cluster),
            "price_range": (min(prices), max(prices)),
            "prints": cluster,
        })
    
    return sorted(result, key=lambda x: x["total_premium"], reverse=True)
```

---

## Support/Resistance from Dark Pool: 5-Step Framework

### Step 1: Filter for Significant Size

Apply size filters before any analysis. Small prints are noise from retail dark pool routing.

| ADV Threshold | Signal Strength | Action |
|--------------|----------------|--------|
| < 0.5% ADV | Noise | Discard |
| 0.5-1% ADV | Moderate | Include with low weight |
| 1-2% ADV | Strong | Include with standard weight |
| > 2% ADV | Very strong | High-priority level |

For QQQ, ADV is roughly 80-100M shares/day. A "strong" print is 800K-2M shares.

### Step 2: Identify Institutional Levels

After filtering, cluster remaining prints using the algorithm above. Levels with 3+ prints and $50M+ total premium are institutional levels worth tracking.

### Step 3: Define S/R Zones

Each cluster becomes a zone, not a line. Use the `price_range` from the cluster as the zone boundaries. Price tends to react at the zone edges, not a single tick.

### Step 4: Confirm with Convergence

A dark pool level alone is weak. Confirm with:
- GEX wall within 0.5% of the level
- Options flow (calls or puts) at the same strike
- Volume Profile HVN or POC at the same price
- Prior swing high/low at the same level

Each additional confluence adds conviction. Two confirmations = tradeable. Three = high conviction.

### Step 5: Execute on Momentum Shift

Don't fade into a dark pool level blindly. Wait for:
- Price approaches the level
- Order flow shows absorption or exhaustion at the level
- Momentum indicator (delta, CVD) shows reversal

The dark pool level tells you *where* to watch. Order flow tells you *when* to act.

---

## Time-of-Day Effects

Dark pool activity isn't uniform. Timing matters for signal quality.

| Session | Time (ET) | Dark Pool Activity | Signal Weight |
|---------|-----------|-------------------|---------------|
| Opening accumulation | 9:30-11:00 AM | Heaviest (~40% of daily volume) | High — institutions establishing positions |
| Midday distribution | 11:30 AM-1:00 PM | Moderate, often distribution | Medium — watch for selling into strength |
| Afternoon accumulation | 2:30-3:30 PM | Secondary accumulation phase | High — pre-close positioning |
| Final 30 minutes | 3:30-4:00 PM | Highest signal weight per print | Very high — end-of-day institutional intent |

Prints in the final 30 minutes carry the most information because institutions are making final positioning decisions for the day. A large dark pool print at 3:45 PM is more meaningful than the same print at 10:15 AM.

---

## Relevance Decay

Dark pool levels don't last forever.

**Active window**: 30-45 days. A level established 6 weeks ago is stale unless price has recently retested it.

**Level death**: If price slices through a dark pool level with no pause, no absorption, and no reversal attempt, the level is dead. Remove it from your map. The institutions who established it have either exited or been stopped out.

**Level strengthening**: Each successful retest of a dark pool level increases its significance. A level that has held twice is stronger than one that's never been tested.

**Recency weighting**: When multiple levels exist, weight recent prints (last 10 days) 3x more than older prints (11-45 days).

---

## Confluence with GEX

Dark pool prints within 0.5% of a gamma wall create the strongest S/R levels in the system.

**Why this works**: Gamma walls exist because market makers have large options exposure at that strike. They hedge by buying/selling the underlying near that level. Their hedging shows up as dark pool prints. So a gamma wall with dark pool clustering means *two independent institutional forces* are active at the same price.

**Confidence boost**: +0.15 to the DEEP6 signal score when dark pool level and gamma wall are within 0.5%.

```python
def check_gex_confluence(dp_level: float, gex_walls: list[float], 
                          threshold_pct: float = 0.005) -> bool:
    """Check if dark pool level is within threshold of any GEX wall."""
    for wall in gex_walls:
        if abs(dp_level - wall) / wall <= threshold_pct:
            return True
    return False
```

---

## Confluence with Options Flow

Dark pool accumulation combined with directional options flow in the same 30-minute window is the highest-conviction setup in the system.

**Bullish confluence**: Dark pool prints (accumulation) + call sweeps in same 30-min window = +0.20 confidence boost

**Bearish confluence**: Dark pool prints (distribution) + put sweeps in same 30-min window = +0.20 confidence boost

**Why 30 minutes**: Institutions often execute dark pool equity positions and options hedges within the same execution window. The 30-minute window captures this coordinated activity.

Distinguishing accumulation from distribution in dark pool prints is imprecise — you're looking at print clustering near support (accumulation) vs. resistance (distribution) relative to recent price action.

---

## Python Code Examples

### Fetch Dark Pool Prints for QQQ

```python
import httpx
from datetime import date

async def fetch_dark_pool(ticker: str, 
                           min_premium: float = 1_000_000,
                           limit: int = 500) -> list[dict]:
    """
    Fetch dark pool prints for a ticker.
    min_premium: minimum dollar value to filter noise (default $1M)
    """
    url = f"https://api.unusualwhales.com/api/darkpool/{ticker}"
    params = {
        "date": date.today().isoformat(),
        "min_premium": min_premium,
        "limit": limit,
    }
    headers = {"Authorization": f"Bearer {API_KEY}"}
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json().get("data", [])
```

### Cluster Prints by Price Level

```python
async def get_dark_pool_levels(ticker: str, 
                                min_premium: float = 5_000_000,
                                cluster_pct: float = 0.005) -> list[dict]:
    """
    Fetch and cluster dark pool prints into S/R levels.
    Returns levels sorted by total premium (strongest first).
    """
    prints = await fetch_dark_pool(ticker, min_premium=min_premium)
    
    if not prints:
        return []
    
    # Filter canceled trades
    active_prints = [p for p in prints if not p.get("canceled", False)]
    
    return cluster_dark_pool_prints(active_prints, cluster_pct=cluster_pct)
```

### Component Aggregation for NQ Proxy

```python
async def get_nq_proxy_levels(nq_price: float) -> list[dict]:
    """
    Aggregate dark pool levels from QQQ + top NQ components.
    Converts component levels to NQ-equivalent prices.
    """
    import asyncio
    
    tickers = ["QQQ", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"]
    
    # Fetch all in parallel
    tasks = [get_dark_pool_levels(t, min_premium=10_000_000) for t in tickers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Get current prices for conversion
    # (assumes you have a price feed)
    prices = await get_current_prices(tickers)
    
    all_levels = []
    for ticker, levels in zip(tickers, results):
        if isinstance(levels, Exception):
            continue
        
        ticker_price = prices.get(ticker, 0)
        if ticker_price == 0:
            continue
        
        # Convert to NQ-equivalent
        ratio = nq_price / ticker_price
        weight = NQ_COMPONENTS[ticker]["weight"]
        
        for level in levels:
            nq_equiv = level["level"] * ratio
            all_levels.append({
                "nq_level": nq_equiv,
                "source_ticker": ticker,
                "source_price": level["level"],
                "total_premium": level["total_premium"] * weight,
                "print_count": level["print_count"],
                "weight": weight,
            })
    
    # Re-cluster the NQ-equivalent levels
    # (multiple components may point to same NQ level)
    return cluster_nq_levels(all_levels, cluster_pct=0.003)
```

### Off/Lit Price Levels

```python
async def get_price_level_distribution(ticker: str) -> list[dict]:
    """
    Get aggregated off-exchange vs lit volume by price level.
    Useful for identifying where institutions have been most active.
    """
    url = f"https://api.unusualwhales.com/api/stock/{ticker}/stock-volume-price-levels"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    
    # Calculate off-exchange ratio per level
    for level in data:
        total = level["lit_vol"] + level["off_vol"]
        level["off_ratio"] = level["off_vol"] / total if total > 0 else 0
    
    # Levels with high off-exchange ratio = institutional interest
    return sorted(data, key=lambda x: x["off_vol"], reverse=True)
```

---

## DEEP6 Integration

Dark pool levels feed into the DEEP6 signal engine as contextual S/R zones, not standalone signals.

**Signal weight**: Dark pool level proximity contributes up to +0.10 to the base confidence score. With GEX confluence, +0.15. With options flow confluence, +0.20.

**Update frequency**: Refresh dark pool levels every 15 minutes during market hours. The 15-60 second TRF reporting lag means real-time polling adds no value.

**Level storage**: Maintain a rolling 45-day window of significant levels. Prune levels that price has sliced through without reaction.

**Integration point**: The `DarkPoolLevelProvider` class should expose:
- `get_nearest_level(price, direction)` — closest level above/below current price
- `get_level_strength(price)` — confidence score contribution for proximity to a level
- `is_at_level(price, tolerance_pct=0.003)` — boolean check for level proximity

---

## Limitations

**Hedging masquerades as directional**: A large dark pool print might be a hedge against an existing position, not a new directional bet. You can't distinguish these from the print alone.

**Rebalancing noise**: Index funds rebalance quarterly. Their dark pool activity around rebalancing dates creates false levels that disappear after the rebalance completes.

**Stale reference prices**: Approximately 3.5% of dark pool prints use stale reference prices (not current NBBO). These prints appear at prices that don't reflect current market conditions.

**Information lag**: TRF reporting introduces 15-60 seconds of latency. By the time you see a print, the execution is already done. You're reading history, not the present.

**False positive rate**: 30-45% of dark pool levels identified by clustering alone don't produce meaningful price reactions. Multi-signal confirmation is required to bring this down to a tradeable range.

**No directional information**: Dark pool data shows *that* a transaction occurred, not whether the buyer or seller was the informed party. A large print at support could be accumulation or distribution.

---

## Academic Context

**Zhu (2014)** — "Do Dark Pools Harm Price Discovery?" (*Review of Financial Studies*): Dark pools improve price discovery when informed traders use them, because their activity eventually gets incorporated into lit market prices. This supports using dark pool levels as leading indicators of where price will find support or resistance.

**Comerton-Forde & Putniņš (2015)** — "Dark Trading and Price Discovery" (*Journal of Financial Economics*): Dark pool trading improves price efficiency up to a threshold (~10% of volume). Above that threshold, price discovery degrades. Current US dark pool volume is near this threshold, which means the signal quality from dark pool data is at its historical peak.

Both papers support the core thesis: dark pool prints reveal institutional price targets, and those targets become S/R levels in the lit market.
