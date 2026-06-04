# Dark Pool Trading Intelligence — Master Skill

## Identity & Purpose

This skill gives Claude everything needed to interpret dark pool data for NQ futures trading. Load it when analyzing dark pool prints, building S/R levels from institutional flow, or producing a directional bias narrative for NQ.

**Invoke when:**
- Interpreting Unusual Whales dark pool prints for NQ
- Building support/resistance levels from institutional flow
- Scoring dark pool confluence with GEX walls
- Producing a dark pool bias narrative for the DEEP6 signal grid
- Explaining accumulation vs distribution patterns

**Does NOT cover:**
- Unusual Whales API authentication setup (see `unusual-whales/api-reference`)
- WebSocket streaming configuration (see `unusual-whales/websocket`)
- Pure GEX theory without dark pool context (see `options-bias-engine/domains/gex-theory`)
- Footprint chart reading (see `trader-dale-footprint/`)
- PhD-level microstructure theory (see `dark-pool-nq-charting/microstructure-theory`)

---

## Core Thesis

Dark pool prints in QQQ and top NQ components cluster at prices where institutions are accumulating or distributing. These clusters become support and resistance for NQ futures 1 to 3 days before the move appears in price action. Combined with GEX walls and options flow, dark pool levels produce 55 to 70% directional accuracy. Used alone, they produce 30 to 45%.

The dark pool is the truth layer. Visible options flow is real-time noise. When they agree, conviction is maximum. When they disagree, trust the dark pool.

---

## Section 1: Dark Pool Mechanics

### What Dark Pools Are

Dark pools are private Alternative Trading Systems (ATS) where institutional orders execute away from public exchanges. They exist because large orders displayed publicly would be front-run before the institution could complete their trade.

A pension fund buying 500,000 QQQ shares on a lit exchange would immediately cause other traders to buy ahead of them, driving up the price. Dark pools let the institution execute at a negotiated price (typically the NBBO midpoint) without revealing intent.

**Participants:** Overwhelmingly institutional. Pension funds, hedge funds, mutual funds, sovereign wealth funds, prop desks. Retail traders don't access dark pools directly. Their orders are either routed to lit exchanges or internalized by their broker (Citadel, Virtu).

### Volume Reality Check

| Metric | Value | Source |
|--------|-------|--------|
| Dark pool share of US equity volume | 40.3% (Q1 2026, record high) | FINRA ATS |
| True ATS dark pool volume | ~15-18% of total | FINRA |
| Retail internalization (Citadel/Virtu) | ~25-30% of total | SEC filings |
| FINRA TRF reporting latency (median) | 2.5 milliseconds | NYU Stern 2021 |
| FINRA TRF reporting latency (95th pct) | 200 milliseconds | NYU Stern 2021 |
| Dark pool trades at stale prices | ~4% | BIS 2023 |
| Canceled dark pool orders (invisible) | 7-10% | SEC Rule 605 |
| Informative dark pool volume | ~35% | Kolm et al. 2023 |

The 40.3% headline number is misleading. Only 15-18% is true institutional ATS activity. The rest is retail internalization, which carries far less directional information.

### FINRA TRF Reporting

Dark pool trades are reported to FINRA Trade Reporting Facilities (TRF) within 10 seconds for equity trades. Unusual Whales aggregates these with an additional processing delay. Total latency from execution to your screen: 30 seconds to 5 minutes.

This means dark pool data is a CONFIRMING signal, not a leading signal. You're reading what institutions did 30 to 300 seconds ago. Their positions don't change in 5 minutes. The signal is still valid.

### 7 Data Biases Every Trader Must Know

1. **Retail internalization masquerades as dark pool.** Citadel and Virtu internalize ~25-30% of all US equity volume. These prints appear in dark pool data but carry no institutional directional information.

2. **Stale reference prices.** ~4% of dark pool prints execute at prices that don't reflect current NBBO. These appear at levels that seem significant but are artifacts of delayed pricing.

3. **Canceled orders are invisible.** 7-10% of dark pool orders are canceled after partial fill. You see the executed portion but not the full intended size.

4. **ETF rebalancing noise.** Index funds rebalance quarterly. Their dark pool activity creates false levels that disappear after the rebalance.

5. **Dividend capture distortion.** Institutions buy before ex-dividend dates and sell after. This creates dark pool buying followed by selling that has no directional meaning.

