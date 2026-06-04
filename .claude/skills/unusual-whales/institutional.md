# Unusual Whales Institutional & Political Data — 13F, Insider, Congressional

## Overview

Unusual Whales tracks ~9,000 institutional 13F filers, congressional trading disclosures, and SEC Form 4 insider transactions. This reference covers all three domains with verified endpoints, data quirks, and NQ-specific application patterns.

---

## 1. Institutional 13F Data

### CIK Format (Critical)

CIK is always a **10-digit zero-padded string**. Never an integer.

```python
# Correct
cik = "0001067983"

# Wrong — will break lookups
cik = 1067983
```

### Endpoints

**List all institutions**
```
GET /api/institutions
```
Params: `name`, `tags[]`, `min_total_value`, `max_total_value`, `order`, `order_direction`, `limit`, `page`

**Recent filings**
```
GET /api/institutions/latest_filings
```
Params: `name`, `date`, `order`, `limit`, `page`

**Institution activity (v2)**
```
GET /api/institution/{cik}/activity/v2
```
Params: `start_date`, `end_date` (YYYY-MM-DD), `ticker_symbol` (comma-separated; prefix `-` to exclude), `order` (`units` or `units_change`), `order_direction`, `limit`, `page`

Note: The response does NOT include the CIK. Inject it from the request context when storing results.

**Holdings**
```
GET /api/institution/{cik}/holdings
```
Params: `date`, `security_types`, `limit`, `page`, `order`, `order_direction`

**Sector exposure**
```
GET /api/institution/{cik}/sectors
```
Params: `date`, `limit`

**Institutional ownership by ticker**
```
GET /api/institution/{ticker}/ownership
```
Params: `date`, `tags`, `order`, `order_direction`, `limit`, `page`

This is the only endpoint that takes a ticker instead of a CIK. Don't mix them up.

---

### Institution Tags

Use these to filter by fund type:

`hedge_fund`, `known`, `activist`, `value_investor`, `public_companies`, `biotech`, `tiger_club`, `technology`, `small_cap`, `credit`, `13d_activist`, `energy`, `event`, `real_estate`, `esg`

---

### Holdings Response Fields

| Field | Description |
|---|---|
| `units` | Current share count |
| `units_change` | Change from prior quarter |
| `value` | Dollar value of position |
| `perc_of_share_value` | Position as % of total portfolio |
| `historical_units` | 8-quarter array; index 0 = current, index 7 = oldest |
| `avg_price` | Average cost basis |
| `close` | Current close price |
| `change_perc` | Price change % |
| `first_buy` | Date of initial purchase |
| `security_type` | Shares, options, etc. |
| `put_call` | `null` for shares/funds, `"put"` or `"call"` for options |
| `sector` | Sector classification |

**Data quality note:** Numeric values come back as string floats (`"123456.0"`). Convert with `float()` then `int()` where needed.

---

### Position Classification

Classify each holding based on `units`, `units_change`, and `first_buy`:

```python
def classify_position(holding, report_date):
    units = int(float(holding["units"]))
    units_change = int(float(holding["units_change"]))
    first_buy = holding["first_buy"]

    if units == 0:
        return "closed"
    if units > 0 and first_buy == report_date:
        return "new"
    if units_change > 0 and first_buy != report_date:
        return "added"
    if units_change < 0:
        return "trimmed"
    if units_change == 0 and first_buy != report_date:
        return "held"
```

---

### Trajectory Classification

Use `historical_units` (8-quarter array, index 0 = most recent) to classify conviction:

```python
def classify_trajectory(historical_units):
    h = [int(float(x)) for x in historical_units if x is not None]
    if len(h) < 2:
        return "insufficient_data"

    quarters_held = sum(1 for x in h if x > 0)

    if all(h[i] >= h[i+1] for i in range(len(h)-1)):
        return "building"          # monotonically increasing over 3+ quarters
    if all(h[i] <= h[i+1] for i in range(len(h)-1)):
        return "harvesting"        # monotonically decreasing over 3+ quarters
    if quarters_held <= 2 and h[0] > 0:
        return "new_conviction"    # recent entry, still growing
    if max(h) > 2 * min(x for x in h if x > 0):
        return "volatile"          # large swings
    return "steady"
```

---

