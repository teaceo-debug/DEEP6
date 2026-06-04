# Unusual Whales — Master Skill Router

> Institutional-grade market data: options flow, dark pool, GEX, congressional trading, and 100+ API endpoints.
> Use QQQ/SPY dark pool + options flow as NQ/ES proxy for DEEP6 signal integration.

## Identity

This skill tree provides deep knowledge of the Unusual Whales platform and API for building NQ trading signals from institutional flow data. It covers dark pool levels as support/resistance, options flow alerts, gamma exposure, real-time WebSocket streaming, and Python async integration patterns.

**This skill complements** the existing `options-bias-engine/` (theory), `nq-options-algo-engine/` (implementation), and `flashalpha-options/` (FlashAlpha GEX) skills. Unusual Whales provides an independent, comprehensive data source with 100+ endpoints and official Python SDK.

## When to Load This Skill

Load when the task involves ANY of:
- Querying the Unusual Whales API (REST, WebSocket, or MCP)
- Using dark pool levels from QQQ/SPY as NQ support/resistance
- Building options flow alerts or screening for unusual activity
- Accessing GEX/gamma exposure data from Unusual Whales
- Integrating UW data into DEEP6's async Python pipeline
- Congressional or insider trading data
- Institutional 13F holdings analysis
- Real-time market sentiment (Market Tide)

Do NOT load for:
- FlashAlpha-specific GEX data → load `flashalpha-options/`
- Pure options theory → load `options-bias-engine/knowledge`
- Massive.com raw chain data → load `nq-options-algo-engine/data-sources/massive-api`
- NinjaTrader anything → load `nt8-expert/`

---

## Platform Overview

| Attribute | Value |
|-----------|-------|
| **Base URL** | `https://api.unusualwhales.com` |
| **Auth** | `Authorization: Bearer <TOKEN>` + `UW-CLIENT-API-ID: 100001` |
| **Protocol** | REST (GET only), WebSocket, Kafka |
| **Endpoints** | 100+ across 20 categories |
| **Python SDK** | `unusualwhales-python` (official, async-native via httpx) |
| **MCP Server** | `https://api.unusualwhales.com/api/mcp` (official) |
| **OpenAPI Spec** | `https://api.unusualwhales.com/api/openapi` |
| **Rate Limit** | 120 requests/minute (default) |
| **Pricing** | API: $150/mo (Basic), $375/mo (Advanced + WS/Kafka) |

---

## Sub-Skill Routing Table

| File | Domain | Load When |
|------|--------|-----------|
| `api-reference.md` | Complete endpoint reference, auth, anti-hallucination blacklist | Building API calls, need exact endpoint paths/params, debugging 404s |
| `dark-pool.md` | Dark pool levels, NQ proxy via QQQ, clustering methodology, S/R | Using dark pool data for NQ trading, identifying institutional levels |
| `options-flow.md` | Flow alerts, screening, sweep detection, 6-component scoring | Screening for unusual options activity, building flow-based signals |
| `gex-greeks.md` | GEX endpoints, spot exposures, Greek flow, IV, vol surface | Gamma exposure analysis, comparing with FlashAlpha GEX |
| `websocket.md` | Real-time streaming channels, production patterns, backpressure | Building live data feeds, real-time dark pool / flow monitoring |
| `implementation.md` | Python async client, rate limiting, circuit breaker, DEEP6 integration | Writing Python code that consumes UW API, building the data pipeline |
| `institutional.md` | 13F filings, institutional ownership, politician trades, CIK lookup | Analyzing institutional positioning, congressional trade tracking |

---

## DEEP6 Integration Points

