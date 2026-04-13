# Python L2 DOM Options for NQ/ES Futures

**Question:** Can Python get Level 2 DOM (order book) data for NQ futures without NinjaTrader?
**Researched:** 2026-04-11
**Overall confidence:** HIGH (primary sources verified; pricing specifics LOW on some providers)

---

## Baseline: What You Have With Rithmic + NinjaTrader

- **40+ DOM levels** per side (bid and ask)
- **1,000 callbacks/second** peak on NQ's `OnMarketDepth`
- Native C++ feed, zero-copy protobuf delivery through NinjaTrader's managed layer
- Execution and data over the same connection
- Cost is bundled into your broker relationship (typically $0/month extra for data, $0.10/contract commissions)

This is the benchmark every alternative must be measured against.

---

## Option 1: Rithmic Direct Python (RECOMMENDED — Best Like-for-Like)

**Verdict: YES. Direct Python access to Rithmic is fully possible without NinjaTrader.**

### How it works

Rithmic's R|Protocol API is a WebSocket + Google Protocol Buffers wire spec. It is language-agnostic by design. You do NOT need NinjaTrader. You do NOT need the R|Trader desktop app. You connect websockets directly to Rithmic's infrastructure from Python.

Two community Python libraries implement this:

**`async-rithmic`** (recommended — actively maintained, Python 3.11+)
- PyPI: `pip install async-rithmic`
- GitHub: https://github.com/rundef/async_rithmic
- Docs: https://async-rithmic.readthedocs.io/
- Architecture: Asyncio-native, event-driven callbacks
- Supports: L2 full order book streaming, tick data, historical data, order execution, multi-account

**`pyrithmic`** (older, less maintained)
- PyPI: `pip install pyrithmic`
- GitHub: https://github.com/jacksonwoody/pyrithmic
- Supports: TICKER_PLANT, HISTORY_PLANT, ORDER_PLANT

### DOM Depth

async_rithmic supports "Full Order Book (L2) Streaming" — described as streaming real-time depth of market across all bids/asks at multiple price levels. The exact level count delivered is whatever Rithmic pushes (which for NQ via the standard feed is 40+ levels per side, same as what NinjaTrader receives — the data comes from the same infrastructure). Rithmic does not truncate the feed at the API level.

Update type handling: updates arrive as BEGIN/MIDDLE/END sets or SOLO updates. The asyncio event loop processes them as they arrive.

### Code pattern

```python
from async_rithmic import RithmicClient, DataType

client = RithmicClient(uri=..., user=..., password=..., system_name=...)
await client.connect()

async def on_order_book(update):
    # update contains price level, side, size
    ...

client.on_order_book += on_order_book
await client.subscribe_to_market_data("NQM5", "CME", DataType.ORDER_BOOK)
```

### Access requirements

- You need a Rithmic-enabled broker account. You do NOT need NinjaTrader as a platform.
- Rithmic can be purchased data-only without a trading account (via direct Rithmic signup or brokers like EdgeClear at ~$20/month data fee).
- Must sign Rithmic's Market Data Subscription Agreement electronically via R|Trader or R|Trader Pro.
- Test environment access is free; production requires broker account approval.
- API access page: https://www.rithmic.com/api-request

### Execution support

YES — full order management via ORDER_PLANT. This replaces NinjaTrader for execution too.

### macOS support

YES — pure Python + WebSocket + protobuf. No native DLLs. Runs anywhere Python runs.

### Cost

Same as your current setup. If you already have a Rithmic broker account, you likely pay $0 extra for the data feed. Data-only adds ~$20/month depending on broker. No additional SDK fee.

### Latency

Same underlying feed as NinjaTrader. You lose NinjaTrader's C++ preprocessing layer — Python asyncio adds some overhead (~1-5ms depending on your event loop load). For analytics this is acceptable. For co-located HFT execution, it is not ideal.

### Confidence: HIGH

