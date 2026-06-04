# Dark Pool Reading — Institutional Flow from Unusual Whales

## Purpose

Dark pool data is the truth layer beneath the visible options flow. When dark pool and visible flow agree, conviction is maximum. When they disagree, dark pool is almost always the smarter signal. This document covers the mechanics of dark pools, how to read Unusual Whales data, the cross-validation protocol with visible flow, and how dark pool activity at specific options levels changes the interpretation of those levels.

Data sources:
- **Unusual Whales**: Primary dark pool data source. Aggregates FINRA ATS (Alternative Trading System) reports.
- **Massive.com**: Visible flow for cross-validation.
- **FlashAlpha**: GEX context for interpreting dark pool activity at specific levels.
- **Rithmic MBO**: Order book confirmation of dark pool signals.

---

## What Dark Pools Are

### The Mechanics

Dark pools are Alternative Trading Systems (ATS) — private exchanges where large orders execute without displaying on public exchanges. They exist because large institutional orders, if displayed publicly, would move the market against the institution before they could complete their trade.

**The problem dark pools solve**: If a pension fund wants to buy 500,000 shares of QQQ, displaying that order on a public exchange would immediately cause other traders to front-run the order (buy ahead of the pension fund, driving up the price). Dark pools allow the pension fund to execute without revealing their intent.

**How dark pools work**:
1. The institution sends an order to a dark pool (e.g., Goldman Sachs' Sigma X, Morgan Stanley's MS Pool, Liquidnet, IEX).
2. The dark pool matches the order against other dark pool participants (other institutions).
3. The trade executes at a negotiated price (often the midpoint of the public bid/ask).
4. FINRA requires reporting of dark pool trades, but with a delay (typically 10 seconds to several minutes for equity trades).

**Dark pool participants**: Overwhelmingly institutional. Pension funds, hedge funds, mutual funds, sovereign wealth funds, and proprietary trading desks. Retail traders do not have access to dark pools (their orders are routed to public exchanges or internalized by their broker).

### Why Dark Pool Data Is the Truth Layer

Dark pool participants are:
1. **Institutional**: They have research teams, risk management, and significant capital.
2. **Hiding their activity**: They're trading in dark pools specifically to avoid revealing their intent.
3. **Patient**: Dark pool trades are negotiated, not swept. They're not in a hurry.

When dark pool flow and visible flow disagree, the dark pool participant is almost always the smarter money. The visible flow may be retail, algorithmic noise, or hedge adjustments. The dark pool flow is deliberate institutional positioning.

**The key insight**: Dark pool data is delayed institutional truth. Visible flow is real-time noise. When they agree, it's maximum conviction. When they disagree, trust the dark pool.

---

## Reading Dark Pool Direction from Unusual Whales

### Net Premium

Unusual Whales reports net dark pool premium: the dollar value of dark pool buying minus dark pool selling.

```
net_dark_pool_premium = dark_pool_buying_premium - dark_pool_selling_premium
```

**Positive net premium**: Net dark pool buying. Institutions are accumulating. Bullish signal.

**Negative net premium**: Net dark pool selling. Institutions are distributing. Bearish signal.

**Thresholds**:
- |net_premium| < $10M: Noise. No directional signal.
- $10M - $30M: Moderate signal. Note the direction.
- $30M - $100M: Strong signal. Adjust bias.
- $100M+: Maximum signal. High conviction.

### Dark Pool Prints at Specific Prices

Unusual Whales shows individual dark pool prints with price, size, and time. A cluster of prints at a specific price level = institutional accumulation or distribution at that level.

**Cluster definition**:
- 3+ prints within a 10-tick NQ range (2.5 points).
- Or a single print exceeding $50M notional.
- Within a 2-hour window.

**Cluster interpretation**:
- Cluster below current spot: Institutional buying at that level. Support zone.
- Cluster above current spot: Institutional selling at that level. Resistance zone.
- Cluster at current spot: Active institutional positioning. High-stakes level.

### Dark Pool Volume Relative to Total

Unusual Whales reports dark pool volume as a percentage of total volume.

**High dark pool % (> 40% of total volume)**: Institutions are dominant. The market is being driven by institutional activity. Dark pool signals are highly reliable.

**Low dark pool % (< 20% of total volume)**: Retail-dominated day. Dark pool signals are less reliable (smaller sample size). Visible flow may be more representative.

**Normal dark pool % (20-40%)**: Mixed. Both institutional and retail are active. Use dark pool as a confirming signal, not a primary signal.

---

## Dark Pool + Visible Flow Cross-Validation

The most powerful signal in the options bias engine is the divergence between dark pool and visible flow. This divergence reveals what smart money is doing while retail is distracted.

### Scenario 1: Both Bullish (Maximum Conviction Bullish)

