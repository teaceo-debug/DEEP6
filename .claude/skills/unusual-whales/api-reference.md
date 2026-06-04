# Unusual Whales API Reference

## ANTI-HALLUCINATION (READ FIRST)

These fake endpoints are commonly hallucinated. **Never use them.**

| ❌ Hallucinated | ✅ Correct |
|---|---|
| `/api/options/flow` | `/api/option-trades/flow-alerts` |
| `/api/flow` or `/api/flow/live` | `/api/option-trades/flow-alerts` |
| `/api/stock/{ticker}/flow` | `/api/stock/{ticker}/flow-recent` |
| `/api/stock/{ticker}/options` | `/api/stock/{ticker}/option-contracts` |
| `/api/unusual-activity` | `/api/option-trades/flow-alerts` |
| `/api/v1/...` or `/api/v2/...` | No versioned paths exist |
| `?apiKey=` or `?api_key=` | Use `Authorization` header only |

### Concept Mapping

When someone says... use this endpoint:

| Concept | Endpoint |
|---|---|
| "Live Flow" / "Whale Trades" | `/api/option-trades/flow-alerts` |
| "Options Screener" | `/api/screener/option-contracts` |
| "Market Sentiment" | `/api/market/market-tide` |
| "Dark Pool" | `/api/darkpool/recent` or `/api/darkpool/{ticker}` |
| "Contract Greeks" | `/api/stock/{ticker}/greeks` |
| "Spot GEX" | `/api/stock/{ticker}/spot-exposures/strike` |
| "Financials" | `/api/stock/{ticker}/financials` |
| "Technical Indicator" | `/api/stock/{ticker}/technical-indicator/{function}` |

---

## Base URL

```
https://api.unusualwhales.com
```

All endpoints are **GET only**. No POST, PUT, or DELETE.

---

## Authentication

Every request requires two headers:

```http
Authorization: Bearer YOUR_TOKEN
UW-CLIENT-API-ID: 100001
```

No query-string auth. Headers only.

---

## Rate Limits

Default: **120 requests/minute**

### Response Headers for Usage Monitoring

| Header | Description |
|---|---|
| `x-uw-token-req-limit` | Daily request limit |
| `x-uw-daily-req-count` | Requests used today |
| `x-uw-req-per-minute-remaining` | Remaining in current minute window |
| `x-uw-minute-req-counter` | Requests made this minute |
| `x-uw-req-per-minute-reset` | Milliseconds until minute window resets |

Daily counter resets at **8 PM Eastern**.

---

## Response Format

All endpoints wrap their payload in a `data` key:

```json
{
  "data": [...]
}
```

Single-object responses use `"data": {}`. Always read from `response["data"]`.

---

## Endpoints

### Dark Pool

| Method | Path | Description |
|---|---|---|
| GET | `/api/darkpool/recent` | Recent dark pool prints across all tickers |
| GET | `/api/darkpool/{ticker}` | Dark pool prints for a specific ticker |

---

### Lit Flow

| Method | Path | Description |
|---|---|---|
| GET | `/api/lit-flow/recent` | Recent lit exchange flow |
| GET | `/api/lit-flow/{ticker}` | Lit flow for a specific ticker |

---

### GEX / Greeks

All under `/api/stock/{ticker}/`:

| Method | Path | Description |
|---|---|---|
| GET | `/api/stock/{ticker}/greek-exposure` | Aggregate greek exposure |
| GET | `/api/stock/{ticker}/greek-exposure/expiry` | Greek exposure by expiry |
| GET | `/api/stock/{ticker}/greek-exposure/strike` | Greek exposure by strike |
| GET | `/api/stock/{ticker}/greek-exposure/strike-expiry` | Greek exposure by strike and expiry |
| GET | `/api/stock/{ticker}/greek-flow` | Greek flow |
| GET | `/api/stock/{ticker}/greek-flow-expiry` | Greek flow by expiry |
| GET | `/api/stock/{ticker}/spot-exposures/one-minute` | Spot exposure at 1-minute resolution |
| GET | `/api/stock/{ticker}/spot-exposures/strike-expiry` | Spot exposure by strike and expiry |
| GET | `/api/stock/{ticker}/spot-exposures/strike` | Spot GEX by strike |

---

### Alerts

| Method | Path | Description |
|---|---|---|
| GET | `/api/alerts` | Your configured alerts |
| GET | `/api/alert-configs` | Alert configuration list |

---

### Companies

| Method | Path | Description |
|---|---|---|
| GET | `/api/companies/dividends` | Dividend data |
| GET | `/api/companies/earnings-estimates` | Earnings estimates |
| GET | `/api/companies/profile` | Company profile |
| GET | `/api/companies/splits` | Stock splits |
| GET | `/api/companies/transcript` | Earnings call transcripts |

