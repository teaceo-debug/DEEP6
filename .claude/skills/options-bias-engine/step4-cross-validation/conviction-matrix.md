# Conviction Matrix — Master Cross-Validation Framework

## Overview

The conviction matrix is the synthesis layer of the Options Bias Engine. Raw signals from four data rivers — FlashAlpha (structure), Massive.com (flow), Unusual Whales (dark pool), and Rithmic MBO (order book) — plus a fifth derived dimension, are scored and combined into a single conviction level that governs position sizing, target selection, and trade management.

No single river is sufficient. The edge comes from alignment. When all five dimensions point the same direction, the probability of a sustained move is materially higher than any individual signal suggests. When they diverge, the correct response is usually to wait.

This document defines exactly how to score each dimension, how to combine scores, and how to adjust for real-time changes in the order book.

---

## The Five Input Dimensions

### Dimension 1: STRUCTURE (FlashAlpha)

Structure is the slowest-moving dimension. GEX, DEX, VEX, and CHEX are computed from open interest, which changes as positions are opened and closed throughout the day. Structure tells you the mechanical forces that dealers must exert on the market to maintain their hedges.

**Inputs:**
- GEX (Gamma Exposure): Total dealer gamma in dollar terms. Positive = dealers buy dips and sell rips (stabilizing). Negative = dealers sell dips and buy rips (destabilizing).
- GEX Flip Level: The price at which aggregate dealer gamma crosses zero. The single most important structural level.
- Call Wall: The strike with the highest positive GEX concentration. Acts as a ceiling in positive gamma.
- Put Wall: The strike with the highest negative GEX concentration (or highest put OI). Acts as a floor in positive gamma.
- DEX (Delta Exposure): Net dealer delta. Negative DEX means dealers are net short delta and must buy the underlying to hedge. Positive DEX means dealers are net long delta and must sell.
- VEX (Vanna Exposure): Sensitivity of dealer delta to changes in implied volatility. Positive VEX + falling VIX = dealers must buy. Negative VEX + rising VIX = dealers must sell.
- CHEX (Charm Exposure): Sensitivity of dealer delta to time decay. Drives the mechanical end-of-day flows.

**Scoring STRUCTURE as BULLISH (aligned bullish):**
- GEX is positive (above zero in dollar terms)
- Current NQ price is above the gamma flip level
- Price is between the flip and the call wall (not yet at the ceiling)
- DEX is negative (dealers need to buy to hedge)
- VEX is positive AND VIX is declining or flat
- CHEX is positive (time decay will force dealer buying into close)

All six conditions = strong bullish structure. Four or five = moderate. Fewer than four = structure is not aligned bullish.

**Scoring STRUCTURE as BEARISH (aligned bearish):**
- GEX is negative (below zero)
- Current NQ price is below the gamma flip level
- DEX is positive (dealers need to sell to hedge)
- VEX is negative AND VIX is rising or elevated
- CHEX is negative (time decay forces dealer selling into close)

**Scoring STRUCTURE as NEUTRAL:**
- Price is within 0.15% of the gamma flip (too close to call)
- GEX is near zero (less than $200M absolute value for NQ proxy)
- DEX is near zero (no strong directional hedging pressure)

**Quantitative thresholds for NQ (via QQQ/NDX proxy, ~85.7x ratio):**
- GEX > $500M positive: Strong positive gamma. Regime A or B.
- GEX $100M to $500M positive: Moderate positive gamma. Regime B or C.
- GEX -$100M to +$100M: Transition zone. Regime C or D.
- GEX < -$100M: Negative gamma. Regime D or E.
- Flip distance: If price is within 0.15% of flip, treat as neutral. If 0.3%+ away, treat as directional.

---

### Dimension 2: FLOW (Massive.com)

Flow is the fastest-moving dimension after the DOM. It captures what participants are actually doing with options right now, not what they did yesterday. Flow can shift within minutes.

**Inputs:**
- Net premium: Total call premium minus total put premium traded in the session. Positive = net call buying. Negative = net put buying.
- Sweeps: Market orders that sweep multiple strikes or exchanges, indicating urgency. Bullish sweeps = call sweeps. Bearish sweeps = put sweeps.
- Blocks: Large single-exchange prints, often institutional. Bullish blocks = call blocks. Bearish blocks = put blocks.
- Unusual trades: Volume significantly above open interest or average daily volume. Flags potential informed trading.
- Bid/ask side: Whether premium is being paid at the ask (aggressive buying) or at the bid (aggressive selling). At-ask = conviction. At-bid = distribution or closing.