### Local SQLite DB for CIK Lookups

With ~9,000 filers, paginating the API to build a name-to-CIK map takes 18+ calls. Build a local cache instead:

```python
import sqlite3

def build_institution_cache(db_path="institutions.db"):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS institutions (
            cik TEXT PRIMARY KEY,
            name TEXT,
            tags TEXT,
            total_value REAL
        )
    """)
    # Paginate /api/institutions and insert rows
    # Run once, refresh quarterly
    conn.commit()
    conn.close()

def lookup_cik(name_fragment, db_path="institutions.db"):
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT cik, name FROM institutions WHERE name LIKE ?",
        (f"%{name_fragment}%",)
    ).fetchall()
    conn.close()
    return rows
```

---

### Verified Test CIKs

| Institution | CIK |
|---|---|
| Berkshire Hathaway | `0001067983` |
| Duquesne / Druckenmiller | `0001536411` |
| Appaloosa / Tepper | `0001656456` |
| Alkeon Capital | `0001230239` |

---

## 2. Congressional Trading

All endpoints are GET only.

```
GET /api/congress/recent-trades
```
Params: `member`, `limit`

```
GET /api/congress/traders
```
Returns congress members with trade data.

```
GET /api/congress/late-reports
```
Late STOCK Act filings.

```
GET /api/congress/politicians
```
Full politician list.

```
GET /api/politician-portfolios/people
```
Politicians with portfolio data.

```
GET /api/politician-portfolios/portfolios
```
Portfolio holdings.

```
GET /api/politician-portfolios/recent-trades
```
Recent politician trades.

```
GET /api/politician-portfolios/holds-ticker
```
Which politicians hold a specific ticker.

```
GET /api/politician-portfolios/disclosures
```
Annual disclosures with PDF links.

---

## 3. Insider Trading

SEC Form 4 filings and aggregated insider flow.

```
GET /api/insider/transactions
```
Params: `ticker_symbol`, `limit`

```
GET /api/insider/sector-flow
```
Aggregated insider activity by sector.

```
GET /api/insider/insiders
```
List of tracked insiders.

```
GET /api/insider/ticker-flow
```
Insider activity for a specific stock.

```
GET /api/market/insider-buy-sells
```
Market-wide insider buy vs. sell summary.

---

## 4. NQ Trading Application

These data sources feed macro and directional bias for NQ futures trading.

**Institutional ownership shifts in NQ components**
Monitor quarterly 13F changes for QQQ, AAPL, MSFT, NVDA. Large hedge funds trimming tech = bearish macro context. New conviction entries from known value investors = support.

**Congressional trades as macro signal**
Tech-sector congressional buys cluster before favorable legislation or earnings cycles. Use as a slow-moving directional bias layer, not a timing signal.

**Insider buying in NQ components**
C-suite open-market buys (not option exercises) in top NQ names confirm bullish bias. Cluster buying across multiple names in the same week is a stronger signal.

**Hedge fund QQQ/NDX options positioning**
13F filings report options positions. Large put accumulation in QQQ by known hedge funds = elevated downside risk. Cross-reference with GEX data for confluence.

---

## 5. Gotchas

**CIK is always a string, always 10 digits, always zero-padded.**
`"0001067983"` not `1067983`. Every lookup will fail silently or return nothing if you pass an integer.

**Activity endpoint doesn't return CIK.**
`/api/institution/{cik}/activity/v2` responses don't echo the CIK back. If you're storing results, inject it from the request before writing to DB.

**`put_call` is null for non-options.**
For regular share positions and funds, `put_call` is `null`. Only options positions carry `"put"` or `"call"`. Don't assume a null means missing data.

**Ownership endpoint uses ticker, not CIK.**
`/api/institution/{ticker}/ownership` is the only endpoint in this group that takes a ticker symbol. Every other institution endpoint takes a CIK. Don't swap them.

**Only send params you need.**
Don't send default values as explicit params. The API behaves differently when params are present vs. absent in some cases.

**Numeric fields are string floats.**
`"123456.0"` not `123456`. Always convert: `int(float(value))` for unit counts, `float(value)` for prices and percentages.

**`historical_units` index 0 is current.**
Index 0 = most recent quarter, index 7 = oldest. This is the reverse of what you might expect from a time series.