---

### Congress

| Method | Path | Description |
|---|---|---|
| GET | `/api/congress/traders` | Congress members with trading activity |
| GET | `/api/congress/late-reports` | Late disclosure filings |
| GET | `/api/congress/politicians` | Politician list |
| GET | `/api/congress/recent-trades` | Recent congressional trades |

---

### Option Contract

| Method | Path | Description |
|---|---|---|
| GET | `/api/option-contract/{id}/flow` | Flow for a specific contract |
| GET | `/api/option-contract/{id}/history` | Historical data for a contract |
| GET | `/api/option-contract/{id}/intraday` | Intraday data |
| GET | `/api/option-contract/{id}/volume-profile` | Volume profile |
| GET | `/api/option-contract/{id}/expiry-breakdown` | Expiry breakdown |
| GET | `/api/option-contract/{id}/option-contracts` | Related contracts |

---

### Option Trades

| Method | Path | Description |
|---|---|---|
| GET | `/api/option-trades/flow-alerts` | Live flow alerts (whale trades, unusual activity) |
| GET | `/api/option-trades/flow-alert/{id}` | Single flow alert by ID |
| GET | `/api/option-trades/full-tape` | Full options tape |

---

### Stock (37 endpoints)

All under `/api/stock/{ticker}/`:

| Method | Path | Description |
|---|---|---|
| GET | `/api/stock/{ticker}/info` | Basic stock info |
| GET | `/api/stock/{ticker}/ohlc/{candle_size}` | OHLC candles |
| GET | `/api/stock/{ticker}/flow-alerts` | Flow alerts for ticker |
| GET | `/api/stock/{ticker}/flow-per-expiry` | Flow grouped by expiry |
| GET | `/api/stock/{ticker}/flow-per-strike` | Flow grouped by strike |
| GET | `/api/stock/{ticker}/flow-per-strike-intraday` | Intraday flow by strike |
| GET | `/api/stock/{ticker}/flow-recent` | Recent flow (not `/flow`) |
| GET | `/api/stock/{ticker}/greeks` | Greeks snapshot |
| GET | `/api/stock/{ticker}/greek-flow` | Greek flow |
| GET | `/api/stock/{ticker}/interpolated-iv` | Interpolated implied volatility |
| GET | `/api/stock/{ticker}/iv-rank` | IV rank and percentile |
| GET | `/api/stock/{ticker}/max-pain` | Max pain by expiry |
| GET | `/api/stock/{ticker}/net-prem-ticks` | Net premium ticks |
| GET | `/api/stock/{ticker}/nope` | NOPE (Net Options Pricing Effect) |
| GET | `/api/stock/{ticker}/oi-change` | Open interest change |
| GET | `/api/stock/{ticker}/oi-per-expiry` | OI by expiry |
| GET | `/api/stock/{ticker}/oi-per-strike` | OI by strike |
| GET | `/api/stock/{ticker}/option-chains` | Full option chain |
| GET | `/api/stock/{ticker}/option-contracts` | Option contracts (not `/options`) |
| GET | `/api/stock/{ticker}/option-price-level` | Price levels |
| GET | `/api/stock/{ticker}/options-volume` | Options volume |
| GET | `/api/stock/{ticker}/ownership` | Institutional ownership |
| GET | `/api/stock/{ticker}/last-stock-state` | Latest stock state |
| GET | `/api/stock/{ticker}/stock-volume-price-levels` | Volume at price levels |
| GET | `/api/stock/{ticker}/realized-volatility` | Realized volatility |
| GET | `/api/stock/{ticker}/volatility-stats` | Volatility statistics |
| GET | `/api/stock/{ticker}/implied-volatility-term-structure` | IV term structure |
| GET | `/api/stock/{ticker}/historical-risk-reversal-skew` | Risk reversal skew history |
| GET | `/api/stock/{ticker}/atm-chains` | ATM option chains |
| GET | `/api/stock/{ticker}/insider-buy-sell` | Insider transactions |
| GET | `/api/stock/{ticker}/financials` | Financial summary |
| GET | `/api/stock/{ticker}/income-statements` | Income statements |
| GET | `/api/stock/{ticker}/balance-sheets` | Balance sheets |
| GET | `/api/stock/{ticker}/cash-flows` | Cash flow statements |
| GET | `/api/stock/{ticker}/earnings` | Earnings history |
| GET | `/api/stock/{ticker}/technical-indicator/{function}` | Technical indicator values |
| GET | `/api/stock/{ticker}/companies-in-sector` | Peers in same sector |
| GET | `/api/stock/{ticker}/vol-oi-per-expiry` | Volume and OI by expiry |

---

### Market