Sources confirmed by multiple GitHub repos, PyPI packages, official Rithmic site (https://www.rithmic.com/apis), and community forums.

---

## Option 2: Databento (BEST THIRD-PARTY ALTERNATIVE)

**Verdict: YES, but with trade-offs. MBO gives you full order book. MBP-10 gives only 10 levels. Not a drop-in replacement for 40-level DOM at Rithmic callback rates.**

### What they provide

Databento is a CME-licensed market data vendor that connects directly to CME's colocation at Globex MDP 3.0. They offer:

| Schema | Type | Depth |
|--------|------|-------|
| MBO | Market-by-Order (L3) | Full order book — every individual order event at every price |
| MBP-10 | Market-by-Price (L2) | Top 10 price levels only |
| MBP-1 | Top-of-book | 1 level |
| Trades | Tick trades | N/A |

**For 40+ level DOM: you must use MBO (L3), not MBP-10.**

MBO provides every order-level event (add, modify, cancel) giving you full reconstructibility of the book. From MBO events you can reconstruct any depth of price-aggregated view in Python.

### Latency

- 42 microseconds (cross-connect in CME colo)
- 590 microseconds (standard internet)
- 64 microseconds median to public cloud
- Nanosecond timestamps on all records

### Python SDK

Official first-party: `pip install databento`

```python
import databento as db

live = db.Live(key='YOUR_API_KEY')
live.subscribe(dataset='GLBX.MDP3', schema='mbo', stype_in='continuous',
               symbols=['NQ.c.0'])
for msg in live:
    # msg is a typed Python object with nanosecond ts
    process(msg)
```

Uses TCP socket (not WebSocket) — lower latency than WebSocket-based alternatives.

Same code works for historical replay — enables unified backtest/live codebase.

### Update frequency

MBO delivers every order event as it happens. For NQ during peak market hours this can exceed thousands of events/second at the raw level. The limiting factor becomes your Python processing speed.

### Pricing (as of April 2025)

- **Standard plan: $179/month** — includes live CME data (CME licensing bundled, no upcharge)
- **Plus plan**: higher tier (contact for pricing)
- **Unlimited plan**: ~$3,500/month
- Historical data: pay-as-you-go (separate from live)
- Note: Usage-based live pricing was discontinued April 16, 2025 — subscriptions only
- CME requires regulatory questionnaire to determine professional vs non-professional classification — this can increase fees

Official pricing blog: https://databento.com/blog/introducing-new-cme-pricing-plans

### Execution support

NO. Databento is data-only. You would need a separate order execution connection (Interactive Brokers, Rithmic, CQG, etc.).

### macOS support

YES. Pure Python SDK over TCP. No platform restrictions.

### NautilusTrader integration

NautilusTrader (Rust-native algo trading engine with Python API) has a built-in Databento adapter that supports MBO and MBP-10 live streaming with the same interfaces as historical replay. This is likely the best path for building a serious Python trading system on top of Databento data.
- https://nautilustrader.io/docs/latest/integrations/databento/

### Confidence: HIGH

Sources: Official Databento docs, pricing blog, dataset page (https://databento.com/datasets/GLBX.MDP3), CME Group vendor listing.

---

## Option 3: Interactive Brokers TWS API

**Verdict: PARTIAL. Real L2 available but severely depth-limited (10 levels per side). Not a replacement for Rithmic DOM.**

### What they provide

IBKR's `reqMktDepth` Python API call returns market depth (L2) for futures. However:

- **Maximum depth: ~10 rows per side** (10 bid + 10 ask = 20 total rows for CME futures). Confirmed in community discussions — NQ/ES via IBKR shows approximately 20 total rows vs Rithmic's 40+ per side.
- **Max simultaneous depth subscriptions: 3–60**, depending on the number of paid market data lines on your account.
- Smart Depth (`isSmartDepth=True`) aggregates from multiple venues — useful for equities but less meaningful for futures.
- Update throttling: IBKR applies sampling/throttling internally. You will NOT get 1,000 callbacks/second — IBKR throttles significantly below Rithmic's raw feed rates.

### Code pattern

```python
app.reqMktDepth(reqId=1, contract=nq_contract, numRows=20, isSmartDepth=True, mktDepthOptions=[])
# Returns: updateMktDepth(reqId, position, operation, side, price, size)
```

### Execution support

YES — IBKR provides full execution via the same TWS API. Best-in-class for execution through a single Python connection.

### Pricing

- IBKR Pro account: ~$0/month platform fee
- Market data subscriptions required for CME futures depth: ~$10–30/month for relevant packages
- Execution commissions: ~$0.85/contract for futures

### macOS support

YES. Pure Python, runs anywhere. Requires TWS or IB Gateway running locally.

### Verdict

Good enough for light DOM monitoring. Not viable for footprint charts or serious DOM analysis requiring 40+ levels and high-frequency updates. Use IBKR for execution, not as your primary DOM data source.

### Confidence: HIGH

Sources: Official TWS API docs (https://interactivebrokers.github.io/tws-api/market_depth.html), community forum confirmations of 10-level limit for futures.

---

## Option 4: CQG WebAPI

**Verdict: YES for DOM data, but institutional/broker-gated access. Not self-serve.**

### What they provide

CQG offers a WebSocket + Protocol Buffers API (similar architecture to Rithmic) with DOM/depth data for CME futures. They route through their own infrastructure with direct exchange connections.

- Official Python samples: https://github.com/cqg/WebAPIPythonSamples
- Protocol: WSS + Protobuf, language-agnostic
- DOM depth: CQG's depth parameter can be configured — default 10, but more levels available
- Direct exchange access via CQG's co-located gateways

### Access requirements

CQG API access requires working with a CQG-connected broker (AMP Futures, Wedbush, etc.). It is not self-serve — you must have a CQG-enabled brokerage account. CQG does not sell data-only subscriptions to retail users easily.

### Execution support

YES. Full order routing via the same API.

### macOS support

YES — Python WebSocket + Protobuf.

### Cost

Embedded in broker relationship. No standalone pricing published. AMP Futures offers CQG access with their account structure.

### Depth levels

Not definitively confirmed in public docs for the max levels, but CQG's platform supports deep DOM (order flow traders use CQG DOM extensively). Likely comparable to Rithmic levels when configured.

### Confidence: MEDIUM

Sources: CQG partner portal (https://partners.cqg.com/api-resources/web-api), GitHub samples (https://github.com/cqg/WebAPIPythonSamples). Depth level maximum requires direct CQG documentation access.

---

## Option 5: Sierra Chart via DTC Protocol

**Verdict: BLOCKED for CME futures. DTC server explicitly rejects CME data requests.**

### Critical limitation

Sierra Chart's DTC Protocol Server documentation explicitly states:

> "It is not possible to access real-time or historical data from the CME Group of exchanges, NASDAQ, CBOE, US equities data originating from UTP or CTA, from the DTC Protocol server."

This is an exchange licensing restriction — Sierra Chart cannot re-distribute CME data via DTC to external Python clients.

### What DTC CAN do

- Python WebSocket clients can connect to Sierra's DTC server (JSON over WebSocket supported)
- Market depth IS in the DTC protocol messages (MarketDepthUpdateLevel message type)
- Sierra Chart itself can receive 500–1400 levels from CME via their SC Exchange Data Feed or Denali feed
- But none of that can be piped out to a Python DTC client for CME instruments

### Workaround (complex)

You could run Sierra Chart with a DTC-compatible non-CME data source (e.g., CQG feeding Sierra) and then have Python connect via DTC. But this adds complexity for no gain over direct CQG API access.

### Confidence: HIGH

Source: Official DTC Server documentation (https://www.sierrachart.com/index.php?page=doc/DTCServer.php).

---

## Option 6: dxFeed Python API

**Verdict: YES for CME L2 depth data, affordable, but update rate and depth level specifics need verification.**

### What they provide

dxFeed is a licensed CME market data vendor offering Python API access:

- **Python API**: Available at https://dxfeed.com/api/python-api/ — provides real-time, delayed, and historical data
- **CME coverage**: CME, CBOT, NYMEX, COMEX futures including NQ/ES
- **Data types**: Market Depth (Level 2), Top of Book (L1)
- **Integration**: Powers Bookmap's CME data (dxFeed + Bookmap is an established combo)
- Note: dxFeed Retail (separate from institutional dxFeed) is the retail-facing product

### Pricing

- CME Market Depth: **~$29/month per exchange** (CME, CBOT, etc. are separate)
- CME bundle: **~$79/month** (covers CME, CBOT, NYMEX, COMEX)
- Some plans from $19/month for top-of-book only
- Source: https://dxfeed.com/dxfeed-makes-real-time-cme-market-depth-available-to-medved-trader-users-for-19/

### Depth levels

"Price level" and "Market Depth" subscription types are available. The exact number of levels via their Python API was not confirmed from public documentation (requires API docs access). Their subscription terminology distinguishes between "top of book," "price levels," and "market depth" — the latter likely gives the deepest view.

### Update frequency

Not confirmed at Rithmic-equivalent rates. dxFeed targets retail/semi-institutional users; 1,000 updates/second performance is not confirmed in public docs.

### Execution support

NO. dxFeed is data-only.

### macOS support

Likely YES — Python SDK. Needs verification against their specific library requirements.

### Confidence: MEDIUM

Sources: https://dxfeed.com/market-data/futures/cme/, https://dxfeed.com/api/python-api/, Bookmap partner page.

---

## Option 7: Trading Technologies (TT) API

**Verdict: YES for DOM data but NOT Python-native. Institutional-grade, expensive, complex.**

### What they provide

TT is an institutional trading platform with direct CME connectivity. Their API provides:

- Microsecond-level execution speeds
- Full DOM/depth data for NQ, ES, and all CME futures
- Direct market access to CME, CBOT, NYMEX, etc.

### Python support — significant limitation

TT's primary SDK is the .NET SDK. Python support is via **IronPython** (a .NET implementation of Python), NOT CPython. This means:

- Standard Python libraries (pandas, numpy, asyncio, etc.) do not work
- Cannot use pip-installed packages that have C extensions
- TT officially states they "do not support specific Python implementations"

TT also has a REST API v2 — limited to non-streaming use cases (order management, risk queries), not suitable for 1,000/sec DOM streaming.

### Access

Institutional access only. Requires a TT account through a prime broker or direct TT relationship. Not available retail. Costs are enterprise-level ($500–$2,000+/month range, not publicly listed).

### macOS support

IronPython typically runs on Windows. The REST API is cross-platform. The DOM streaming use case on macOS via TT is essentially unsupported.

### Confidence: MEDIUM

Sources: https://library.tradingtechnologies.com/tt-net-sdk/articles/tls-working-with-python.html, https://tradingtechnologies.com/trading/apis/

---

## Option 8: Bookmap Python API

**Verdict: YES for DOM/order book data, but requires Bookmap application running. Not standalone.**

### What they provide

Bookmap has an official Python API for developing add-ons:

- PyPI: `pip install bookmap`
- GitHub: https://github.com/BookmapAPI/python-api
- Supports: `subscribe_to_depth()` for L2 order book updates (price level + size)
- Also supports MBO events via `subscribe_to_mbo()` when your data provider sends MBO data
- Real-time depth updates: snapshot on first subscribe, then streaming delta updates

### Critical limitation

The Bookmap Python API **runs as an add-on inside the Bookmap application**. It is NOT a standalone Python script. You cannot run it headlessly or as a pure Python process. Bookmap must be running on the machine.

### Use case fit

If you are already using Bookmap (which supports Rithmic as a data source), you could write Python add-ons that consume the DOM data Bookmap already receives. But this does not eliminate Bookmap dependency — it adds Python scripting ON TOP of Bookmap, not instead of it.

### macOS support

Bookmap runs on macOS (Java-based desktop app). Python add-on runs within Bookmap.

### Cost

Bookmap subscription required: ~$99–$249/month depending on tier. Plus data feed cost (dxFeed, Rithmic, etc.).

### Confidence: HIGH

Sources: https://bookmap.com/knowledgebase/docs/Addons-Python-API, https://github.com/BookmapAPI/python-api

---

## Option 9: Polygon.io

**Verdict: NO for L2/DOM. Explicitly does not provide Level 2 data. Confirmed.**

From Polygon.io's own knowledge base:

> "Polygon.io currently does not provide level 2 data."

They do cover CME futures (NQ, ES) for tick trades and L1 quotes but not depth of market. This is a hard NO.

Source: https://polygon.io/knowledge-base/article/does-polygon-offer-level-2-data

---

## Summary Comparison Table

| Provider | Real L2? | Depth Levels | Update Rate | Python? | Execution? | macOS? | Cost/mo |
|----------|----------|-------------|-------------|---------|------------|--------|---------|
| **Rithmic Direct (async_rithmic)** | YES | 40+ (same as NT8) | 1,000+/sec | YES (native) | YES | YES | ~$0–20 |
| **Databento MBO (L3)** | YES (full book) | All levels | Very high | YES (official) | NO | YES | $179+ |
| **Databento MBP-10** | YES (L2) | 10 levels only | Very high | YES (official) | NO | YES | $179+ |
| **Interactive Brokers** | YES (limited) | ~10/side | Throttled | YES (official) | YES | YES | ~$10–30 |
| **CQG WebAPI** | YES | Deep (unconfirmed) | High | YES (samples) | YES | YES | broker-bundled |
| **Sierra Chart DTC** | BLOCKED | N/A | N/A | YES (protocol) | N/A | N/A | N/A |
| **dxFeed** | YES (likely) | Unconfirmed | Unconfirmed | YES | NO | Likely YES | $29–79 |
| **Trading Technologies** | YES | Deep | Microsecond | IronPython only | YES | NO | $500+ |
| **Bookmap Python API** | YES (via Bookmap) | Full | Real-time | YES (add-on only) | Via Bookmap | YES | $99–249 |
| **Polygon.io** | NO | None | N/A | YES | NO | YES | $0–200 |

---

## Decision Guide

### You want a drop-in replacement for NinjaTrader + Rithmic DOM in Python

**Use: Rithmic Direct via `async-rithmic`**

Same data infrastructure, same feed, same broker account. You get identical DOM levels and update rates. Add execution via the same library. Zero additional cost. Runs on macOS. This is the unambiguous answer for maintaining parity.

### You want a data-only feed that's independent of your broker

**Use: Databento MBO ($179/month)**

MBO (L3) gives you full order book reconstruction at all depths. Better for research, backtesting, and independent validation because your historical and live data come from the same source with identical schema. The NautilusTrader integration makes this production-ready for Python algo trading. Does not replace execution — pair with IBKR or keep Rithmic for orders.

### You want cheap execution + some DOM, don't need 40 levels

**Use: Interactive Brokers TWS API**

$0 platform fee, ~$10/month for CME data, Python officially supported. Accept the 10-level limitation. Workable for basic DOM reference, not for footprint charts or deep order flow analysis.

### You want to monitor DOM without leaving Bookmap

**Use: Bookmap Python API**

Write Python add-ons that process Bookmap's already-received DOM data. Keeps Bookmap as the data source, adds Python analytics on top.

---

## Building Footprint Charts from L2 Data in Python

YES — fully achievable. A footprint chart requires: for each price bar (time or volume based), accumulate the total volume transacted at each price level, split by aggressor side (bid-initiated = sell, ask-initiated = buy).

### Data source requirement

You need **tick-level trade data with aggressor side** (buy-initiated vs sell-initiated). This comes from:
- Rithmic TICKER_PLANT (tick data stream has trade direction)
- Databento MBO or Trades schema (includes aggressor side flag)
- Any source providing individual trade ticks with side information

L2 order book snapshots alone are NOT enough — you need the actual tick trades to build footprint bars.

### Libraries available

**Order book management (for maintaining live book state)**
- `orderbook` — C-backed Python library: https://github.com/bmoscon/orderbook — fast L2/L3 book state, O(1) updates
- `order-book` (PyPI) — similar C-backed implementation

**Footprint chart construction**
- `OrderflowChart` — https://github.com/murtazayusuf/OrderflowChart — Plotly-based footprint visualization, takes bid_size/price/ask_size per level
- `py-market-profile` — https://github.com/bfolkens/py-market-profile — Market Profile / Volume Profile from Pandas DataFrames
- `footprint-system` — https://github.com/FutTrader/footprint-system — reversal footprint bars

**Pure Python footprint construction pattern**

```python
from collections import defaultdict

# Per-bar accumulator
bar_footprint = defaultdict(lambda: {'bid_vol': 0, 'ask_vol': 0})

def on_tick(price, size, is_buy):
    key = round(price / tick_size) * tick_size  # snap to tick
    if is_buy:
        bar_footprint[key]['ask_vol'] += size  # buy = lifted offer
    else:
        bar_footprint[key]['bid_vol'] += size  # sell = hit bid
```

Aggregate across a bar's time range, then display as a footprint with delta (ask_vol - bid_vol) at each level. No external library required for the aggregation itself — it's pandas/dict operations.

**Visualization**
- Plotly (via OrderflowChart) for interactive HTML charts
- Matplotlib for static charts
- No mainstream charting library has a built-in footprint chart type (it requires custom implementation)

### Performance note

For real-time footprint at 1,000 ticks/second, you want the aggregation in a tight loop with minimal Python overhead. Consider:
- NumPy arrays indexed by price level (integer key = price / tick_size)
- Avoid dict lookups in the hot path; pre-allocate arrays covering your expected price range
- Separate the accumulation thread from the rendering thread

---

## Recommended Architecture for Pure Python DOM System

```
[Rithmic WebSocket] ──protobuf──► [async_rithmic] ──asyncio events──► [Python process]
                                                                              │
                                              ┌───────────────────────────────┤
                                              │                               │
                                    [DOM State (orderbook lib)]    [Tick Accumulator]
                                              │                               │
                                    [L2 Snapshot/Streaming]         [Footprint Builder]
                                              │                               │
                                    [Analytics / Signals]         [Plotly/matplotlib]
                                              │
                                    [Order Execution via async_rithmic ORDER_PLANT]
```

- **Single broker connection** handles both data and execution
- **Zero additional monthly cost** beyond current broker fees
- **macOS native** — pure Python, no Wine/Windows required
- **Same DOM depth** as NinjaTrader
- **Same update frequency** — you become the bottleneck, not the feed

---

## Sources

- Rithmic API page: https://www.rithmic.com/apis
- async_rithmic GitHub: https://github.com/rundef/async_rithmic
- pyrithmic GitHub: https://github.com/jacksonwoody/pyrithmic
- Databento GLBX.MDP3: https://databento.com/datasets/GLBX.MDP3
- Databento Live API: https://databento.com/live
- Databento CME pricing blog: https://databento.com/blog/introducing-new-cme-pricing-plans
- NautilusTrader Databento integration: https://nautilustrader.io/docs/latest/integrations/databento/
- IBKR TWS Market Depth: https://interactivebrokers.github.io/tws-api/market_depth.html
- Sierra Chart DTC Server: https://www.sierrachart.com/index.php?page=doc/DTCServer.php
- CQG WebAPI Python Samples: https://github.com/cqg/WebAPIPythonSamples
- CQG Partner Portal: https://partners.cqg.com/api-resources/web-api
- dxFeed Python API: https://dxfeed.com/api/python-api/
- dxFeed CME Market Data: https://dxfeed.com/market-data/futures/cme/
- TT Python SDK (IronPython): https://library.tradingtechnologies.com/tt-net-sdk/articles/tls-working-with-python.html
- Bookmap Python API: https://bookmap.com/knowledgebase/docs/Addons-Python-API
- Bookmap Python API GitHub: https://github.com/BookmapAPI/python-api
- Polygon.io L2 FAQ: https://polygon.io/knowledge-base/article/does-polygon-offer-level-2-data
- OrderflowChart (footprint): https://github.com/murtazayusuf/OrderflowChart
- bmoscon orderbook library: https://github.com/bmoscon/orderbook
- py-market-profile: https://github.com/bfolkens/py-market-profile