**Scoring FLOW as BULLISH:**
- Net call premium is positive AND growing (not just a morning spike that faded)
- Call sweeps outnumber put sweeps by at least 2:1 in the last 30 minutes
- Call blocks present, especially in near-term expiries (0DTE, 1DTE)
- Premium being paid at the ask (buyers are aggressive, not waiting)
- Unusual call activity flagged by Massive

**Scoring FLOW as BEARISH:**
- Net put premium is positive AND growing
- Put sweeps outnumber call sweeps by at least 2:1 in the last 30 minutes
- Put blocks present in near-term expiries
- Premium being paid at the ask for puts (aggressive put buying)
- Unusual put activity flagged

**Scoring FLOW as NEUTRAL:**
- Net premium near zero (within $5M for QQQ/NDX)
- Sweeps roughly balanced (less than 2:1 ratio)
- No unusual activity flagged
- Mixed bid/ask side (some at ask, some at bid)

**Critical nuance:** Always check whether call buying is OPENING or CLOSING. A surge in call volume at the bid is not bullish — it's call sellers closing longs (distribution). Massive should show the open/close flag. If unavailable, use the bid/ask side as a proxy: at-ask = opening (bullish), at-bid = closing (bearish or neutral).

**Flow freshness:** Flow from more than 90 minutes ago carries less weight. A bullish flow reading from 10 AM that hasn't been reinforced by 1 PM is stale. Weight recent flow (last 30 minutes) at 2x versus older flow.

---

### Dimension 3: DARK (Unusual Whales)

Dark pool data captures institutional activity that bypasses the lit exchange. Dark pool prints are large, often block-sized, and represent informed or institutional positioning. The direction of dark pool flow is one of the highest-quality signals in the system.

**Inputs:**
- Dark pool direction: Net buying vs. net selling in dark pools for QQQ/NDX
- Net dark premium: Dollar value of dark pool call activity minus put activity
- Institutional sweep alerts: Large sweeps flagged by UW as institutional in origin
- Dark pool volume relative to lit volume: High dark/lit ratio suggests institutional activity is elevated

**Scoring DARK as BULLISH:**
- Dark pool net direction is buying (more dark pool buys than sells)
- Net dark premium is positive (dark pool call activity exceeds put activity)
- Institutional sweep alerts are bullish (call sweeps flagged as institutional)
- Dark/lit volume ratio is elevated (>30% dark pool share), suggesting institutional engagement

**Scoring DARK as BEARISH:**
- Dark pool net direction is selling
- Net dark premium is negative
- Institutional sweep alerts are bearish
- Dark/lit ratio elevated with bearish direction

**Scoring DARK as NEUTRAL:**
- Dark pool direction is mixed or unclear
- Net dark premium near zero
- No institutional sweep alerts
- Dark/lit ratio is normal (15-25%)

**Reporting delay:** UW dark pool data has a reporting lag of 5-15 minutes. When making real-time decisions, account for this. A dark pool signal that just appeared may reflect activity from 10 minutes ago. This matters most in fast-moving markets.

**Distinguishing hedging from directional:** Large put buying in dark pools can be portfolio hedging (bearish signal) or protective hedging by a fund that is actually bullish on the underlying. The key discriminator is strike selection and expiry. ATM or near-ATM, short-dated puts in dark pools = directional bearish. Far OTM, long-dated puts = hedging (less bearish signal).

---

### Dimension 4: DOM (Rithmic MBO)

The order book is the ground truth of what is happening right now. It's the only dimension that operates in real time with zero lag. It shows the actual supply and demand at every price level.

**Inputs:**
- Depth asymmetry: Total bid depth (in contracts) vs. total ask depth within 10 ticks of current price
- Aggression imbalance: Market buys vs. market sells in the last 60 seconds
- Level defense: Whether large resting orders at key levels reload after being hit
- Iceberg detection: Hidden large orders that reveal themselves as small visible quantities that continuously replenish
- Spoof detection: Large orders that pull before being hit (fake liquidity)
- Absorption: Price approaching a level but not advancing despite significant volume (the level is absorbing the flow)