| Method | Path | Description |
|---|---|---|
| GET | `/api/market/correlations` | Asset correlations |
| GET | `/api/market/events` | Market events calendar |
| GET | `/api/market/fda-calendar` | FDA event calendar |
| GET | `/api/market/insider-buy-sells` | Market-wide insider activity |
| GET | `/api/market/market-tide` | Market sentiment / tide |
| GET | `/api/market/oi-change` | Market-wide OI change |
| GET | `/api/market/sector-etfs` | Sector ETF data |
| GET | `/api/market/top-net-impact` | Top net premium impact |
| GET | `/api/market/total-options-volume` | Total options volume |
| GET | `/api/market/sec-indst` | SEC industry data |
| GET | `/api/market/etf-tide` | ETF tide / sentiment |
| GET | `/api/net-flow/expiry` | Net flow by expiry |

---

### Screener

| Method | Path | Description |
|---|---|---|
| GET | `/api/screener/analyst-ratings` | Analyst rating screener |
| GET | `/api/screener/option-contracts` | Options screener |
| GET | `/api/screener/stocks` | Stock screener |

---

### Short Interest

| Method | Path | Description |
|---|---|---|
| GET | `/api/short/short-screener` | Short interest screener |
| GET | `/api/short/short-data` | Short data for a ticker |
| GET | `/api/short/failures-to-deliver` | FTD data |
| GET | `/api/short/short-interest-and-float-v2` | Short interest and float |
| GET | `/api/short/short-volume-and-ratio` | Short volume and ratio |
| GET | `/api/short/short-volume-by-exchange` | Short volume broken out by exchange |

---

### ETFs

| Method | Path | Description |
|---|---|---|
| GET | `/api/etf/{ticker}/exposure` | ETF exposure breakdown |
| GET | `/api/etf/{ticker}/holdings` | ETF holdings |
| GET | `/api/etf/{ticker}/in-outflow` | Fund inflows and outflows |
| GET | `/api/etf/{ticker}/info` | ETF info |
| GET | `/api/etf/{ticker}/weights` | Holdings weights |

---

### Insider

| Method | Path | Description |
|---|---|---|
| GET | `/api/insider/transactions` | All insider transactions |
| GET | `/api/insider/sector-flow` | Insider flow by sector |
| GET | `/api/insider/insiders` | Insider list |
| GET | `/api/insider/ticker-flow` | Insider flow for a ticker |

---

### Institutions

| Method | Path | Description |
|---|---|---|
| GET | `/api/institution/{name}/activity/v2` | Institution trading activity |
| GET | `/api/institution/{name}/holdings` | Institution holdings |
| GET | `/api/institution/{name}/sectors` | Sector allocation |
| GET | `/api/institution/{name}/ownership` | Ownership data |
| GET | `/api/institutions` | List of tracked institutions |
| GET | `/api/institutions/latest-filings` | Latest 13F filings |

---

### Intel

| Method | Path | Description |
|---|---|---|
| GET | `/api/intel/analytics-sliding` | Sliding window analytics |
| GET | `/api/intel/analytics-window` | Fixed window analytics |
| GET | `/api/intel/ipo-calendar` | IPO calendar |
| GET | `/api/intel/listings` | New listings |
| GET | `/api/intel/movers` | Market movers |

---

### News

| Method | Path | Description |
|---|---|---|
| GET | `/api/news/headlines` | News headlines |

---

## WebSocket Channels

Connect to `wss://api.unusualwhales.com/ws` and subscribe to channels by name.

| Channel | Description |
|---|---|
| `flow-alerts` | Real-time options flow alerts |
| `option-trades` | Raw options trade tape |
| `off-lit-trades` | Off-exchange (dark pool) trades |
| `lit-trades` | Lit exchange trades |
| `gex` | GEX updates |
| `market-tide` | Market tide / sentiment updates |
| `price` | Price updates |
| `news` | Breaking news |
| `trading-halts` | Trading halt notifications |
| `contract-screener` | Contract screener hits |
| `custom-alerts` | Your custom alert triggers |
| `interval-flow` | Flow aggregated by interval |
| `net-flow` | Net flow updates |

---

## Quick Reference: Common Tasks

```python
import httplib2

BASE = "https://api.unusualwhales.com"
HEADERS = {
    "Authorization": "Bearer YOUR_TOKEN",
    "UW-CLIENT-API-ID": "100001",
}

# Live flow alerts
GET /api/option-trades/flow-alerts

# Flow for a specific ticker
GET /api/stock/AAPL/flow-recent

# Options screener
GET /api/screener/option-contracts

# Market sentiment
GET /api/market/market-tide

# Dark pool prints
GET /api/darkpool/recent

# GEX by strike
GET /api/stock/SPY/spot-exposures/strike

# IV rank
GET /api/stock/QQQ/iv-rank

# Congress trades
GET /api/congress/recent-trades
```