6. **Tax-loss harvesting (November-December).** Year-end selling of losing positions creates dark pool selling that is tax-driven, not bearish.

7. **Single large prints can be one-offs.** A $500M+ single print may be a pension fund rebalancing or merger-related hedge, not a directional bet. Look for clusters, not single prints.

### What Data Is Available Per Print

| Field | Description |
|-------|-------------|
| `executed_at` | Execution timestamp |
| `price` | Execution price |
| `size` | Number of shares |
| `premium` | Dollar value (price × size) |
| `nbbo_bid` | National Best Bid at execution |
| `nbbo_ask` | National Best Ask at execution |
| `market_center` | Reporting venue |
| `trade_code` | Trade condition code |
| `canceled` | Whether later canceled |

**What is NOT available:** Order book state, full intended order size, whether the buyer or seller was the informed party, intent (accumulation vs hedge vs rebalance).

---

## Section 2: NQ Proxy Architecture

NQ futures have no direct dark pool data. The proxy chain converts QQQ and component prints to NQ-equivalent levels.

### QQQ as Primary Proxy

QQQ tracks the Nasdaq-100 with ~99.8% correlation to NQ. Dark pool prints in QQQ represent institutional positioning in the same underlying index.

**Conversion formula:**
```
NQ_Level = QQQ_Level × (NQ_Price / QQQ_Price)
```

Current approximate ratio: ~41.16 (NQ ~30,500 / QQQ ~741). This ratio changes daily. Always compute it dynamically from live prices, never use a fixed constant.

### Top-5 Component Aggregation

| Ticker | Approx NQ Weight | Signal Strength |
|--------|-----------------|----------------|
| QQQ | 1.0 (ETF) | Primary proxy |
| AAPL | ~9% | Largest component |
| MSFT | ~8% | Second largest |
| NVDA | ~8% | High volatility, strong signals |
| GOOGL | ~5% | Large blocks go dark |
| AMZN | ~5% | Frequent dark pool cycles |

When 3 or more of these show dark pool accumulation at similar NQ-equivalent levels, the confluence signal is strong. One component alone is weak.

### When the Proxy Breaks

The QQQ-to-NQ proxy degrades in these conditions:

- **Basis blowout:** During extreme volatility, QQQ and NQ futures can diverge by 0.3-0.5%. Dark pool levels from QQQ may not map cleanly to NQ.
- **Ex-dividend dates:** QQQ pays quarterly dividends. On ex-div dates, QQQ price drops by the dividend amount. Adjust the ratio accordingly.
- **OPEX (monthly options expiration):** QQQ options expiration creates mechanical flows that temporarily distort the proxy.
- **ETF creation/redemption:** Large authorized participant activity can create dark pool prints in QQQ that reflect ETF mechanics, not directional positioning.

In these conditions, weight NDX component prints more heavily than QQQ prints.

### NDX vs QQQ for Level Types

- **QQQ:** Best for intraday dark pool levels. High volume, frequent prints, tight bid/ask.
- **NDX components (AAPL, MSFT, NVDA):** Best for structural multi-day levels. Larger prints, more deliberate positioning.
- **NDX index options:** Best for GEX walls. Options are written on NDX, not QQQ, for institutional hedging.

---

## Section 3: Dark Pool Print Classification

### Buy vs Sell Aggression

The NBBO midpoint is the reference:

- **Print above NBBO midpoint:** Buy aggression. The buyer paid more than the midpoint to get filled. Bullish.
- **Print below NBBO midpoint:** Sell aggression. The seller accepted less than the midpoint to get filled. Bearish.
- **Print at NBBO midpoint:** Ambiguous. Classify by the tick direction of the next lit trade.

```
midpoint = (nbbo_bid + nbbo_ask) / 2
if price > midpoint: direction = "buy"
elif price < midpoint: direction = "sell"
else: direction = "neutral"  # classify by tick
```

### Size Thresholds

| Size | Classification | Signal Weight |
|------|---------------|--------------|
| < 0.5% of ADV | Noise | Discard |
| 0.5-1% of ADV | Moderate | Low weight |
| 1-2% of ADV | Strong | Standard weight |
| > 2% of ADV | Very strong | High priority |
| > 10,000 shares | Block trade | Elevated attention |

For QQQ (ADV ~80-100M shares/day): a "strong" print is 800K to 2M shares.

**Institutional threshold:** $500K premium per print minimum. Below this, the print is likely retail internalization.

