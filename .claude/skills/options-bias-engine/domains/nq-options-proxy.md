# NQ Options Proxy: Using QQQ and NDX Options for NQ Futures Analysis

## Why NQ Doesn't Have Its Own Liquid Options Chain

NQ futures options exist. They trade on the CME. But they're thinly traded compared to QQQ and NDX options, and for good reason: the institutional options market for Nasdaq 100 exposure has consolidated around QQQ and NDX, not NQ futures options.

The liquidity hierarchy for Nasdaq 100 options:

```
QQQ options:  200M+ contracts/day. Tightest bid-ask. Most liquid equity options chain in the world.
NDX options:  10-30M contracts/day. Liquid. Institutional focus. Larger notional per contract.
NQ options:   1-5M contracts/day. Thin. Wide bid-ask. Institutional use only.
```

The practical consequence: All the GEX data, all the flow data, all the positioning data from FlashAlpha, Massive.com, and Unusual Whales is computed on QQQ and NDX, not NQ. To use this data for NQ trading, you must convert.

The conversion is not just a mathematical exercise. It requires understanding WHY the proxy works, WHERE it breaks down, and HOW to maintain accuracy as market conditions change.

---

## The QQQ-to-NQ Conversion: Mathematics and Practice

### The Underlying Relationship

QQQ (Invesco QQQ Trust) is an ETF that tracks the Nasdaq 100 index. Each QQQ share represents approximately 1/100th of the Nasdaq 100 index value.

```
QQQ_price ≈ NDX_index / 100

At NDX = 21,000: QQQ ≈ $210... 

Wait. Let's be precise.
```

Actually, QQQ's NAV is not exactly NDX/100. The ETF has accumulated dividends, fees, and tracking differences over its history. The actual relationship is:

```
QQQ_price = NDX_index × (QQQ_shares_outstanding / NDX_divisor) × adjustment_factor
```

In practice, the ratio drifts over time. As of 2025-2026, with NDX around 21,000 and QQQ around $520:

```
Conversion_ratio = NDX / QQQ = 21,000 / 520 ≈ 40.4
```

This means: a $1 move in QQQ corresponds to approximately 40.4 points in NDX (and therefore NQ).

### The Level Conversion Formula

To convert a QQQ options level to an NQ level:

```
NQ_level = QQQ_level × conversion_ratio

Where:
  conversion_ratio = current_NQ_price / current_QQQ_price
```

**Concrete example:**

```
Current QQQ price: $521.50
Current NQ price: 21,100

Conversion ratio: 21,100 / 521.50 = 40.46

FlashAlpha QQQ levels:
  Call wall: $525.00
  Put wall:  $518.00
  Gamma flip: $522.00

NQ equivalents:
  Call wall: 525.00 × 40.46 = 21,242 → round to 21,240 (nearest 5 NQ points)
  Put wall:  518.00 × 40.46 = 20,958 → round to 20,960
  Gamma flip: 522.00 × 40.46 = 21,120 → round to 21,120
```

### Rounding Convention