**Dark pool**: Net buying. Clusters below spot. High dark pool %.
**Visible flow (Massive.com)**: Call sweeps. Net call premium positive. Escalating size.

**Interpretation**: Maximum conviction bullish. Both institutional (dark pool) and visible (sweeps) flow agree. The move is coming.

**Bias score**: +3 (maximum bullish).

**Trade**: Long NQ. Full size. Tight stop.

### Scenario 2: Both Bearish (Maximum Conviction Bearish)

**Dark pool**: Net selling. Clusters above spot. High dark pool %.
**Visible flow**: Put sweeps. Net put premium positive. Escalating size.

**Interpretation**: Maximum conviction bearish. Both flows agree. The decline is coming.

**Bias score**: -3 (maximum bearish).

**Trade**: Short NQ. Full size. Tight stop.

### Scenario 3: Visible Bullish + Dark Bearish (DISTRIBUTION)

**Dark pool**: Net selling. Clusters above spot.
**Visible flow**: Call buying. Net call premium positive. Retail is bullish.

**Interpretation**: DISTRIBUTION. Smart money is selling into retail buying. This is the most dangerous scenario for longs. The visible bullish flow is retail. The dark pool selling is institutional. The institutions are exiting while retail buys.

**Bias score**: -2 (bearish, despite bullish visible flow).

**Trade**: Do not buy. Prepare for reversal. Short when visible flow dies.

**Why this happens**: Institutions who accumulated earlier are now distributing. They need retail buyers to absorb their selling. They may even be creating the bullish visible flow (by buying calls to create the appearance of bullish flow while selling the underlying in dark pools). This is the "pump and dump" at the institutional level.

### Scenario 4: Visible Bearish + Dark Bullish (ACCUMULATION)

**Dark pool**: Net buying. Clusters below spot.
**Visible flow**: Put buying. Net put premium positive. Retail is bearish.

**Interpretation**: ACCUMULATION. Smart money is buying into retail selling. This is the most dangerous scenario for shorts. The visible bearish flow is retail (or institutional hedging). The dark pool buying is institutional accumulation.

**Bias score**: +2 (bullish, despite bearish visible flow).

**Trade**: Do not short. Prepare for reversal. Long when visible flow dies.

**Why this happens**: Institutions who want to accumulate need retail sellers to provide liquidity. They may even be creating the bearish visible flow (by buying puts to create the appearance of bearish flow while buying the underlying in dark pools). This is the "shake and bake" — shake out weak longs, then accumulate.

### Scenario 5: Visible Bullish + Dark Neutral

**Dark pool**: Neutral. No significant net premium. No clusters.
**Visible flow**: Call sweeps. Net call premium positive.

**Interpretation**: Moderate bullish. The visible flow is genuine but not confirmed by institutional dark pool. The move may be real but lacks institutional backing.

**Bias score**: +1.5 (moderate bullish).

**Trade**: Long NQ. Half size. Normal stop.

### Scenario 6: Visible Bearish + Dark Neutral

**Dark pool**: Neutral.
**Visible flow**: Put sweeps. Net put premium positive.

**Interpretation**: Moderate bearish. Same logic as Scenario 5 but inverted.

**Bias score**: -1.5 (moderate bearish).

**Trade**: Short NQ. Half size. Normal stop.

---

## Dark Pool at Specific Options Levels

Dark pool activity at specific price levels changes the interpretation of those levels. This is the most nuanced application of dark pool data.

### Dark Pool at the Call Wall

**Dark pool SELLING at the call wall**:
- Institutions are selling at the call wall level.
- This confirms the call wall as resistance.
- The wall is being actively defended by institutional sellers.
- **Implication**: Fade the call wall with maximum conviction. The institutions are on your side.

**Dark pool BUYING at the call wall**:
- Institutions are buying at the call wall level.
- This is a BREAK signal. Institutions are buying through the resistance.
- The call wall is about to break.
- **Implication**: Do not fade the call wall. Stand aside or trade the break.

**No dark pool activity at the call wall**:
- Nobody institutional cares about this level.
- The call wall is weaker than it appears.
- **Implication**: Fade with reduced conviction. The wall may hold on the first test but is vulnerable.

### Dark Pool at the Put Wall

**Dark pool BUYING at the put wall**:
- Institutions are buying at the put wall level.
- This confirms the put wall as support.
- The floor is being actively defended by institutional buyers.
- **Implication**: Buy the put wall with maximum conviction. The institutions are on your side.

**Dark pool SELLING at the put wall**:
- Institutions are selling at the put wall level.
- This is a BREAK signal. Institutions are selling through the support.
- The put wall is about to break (trapdoor).
- **Implication**: Do not buy the put wall. Stand aside or trade the break.