### Premium Calculation

```
premium = price × size × 100  (for options)
premium = price × size         (for equity)
```

Premium is the primary sorting metric. A 1,000-share print at $500 ($500K premium) matters more than a 10,000-share print at $10 ($100K premium).

---

## Section 4: Level Clustering

Individual prints are noise. Clusters are signal.

### Why Prints Cluster

**Order splitting:** A $500M institutional order can't execute in one block. Algorithms split it into hundreds of smaller prints over hours or days, all near the same target price.

**VWAP execution:** Institutions executing against VWAP naturally concentrate prints around the day's VWAP, which tends to be near significant price levels.

**Gamma walls:** Market makers hedge near gamma wall strikes. Their hedging shows up as dark pool prints because they route through dark venues to minimize market impact.

**Psychological levels:** Round numbers attract institutional limit orders. Dark pool prints cluster at these levels because that's where the orders sit.

### Clustering Algorithm (Greedy Merge)

1. Sort all prints by price.
2. Start a new cluster with the first print.
3. For each subsequent print: if its price is within 0.5% of the cluster's reference price, add it to the cluster. Otherwise, start a new cluster.
4. Compute the premium-weighted center of each cluster: `sum(price × premium) / sum(premium)`.
5. Sort clusters by total premium (strongest first).

**Cluster metadata to track:**
- `level`: premium-weighted center price
- `total_premium`: sum of all print premiums in cluster
- `print_count`: number of prints
- `price_range`: (min_price, max_price) in cluster
- `buy_premium`: sum of buy-side premiums
- `sell_premium`: sum of sell-side premiums
- `net_direction`: buy_premium - sell_premium

### Support vs Resistance

- **Cluster below current price:** Support zone. Institutions bought here. They'll defend it.
- **Cluster above current price:** Resistance zone. Institutions sold here. They'll sell again.
- **Cluster at current price:** Active institutional zone. High-stakes level. Watch for absorption or exhaustion.

### Level Lifecycle

| Stage | Description | Trading Implication |
|-------|-------------|---------------------|
| Fresh | New cluster, not yet tested | Treat as potential S/R |
| Tested | Price touched the level once | Level confirmed, higher conviction |
| Defended | Price bounced from level 2+ times | Strong S/R, trade with conviction |
| Broken | Price sliced through with no reaction | Remove from map, level is dead |

**Active window:** 30 to 45 days. Levels older than 45 days are stale unless price has recently retested them. Apply 3x recency weight to prints from the last 10 days vs prints from 11 to 45 days ago.

---

## Section 5: Accumulation vs Distribution Detection

### Accumulation Pattern

Institutions buying the dip on dark pools. Prints cluster BELOW current price, buy-side dominant.

**Signals:**
- Dark pool clusters forming at or below recent swing lows
- `buy_premium > sell_premium × 1.2` in lower clusters
- Print count increasing over 2 to 3 days at the same level
- Prints appearing during pullbacks (price declining, dark pool buying)

**Interpretation:** Smart money is loading up. The level below is a floor. Expect a bounce.

### Distribution Pattern

Institutions selling into strength. Prints cluster ABOVE current price, sell-side dominant.

**Signals:**
- Dark pool clusters forming at or above recent swing highs
- `sell_premium > buy_premium × 1.2` in upper clusters
- Print count increasing over 2 to 3 days at the same level
- Prints appearing during rallies (price rising, dark pool selling)

**Interpretation:** Smart money is unloading. The level above is a ceiling. Expect a reversal.

### Neutral Pattern

Balanced buy/sell across clusters. No dominant direction. Institutions are repositioning, not making a directional bet.

**Interpretation:** Stand aside. Wait for the pattern to resolve into accumulation or distribution.

### The Divergence Trap

The most dangerous scenario: visible flow is bullish (call sweeps, retail buying) while dark pool is bearish (net selling, distribution clusters above price).

This is DISTRIBUTION. Institutions are selling into retail buying. They may even be creating the bullish visible flow (buying calls to create the appearance of bullish flow while selling the underlying in dark pools). Do not buy. Prepare for reversal.

The inverse: visible flow is bearish while dark pool is bullish. This is ACCUMULATION. Institutions are buying into retail selling. Do not short. Prepare for reversal.

---

## Section 6: Dark Pool + GEX Confluence

This is the highest-conviction signal combination in the system.

### Why It Works

