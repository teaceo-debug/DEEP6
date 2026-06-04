# Setup 7: Sweep Cascade

## Overview

The Sweep Cascade is the urgency signal. When three or more sweeps occur in the same direction within a 5-minute window, with escalating size, someone needs exposure URGENTLY and at ANY price. They're not waiting for a better fill. They're not using limit orders. They're sweeping the book — hitting every available offer (for calls) or bid (for puts) across multiple strikes and exchanges simultaneously.

This is the strongest urgency signal in the options market. It means an informed participant has information (or a strong conviction) that requires immediate positioning. The sweep cascade is the market's way of screaming that something is happening.

The setup does NOT enter on the sweep itself. The sweep has already moved the market. Entering on the sweep means buying the top or selling the bottom of the initial spike. The edge is in waiting for the FIRST PULLBACK after the initial sweep impact — 1 to 3 bars — and entering on the pullback. If no pullback occurs, the opportunity has passed.

The most important risk in this setup: the sweep may be a HEDGE, not a directional bet. A fund buying 20,000 OTM puts to protect a $2B long portfolio looks exactly like an aggressive bearish sweep. But it's defensive, not directional. The dark pool check is the primary filter for this risk.

---

## 1. Setup Name and Overview

**Name:** Sweep Cascade (Urgent Flow Continuation)
**Type:** Momentum continuation after urgent options flow
**Frequency:** 2-5 times per week (clear cascades); 1-2 times per week (high-conviction cascades)
**Best variant:** Call sweep cascade with dark pool confirmation in Regime B or C (bullish urgency with institutional backing)
**Worst variant:** Put sweep cascade in Regime E without dark pool confirmation (may be hedging, not directional)

The setup enters on the first pullback after a sweep cascade, trading the continuation in the direction of the sweeps.

---

## 2. Regime Requirements

**Regime A (strong positive gamma):**
- Sweep cascades are less common (positive gamma dampens moves)
- When they occur, they're significant (the cascade is fighting the mechanical stabilizing force)
- Win rate: 60-65%
- R:R: 1.5:1 to 2.5:1
- The pullback is often clean and well-defined (positive gamma creates a natural pullback)

**Regime B (moderate positive gamma):**
- Sweep cascades are more common
- Win rate: 62-68%
- R:R: 1.5:1 to 2.5:1
- Good regime for sweep cascade trades

**Regime C (weak positive gamma / near flip):**
- Sweep cascades can trigger a flip cross (see gamma-flip-cross.md)
- Win rate: 62-68%
- R:R: 2:1 to 3:1 (if the cascade triggers a flip cross, the move is amplified)

**Regime D (negative gamma, controlled):**
- Sweep cascades are amplified by negative gamma
- Win rate: 60-65%
- R:R: 2:1 to 3:1
- The pullback may be shallower (negative gamma amplifies the initial move)

**Regime E (negative gamma, crisis):**
- Sweep cascades are common but often driven by panic/hedging rather than directional conviction
- Win rate: 55-60%
- R:R: 1.5:1 to 2.5:1
- Require dark pool confirmation. Reduce position size by 50%.

---

## 3. Entry Conditions (All Four Rivers + Derived)

### The Sweep Cascade Trigger

The primary trigger is the sweep cascade itself. All three conditions must be met:

1. **Three or more sweeps in the same direction within 5 minutes.** A single sweep is noise. Two sweeps is a signal. Three or more sweeps is a cascade.

2. **Escalating size.** The sweeps must be getting larger, not smaller. Escalating size indicates increasing urgency — the participant is not satisfied with the exposure from the first sweep and is adding more.
   - Example: First sweep $2M premium, second sweep $3.5M, third sweep $5M. Escalating.
   - Counter-example: First sweep $5M, second sweep $3M, third sweep $1M. Decelerating. Not a cascade.

3. **Concentrated in 0DTE or near-term expiries.** Sweeps in 0DTE or 1-7 DTE options indicate near-term directional conviction. Sweeps in 30+ DTE options may be hedging or longer-term positioning (less urgency signal).