**No dark pool activity at the put wall**:
- Nobody institutional cares about this level.
- The put wall is weaker than it appears.
- **Implication**: Buy with reduced conviction. The wall may hold on the first test but is vulnerable.

### Dark Pool at the Gamma Flip

**Dark pool BUYING at the gamma flip**:
- Institutions are buying at the regime boundary.
- They're defending positive gamma.
- The flip is likely to hold.
- **Implication**: The flip will hold. Positive gamma regime is being defended.

**Dark pool SELLING at the gamma flip**:
- Institutions are selling at the regime boundary.
- They're positioning for negative gamma.
- The flip is at risk.
- **Implication**: The flip may break. Prepare for regime transition.

**Dark pool BOTH SIDES at the gamma flip**:
- The regime boundary is contested. Both bulls and bears are active.
- This is the highest-stakes scenario.
- **Implication**: Wait for one side to win. The first side to establish dominance (net dark pool in one direction) wins the regime battle.

### Dark Pool at the HVL

**Dark pool activity at HVL**:
- HVL is the maximum hedging activity level. Dark pool activity here is expected.
- Both buying and selling at HVL is normal (two-sided hedging).
- **Implication**: HVL is confirmed as the magnet. Price will gravitate toward it.

**No dark pool activity at HVL**:
- Unusual. HVL normally has significant dark pool activity.
- May indicate that the HVL has shifted (FlashAlpha data is stale).
- **Implication**: Re-poll FlashAlpha. The HVL may have moved.

### Dark Pool at Expected Move Boundaries

**Dark pool BUYING at EM low**:
- Institutions are buying at the statistical floor.
- They believe the EM low will hold.
- **Implication**: Fade the EM low with high conviction. Institutional support confirmed.

**Dark pool SELLING at EM high**:
- Institutions are selling at the statistical ceiling.
- They believe the EM high will hold.
- **Implication**: Fade the EM high with high conviction. Institutional resistance confirmed.

**No dark pool activity at EM boundaries**:
- The EM boundaries are statistical, not institutional.
- Without dark pool confirmation, the EM is a weaker level.
- **Implication**: Fade with reduced conviction. The EM may not hold.

---

## Timing and Delay Considerations

Dark pool data has a reporting delay. This is critical for understanding how to use it.

### Reporting Delay

FINRA requires dark pool trades to be reported within 10 seconds for equity trades. In practice:
- Equity dark pool trades: 10 seconds to 2 minutes delay.
- Options dark pool trades: Longer delay (options are reported less frequently).
- Unusual Whales aggregates and displays this data with an additional processing delay.

**Total delay**: Expect 30 seconds to 5 minutes between when a dark pool trade executes and when it appears in Unusual Whales.

### Implications for Trading

Dark pool data is NOT real-time. It is a CONFIRMING signal, not a leading signal.

**Correct use**: 
1. Identify a potential trade setup from visible flow (Massive.com) and order book (Rithmic).
2. Check dark pool (Unusual Whales) for confirmation.
3. If dark pool confirms, enter the trade.
4. If dark pool contradicts, reduce conviction or stand aside.

**Incorrect use**:
- Using dark pool as a leading signal (entering before visible flow confirms).
- Expecting dark pool to predict the next 30 seconds of price action.
- Treating dark pool as real-time data.

### The Delayed Truth Advantage

Despite the delay, dark pool data has a significant advantage: it reveals what institutions did, not what they said. Institutions can create misleading visible flow (buying calls while selling the underlying). But dark pool data shows the actual underlying trades.

The delay means you're seeing what institutions did 30 seconds to 5 minutes ago. But institutional positions don't change in 5 minutes. If dark pool shows net buying 5 minutes ago, the institution is still long. The signal is still valid.

---

## Dark Pool Noise and Limitations

Not all dark pool activity is directional. Understanding the noise sources prevents misclassification.

### Algorithmic Rebalancing

Large algorithmic trading systems (index funds, ETFs, risk parity funds) rebalance their portfolios regularly. This creates dark pool activity that is NOT directional.

**Characteristics**:
- Regular pattern (same time every day, same size).
- Both buying and selling in the same session (rebalancing, not accumulating).
- No correlation with price direction.

**Detection**: If dark pool activity appears at the same time every day (e.g., 3:45 PM ET for end-of-day rebalancing), it's algorithmic. Ignore.

### Tax-Loss Harvesting

At year-end (November-December), institutions sell losing positions for tax purposes. This creates dark pool selling that is NOT bearish — it's tax-driven.

**Characteristics**:
- Concentrated in November-December.
- Selling of positions that have declined significantly.
- Often followed by buying of similar (but not identical) positions.

**Detection**: If dark pool selling is concentrated in positions that have declined significantly, and it's November-December, it may be tax-loss harvesting. Reduce bearish conviction.

### Dividend Capture