Gamma walls exist because market makers have large options exposure at that strike. They hedge by buying or selling the underlying near that level. Their hedging activity shows up as dark pool prints because they route through dark venues to minimize market impact.

A gamma wall with dark pool clustering means two independent institutional forces are active at the same price. The level is doubly defended.

### Confluence Scoring

| Signal Combination | Reliability |
|-------------------|-------------|
| Dark pool level alone | 30-45% |
| Dark pool + GEX wall (within 0.5%) | 65-70% |
| Dark pool + GEX + options flow | 70-75% |
| Dark pool + GEX + flow + footprint absorption | 75-80% |

**Proximity threshold:** Dark pool level within 0.5% of a GEX wall = confluence confirmed.

### Level-Specific Confluence Rules

**Call wall + dark pool SELLING:**
- Institutions are selling at the call wall level.
- The wall is actively defended by institutional sellers.
- Fade the call wall with maximum conviction.

**Call wall + dark pool BUYING:**
- Institutions are buying through the resistance.
- The call wall is about to break.
- Do not fade. Stand aside or trade the break.

**Put wall + dark pool BUYING:**
- Institutions are buying at the put wall level.
- The floor is actively defended.
- Buy the put wall with maximum conviction.

**Put wall + dark pool SELLING:**
- Institutions are selling through the support.
- The put wall is about to break (trapdoor).
- Do not buy. Stand aside or trade the break.

**Gamma flip + dark pool level:**
- The regime boundary has institutional interest.
- Dark pool buying at flip = positive gamma regime defended.
- Dark pool selling at flip = regime transition incoming.

**No dark pool activity at a GEX wall:**
- Nobody institutional cares about this level.
- The wall is weaker than it appears.
- Fade with reduced conviction. Vulnerable on second test.

---

## Section 7: Time-of-Day Effects

Dark pool activity is not uniform. Timing changes signal quality.

| Session | Time (ET) | Dark Pool Activity | Signal Weight |
|---------|-----------|-------------------|--------------|
| Pre-market | 4:00-9:30 | Low volume, wide spreads | Low |
| NY Open | 9:30-10:30 | Heaviest (~40% of daily) | High |
| Midday | 10:30-14:00 | Lower, rebalancing noise | Medium |
| Power Hour | 14:00-15:00 | Increasing, end-of-day positioning | High |
| Close | 15:00-16:00 | MOC orders, highest volume | Very High |
| After-hours | 16:00+ | Thin, unreliable | Discard |

**Final 30 minutes (15:30-16:00 ET):** Highest signal weight per print. Institutions are making final positioning decisions for the day. A large dark pool print at 15:45 ET is more meaningful than the same print at 10:15 ET.

**Midday caution:** 10:30 to 14:00 ET has the highest proportion of algorithmic rebalancing noise. Apply a 0.7x multiplier to dark pool signals during this window.

---

## Section 8: Signal Grid Integration

Dark pool data feeds into the DEEP6 10-signal grid. Each signal votes BUY or SELL.

| Signal | Source | Dark Pool Role |
|--------|--------|---------------|
| 1. 13F Institutions | Quarterly 13F filings | Structural directional bias |
| 2. Floor/Lit Flow | Exchange floor prints | Cross-validate dark pool direction |
| 3. Dark Pool Bias | Unusual Whales net premium | Primary dark pool signal |
| 4. Market Tide | Bull/bear premium balance | Macro flow context |
| 5. Multi-Day Swing | DP level persistence across days | Structural S/R confirmation |
| 6. Daily OI Bias | Options OI change direction | Dealer positioning context |
| 7. Sweep Flow | Aggressive sweep trades | Visible flow cross-validation |
| 8. Block Flow | Large block trade direction | Institutional size confirmation |
| 9. OI Change | Open interest delta | Positioning shift detection |
| 10. DP Blocks | Dark pool clustered block direction | Block-level dark pool signal |

**Confluence rule:** Count BUY and SELL votes out of 10.
- 7+ BUY: Strong bullish bias. Full size long.
- 7+ SELL: Strong bearish bias. Full size short.
- 5-6 either direction: Moderate bias. Half size.
- < 5 either direction: Stand aside. No trade.

---

## Section 9: Quantitative Scoring

### DIX (Dark Index)

Dollar-weighted dark pool short ratio from SqueezeMetrics.

```
DIX = dark_pool_short_volume_dollars / total_dark_pool_volume_dollars
```