NQ trades in 0.25-point increments ($5/tick). For GEX levels, round to the nearest 5 or 10 NQ points (the precision of the conversion doesn't justify sub-5-point accuracy).

```
Rounding rule: Round to nearest 5 NQ points for walls and flip.
Example: 21,242 → 21,240 (nearest 5)
Example: 20,958 → 20,960 (nearest 5)
```

For very precise levels (e.g., a specific 0DTE pin strike), round to the nearest 25 NQ points (the nearest round QQQ strike × conversion ratio).

### Updating the Conversion Ratio

The conversion ratio changes as QQQ and NQ prices change. It drifts slowly (0.1-0.5 per day) but compounds over weeks.

**Update frequency:**
- Recalculate on every FlashAlpha poll (typically 2-4 times per day)
- Use the CURRENT QQQ and NQ prices at the time of the poll
- Do NOT use a fixed ratio. It will drift and create level errors.

**Practical implementation:**

```python
def qqq_to_nq(qqq_level, current_qqq_price, current_nq_price):
    ratio = current_nq_price / current_qqq_price
    nq_level = qqq_level * ratio
    return round(nq_level / 5) * 5  # Round to nearest 5 NQ points

# Example:
qqq_call_wall = 525.00
current_qqq = 521.50
current_nq = 21100

nq_call_wall = qqq_to_nq(qqq_call_wall, current_qqq, current_nq)
# Result: 21240
```

---

## The NDX-to-NQ Conversion: The Direct Mapping

### Why NDX Is Simpler

NDX (Nasdaq 100 Index) IS the Nasdaq 100 index. NQ futures ARE NDX futures. They track the same underlying. The conversion is nearly 1:1.

```
NDX_level ≈ NQ_level (with a small basis adjustment)
```

The basis (NQ premium/discount to NDX fair value) is typically less than 10 NQ points. For level purposes, this is negligible.

**NDX level conversion:**

```
NQ_level ≈ NDX_level + basis

Where basis = NQ_price - NDX_index (typically -10 to +10 points)
```

For practical purposes, treat NDX levels as NQ levels directly:

```
NDX call wall at 21,200 → NQ call wall at 21,200 (no conversion needed)
NDX put wall at 20,800 → NQ put wall at 20,800
NDX gamma flip at 21,000 → NQ gamma flip at 21,000
```

### The NQ-NDX Basis

The basis exists because NQ futures price in the cost of carry (interest rate minus dividend yield) over the life of the futures contract:

```
NQ_fair_value = NDX × e^((r - q) × T)

Where:
  r = risk-free rate (annualized)
  q = dividend yield of NDX (annualized)
  T = time to NQ futures expiration (years)
```

At typical rates (r = 5%, q = 0.5%, T = 0.25 years for front-month):
```
NQ_fair_value = NDX × e^((0.05 - 0.005) × 0.25) = NDX × 1.0113
```

So NQ should trade at approximately 1.13% above NDX. At NDX = 21,000:
```
NQ_fair_value = 21,000 × 1.0113 = 21,237
```

But in practice, the basis fluctuates around fair value due to supply/demand imbalances in the futures market. The actual basis is observable in real-time by comparing NQ price to NDX index.

For level purposes: the basis is small enough to ignore. NDX levels translate directly to NQ levels.

---

## When to Use QQQ vs. NDX

### QQQ: Best for Intraday Analysis

QQQ is the better proxy for intraday analysis because:

1. **Highest 0DTE volume**: QQQ has the most 0DTE options activity of any instrument. The intraday walls are most clearly visible in QQQ.

2. **Most liquid flow**: Massive.com captures the most options flow in QQQ. The flow signals are clearest.

3. **Tightest bid-ask**: QQQ options have the tightest bid-ask spreads, meaning the prices are the most accurate reflection of market expectations.

4. **Retail participation**: Retail traders use QQQ options heavily. Retail flow creates the 0DTE walls that dominate intraday NQ behavior.

**Use QQQ for:**
- 0DTE wall identification
- Intraday flow reading (Massive.com)
- Real-time GEX updates
- Intraday pin strike identification

### NDX: Best for Structural Analysis

NDX is the better proxy for multi-day and structural analysis because:

1. **Institutional positioning**: Institutional hedges and structured products use NDX options (larger notional per contract, cash-settled). The monthly and quarterly OI is dominated by NDX.

2. **Direct index mapping**: NDX levels translate directly to NQ levels without conversion. No ratio drift.

3. **Gamma flip accuracy**: The gamma flip from NDX options is more accurate for NQ because it's the same underlying.

4. **Monthly/quarterly walls**: The large OI at monthly and quarterly strikes is in NDX, not QQQ.

**Use NDX for:**
- Monthly and quarterly GEX structure
- Gamma flip computation
- Structural support/resistance levels
- OPEX week analysis

### Best Practice: Use Both, Cross-Reference

The optimal approach:
1. Use QQQ for intraday signals (0DTE walls, flow, real-time GEX)
2. Use NDX for structural levels (monthly walls, gamma flip, OPEX analysis)
3. Cross-reference: if a QQQ-derived level (converted to NQ) coincides with an NDX-derived level, it's doubly strong

**Example:**
```
QQQ call wall at $525 → NQ equivalent: 21,240
NDX call wall at 21,250

These are within 10 NQ points of each other. The level 21,240-21,250 is doubly strong.
```

When QQQ and NDX levels diverge significantly (> 50 NQ points), investigate why. It may indicate a structural difference in the options market (e.g., institutional hedging at a specific NDX level that retail isn't matching in QQQ).

---

## Where the Proxy Breaks Down

### Breakdown 1: NQ-Specific Futures Flows

NQ futures have their own supply and demand dynamics that are independent of QQQ/NDX options. Large NQ-specific flows (fund rebalancing, futures rolling, CTA trend-following) affect NQ price without affecting QQQ options.

**Example:**
- A large CTA fund is selling NQ futures to reduce equity exposure
- This selling pressure is in NQ futures only, not in QQQ options
- The QQQ GEX levels don't reflect this selling pressure
- NQ may break through a QQQ-derived support level that "should" hold

**How to detect:**
- Watch Rithmic MBO for large, sustained directional order flow that doesn't match the GEX prediction
- If NQ is breaking through a GEX wall without the expected counter-hedging, it's likely a futures-specific flow
- Check the NQ-NDX basis: if NQ is trading at a large discount to NDX fair value, futures selling is overwhelming the options hedging

### Breakdown 2: Basis Divergence in Stress Events

In stress events (flash crashes, circuit breakers, liquidity crises), NQ can trade at a significant discount to NDX fair value. The futures market is selling faster than the options market can adjust.

**Example:**
- A flash crash causes NQ to drop 200 points in 30 seconds
- NDX index (computed from stock prices) has only dropped 150 points (stocks are slower to reprice)
- QQQ options are priced off NDX, not NQ
- The QQQ GEX levels are "correct" for NDX but wrong for NQ's actual price

**Implication:**
- During stress events, the QQQ/NDX proxy may be temporarily unreliable
- NQ may trade through GEX levels that "should" hold because the basis has blown out
- Wait for the basis to normalize before relying on GEX levels again

**How to detect:**
- Monitor the NQ-NDX basis in real-time
- Normal basis: ±10 NQ points
- Stress basis: ±50+ NQ points
- When basis > 30 NQ points, treat GEX levels with caution

### Breakdown 3: After-Hours and Pre-Market

NQ futures trade nearly 24 hours (Sunday 6:00 PM to Friday 5:00 PM ET, with a 1-hour break). QQQ and NDX options trade 9:30 AM to 4:00 PM ET (with some extended hours for NDX).

**Implication:**
- GEX levels are only meaningful during options trading hours (9:30 AM to 4:00 PM ET)
- After-hours NQ moves are not constrained by dealer hedging (no options trading)
- Pre-market NQ moves may establish a price far from the GEX levels
- At the open, the market must reconcile the overnight NQ move with the GEX structure

**Practical rule:**
- Do not use GEX levels to predict after-hours NQ behavior
- At the open, check if NQ has gapped above or below the gamma flip
- A gap above the flip: positive gamma regime from the start. Bullish.
- A gap below the flip: negative gamma regime from the start. Bearish.
- A gap through a major wall: the wall may be tested and may hold or break

### Breakdown 4: Dividend and Rebalancing Effects

QQQ pays dividends (small, quarterly). NDX doesn't (it's an index). Around QQQ ex-dividend dates, QQQ options pricing adjusts (calls become cheaper, puts become more expensive by the dividend amount). NQ doesn't have this adjustment.

**Implication:**
- Around QQQ ex-dividend dates (typically March, June, September, December), QQQ-derived levels may be slightly off
- The effect is small (QQQ dividend yield is ~0.5% annually, so quarterly dividend is ~0.125%)
- At QQQ = $520, the quarterly dividend is approximately $0.65
- This creates a ~$0.65 discrepancy in QQQ-derived levels around ex-div dates
- In NQ terms: 0.65 × 40.4 ≈ 26 NQ points. Not negligible for precise levels.

**Practical rule:**
- Around QQQ ex-dividend dates, prefer NDX-derived levels over QQQ-derived levels
- The ex-dividend date is typically the third Friday of the quarter (same as OPEX)

### Breakdown 5: Single-Stock Concentration Effects

The Nasdaq 100 is heavily concentrated in a few mega-cap stocks. The top 5 stocks (AAPL, MSFT, NVDA, AMZN, META) represent 40-50% of the index weight.

**Implication:**
- If AAPL alone is moving the Nasdaq (single-stock event like earnings), QQQ options reflect it
- But the impact on NQ is diluted by the other 95 components
- A QQQ GEX wall derived from AAPL-driven options activity may not translate accurately to NQ

**Example:**
- AAPL reports earnings and gaps up 10%
- AAPL is 12% of QQQ. QQQ rises 1.2% from AAPL alone.
- QQQ options are repriced for the new QQQ level
- But NQ's move depends on all 100 components, not just AAPL
- The QQQ GEX levels may be "correct" for QQQ but slightly off for NQ

**Practical rule:**
- During single-stock events (major earnings, M&A, etc.) for top-10 Nasdaq components, treat QQQ-derived levels with caution
- Prefer NDX-derived levels (NDX is the same index as NQ, so single-stock effects are identical)

---

## The Conversion in Practice: A Complete Example

### Pre-Market Setup

```
Time: 9:00 AM ET
Current QQQ price: $521.50 (pre-market)
Current NQ price: 21,100 (pre-market)
Conversion ratio: 21,100 / 521.50 = 40.46

FlashAlpha QQQ data (from last night's close):
  Total GEX: +$4.2B (positive gamma regime)
  Call wall: $525.00
  Put wall: $518.00
  Gamma flip: $522.00
  HVL: $521.00

NQ equivalents:
  Call wall: 525.00 × 40.46 = 21,242 → 21,240
  Put wall: 518.00 × 40.46 = 20,958 → 20,960
  Gamma flip: 522.00 × 40.46 = 21,120 → 21,120
  HVL: 521.00 × 40.46 = 21,080 → 21,080

FlashAlpha NDX data:
  Call wall: 21,250
  Put wall: 20,950
  Gamma flip: 21,100

Cross-reference:
  Call wall: QQQ-derived 21,240 vs NDX 21,250 → use 21,240-21,250 zone
  Put wall: QQQ-derived 20,960 vs NDX 20,950 → use 20,950-20,960 zone
  Gamma flip: QQQ-derived 21,120 vs NDX 21,100 → use 21,100-21,120 zone
```

### Intraday Update

```
Time: 11:30 AM ET
Current QQQ price: $523.20 (market has rallied)
Current NQ price: 21,175
New conversion ratio: 21,175 / 523.20 = 40.47

FlashAlpha intraday update:
  Call wall: $525.00 (unchanged)
  Put wall: $519.00 (shifted up slightly)
  Gamma flip: $522.50 (shifted up slightly)

Updated NQ equivalents:
  Call wall: 525.00 × 40.47 = 21,247 → 21,245
  Put wall: 519.00 × 40.47 = 21,004 → 21,005
  Gamma flip: 522.50 × 40.47 = 21,146 → 21,145

Note: The ratio barely changed (40.46 → 40.47). The level changes are minimal.
But the put wall shifted from 20,960 to 21,005 (45 NQ points) due to OI changes.
This is a meaningful shift. The put wall is now closer to current price.
```

### End-of-Day Validation

After the session, validate the proxy:
- Did NQ respect the converted levels?
- Did the call wall hold as resistance?
- Did the put wall hold as support?
- Did the gamma flip correctly identify the regime?

Track this validation over time. If the proxy is working (levels respected ~80% of the time), the conversion ratio is accurate. If levels are consistently off by a fixed amount, the ratio may need adjustment.

---

## GEX Magnitude Conversion

### Why Dollar Magnitude Matters

The GEX dollar magnitude (e.g., +$4.2B) is expressed in QQQ terms. To understand the impact on NQ, you need to convert to NQ terms.

### The Conversion

```
NQ_GEX = QQQ_GEX × (NQ_notional / QQQ_notional)

Where:
  NQ_notional = NQ_price × $20 (NQ contract value per point)
  QQQ_notional = QQQ_price × 100 (QQQ contract value per share, assuming 1 contract = 100 shares)
```

Wait, this isn't quite right. Let's think more carefully.

QQQ GEX is in dollars of QQQ hedging per 1% QQQ move. NQ GEX should be in dollars of NQ hedging per 1% NQ move.

Since QQQ and NQ track the same index, a 1% QQQ move = a 1% NQ move. So the dollar amounts are directly comparable IF the hedging executes in the same market.

But the hedging may execute in QQQ shares OR NQ futures. The proportion depends on the dealer's preference. For large dealers, NQ futures are often preferred for large hedges.

**Practical approach:**
- The SIGN and REGIME of QQQ GEX translates directly to NQ (positive QQQ GEX = positive NQ regime)
- The LEVEL POSITIONS (walls, flip) translate via the conversion ratio
- The DOLLAR MAGNITUDE is less important for trading decisions than the sign and levels
- For rough magnitude comparison: QQQ GEX × 1 ≈ NQ GEX (they're both measuring the same underlying)

### When Dollar Magnitude Matters

Dollar magnitude matters when estimating the IMPACT of dealer hedging on NQ price:

```
NQ_impact_per_1pct_move = QQQ_GEX × (NQ_ADV_dollars / QQQ_ADV_dollars)

Where:
  NQ_ADV_dollars = NQ average daily volume × NQ_price × $20
  QQQ_ADV_dollars = QQQ average daily volume × QQQ_price
```

**Example:**
```
QQQ GEX: +$4.2B
QQQ ADV: 80M shares × $521 = $41.7B
NQ ADV: 500,000 contracts × 21,100 × $20 = $211B

NQ_impact = $4.2B × ($211B / $41.7B) = $4.2B × 5.06 = $21.3B per 1% NQ move

But wait: NQ ADV is much larger than QQQ ADV. The GEX impact as a fraction of ADV:
  QQQ: $4.2B / $41.7B = 10% of ADV per 1% move
  NQ: $4.2B / $211B = 2% of ADV per 1% move (if all hedging is in NQ)
```

The key insight: The same QQQ GEX creates a smaller percentage impact on NQ (because NQ is more liquid). But the absolute dollar impact is the same (the hedging is the same amount of money, just a smaller fraction of NQ's larger volume).

---

## Validation: Does the Proxy Actually Work?

### Empirical Evidence

The QQQ/NDX-to-NQ proxy works because the hedging that enforces GEX levels executes in NQ futures. This is not theoretical; it's observable.

When QQQ dealers need to buy delta (positive gamma regime, price falling), they execute in NQ futures. The Rithmic MBO feed captures this as large buy orders appearing at the converted GEX support levels. The levels hold because the hedging is real and executes in NQ.

### Validation Methodology

Track the following over 20+ trading days:
1. Record the converted NQ levels (call wall, put wall, gamma flip) each morning
2. Record whether NQ respected each level during the session
3. Compute the hit rate: what percentage of levels were respected?

Expected hit rates:
- Call wall (resistance): 70-80% of the time
- Put wall (support): 70-80% of the time
- Gamma flip (regime boundary): 65-75% of the time (more complex, can be tested multiple times)

If hit rates are below 60%, investigate:
- Is the conversion ratio drifting? (Recalculate more frequently)
- Is the proxy breaking down for structural reasons? (Check the breakdown conditions above)
- Is the GEX data stale? (Check FlashAlpha update frequency)

### When the Proxy Fails

The proxy fails most often when:
1. NQ-specific futures flows overwhelm the options hedging (large CTA selling, fund rebalancing)
2. The basis has blown out (stress event, flash crash)
3. It's post-OPEX Monday (levels have been reset, new structure not yet established)
4. A single mega-cap stock is dominating the move (AAPL earnings, NVDA earnings)

In these cases, fall back to:
- Rithmic MBO for real-time support/resistance (where is absorption occurring?)
- Price action (where is the market actually finding support/resistance?)
- NDX-derived levels (more direct mapping, less affected by QQQ-specific issues)

---

## Summary: The NQ Options Proxy in One Page

**The core relationship:**
- QQQ ≈ NDX/40.4 (approximately, varies with price)
- NDX = NQ (same underlying, small basis)
- QQQ levels × conversion_ratio = NQ levels
- NDX levels = NQ levels (direct)

**Conversion formula:**
```
conversion_ratio = current_NQ_price / current_QQQ_price
NQ_level = QQQ_level × conversion_ratio (round to nearest 5 NQ points)
```

**Update frequency:** Every FlashAlpha poll (2-4x per day)

**Use QQQ for:** Intraday (0DTE walls, flow, real-time GEX)
**Use NDX for:** Structural (monthly walls, gamma flip, OPEX analysis)

**Where it breaks:**
1. NQ-specific futures flows (CTA, fund rebalancing)
2. Basis divergence in stress events
3. After-hours (no options trading)
4. QQQ ex-dividend dates
5. Single mega-cap stock events

**Validation target:** 70-80% level respect rate over 20+ days

**The bottom line:** The proxy works because the hedging that enforces QQQ/NDX GEX levels executes in NQ futures. The levels are real. The conversion is necessary but straightforward. The breakdowns are identifiable and manageable.
