# DEEP6 V8 Signal Clarity & Directional Bias Research

**Date**: May 24, 2026  
**Scope**: Professional footprint trading platforms (ATAS, Bookmap, Sierra Chart, Jigsaw Daytradr, Exocharts)  
**Goal**: Extract actionable design patterns for signal display clarity and directional bias determination

---

## Executive Summary

Professional footprint platforms solve signal clutter through **three core mechanisms**:

1. **Filtering by Confluence** — Only display signals when multiple conditions align (delta + volume + imbalance)
2. **Threshold-Based Gating** — Set minimum magnitude thresholds (e.g., 3:1 imbalance ratio, 90% volume percentile)
3. **Decay/Weighting** — Reduce signal strength over time or by distance from price (half-life decay, proximity weighting)

**Directional bias** is derived from **absorption + exhaustion asymmetry**:
- **LONG bias** = Absorption on bids (buyers defending) + Exhaustion on asks (sellers running out)
- **SHORT bias** = Absorption on asks (sellers defending) + Exhaustion on bids (buyers running out)
- **NEUTRAL** = Balanced absorption or no clear exhaustion pattern

---

## Platform Analysis

### 1. ATAS — Cluster Statistic Filtering Model

**Source**: [ATAS Blog: 7 Footprint Analysis Methods](https://atas.net/blog/7-footprint-analysis-methods-with-cluster-statistic/) (Feb 2026)

#### Clutter Reduction Strategy

ATAS uses **Cluster Statistic** as a dashboard layer that aggregates footprint data into scannable metrics:

| Metric | Purpose | Clutter Reduction |
|--------|---------|-------------------|
| **Delta** | Buy/sell pressure at each level | Only highlight bars with abnormal delta (>90th percentile) |
| **Session Delta** | Cumulative directional bias | Ignore noise; watch for sustained growth/decline |
| **Maximum Delta** | Peak buyer strength | Flag reversal points when max delta fails to hold |
| **Minimum Delta** | Peak seller strength | Identify support zones where sellers exhausted |
| **Delta/Volume (%)** | Directional dominance ratio | Highlight when >70% of volume is one-sided |
| **Trades Count** | Participation level | Alert when trades drop sharply (exhaustion signal) |

**Key Insight**: Instead of labeling every cluster, ATAS shows a **summary table** with only the bars that stand out. Traders then drill into those specific bars.

#### Imbalance Highlighting Algorithm

ATAS's **Bid/Ask Imbalance Mode** uses a **percentage-based threshold**:

`
Imbalance Rate (default 150%, adjustable 100%-500%):
- If (bid_volume / ask_volume) > 150%, highlight as bullish imbalance
- If (ask_volume / bid_volume) > 150%, highlight as bearish imbalance
`

**Recommendation for DEEP6**: Start at **300% (3:1 ratio)** as default. Lower thresholds (200%) flood the chart; higher (500%) hide valid signals.

#### Directional Bias Determination

ATAS combines three metrics for bias:

1. **Delta direction** — Positive = buyers, Negative = sellers
2. **Session Delta trend** — Rising = sustained buying, Falling = sustained selling
3. **Divergence detection** — If Session Delta rises but price consolidates, expect reversal (warning signal)

**Algorithm**:
`
IF Session_Delta is rising AND Delta is positive AND Volume is increasing
  → LONG bias (high confidence)
ELSE IF Session_Delta is falling AND Delta is negative AND Volume is increasing
  → SHORT bias (high confidence)
ELSE IF Session_Delta diverges from price
  → NEUTRAL (low confidence, watch for reversal)
`

---

### 2. Bookmap — Market Pulse Multi-Algorithm Approach

**Source**: [Bookmap Market Pulse Documentation](https://bookmap.com/knowledgebase/docs/Addons-Market-Pulse) (Jan 2026)

#### Clutter Reduction: Algorithm Stacking

Bookmap's **Market Pulse** uses **multiple independent algorithms** that each output a single metric. Traders combine them for confluence:

| Algorithm | Output | Clutter Reduction |
|-----------|--------|-------------------|
| **Volume Pressure** | Buyer/seller pressure over time | Decays over half-life period; only shows current state |
| **Orderbook Pressure** | Liquidity proximity to BBO | Weights by distance; closer orders = higher weight |
| **Orderbook Pressure Imbalance** | Difference between buyer/seller liquidity | Shows only the imbalance, not raw values |
| **Absorption Pressure** | Passive buyer/seller strength | Decays by half-life; shows only active absorption |
| **Sweeps Pressure** | Aggressive order flow | Alerts only on threshold crossing |
| **Stops & Icebergs Pressure** | Hidden order detection | Flags only when iceberg size exceeds threshold |

**Key Insight**: Each algorithm has a **threshold parameter** and **half-life decay**. Signals fade over time, preventing stale labels from cluttering the chart.

#### Half-Life Decay Model

`
Signal_Strength(t) = Initial_Strength × 0.5^(t / half_life_period)

Example: If half_life = 60 seconds
- At t=0: Signal = 100%
- At t=60s: Signal = 50%
- At t=120s: Signal = 25%
- At t=180s: Signal = 12.5% (effectively invisible)
`

**Recommendation for DEEP6**: Implement **60-120 second half-life** for absorption/exhaustion signals. Older signals fade, preventing label accumulation.

#### Directional Bias: Pressure Imbalance

Bookmap's **Orderbook Pressure Imbalance** algorithm:

`
Buyer_Pressure = SUM(liquidity_at_each_level × proximity_weight)
Seller_Pressure = SUM(liquidity_at_each_level × proximity_weight)

Imbalance = (Buyer_Pressure - Seller_Pressure) / (Buyer_Pressure + Seller_Pressure)

IF Imbalance > +0.3 → LONG bias
IF Imbalance < -0.3 → SHORT bias
ELSE → NEUTRAL
`

**Proximity Weight**: Orders closer to BBO have higher weight. An order 5 ticks away has ~50% the weight of an order at BBO.

---

### 3. Sierra Chart — Footprint Accuracy + Historical Replay

**Source**: [NexusFi Academy: Footprint Charts for Futures Trading](https://nexusfi.com/a/platforms/footprint-charts) (Apr 2026)

#### Clutter Reduction: Imbalance Highlighting + Stacking Detection

Sierra Chart's **Numbers Bars** (footprint) support:

1. **Imbalance Highlighting** — Color-code cells where bid/ask ratio exceeds threshold
2. **Stacked Imbalance Detection** — Flag when 3+ consecutive price levels show same directional extreme
3. **Delta Coloring** — Shade cells by delta magnitude (darker = stronger directional bias)

**Imbalance Threshold Recommendation** (from NexusFi):
`
Default: 300% (3:1 ratio)
- 200%: Too sensitive, floods chart with weak signals
- 300%: Sweet spot for NQ futures
- 500%: Too strict, misses valid setups
`

**Stacked Imbalance Algorithm**:
`
FOR each price level in bar:
  IF (bid_volume / ask_volume > 3.0) OR (ask_volume / bid_volume > 3.0):
    mark as imbalanced
    
IF 3+ consecutive levels are imbalanced in same direction:
  flag as stacked imbalance (high-probability support/resistance)
`

#### Directional Bias: Delta + Imbalance Combination

Sierra Chart combines:

1. **Delta** — Net buying vs. selling pressure
2. **Imbalance stacking** — Structural support/resistance
3. **Volume profile** — Where activity concentrated

**Algorithm**:
`
IF Delta > 0 AND Imbalance_Stack_Direction = BUY AND Volume_Concentrated_Below:
  → LONG bias (high confidence)
ELSE IF Delta < 0 AND Imbalance_Stack_Direction = SELL AND Volume_Concentrated_Above:
  → SHORT bias (high confidence)
ELSE:
  → NEUTRAL
`

**Key Insight**: Sierra stores **historical bid/ask data**, enabling replay analysis. Traders can backtest imbalance patterns in replay mode before trading live.

---

### 4. Jigsaw Daytradr — Absorption Detection + Tape Reconstruction

**Source**: [NexusFi Academy: Jigsaw Daytradr](https://nexusfi.com/a/platforms/jigsaw-daytradr) (Apr 2026) + [Jigsaw Trading Blog](https://www.jigsawtrading.com/blog/get-your-trading-to-an-institutional-level-with-big-discounts-and-even-a-payment-plan/) (May 2026)

#### Clutter Reduction: Tape Reconstruction + Summary Aggregation

Jigsaw's **reconstructed tape** aggregates individual trades into meaningful events:

`
Raw tape (cluttered):
  BUY 100 @ 18,440
  BUY 150 @ 18,440
  BUY 200 @ 18,440
  BUY 350 @ 18,440
  
Reconstructed tape (clear):
  BUY 800 @ 18,440 (buy aggressor)
`

**Summary Tape** compresses further:
`
Aggregated by price + time:
  18,440: 5,000 buy contracts vs. 800 sell contracts
  → Imbalance = 6.25:1 (absorption signal)
`

#### Absorption Detection Algorithm

Jigsaw's **Auction Vista** heatmap identifies absorption by watching:

1. **Order density at level** — Are large orders sitting passively?
2. **Order pull rate** — Are orders being canceled as price approaches?
3. **Velocity of aggression** — Is one side stepping through multiple levels?

**Absorption Signature**:
`
IF (large_passive_orders_at_level AND aggressive_flow_hitting_them AND price_not_moving):
  → Absorption detected
  → Defending side is absorbing aggression
  → Reversal likely when defender exhausts
`

**Exhaustion Signature**:
`
IF (aggressive_flow_declining AND volume_z_score_elevated AND nti_near_zero):
  → Both sides burning fuel equally
  → Standoff ending soon
  → Reversal imminent
`

#### Directional Bias: Absorption Asymmetry

`
Bid_Absorption = SUM(passive_bid_orders_filled_by_aggressive_sellers)
Ask_Absorption = SUM(passive_ask_orders_filled_by_aggressive_buyers)

IF Bid_Absorption > Ask_Absorption:
  → Buyers defending bids (absorbing sell pressure)
  → LONG bias
ELSE IF Ask_Absorption > Bid_Absorption:
  → Sellers defending asks (absorbing buy pressure)
  → SHORT bias
ELSE:
  → NEUTRAL (balanced absorption)
`

---

### 5. Exocharts — Order Flow Imbalance Visualization

**Source**: [Exocharts Platform](https://exocharts.com) (referenced in NexusFi, Apr 2026)

#### Clutter Reduction: Imbalance Coloring + Threshold Filtering

Exocharts visualizes **order flow imbalance** by coloring footprint cells:

- **Green cells** = Ask volume > Bid volume (bullish imbalance)
- **Red cells** = Bid volume > Ask volume (bearish imbalance)
- **Gray cells** = Balanced (no imbalance)

**Threshold**: Only color cells where imbalance exceeds **2:1 ratio** (configurable).

#### Directional Bias: Imbalance Dominance

`
Bullish_Imbalance_Count = COUNT(cells where ask_volume > 2 × bid_volume)
Bearish_Imbalance_Count = COUNT(cells where bid_volume > 2 × ask_volume)

IF Bullish_Imbalance_Count > Bearish_Imbalance_Count:
  → LONG bias
ELSE IF Bearish_Imbalance_Count > Bullish_Imbalance_Count:
  → SHORT bias
ELSE:
  → NEUTRAL
`

---

## Clutter Reduction Techniques Summary

| Technique | Platform | Implementation |
|-----------|----------|-----------------|
| **Threshold Filtering** | ATAS, Sierra, Exocharts | Only display signals exceeding 3:1 ratio or 90th percentile |
| **Decay/Half-Life** | Bookmap | Signal strength decays exponentially; fades after 60-120s |
| **Confluence Gating** | ATAS, Sierra, Jigsaw | Require 2+ signals (delta + volume + imbalance) before display |
| **Aggregation/Summary** | Jigsaw, Bookmap | Show summary metrics instead of raw data |
| **Stacking Detection** | Sierra | Only flag imbalances when 3+ consecutive levels align |
| **Proximity Weighting** | Bookmap | Weight orders by distance from BBO |
| **Divergence Detection** | ATAS | Alert when Session Delta diverges from price (warning) |

---

## Directional Bias Box Algorithm Recommendation for DEEP6 V8

### Core Algorithm

`python
def calculate_directional_bias(absorption_signals, exhaustion_signals, delta, volume):
    "
    Determine LONG/SHORT/NEUTRAL bias from absorption + exhaustion asymmetry.
    
    Inputs:
    - absorption_signals: dict with 'bid_absorption' and 'ask_absorption' (0-100 scale)
    - exhaustion_signals: dict with 'bid_exhaustion' and 'ask_exhaustion' (0-100 scale)
    - delta: net buying pressure (-100 to +100)
    - volume: total bar volume
    
    Returns:
    - bias: 'LONG' | 'SHORT' | 'NEUTRAL'
    - confidence: 0-100 (higher = more confident)
    "
    
    # Step 1: Absorption asymmetry
    absorption_imbalance = (
        absorption_signals['bid_absorption'] - 
        absorption_signals['ask_absorption']
    )
    
    # Step 2: Exhaustion asymmetry
    exhaustion_imbalance = (
        exhaustion_signals['bid_exhaustion'] - 
        exhaustion_signals['ask_exhaustion']
    )
    
    # Step 3: Confluence scoring
    # Absorption + Exhaustion must align for high confidence
    
    if absorption_imbalance > 20 and exhaustion_imbalance > 20:
        # Buyers defending bids + sellers exhausting
        bias = 'LONG'
        confidence = min(100, 50 + abs(absorption_imbalance) + abs(exhaustion_imbalance))
    
    elif absorption_imbalance < -20 and exhaustion_imbalance < -20:
        # Sellers defending asks + buyers exhausting
        bias = 'SHORT'
        confidence = min(100, 50 + abs(absorption_imbalance) + abs(exhaustion_imbalance))
    
    elif abs(absorption_imbalance) < 10 and abs(exhaustion_imbalance) < 10:
        # Balanced on both sides
        bias = 'NEUTRAL'
        confidence = 30
    
    else:
        # Conflicting signals (one side absorbing, other exhausting)
        bias = 'NEUTRAL'
        confidence = 40
    
    return bias, confidence
`

### Threshold Recommendations

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Absorption Threshold** | >20 (on 0-100 scale) | Requires meaningful passive order absorption |
| **Exhaustion Threshold** | >20 (on 0-100 scale) | Requires clear volume/participation decline |
| **Confluence Gate** | Both signals must align | Prevents false signals from single-sided activity |
| **Confidence Decay** | 50% per 60 seconds | Older signals fade; prevents stale labels |
| **Minimum Volume** | 90th percentile | Only flag on high-activity bars |

---

## Visual Design Rules for Bias Box

### Color Coding

| Bias | Color | Hex | Rationale |
|------|-------|-----|-----------|
| **LONG** | Green | #00AA00 | Bullish, buyer control |
| **SHORT** | Red | #DD0000 | Bearish, seller control |
| **NEUTRAL** | Gray | #888888 | No clear directional control |

### Label Density Rules

1. **Only display bias box on bars with high confidence (>60%)**
   - Prevents label clutter on weak signals
   - Matches ATAS Cluster Statistic philosophy

2. **Fade labels after 60-120 seconds**
   - Implement half-life decay (Bookmap model)
   - Prevents accumulation of stale labels

3. **Stack labels vertically, not horizontally**
   - Reduces visual width footprint
   - Easier to scan multiple bars

4. **Use box size to indicate confidence**
   - Larger box = higher confidence (60-100%)
   - Smaller box = lower confidence (40-60%)
   - No box = below threshold (<40%)

### Example Layout

`
Bar 1 (High Confidence LONG):
  ┌─────────────────┐
  │      LONG       │  ← Large green box, confidence 85%
  │    (85%)        │
  └─────────────────┘

Bar 2 (Medium Confidence SHORT):
  ┌──────────┐
  │  SHORT   │      ← Medium red box, confidence 65%
  │  (65%)   │
  └──────────┘

Bar 3 (Low Confidence NEUTRAL):
  ┌────┐
  │ ⚪ │            ← Small gray dot, confidence 45%
  └────┘

Bar 4 (Below Threshold):
  (no label)         ← No box, confidence <40%
`

---

## Implementation Checklist for DEEP6 V8

- [ ] **Absorption Signal Engine**
  - Detect passive order absorption at bid/ask
  - Track absorption strength over time
  - Implement half-life decay (60-120s)

- [ ] **Exhaustion Signal Engine**
  - Detect volume/participation decline
  - Track exhaustion strength over time
  - Implement half-life decay

- [ ] **Confluence Gate**
  - Require both absorption + exhaustion to align
  - Set minimum thresholds (>20 on 0-100 scale)
  - Calculate confidence score (0-100)

- [ ] **Directional Bias Determination**
  - Absorption asymmetry (bid vs. ask)
  - Exhaustion asymmetry (bid vs. ask)
  - Output: LONG | SHORT | NEUTRAL + confidence

- [ ] **Visual Rendering**
  - Green box for LONG, Red for SHORT, Gray for NEUTRAL
  - Box size proportional to confidence
  - Fade labels after 60-120s
  - Only display boxes with confidence >60%

- [ ] **Backtesting Validation**
  - Test on 2-4 weeks of NQ 5-min replay data
  - Measure false signal rate (target <20%)
  - Measure win rate on absorption+exhaustion setups (target >55%)

---

## Key Takeaways

1. **Clutter is solved by confluence, not by showing more data**
   - ATAS: Cluster Statistic dashboard (summary, not raw)
   - Bookmap: Multi-algorithm stacking (threshold + decay)
   - Sierra: Imbalance highlighting + stacking detection
   - Jigsaw: Tape reconstruction + absorption detection

2. **Directional bias comes from absorption + exhaustion asymmetry**
   - LONG = Buyers absorbing + Sellers exhausting
   - SHORT = Sellers absorbing + Buyers exhausting
   - NEUTRAL = Balanced or conflicting signals

3. **Threshold-based filtering is essential**
   - 3:1 imbalance ratio (300%) is industry standard for NQ
   - 90th percentile volume filtering prevents noise
   - Confidence gates (>60%) prevent false labels

4. **Decay/half-life prevents label accumulation**
   - 60-120 second half-life is optimal
   - Older signals fade naturally
   - No need for manual label cleanup

5. **Confluence gating is the highest-alpha filter**
   - Single signals (delta alone, volume alone) are noisy
   - Absorption + Exhaustion alignment = high-probability setup
   - Require 2+ signals before displaying label

---

## Sources

| Source | URL | Confidence | Date |
|--------|-----|-----------|------|
| ATAS: 7 Footprint Analysis Methods | https://atas.net/blog/7-footprint-analysis-methods-with-cluster-statistic/ | HIGH | Feb 2026 |
| ATAS: Cluster Statistic Basics | https://atas.net/blog/cluster-statistic-basics/ | HIGH | Feb 2026 |
| Bookmap: Market Pulse Documentation | https://bookmap.com/knowledgebase/docs/Addons-Market-Pulse | HIGH | Jan 2026 |
| Bookmap: Tradermap Pro Filters | https://bookmap.com/knowledgebase/docs/Addons-Tradermap-Pro | HIGH | Jan 2026 |
| Bookmap: Heatmap Trading Guide | https://blog.bookmap.com/blog/heatmap-in-trading-the-complete-guide-to-market-depth-visualization/ | HIGH | Feb 2026 |
| NexusFi: Footprint Charts for Futures | https://nexusfi.com/a/platforms/footprint-charts | HIGH | Apr 2026 |
| NexusFi: Jigsaw Daytradr | https://nexusfi.com/a/platforms/jigsaw-daytradr | HIGH | Apr 2026 |
| Jigsaw Trading: Institutional Education | https://www.jigsawtrading.com/blog/get-your-trading-to-an-institutional-level-with-big-discounts-and-even-a-payment-plan/ | HIGH | May 2026 |
| Anomiq: Absorption & Exhaustion Examples | https://anomiq.io/blog/absorption-exhaustion-examples/ | HIGH | Mar 2026 |
| Kalena: Absorption Trading Crypto | https://blog.kalena.ai/absorption-trading-crypto-the-complete-pattern-taxonomy-9-order-book-signals-that-separate-institutional-accumulation-from-retail-noise | HIGH | Apr 2026 |
| Order Flow Trading Guide | https://proptradingvibes.com/blog/order-flow-trading-guide | HIGH | Mar 2026 |
| Bookmap Tips & Tricks 2026 | https://tradingtoolshub.com/blog/bookmap-tips-and-tricks/ | HIGH | Apr 2026 |

---

## Next Steps

1. **Implement absorption detection** in DEEP6 signal engine
2. **Implement exhaustion detection** in DEEP6 signal engine
3. **Test confluence gating** on historical NQ data
4. **Validate directional bias accuracy** against manual chart review
5. **Implement visual rendering** with decay/half-life
6. **Backtest on 4-week NQ replay** before live deployment