- DIX > 0.45: Bullish. Institutions are buying into selling pressure.
- DIX < 0.40: Bearish. Institutions are selling into buying pressure.
- DIX 0.40-0.45: Neutral.

Historical: DIX > 0.45 produces mean 60-day return of +5.3% vs +2.8% baseline.

### Z-Score Anomaly Detection

```
z = (current_metric - rolling_mean_20d) / rolling_std_20d
```

- |z| > 2.0: Statistically significant anomaly. Act on it.
- |z| > 3.0: Extreme anomaly. High conviction.
- |z| < 1.5: Within normal range. Background noise.

Apply z-score to: net premium, print count, cluster premium, dark pool volume %.

### Aggression Ratio

```
aggression = buy_premium / (buy_premium + sell_premium)
```

- > 0.55: Buy aggression. Bullish.
- < 0.45: Sell aggression. Bearish.
- 0.45-0.55: Balanced. Neutral.

### Dark Pool POC

The premium-weighted center of ALL prints across all clusters. Analogous to the Volume Profile Point of Control. Price gravitates toward the Dark Pool POC over 1 to 3 days.

```
dp_poc = sum(level × total_premium for each cluster) / sum(total_premium for all clusters)
```

If current NQ price is above the DP POC, expect gravitational pull downward. If below, expect pull upward. This is a mean-reversion signal, not a momentum signal.

### Dark Pool Score (Composite)

```
score = (premium_score × 0.6 + cluster_score × 0.4) × dp_multiplier

premium_score:
  |net_premium| < $10M  → 0
  $10M-$30M             → ±1
  $30M-$100M            → ±2
  > $100M               → ±3

dp_multiplier:
  dark_pool_pct > 40%   → 1.0
  dark_pool_pct 20-40%  → 0.7
  dark_pool_pct < 20%   → 0.4

Final score clamped to [-3, +3]
```

---

## Section 10: Institutional 13F Intelligence

### What 13F Filings Are

Quarterly institutional holdings reports filed with the SEC. Any institution managing >$100M in US equities must file within 45 days of quarter end. ~9,000 filers tracked by Unusual Whales.

**Filing lag:** 45 days after quarter end. A Q1 filing (January-March) appears by mid-May. This is a SLOW structural signal, not an intraday trigger.

### CIK Format (Critical)

CIK is always a 10-digit zero-padded string. Never an integer.

```
Correct:   "0001067983"
Wrong:     1067983
```

Every lookup will fail silently if you pass an integer.

### Position Classification

| Classification | Condition |
|---------------|-----------|
| New | `units > 0` and `first_buy == report_date` |
| Added | `units_change > 0` and `first_buy != report_date` |
| Trimmed | `units_change < 0` |
| Held | `units_change == 0` and `first_buy != report_date` |
| Closed | `units == 0` |

### Trajectory Classification

Using `historical_units` (8-quarter array, index 0 = most recent):

| Trajectory | Pattern |
|-----------|---------|
| Building | Monotonically increasing over 3+ quarters |
| Harvesting | Monotonically decreasing over 3+ quarters |
| New conviction | Recent entry, still growing |
| Volatile | Large swings quarter to quarter |
| Steady | Consistent hold with minor changes |

### Key Institutions for NQ

Watch these for QQQ/NDX/NQ component positioning:
- Morgan Stanley, Bank of America (large QQQ holders)
- Susquehanna, Citadel (options market makers, GEX-relevant)
- Two Sigma, Renaissance (quant funds, systematic positioning)
- Berkshire Hathaway (AAPL weight, structural NQ signal)

### Numeric Field Gotcha

All numeric values in 13F responses come back as string floats: `"123456.0"` not `123456`. Always convert: `int(float(value))` for unit counts, `float(value)` for prices.

---

## Section 11: Unusual Whales API Integration

### Endpoint Reference

| Endpoint | Purpose | Poll Frequency |
|----------|---------|---------------|
| `GET /api/darkpool/{ticker}` | Dark pool prints for a ticker | Every 15 min |
| `GET /api/stock/{ticker}/stock-volume-price-levels` | Aggregated off/lit volume by price | Every 30 min |
| `GET /api/market/market-tide` | Bull/bear premium balance | Every 1 min |
| `GET /api/option-trades/flow-alerts` | Options flow alerts | Every 1 min |
| `GET /api/stock/{ticker}/ownership` | Institutional ownership | Every 1 hr |
| `GET /api/institutions/latest_filings` | Recent 13F filings | Every 1 hr |
| `GET /api/stock/{ticker}/oi-change` | Open interest change | Every 15 min |
| `GET /api/darkpool/recent` | Market-wide recent prints | Every 5 min |