**Scoring DOM as BULLISH:**
- Bid depth > ask depth by at least 1.5:1 within 10 ticks of current price
- Market buys > market sells by at least 1.5:1 in the last 60 seconds
- Icebergs detected on the bid side (hidden buyers)
- Large resting bids that reload after being hit (genuine support)
- Absorption on the ask side (sellers being absorbed, price not dropping)
- No significant spoofing on the bid side

**Scoring DOM as BEARISH:**
- Ask depth > bid depth by at least 1.5:1
- Market sells > market buys by at least 1.5:1
- Icebergs on the ask side (hidden sellers)
- Large resting offers that reload after being hit
- Absorption on the bid side (buyers being absorbed, price not rising)
- No significant spoofing on the ask side

**Scoring DOM as NEUTRAL:**
- Depth ratio between 0.8:1 and 1.2:1 (roughly balanced)
- Aggression imbalance less than 1.3:1
- No clear icebergs or absorption
- Mixed signals (bids thick but market sells dominant, etc.)

**DOM is the fastest signal.** It can flip from bullish to bearish in 30 seconds. Use DOM as the final confirmation before entry, not as a primary directional signal. DOM confirms or denies what the other dimensions are saying.

---

### Dimension 5: DERIVED (Computed)

Derived signals are computed from the other four rivers and from statistical properties of the options market. They provide context that no single river captures alone.

**Inputs:**
- Expected move position: Where is current price relative to the daily expected move high and low? (EM derived from ATM straddle price)
- Max pain pull: The strike at which total option seller profit is maximized. Price tends to gravitate toward max pain as expiry approaches, especially in the last 2 hours.
- 0DTE wall positions: The call and put walls for today's expiry specifically. These are the most active and most defended levels on any given day.
- IV rank/percentile: Where current IV sits relative to the past year. High IV rank = options expensive = sellers have edge. Low IV rank = options cheap = buyers have edge.
- Put/call ratio trend: Is the P/C ratio rising (bearish sentiment building) or falling (bullish sentiment building)?

**Scoring DERIVED as BULLISH:**
- Current price is below the expected move high (room to run upward)
- Max pain is above current price (gravitational pull upward into close)
- 0DTE call wall is above current price and lifting (not being tested)
- IV rank is moderate (30-60%): not so high that calls are overpriced, not so low that there's no premium to drive flows
- P/C ratio is declining (sentiment improving)

**Scoring DERIVED as BEARISH:**
- Current price is above the expected move low (room to fall)
- Max pain is below current price (gravitational pull downward)
- 0DTE put wall is below current price and dropping
- IV rank is elevated (>60%): put premium is expensive, put buyers have conviction
- P/C ratio is rising

**Scoring DERIVED as NEUTRAL:**
- Price is near max pain (within 0.2%)
- Price is near the center of the expected move range
- 0DTE walls are equidistant from current price
- IV rank is in the 40-60% range with no clear trend

---

## Conviction Scoring Matrix

Each dimension is scored as: BULLISH (+1), NEUTRAL (0), or BEARISH (-1).

Sum the five scores. The result ranges from -5 (maximum bearish conviction) to +5 (maximum bullish conviction).

### Conviction Levels

**Score +4 or +5: MAXIMUM BULLISH CONVICTION**
- All or nearly all dimensions aligned bullish
- Full position size (100% of maximum allowed)
- Widest target (next major structural level)
- Highest confidence: hold through normal noise
- Re-evaluate every 15-30 minutes in positive gamma, every 5-10 minutes in negative gamma

**Score +3: HIGH BULLISH CONVICTION**
- Strong alignment with one neutral or one mild disagreement
- 75% of maximum position size
- Standard target (HVL or mid-range)
- Re-evaluate every 10-15 minutes

**Score +2: MODERATE BULLISH CONVICTION**
- Majority aligned but meaningful disagreement present
- 50% of maximum position size
- Tight target (nearest structural level)
- Quick to exit if any dimension flips
- Re-evaluate every 5-10 minutes

**Score +1: LOW BULLISH CONVICTION**
- Slight edge but significant uncertainty
- NO TRADE in most cases
- Exception: textbook setup in perfect regime (Regime A or B) with DOM confirming = 25% position size maximum
- Treat as a scalp only, not a swing