**Quantitative thresholds:**
- Minimum sweep size: $1M premium per sweep (below this, it's retail noise)
- Minimum cascade total: $5M premium across all sweeps in the 5-minute window
- Strong cascade: $10M+ total premium
- Extreme cascade: $20M+ total premium (rare, but creates the largest moves)

### FlashAlpha (Structure) — Supporting
- The cascade direction is consistent with the structural regime (bullish cascade in positive gamma, bearish cascade in negative gamma = aligned)
- The cascade direction is moving toward a structural level (call wall for bullish, put wall for bearish) = the cascade may be trying to break through a wall
- GEX regime: note for amplitude adjustment

### Massive.com (Flow) — Required (the cascade IS the flow signal)
- The cascade is visible on Massive as 3+ sweeps in the same direction within 5 minutes
- The sweeps are escalating in size
- The sweeps are in near-term expiries (0DTE to 7 DTE)
- The sweeps are at the ask (for calls) or at the ask (for puts) — aggressive buying, not selling

**Checking for hedging vs. directional:**
- Directional: Sweeps are ATM or near-ATM (within 1-2% of current price). Near-ATM options have high delta and are most efficient for directional positioning.
- Hedging: Sweeps are far OTM (5-10%+ from current price). Far OTM options are cheap and provide insurance, not directional bets.
- Directional: Sweeps are in short-dated expiries (0DTE to 7 DTE). Short-dated options have high gamma and are most efficient for near-term positioning.
- Hedging: Sweeps are in longer-dated expiries (30+ DTE). Longer-dated options provide sustained protection.

If the sweeps are far OTM AND long-dated, treat as hedging and do not trade.

### Unusual Whales (Dark) — Required
- Dark pool MUST confirm the direction of the cascade
- Bullish cascade: dark pool is buying (institutional conviction that the cascade is directional)
- Bearish cascade: dark pool is selling
- Net dark premium must be in the cascade direction by at least $10M

**If dark pool OPPOSES the cascade:** The sweep may be a HEDGE. A fund buying 20,000 OTM puts to protect a long portfolio looks like an aggressive bearish sweep. But if dark pool is simultaneously buying (the fund is buying the underlying to add to their long), the put sweep is defensive, not directional. Do not trade.

**If dark pool is NEUTRAL:** Reduce position size by 50%. The cascade may be directional but without institutional confirmation, the conviction is lower.

**If dark pool CONFIRMS:** Full position size (within the cascade setup limits).

### Rithmic MBO (DOM) — Required
- The book gets pushed in the cascade direction after the sweeps
- Thin on the break side (no significant resting orders in the cascade direction — the path is clear)
- Thick behind (resting orders on the opposite side of the cascade — support for the move)
- Aggressive market orders in the cascade direction (the sweeps are being followed by market orders)
- No large opposing icebergs (no hidden sellers for bullish cascade, no hidden buyers for bearish cascade)

**The pullback DOM signature:** When price pulls back after the initial sweep impact, the DOM should show:
- Bids appearing at the pullback level (for bullish cascade) — new buyers supporting the level
- Offers appearing at the pullback level (for bearish cascade) — new sellers defending the level
- The pullback is being absorbed (price doesn't continue in the pullback direction)

### Derived — Supporting
- The cascade direction is consistent with the expected move range (bullish cascade: price is below EM high; bearish cascade: price is above EM low)
- Max pain is in the cascade direction
- 0DTE walls are in the cascade direction

---

## 4. Entry Execution

**The cardinal rule: Do NOT enter on the sweep itself.**

The sweep has already moved the market. Entering on the sweep means buying the top or selling the bottom of the initial spike. The spike is not the entry. The pullback is the entry.

**Entry technique:** Wait for the FIRST PULLBACK after the initial sweep impact (1-3 bars on a 1-minute chart). Enter on the pullback.

**Pullback entry specifics:**
- Bullish cascade: Enter long when price pulls back 5-15 ticks from the sweep high. Place a limit order at the pullback level.
- Bearish cascade: Enter short when price pulls back 5-15 ticks from the sweep low. Place a limit order at the pullback level.

**Pullback timing:** The pullback typically occurs within 1-5 bars (1-5 minutes) after the initial sweep impact. If no pullback occurs within 10 minutes, the opportunity has passed. Do not chase.

**If no pullback:** Skip the trade. The market is moving too fast for a safe entry. The next opportunity will come at the next structural level.

**Pullback depth:** The pullback should be 5-15 ticks. A pullback of less than 5 ticks is too shallow (the market is still moving fast, no clean entry). A pullback of more than 20 ticks suggests the sweep impact is being fully retraced (the sweep may have been a hedge or a false signal).

**DOM confirmation at pullback:** When price pulls back to the entry level, the DOM must show defense:
- Bullish cascade pullback: Bids appearing at the pullback level. The pullback is being bought.
- Bearish cascade pullback: Offers appearing at the pullback level. The pullback is being sold.

---

## 5. Stop Loss Rules

**Primary stop:** Sweep impact fully retraced.

- Bullish cascade: Stop is at the price level BEFORE the sweep cascade began (the pre-sweep price). If price retraces the entire sweep impact, the information was priced incorrectly (or the sweep was a hedge).
- Bearish cascade: Stop is at the price level before the sweep cascade began.

**Stop distance:** Typically 15-25 NQ ticks from the entry (depending on the size of the initial sweep impact).

**Why this stop:** If the sweep impact is fully retraced, the market has rejected the information embedded in the sweep. Either the sweep was a hedge (not directional), the information was wrong, or the market has absorbed the sweep and is moving in the opposite direction. In any case, the trade is wrong.

**DOM-based stop:** If the pullback level fails to hold (bids pull for bullish cascade, offers pull for bearish cascade), exit immediately. The pullback is becoming a reversal.

**Regime-specific adjustments:**
- Regime A/B: Stop 15-20 ticks (positive gamma creates cleaner pullbacks)
- Regime C: Stop 15-20 ticks
- Regime D: Stop 20-25 ticks (negative gamma amplifies moves, wider stop needed)
- Regime E: Stop 25-30 ticks (chaotic environment)

---

## 6. Profit Target Rules

**Primary target:** The next major structural level in the cascade direction.

- Bullish cascade: Next call wall, or the expected move high, or the gamma flip (if below current price)
- Bearish cascade: Next put wall, or the expected move low, or the gamma flip (if above current price)

**Target distance:** The next level should be at least 2x the stop distance away. If the stop is 20 ticks and the next level is 30 ticks, the R:R is 1.5:1 — marginal. The minimum acceptable R:R for this setup is 1.5:1.

**Partial profit taking:**
- Take 50% at the halfway point between entry and target
- Let remaining 50% run to the full target
- Move stop to breakeven after taking first partial

**The "cascade continuation" scenario:** If additional sweeps occur after the entry (the cascade continues), the target should be extended. In this case, trail the remaining 50% with a 15-tick trailing stop rather than a fixed target.

---

## 7. Position Sizing

| Dark Pool | Cascade Size | Position Size |
|---|---|---|
| Dark confirms | Extreme ($20M+) | 75% of max |
| Dark confirms | Strong ($10M-$20M) | 62% of max |
| Dark confirms | Standard ($5M-$10M) | 50% of max |
| Dark neutral | Any | 37% of max |
| Dark opposes | Any | 0% — do not trade |

**Regime adjustments:**
- Regime A/B: Standard sizes
- Regime C: Standard sizes (but be ready for flip cross amplification)
- Regime D: Reduce all sizes by 25%
- Regime E: Reduce all sizes by 50%

**The "hedging risk" discount:** If the sweeps are far OTM (5%+ from current price) OR long-dated (30+ DTE), reduce position size by 50% regardless of dark pool confirmation. The hedging risk is elevated.

---

## 8. Order Book Confirmation

**During the sweep cascade (observation phase):**
- Book gets pushed in the cascade direction (offers hit for bullish, bids hit for bearish)
- Thin on the break side (no significant resting orders in the cascade direction)
- Aggressive market orders in the cascade direction
- No large opposing icebergs

**At the pullback (entry phase):**
- Bids appearing at the pullback level (bullish cascade) or offers appearing (bearish cascade)
- The pullback is being absorbed (price doesn't continue in the pullback direction)
- Aggression imbalance shifting back to the cascade direction

**After entry (trade management phase):**
- Market orders in the cascade direction dominating
- No large opposing icebergs
- Book thinning in the cascade direction (clear path to target)

**The "sweep follow-through" DOM signature:** After a genuine directional sweep cascade, the DOM shows a series of smaller market orders in the cascade direction following the initial sweeps. These are participants who saw the sweeps and are following the informed flow. The DOM aggression imbalance should be 2:1 to 3:1 in the cascade direction after the pullback.

**The "hedge sweep" DOM signature:** After a hedging sweep, the DOM shows the opposite: the initial spike is quickly absorbed, the book refills in the opposite direction, and the aggression imbalance returns to neutral or reverses. This is the sign that the sweep was defensive, not directional.

---

## 9. Win Rate and R:R Estimates

| Variant | Dark Pool | Regime | Win Rate | R:R | Expected Value |
|---|---|---|---|---|---|
| Call cascade | Confirms | A/B | 62-68% | 1.5:1 to 2.5:1 | +0.55R to +1.02R |
| Call cascade | Confirms | C | 62-68% | 2:1 to 3:1 | +0.86R to +1.40R |
| Call cascade | Confirms | D | 60-65% | 2:1 to 3:1 | +0.60R to +1.00R |
| Put cascade | Confirms | A/B | 62-68% | 1.5:1 to 2.5:1 | +0.55R to +1.02R |
| Put cascade | Confirms | C | 62-68% | 2:1 to 3:1 | +0.86R to +1.40R |
| Put cascade | Confirms | D/E | 58-63% | 1.5:1 to 2.5:1 | +0.37R to +0.83R |
| Any cascade | Neutral | Any | 55-60% | 1.5:1 to 2:1 | +0.33R to +0.60R |

**Note:** The win rate drops significantly when dark pool doesn't confirm (55-60% vs 62-68%). The dark pool confirmation is the primary filter for the hedging risk. Without it, the setup is marginal.

---

## 10. Failure Modes

### Failure Mode 1: The Sweep Was a Hedge (Most Important)

A fund buys 20,000 OTM puts to protect a $2B long portfolio. This looks exactly like an aggressive bearish sweep cascade. But it's defensive, not directional. The fund is not expecting the market to fall — they're just protecting against the possibility.

**Detection:**
- Sweeps are far OTM (5%+ from current price)
- Sweeps are in longer-dated expiries (30+ DTE)
- Dark pool is neutral or buying (the fund is not selling the underlying)
- DOM shows no follow-through (the book refills quickly after the sweep)

**Prevention:** Check strike selection and expiry. Check dark pool direction. If dark pool opposes the sweep, do not trade.

### Failure Mode 2: No Pullback (Runaway Move)

Price sweeps and never pulls back. The move is too fast and too strong for a safe entry.

**Response:** Skip the trade. The opportunity has passed. The next entry will be at the next structural level.

### Failure Mode 3: Pullback Becomes a Reversal

Price pulls back to the entry level but instead of bouncing, it continues in the pullback direction. The sweep impact is being fully retraced.

**Detection:** Price retraces more than 20 ticks from the sweep extreme. The DOM shows the pullback level failing (bids pulling for bullish cascade, offers pulling for bearish cascade).
**Response:** Do not enter. The sweep impact is being retraced. The sweep may have been a hedge.

### Failure Mode 4: Cascade Decelerates

The sweeps are getting smaller, not larger. The third sweep is smaller than the second, which is smaller than the first. This is a decelerating cascade — the urgency is fading.

**Detection:** Sweep sizes are declining (e.g., $5M, $3M, $1.5M).
**Response:** Do not trade. The cascade is not escalating. The urgency signal is weak.

### Failure Mode 5: Regime E Hedging Cascade

In Regime E (crisis), large put sweep cascades are common as institutions hedge their portfolios. These look like directional bearish cascades but they're defensive.

**Detection:** Regime E + put sweep cascade + dark pool neutral or buying.
**Response:** Do not trade. In Regime E, put cascades are more likely to be hedging than directional.

---

## 11. Example Scenarios

### Example 1: Bullish Call Cascade in Regime B

**Setup:**
- NQ at 19,450 at 10:15 AM. Regime B (GEX = $310M).
- Massive: Three call sweeps in 4 minutes:
  - 10:11 AM: $2.5M call sweep, 0DTE, ATM strike (19,450)
  - 10:13 AM: $4.2M call sweep, 0DTE, 19,500 strike
  - 10:15 AM: $6.8M call sweep, 0DTE, 19,500 and 19,550 strikes
  - Total: $13.5M in 4 minutes. Escalating. Near-ATM. 0DTE.
- UW: Dark pool net buying. Net dark premium +$18M. Institutional call sweep alerts.
- DOM: Book pushed upward. Thin above 19,450. Aggressive market buys 3.5:1 over sells.

**Cascade confirmed:** 3 sweeps, escalating, near-ATM, 0DTE. Dark pool confirms. DOM confirms.

**Wait for pullback:** Price spikes from 19,450 to 19,478 in 3 minutes. Pulls back to 19,462 over the next 2 minutes.

**Entry:** Long at 19,462 (limit order at pullback level).
**Stop:** 19,445 (17 ticks below entry, back to pre-sweep price).
**Target 1:** Call wall at 19,550 (88 ticks). Take 50%.
**Target 2:** EM high at 19,600 (138 ticks). Let remaining 50% run.
**Size:** 62% of maximum (dark confirms, strong cascade $10M-$20M).

**Result:** Price rallies from 19,462 to 19,552 over 25 minutes (first partial, 90 ticks). Continues to 19,595 (second partial, 133 ticks). Average exit: 111.5 ticks. Stop was 17 ticks. R:R achieved: 6.6:1.

### Example 2: Bearish Put Cascade in Regime C

**Setup:**
- NQ at 19,180 at 1:30 PM. Regime C (GEX = $65M). Flip at 19,100.
- Massive: Three put sweeps in 3 minutes:
  - 1:27 PM: $3M put sweep, 0DTE, 19,150 strike
  - 1:29 PM: $5.5M put sweep, 0DTE, 19,100 and 19,050 strikes
  - 1:30 PM: $8M put sweep, 0DTE, 19,000 strike
  - Total: $16.5M in 3 minutes. Escalating. Near-ATM. 0DTE.
- UW: Dark pool net selling. Net dark premium -$20M. Institutional put sweep alerts.
- DOM: Book pushed downward. Thin below 19,180. Aggressive market sells 4:1 over buys.

**Cascade confirmed:** 3 sweeps, escalating, near-ATM, 0DTE. Dark pool confirms. DOM confirms.

**Wait for pullback:** Price drops from 19,180 to 19,152 in 2 minutes. Pulls back to 19,168 over the next 3 minutes.

**Entry:** Short at 19,168 (limit order at pullback level).
**Stop:** 19,185 (17 ticks above entry, back to pre-sweep price).
**Target 1:** Flip level at 19,100 (68 ticks). Take 50%.
**Target 2:** Put wall at 19,000 (168 ticks). Let remaining 50% run.
**Size:** 62% of maximum (dark confirms, strong cascade).

**Result:** Price drops from 19,168 to 19,098 over 20 minutes (first partial, 70 ticks). Flip crossed — regime transitions to D. Price continues to 19,012 (second partial, 156 ticks). Average exit: 113 ticks. Stop was 17 ticks. R:R achieved: 6.6:1.

---

## 12. Anti-Patterns (When It Looks Like This Setup But Isn't)

### Anti-Pattern 1: Single Large Sweep (Not a Cascade)

A single very large sweep ($20M+) occurs. This is not a cascade — it's a single event. The cascade requires 3+ sweeps to establish the urgency pattern.

**Response:** Do not trade as a sweep cascade. Consider whether this is a distribution/accumulation signal instead.

### Anti-Pattern 2: Decelerating Sweeps

Three sweeps occur but they're getting smaller (decelerating). The urgency is fading, not building.

**Response:** Do not trade. The cascade is not escalating.

### Anti-Pattern 3: Far OTM Sweeps

The sweeps are far OTM (5%+ from current price). This is the hedging signature.

**Response:** Do not trade as a directional cascade. The sweeps are likely hedging.

### Anti-Pattern 4: Long-Dated Sweeps

The sweeps are in 30+ DTE options. This is the hedging signature.

**Response:** Do not trade as a directional cascade.

### Anti-Pattern 5: Dark Pool Opposing

Dark pool is in the opposite direction of the sweeps. The sweeps are hedging.

**Response:** Do not trade. This is the most important anti-pattern filter.

### Anti-Pattern 6: No Pullback After 10 Minutes

The sweep cascade occurs but price never pulls back within 10 minutes. The opportunity has passed.

**Response:** Do not chase. Skip the trade. The next opportunity will be at the next structural level.

---

## 13. Time-of-Day Considerations

**9:30-10:00 AM (Opening):**
- Opening sweep cascades are common but often driven by overnight positioning adjustments, not genuine intraday directional conviction
- Wait for the opening range to establish before trading sweep cascades
- If a cascade occurs in the first 15 minutes, require dark pool confirmation AND DOM confirmation before entering

**10:00 AM-12:00 PM (Morning session):**
- Best time for sweep cascade trades
- Volume is high, dark pool data is current, DOM signals are reliable
- The pullback is clean and well-defined

**12:00-1:30 PM (Lunch lull):**
- Sweep cascades during the lunch lull are often driven by algorithmic activity, not genuine institutional conviction
- Require dark pool confirmation. Reduce position size by 25%.

**1:30-3:00 PM (Afternoon session):**
- Sweep cascades are reliable in this window
- Afternoon cascades often have more follow-through than morning cascades (less time for the market to reverse)
- Good time for sweep cascade trades

**3:00-4:00 PM (Power hour):**
- Sweep cascades in the last hour are often driven by 0DTE expiration positioning
- These can be very fast and violent
- Reduce position size by 25%
- Take profits quickly — don't hold for extended targets in the last hour
- The pullback may not occur in the last 30 minutes (too fast)

**OPEX Fridays:**
- Sweep cascades on OPEX Friday are the most significant of the month
- Maximum 0DTE OI means maximum urgency when cascades occur
- Increase position size by 25% on OPEX Friday cascades (if all conditions met)
- Be especially careful about hedging cascades on OPEX Friday (institutions are rolling positions, creating large put sweeps that look directional but are actually hedging)