**Auth:** `Authorization: Bearer {API_KEY}` header on every request.

**Rate limit:** 120 requests/minute. With the polling frequencies above, DEEP6 uses ~20-30 req/min at peak.

**Key params for dark pool endpoint:**
- `date`: YYYY-MM-DD (default today)
- `min_premium`: filter noise (use $500K minimum)
- `limit`: max 500 per call
- `newer_than` / `older_than`: pagination by timestamp

**Always filter canceled trades:** `[p for p in prints if not p.get("canceled", False)]`

### Stock Volume Price Levels

`GET /api/stock/{ticker}/stock-volume-price-levels` returns aggregated volume by price level: `{price, lit_vol, off_vol}`.

This is the most useful endpoint for S/R identification. It shows the full distribution of where off-exchange volume has concentrated, not just individual prints. Levels with high `off_vol` and high `off_vol / (lit_vol + off_vol)` ratio are institutional interest zones.

---

## Section 12: Interpretation Framework for Claude

When analyzing dark pool data for NQ trading, follow this sequence:

### Step 1: Establish the Dominant Pattern

Look at the last 2 hours of dark pool prints for QQQ and top components. Are clusters forming above or below current price? Is buy_premium or sell_premium dominant? Classify as accumulation, distribution, or neutral.

### Step 2: Locate Key Levels

Identify the top 3 clusters by total premium. Convert each to NQ-equivalent using the live ratio. These are your dark pool S/R levels. Note whether each is support (below price) or resistance (above price).

### Step 3: Check GEX Confluence

For each dark pool level, check if a GEX wall (call wall, put wall, gamma flip) is within 0.5%. If yes, mark as high-conviction. If no, mark as moderate.

### Step 4: Assess Time-of-Day Reliability

Apply the time-of-day multiplier. Prints from 9:30-10:30 ET and 15:00-16:00 ET carry full weight. Midday prints (10:30-14:00 ET) carry 0.7x weight.

### Step 5: Score the Signal Grid

Count BUY and SELL votes across the 10 signals. Compute the net score. Classify as strong bullish, moderate bullish, neutral, moderate bearish, or strong bearish.

### Step 6: Factor in 13F Structural Bias

Check the most recent 13F data for QQQ and top components. Are institutions building or harvesting? This is a slow-moving structural bias that modifies the intraday signal. Building = bullish structural backdrop. Harvesting = bearish structural backdrop.

### Step 7: Produce the Narrative

Output a concise analysis with:
- **Direction:** Bullish / Bearish / Neutral
- **Key level:** The most important dark pool S/R level in NQ terms
- **Conviction:** X/10 signals agree, reliability estimate
- **Risk:** What would invalidate this read (level break, flow reversal)
- **Timeframe:** 1-3 days for dark pool levels to play out

**Example output format:**
```
Dark Pool Read: BULLISH (6/10 signals)
Key level: 21,450 NQ (QQQ $521.50 cluster, $340M premium, 3 prints)
GEX confluence: Yes — within 0.3% of put wall at 21,420
Conviction: 65% (DP + GEX confirmed, flow neutral)
Risk: Break below 21,380 invalidates. Watch for distribution prints above 21,600.
Timeframe: 1-2 days
```

---

## Section 13: Common Mistakes to Avoid

**Treating every dark pool print as institutional.** 70% of dark pool volume is retail internalization (Citadel, Virtu). Only prints above $500K premium with institutional-scale size carry directional information.

**Using stale levels.** Levels older than 45 days are stale unless recently retested. Remove broken levels immediately. A level that price sliced through with no reaction is dead.

**Ignoring NBBO context.** Prints at stale prices (~4% of all prints) appear at levels that seem significant but are artifacts. Always check that the print price is within the NBBO spread at execution time.

**Over-weighting a single large print.** A $500M single print could be ETF rebalancing, a pension fund quarterly adjustment, or a merger-related hedge. Look for clusters of prints over time, not single large events.

**Assuming dark pool = hidden buying.** Dark pool prints can be selling just as easily as buying. Always classify by NBBO midpoint comparison, not by assumption.