**Score 0: NO CONVICTION**
- Balanced or contradictory signals
- Absolutely no trade
- Wait for alignment to develop

**Score -1: LOW BEARISH CONVICTION**
- Same rules as +1, inverted

**Score -2: MODERATE BEARISH CONVICTION**
- Same rules as +2, inverted

**Score -3: HIGH BEARISH CONVICTION**
- Same rules as +3, inverted

**Score -4 or -5: MAXIMUM BEARISH CONVICTION**
- Same rules as +4/+5, inverted

---

## Conviction Multipliers

Certain order book events modify the raw conviction score. These are applied AFTER the initial five-dimension scoring.

### Positive Multipliers (increase conviction by one level)

**Iceberg at GEX level confirming direction:**
An iceberg order detected at a GEX wall (call wall, put wall, or flip level) that is on the same side as your trade direction. Example: you're long, price is at the put wall, and an iceberg is detected on the bid at that level. This means a large participant is actively defending the level. Conviction +1.

**Absorption at GEX level:**
Price approaches a GEX level with significant volume but the level holds. The book is absorbing the flow without yielding. This is the strongest confirmation that the level is real and defended. Conviction +1.

**Sweep cascade confirming direction:**
Three or more sweeps in the same direction within a 5-minute window, with escalating size. This indicates urgent, informed buying or selling. If the cascade direction matches your trade, Conviction +1.

**Dark pool confirmation after flow signal:**
Flow (Massive) shows a directional signal, and within 15 minutes, dark pool (UW) confirms the same direction. The institutional confirmation of the visible flow is a strong signal. Conviction +1.

### Negative Multipliers (decrease conviction by one level)

**Spoof at GEX level opposing your trade:**
A large order appears at a GEX level on the opposite side of your trade, then pulls before being hit. This is a spoof — fake liquidity designed to move price. If it's opposing your trade, it means someone is trying to push price toward your stop. Conviction -1.

**Book depletion at wall with no reload:**
A GEX wall is being hit and the resting orders are NOT reloading. The wall is being consumed. This shifts the setup from a bounce trade to a potential break trade. If you're in a bounce trade, Conviction -1 (consider exiting).

**Dark pool opposing visible flow:**
Flow shows bullish, dark pool shows bearish (or vice versa). This is the distribution/accumulation divergence pattern. It doesn't necessarily mean your trade is wrong, but it means the smart money disagrees with the visible flow. Conviction -1.

**Sweep cascade opposing your trade:**
Three or more sweeps in the opposite direction of your trade within 5 minutes. Someone is urgently positioning against you. Conviction -1 (consider exiting or tightening stop).

---

## Conviction Half-Life and Re-Evaluation Schedule

Conviction is not static. The five dimensions change at different speeds, and a conviction score that was valid 20 minutes ago may be stale now.

### Dimension Change Speeds (fastest to slowest)

1. DOM (Rithmic MBO): Changes second-to-second. Re-check before every entry and every 60 seconds while in a trade.
2. FLOW (Massive.com): Changes minute-to-minute. Re-check every 5-10 minutes.
3. DARK (Unusual Whales): Changes every 5-15 minutes (reporting lag). Re-check every 15 minutes.
4. DERIVED: Changes as price moves and time passes. Re-check every 15-30 minutes.
5. STRUCTURE (FlashAlpha): Changes as OI shifts. Slowest. Re-check every 30-60 minutes or after major news.

### Re-Evaluation Schedule by Regime

**Positive Gamma (Regimes A, B, C):**
- Full conviction re-evaluation: every 15-30 minutes
- DOM check: every 60 seconds while in trade
- Rationale: Levels hold longer in positive gamma. Structure is more stable. Less urgency to re-evaluate.

**Negative Gamma (Regimes D, E):**
- Full conviction re-evaluation: every 5-10 minutes
- DOM check: every 30 seconds while in trade
- Rationale: In negative gamma, moves accelerate and levels break. What was true 10 minutes ago may be completely wrong now. Faster re-evaluation is essential.

### The Conviction Half-Life Rule

After entering a trade, the conviction score that justified the entry begins to decay. The half-life depends on regime:

- Regime A (strong positive gamma): Half-life ~30 minutes. A 5/5 conviction trade remains high-conviction for about 30 minutes without re-evaluation.
- Regime B/C (moderate positive gamma): Half-life ~20 minutes.
- Regime D (transitional/negative gamma): Half-life ~10 minutes.
- Regime E (strong negative gamma): Half-life ~5 minutes.

After one half-life, re-evaluate all five dimensions. If conviction has dropped by two or more levels, consider reducing position size or exiting.

---

## Practical Scoring Workflow

### Step 1: Score each dimension (takes 2-3 minutes)

Open FlashAlpha. Record: GEX sign, flip distance, DEX sign, VEX sign, CHEX sign. Score STRUCTURE.

Open Massive.com. Record: net premium, sweep ratio (last 30 min), block direction, bid/ask side. Score FLOW.

Open Unusual Whales. Record: dark pool direction, net dark premium, institutional alerts. Score DARK.

Open Rithmic DOM. Record: depth ratio, aggression imbalance, icebergs, absorption. Score DOM.

Compute DERIVED: EM position, max pain distance, 0DTE wall positions. Score DERIVED.

### Step 2: Sum scores and determine conviction level

Add the five scores. Apply any multipliers from order book events. Determine conviction level.

### Step 3: Apply conviction to position sizing

| Conviction | Position Size | Target | Stop Tightness |
|---|---|---|---|
| 5/5 (max) | 100% | Widest (next major level) | Normal |
| 4/5 (high) | 75% | Standard (HVL or mid-range) | Normal |
| 3/5 (moderate) | 50% | Tight (nearest level) | Tight |
| 2/5 (low) | 25% (exception only) | Scalp only | Very tight |
| 1/5 or 0/5 | 0% | No trade | N/A |

### Step 4: Set re-evaluation timer

Based on regime, set a timer for the next full conviction re-evaluation. Do not wait for the timer if the DOM shows a sudden shift — re-evaluate immediately on any significant order book change.

---

## Common Scoring Errors

**Error 1: Treating stale flow as current**
Flow from 90+ minutes ago should be discounted heavily. If the morning had strong call flow but it's now 2 PM and flow has gone neutral, the FLOW dimension is neutral, not bullish.

**Error 2: Ignoring the bid/ask side of flow**
High call volume is not automatically bullish. If calls are trading at the bid, it's selling (distribution). Always check the side.

**Error 3: Conflating dark pool hedging with directional flow**
Far OTM, long-dated put buying in dark pools is hedging, not a bearish directional signal. Check strike and expiry before scoring DARK.

**Error 4: Over-weighting DOM in slow markets**
In low-volume, slow markets, the DOM can show misleading depth. Thin books look asymmetric even when there's no real directional pressure. Weight DOM less when overall volume is below 50% of average.

**Error 5: Not applying the half-life rule**
Entering a trade with 5/5 conviction and then not re-evaluating for 45 minutes in a negative gamma regime. The conviction may have decayed to 2/5 while you weren't looking.

**Error 6: Applying multipliers without confirming the order book event**
Claiming an iceberg is present without actually seeing the replenishing quantity. Icebergs must be confirmed by repeated small fills at the same price with no visible resting quantity. Don't assume.

---

## Integration with Regime Playbooks

The conviction matrix operates within the regime framework defined in step1-regimes/. The regime determines which setups are available and how conviction translates to action.

- **Regime A (strong positive gamma):** Conviction matrix is most reliable. Levels hold. 5/5 conviction trades have the highest historical win rates.
- **Regime B (moderate positive gamma):** Reliable but slightly less so. 4/5 or 5/5 required for full size.
- **Regime C (weak positive gamma / near flip):** Conviction matrix is less reliable because the regime itself is unstable. Require 4/5 minimum. Be ready for regime transition.
- **Regime D (negative gamma, controlled):** Conviction matrix still works but moves are larger. Targets must be wider. Re-evaluate faster.
- **Regime E (negative gamma, crisis):** Conviction matrix is least reliable because the regime is chaotic. Only trade 5/5 conviction setups. Reduce all position sizes by 50% regardless of conviction.

Cross-reference: `step1-regimes/regime-a.md`, `step1-regimes/regime-b.md`, `step1-regimes/regime-c.md`, `step1-regimes/regime-d.md`, `step1-regimes/regime-e.md`