Some institutions buy stocks before the ex-dividend date and sell after. This creates dark pool buying followed by selling that is NOT directional.

**Characteristics**:
- Buying concentrated before ex-dividend dates.
- Selling concentrated after ex-dividend dates.
- No correlation with price direction.

**Detection**: Check if the dark pool activity coincides with ex-dividend dates for major index components. If so, it may be dividend capture. Ignore.

### Single Large Prints

A single very large dark pool print ($500M+) may be a one-off institutional trade (pension fund rebalancing, merger-related hedging, etc.) rather than a directional bet.

**Detection**: A single print that is 10x larger than the average print size is likely a one-off. Look for CLUSTERS of prints (multiple prints in the same direction) rather than single large prints.

---

## Quantitative Dark Pool Scoring

For the bias engine, dark pool signals are converted to a numeric score:

```python
def compute_dark_pool_score(uw_data, current_spot, time_window_minutes=30):
    """
    Compute a directional bias score from Unusual Whales dark pool data.
    
    uw_data: list of dark pool prints with {time, price, size, direction}
    current_spot: current NQ price
    time_window_minutes: lookback window
    
    Returns: score in range [-3, +3]
    """
    
    # Filter to recent prints
    recent = [p for p in uw_data if p.time > now - time_window_minutes * 60]
    
    if not recent:
        return 0  # No data
    
    # Compute net premium
    buying_premium = sum(p.size * p.price for p in recent if p.direction == 'buy')
    selling_premium = sum(p.size * p.price for p in recent if p.direction == 'sell')
    net_premium = buying_premium - selling_premium
    
    # Compute dark pool % of total volume
    total_volume = get_total_market_volume(time_window_minutes)
    dark_pool_pct = sum(p.size for p in recent) / total_volume if total_volume > 0 else 0
    
    # Compute cluster score
    clusters = detect_clusters(recent, current_spot, tick_range=10)
    cluster_score = sum(c.net_direction for c in clusters)  # +1 for buy cluster, -1 for sell cluster
    
    # Normalize net premium to score
    if abs(net_premium) < 10_000_000:  # < $10M
        premium_score = 0
    elif abs(net_premium) < 30_000_000:  # $10M - $30M
        premium_score = 1 * (1 if net_premium > 0 else -1)
    elif abs(net_premium) < 100_000_000:  # $30M - $100M
        premium_score = 2 * (1 if net_premium > 0 else -1)
    else:  # > $100M
        premium_score = 3 * (1 if net_premium > 0 else -1)
    
    # Dark pool % multiplier
    if dark_pool_pct > 0.40:
        dp_multiplier = 1.0  # High institutional activity
    elif dark_pool_pct > 0.20:
        dp_multiplier = 0.7  # Normal
    else:
        dp_multiplier = 0.4  # Low institutional activity
    
    # Combine scores
    raw_score = (premium_score * 0.6 + cluster_score * 0.4) * dp_multiplier
    
    # Clamp to [-3, +3]
    return max(-3, min(3, raw_score))
```

---

## Dark Pool Monitoring Protocol

### At Session Open (9:30 AM ET)

1. Check Unusual Whales for overnight dark pool activity.
2. Note any clusters that formed overnight (institutional positioning).
3. Compute net dark pool premium for the last 12 hours.
4. Set the dark pool baseline for the session.

### Every 15 Minutes During Session

1. Check Unusual Whales for new dark pool prints.
2. Update net dark pool premium (rolling 30-minute window).
3. Check for new clusters at key levels (call wall, put wall, gamma flip, HVL).
4. Update dark pool score.

### At Key Level Tests

When price approaches a key level (call wall, put wall, gamma flip):
1. Immediately check Unusual Whales for dark pool activity at that level.
2. Dark pool buying at put wall = wall holds. Dark pool selling at put wall = trapdoor.
3. Dark pool selling at call wall = wall holds. Dark pool buying at call wall = break incoming.
4. This check should happen within 30 seconds of price approaching the level.

### At Flow Divergence

When visible flow (Massive.com) and dark pool (Unusual Whales) diverge:
1. Classify the divergence (Scenario 3 or 4 from above).
2. Adjust bias toward the dark pool direction.
3. Reduce position size (divergence = uncertainty).
4. Wait for the divergence to resolve before adding size.

---

## Cross-Reference

- For flow state classification: `flow-interpretation.md`
- For sweep analysis: `sweep-analysis.md`
- For opening vs closing: `opening-vs-closing.md`
- For expiry intent: `expiry-intent.md`
- For level confirmation: `../step2-levels/level-hierarchy.md`
- For wall defense confirmation: `../step2-levels/wall-dynamics.md`
- For gamma flip confirmation: `../step2-levels/gamma-flip-mechanics.md`
- For regime definitions: `../step1-regimes/`