```
┌─────────────────────────────────────────────────────────────┐
│              UNUSUAL WHALES DATA PIPELINE                    │
│                                                              │
│  ┌──────────────────┐    ┌──────────────────────────────┐   │
│  │  REST API (GET)   │    │  WebSocket (Real-time)        │   │
│  │                   │    │                               │   │
│  │  • Dark pool      │    │  • off-lit-trades (dark pool) │   │
│  │  • Flow alerts    │    │  • flow-alerts (options)      │   │
│  │  • GEX/Greeks     │    │  • gex (gamma exposure)       │   │
│  │  • Market Tide    │    │  • market-tide (sentiment)    │   │
│  │  • Options chains │    │  • option-trades (full tape)  │   │
│  │  • Institutional  │    │  • price (quotes)             │   │
│  └────────┬─────────┘    └──────────────┬───────────────┘   │
│           └──────────┬──────────────────┘                    │
│                      ▼                                       │
│           ┌──────────────────┐                               │
│           │  ASYNC CLIENT    │  ← implementation.md          │
│           │  (httpx + WS)    │                               │
│           │                  │                               │
│           │  Rate limiter    │                               │
│           │  Circuit breaker │                               │
│           │  Usage monitor   │                               │
│           └────────┬─────────┘                               │
│                    ▼                                          │
│           ┌──────────────────┐                               │
│           │  NQ PROXY LAYER  │  ← dark-pool.md               │
│           │                  │                               │
│           │  QQQ → NQ price  │                               │
│           │  Top-5 component │                               │
│           │  aggregation     │                               │
│           └────────┬─────────┘                               │
│                    ▼                                          │
│           ┌──────────────────┐                               │
│           │  SIGNAL ENGINE   │  (existing DEEP6)             │
│           │  (44 signals)    │                               │
│           │                  │                               │
│           │  UW signals feed │                               │
│           │  into composite  │                               │
│           │  confidence      │                               │
│           └──────────────────┘                               │
└─────────────────────────────────────────────────────────────┘
```

### NQ Proxy Strategy

NQ futures have no direct dark pool data. Use these proxies:

1. **QQQ dark pool** — Direct Nasdaq-100 ETF institutional flow
2. **Top-5 NQ components** — AAPL, MSFT, NVDA, GOOGL, AMZN (~45% of NQ weight)
3. **QQQ options GEX** — Gamma exposure from QQQ options chain
4. **NDX options flow** — Options flow on the Nasdaq-100 index itself

### Signal Confluence Weights (Proposed)

| Signal Source | Weight | DEEP6 Integration |
|--------------|--------|-------------------|
| Dark pool levels (QQQ) | 20% | S/R levels for NQ |
| GEX walls (QQQ via UW) | 25% | Gamma regime + walls |
| Options flow (sweeps/blocks) | 25% | Directional bias |
| Footprint absorption (Rithmic) | 20% | Entry timing |
| Volume Profile POC | 10% | Structural context |

---

## Anti-Hallucination Protocol

**CRITICAL**: The UW API is commonly hallucinated by LLMs. Before making ANY API call:

1. Check `api-reference.md` for the exact endpoint path
2. All requests are **GET only** — never POST/PUT/DELETE
3. Auth goes in **header only** — never query params
4. Base URL is `https://api.unusualwhales.com` — no `/v1/` or `/v2/` paths
5. See the full blacklist in `api-reference.md`

---

## Quick Reference: Key Endpoints for NQ Trading

```python
# Dark pool (QQQ as NQ proxy)
GET /api/darkpool/QQQ
GET /api/stock/QQQ/stock-volume-price-levels  # Off/Lit price levels

# Options flow
GET /api/option-trades/flow-alerts?ticker_symbol=QQQ&min_premium=50000
GET /api/stock/QQQ/flow-recent

# GEX / Gamma
GET /api/stock/QQQ/spot-exposures/strike
GET /api/stock/QQQ/spot-exposures/one-minute

# Market sentiment
GET /api/market/market-tide

# Greeks flow
GET /api/stock/QQQ/greek-flow

# IV / Volatility
GET /api/stock/QQQ/iv-rank
GET /api/stock/QQQ/interpolated-iv
GET /api/stock/QQQ/implied-volatility-term-structure
```

## Sources

| Source | URL | Type |
|--------|-----|------|
| Official API Docs | https://api.unusualwhales.com/docs | Interactive |
| Official Skill.md | https://unusualwhales.com/skill.md | AI reference |
| OpenAPI Spec | https://api.unusualwhales.com/api/openapi | JSON |
| Python SDK | https://pypi.org/project/unusualwhales-python/ | PyPI |
| MCP Server | https://unusualwhales.com/public-api/mcp | Official |
| WebSocket Skill | https://unusualwhales.com/skills/websocket.md | AI reference |
| Institutional Skill | https://unusualwhales.com/skills/institutional.md | AI reference |
| Usage Monitor Skill | https://unusualwhales.com/skills/uw-api-usage-monitor-skill.md | AI reference |