**Using a fixed QQQ-to-NQ ratio.** The ratio changes daily. NQ at 30,500 and QQQ at 741 gives 41.16. NQ at 31,000 and QQQ at 752 gives 41.22. Always compute dynamically from live prices.

**Trading against GEX regime based on dark pool alone.** Dark pool levels are S/R zones, not regime signals. If GEX says negative gamma (trending, volatile), don't fade a move just because a dark pool level is nearby. The regime overrides the level.

**Ignoring the divergence trap.** Visible bullish flow + dark pool selling = distribution. This is the most dangerous scenario for longs. The dark pool is always the smarter signal.

**Treating midday prints as equal to open/close prints.** Midday dark pool activity has higher rebalancing noise. Apply the 0.7x multiplier.

**Forgetting the 45-day 13F lag.** 13F data is 45 days stale. Don't use it as an intraday signal. It's structural context only.

---

## Section 14: DEEP6 System Architecture

How dark pool data flows through the DEEP6 system:

```
Unusual Whales API
    → UnusualWhalesAdapter
      (poll every 15min, TTL cache, filter canceled prints)
    
    → DarkPoolLevelEngine
      (cluster prints by 0.5% proximity, premium-weighted centers,
       compute buy/sell dominance, classify accumulation/distribution)
    
    → SignalGridEngine
      (10 signals: 13F, floor flow, DP bias, market tide,
       multi-day swing, OI bias, sweep flow, block flow,
       OI change, DP blocks — vote BUY/SELL, count confluence)
    
    → SwingEquilibriumEngine
      (DP levels + GEX walls + HVL weighted average,
       compute the institutional equilibrium price)
    
    → GEXAnalyzer
      (dark pool modifier: +5/-5 confidence points
       when DP level within 0.5% of GEX wall)
    
    → ConvictionScorer
      (River 4: dark pool institutional bias,
       combines with Rivers 1-3: GEX, flow, footprint)
    
    → ClaudeInterpreter
      (narrative generation using this knowledge brain,
       produces direction + key level + conviction + risk)
    
    → GEXTerminalSnapshot
      → SSE → Desktop App + NT8 Bridge
```

### Key Integration Points

**DarkPoolLevelEngine outputs:**
- `levels[]`: list of S/R levels with NQ-equivalent prices
- `dominant_pattern`: accumulation / distribution / neutral
- `net_score`: composite dark pool score [-3, +3]
- `dp_poc`: premium-weighted center of all prints

**SignalGridEngine inputs from dark pool:**
- Signal 3 (Dark Pool Bias): net_score direction
- Signal 5 (Multi-Day Swing): level persistence across sessions
- Signal 10 (DP Blocks): block-level cluster direction

**ConvictionScorer River 4 (Dark Pool Institutional Bias):**
- Weight: 20% of total conviction score
- Input: net_score from DarkPoolLevelEngine
- Modifier: +0.15 if GEX confluence confirmed

**ClaudeInterpreter:**
- Loads this skill when generating dark pool narrative
- Follows the 7-step interpretation framework (Section 12)
- Outputs structured analysis in the format shown in Section 12

---

## Quick Reference Card

| Situation | Action |
|-----------|--------|
| DP clusters below price, buy dominant | Bullish. Support confirmed. |
| DP clusters above price, sell dominant | Bearish. Resistance confirmed. |
| DP buying + call wall within 0.5% | Break incoming. Don't fade. |
| DP selling + call wall within 0.5% | Strong resistance. Fade with conviction. |
| DP buying + put wall within 0.5% | Strong support. Buy with conviction. |
| DP selling + put wall within 0.5% | Trapdoor. Don't buy. |
| Visible bullish flow + DP selling | Distribution. Prepare for reversal. |
| Visible bearish flow + DP buying | Accumulation. Prepare for reversal. |
| Single large print, no cluster | Likely noise. Wait for cluster formation. |
| Level > 45 days old, no retest | Remove from map. Stale. |
| Midday prints (10:30-14:00 ET) | Apply 0.7x weight. Higher noise. |
| Final 30 min prints (15:30-16:00 ET) | Apply 1.3x weight. Highest signal. |
| 7+ signals agree | Full size trade. |
| < 5 signals agree | Stand aside. |
| DIX > 0.45 | Structural bullish backdrop. |
| DIX < 0.40 | Structural bearish backdrop. |
| Z-score > 2.0 | Statistically significant. Act on it. |
