# Setup 5: Charm Flow

## Overview

Charm Flow is the last 90-minute mechanical trade of the session. Like vanna, it's driven by mathematics — specifically, the time decay of option deltas. As 0DTE options approach expiration, their deltas decay toward zero (for OTM options) or toward 1/-1 (for ITM options). Dealers who hedged those deltas must unwind their hedges as the deltas decay. The direction of the unwind depends on whether the net dealer delta from 0DTE options is positive or negative.

CHEX (Charm Exposure) from FlashAlpha quantifies this: positive CHEX means that as time passes, dealer delta from 0DTE options INCREASES (dealers must buy to maintain delta neutrality). Negative CHEX means dealer delta DECREASES (dealers must sell).

This is the most time-specific setup in the system. It only applies in the last 90 minutes of the session (2:30-4:00 PM ET). Outside this window, charm flows are too small to trade. Inside this window, they can move NQ 20-50 points on strong CHEX days.

The setup is strongest on 0DTE days (every weekday now, since the introduction of daily SPX options) and especially strong on OPEX Fridays when the total 0DTE OI is at its maximum.

---

## 1. Setup Name and Overview

**Name:** Charm Flow (End-of-Day Mechanical Time Decay Trade)
**Type:** Mechanical time-decay-driven dealer unwind
**Frequency:** Daily (every session has some charm flow); tradeable magnitude 3-4 times per week
**Best variant:** Strong positive CHEX on OPEX Friday (dealers must buy into close)
**Worst variant:** Weak CHEX on a low-volume day (magnitude too small to trade)

The setup trades the mechanical dealer delta unwind that occurs in the last 90 minutes of the session as 0DTE option deltas decay.

---

## 2. Regime Requirements

**Regime A (strong positive gamma):**
- Charm flows are DAMPENED by the positive gamma environment
- The mechanical buying/selling is partially offset by dealer gamma hedging
- Win rate: 60-65%
- R:R: 1:1 to 1.5:1 (smaller moves due to dampening)
- Magnitude: 5-15 NQ points on average

**Regime B (moderate positive gamma):**
- Charm flows are moderately dampened
- Win rate: 60-65%
- R:R: 1:1 to 2:1
- Magnitude: 10-25 NQ points on average

**Regime C (weak positive gamma / near flip):**
- Charm flows are less dampened
- Win rate: 60-65%
- R:R: 1.5:1 to 2:1
- Magnitude: 15-30 NQ points on average
- A strong negative CHEX in Regime C can trigger a flip cross (see gamma-flip-cross.md)

**Regime D (negative gamma, controlled):**
- Charm flows are AMPLIFIED by the negative gamma environment
- Win rate: 60-65%
- R:R: 2:1 to 3:1
- Magnitude: 20-50 NQ points on average

**Regime E (negative gamma, crisis):**
- Charm flows are maximally amplified but also most unpredictable
- Win rate: 55-60%
- R:R: 2:1 to 4:1
- Reduce position size by 50%

---

## 3. Entry Conditions (All Four Rivers + Derived)

### The CHEX Trigger

The primary trigger is the CHEX value from FlashAlpha and the time of day.

**Entry window:** 2:30-2:45 PM ET. This is the optimal entry window for charm flow trades.
- Before 2:30 PM: Charm flows are too small (too much time remaining for delta decay to be significant)
- After 2:45 PM: The charm flow may already be partially priced in. Entry is still possible but at a worse price.
- After 3:30 PM: The charm flow is mostly complete. Do not enter new charm flow trades after 3:30 PM.

**CHEX thresholds:**
- Positive CHEX > $500M: Tradeable bullish charm flow. Dealers must buy as time passes.
- Positive CHEX > $1B: Strong bullish charm flow. Increase position size.
- Positive CHEX > $2B: Very strong bullish charm flow. Maximum position size.
- Negative CHEX < -$500M: Tradeable bearish charm flow. Dealers must sell as time passes.
- Negative CHEX < -$1B: Strong bearish charm flow.
- Negative CHEX < -$2B: Very strong bearish charm flow.
- CHEX between -$500M and +$500M: Too small to trade. Skip.

### FlashAlpha (Structure) — Required
- CHEX is clearly positive or negative (above $500M absolute value)
- The CHEX direction is consistent with the 0DTE OI structure (positive CHEX = net dealer delta from 0DTE options is positive and will increase as time passes)
- GEX regime: note for amplitude adjustment
- The 0DTE call wall and put wall positions: these are the levels that charm flow will push price toward or away from

**Understanding CHEX direction:**
- Positive CHEX: As time passes, dealer delta from 0DTE options increases. Dealers must BUY to maintain delta neutrality. This creates upward pressure.
- Negative CHEX: As time passes, dealer delta from 0DTE options decreases. Dealers must SELL to maintain delta neutrality. This creates downward pressure.

The direction of CHEX depends on the net 0DTE OI structure. If there are more 0DTE calls than puts (net call OI), and those calls are near-ATM (high delta), positive CHEX is likely. If there are more 0DTE puts than calls near-ATM, negative CHEX is likely.

### Massive.com (Flow) — Supporting (not required)
- Charm flows are mechanical — they happen regardless of directional options buying
- Flow confirmation increases conviction but is not required
- If flow confirms the charm direction: increase position size by 25%
- If flow opposes: reduce position size by 25%
- If flow is neutral: standard position size

### Unusual Whales (Dark) — Supporting (not required)
- Dark pool confirmation increases conviction
- Dark pool opposing: reduce position size by 25%
- Dark pool neutral: standard position size
- Dark pool confirming: increase position size by 25%

### Rithmic MBO (DOM) — Required
- The DOM must show the mechanical nature of charm flow: steady, persistent directional pressure starting around 2:30 PM
- Charm flow DOM signature:
  - Consistent market orders in the charm direction (not spike-y)
  - Aggression imbalance: 1.5:1 to 2.5:1 (moderate, building over time)
  - No large opposing icebergs
  - Price grinding in the charm direction with minimal pullbacks
  - Volume building as the session approaches close (charm flows accelerate into the close)

**The charm flow acceleration pattern:** Unlike vanna flows (which are strongest at the beginning and then gradual), charm flows ACCELERATE into the close. The delta decay rate increases as expiration approaches. The DOM should show increasing aggression imbalance as the session progresses from 2:30 PM to 4:00 PM.

### Derived — Required
- Time of day: Must be 2:30-2:45 PM ET for entry
- 0DTE options are expiring today (every weekday now)
- CHEX is above the $500M threshold
- The charm direction is consistent with the current price position relative to 0DTE walls

---

## 4. Entry Execution

**Entry timing:** 2:30-2:45 PM ET, after confirming CHEX is above threshold AND DOM shows the charm flow beginning.

**Entry technique:** Limit order in the direction of the charm flow, placed at the current market price or 1-2 ticks better.

**DOM confirmation before entry:** Wait for the DOM to show the charm flow beginning. The aggression imbalance should be at least 1.5:1 in the charm direction before entering. If the DOM is still balanced at 2:30 PM, wait until 2:35-2:40 PM for the flow to begin.

**Do NOT:** Enter before 2:30 PM based on CHEX alone. The charm flow doesn't materialize until the last 90 minutes.

**Do NOT:** Enter after 3:30 PM. The charm flow is mostly complete by then.

**Do NOT:** Enter if the DOM shows a spike rather than a grind. Spikes in the last 90 minutes are often caused by 0DTE option exercises or large end-of-day orders, not charm flows.

---

## 5. Stop Loss Rules

**Primary stop:** 15 NQ ticks against the entry.

The 15-tick stop is based on the nature of charm flows: they're steady grinds. If price moves 15 ticks against the charm direction, the flow is not working as expected.

**CHEX reversal stop:** If FlashAlpha shows CHEX shifting direction (positive CHEX becoming negative, or vice versa), exit immediately. This can happen if large 0DTE trades occur that change the net dealer delta structure.

**Time-based stop:** If the trade has not moved in the charm direction within 15 minutes of entry, exit at market. Charm flows should be visible within 15 minutes of the 2:30 PM entry window.

**Regime-specific adjustments:**
- Regime A/B: Stop 15 ticks
- Regime C: Stop 15 ticks
- Regime D: Stop 18 ticks (amplified environment)
- Regime E: Stop 20 ticks (chaotic environment)

---

## 6. Profit Target Rules

**Primary target:** Into the close. Charm flows are strongest into the 4:00 PM close. The ideal trade is entered at 2:30-2:45 PM and held until 3:45-3:55 PM.

**Magnitude estimates by CHEX level:**
- CHEX $500M-$1B: Expected NQ move 5-15 points
- CHEX $1B-$2B: Expected NQ move 15-30 points
- CHEX > $2B: Expected NQ move 30-50+ points (especially on OPEX Friday)

**Partial profit taking:**
- Take 50% at the halfway point between entry and estimated target
- Let remaining 50% run into the close (3:45-3:55 PM)
- Move stop to breakeven after taking first partial

**Time-based exit:** Exit all remaining positions by 3:55 PM ET. Do not hold charm flow trades into the last 5 minutes of the session (extreme volatility from 0DTE expiration).

**The "charm acceleration" exit:** If the DOM shows the charm flow accelerating sharply (aggression imbalance jumping from 2:1 to 5:1), consider taking full profits immediately. Sharp acceleration often precedes a reversal as the charm flow exhausts itself.

---

## 7. Position Sizing

**Base size:** HALF of the standard position size. Charm flows have high magnitude uncertainty — some days 5 NQ points, some days 50 NQ points. The uncertainty justifies a smaller base size.

| CHEX Level | Flow/Dark | Position Size |
|---|---|---|
| CHEX > $2B | Both confirming | 75% of max |
| CHEX > $2B | One confirming | 50% of max |
| CHEX $1B-$2B | Both confirming | 50% of max |
| CHEX $1B-$2B | One confirming | 37% of max |
| CHEX $500M-$1B | Both confirming | 37% of max |
| CHEX $500M-$1B | Neutral | 25% of max |
| CHEX < $500M | Any | 0% — do not trade |

**OPEX Friday bonus:** Increase all sizes by 25% on OPEX Friday. The maximum 0DTE OI creates the strongest charm flows of the month.

**Regime D/E adjustment:** Reduce all sizes by 25% due to amplification risk.

---

## 8. Order Book Confirmation

**Charm flow DOM signature:**
- Steady, consistent market orders in the charm direction (not spike-y)
- Aggression imbalance: 1.5:1 to 2.5:1 at 2:30 PM, building to 2:1 to 3:1 by 3:30 PM
- No large opposing icebergs
- Price grinding in the charm direction with minimal pullbacks
- Volume building as the session approaches close

**The acceleration pattern:** The key distinguishing feature of charm flow is the acceleration. At 2:30 PM, the aggression imbalance is moderate (1.5:1). By 3:00 PM, it's 2:1. By 3:30 PM, it's 2.5:1 to 3:1. This acceleration is the mathematical consequence of increasing delta decay rate as expiration approaches.

**Distinguishing charm from other end-of-day flows:**

| Characteristic | Charm Flow | End-of-Day Positioning | 0DTE Expiration Spike |
|---|---|---|---|
| Timing | 2:30-4:00 PM | 3:30-4:00 PM | 3:45-4:00 PM |
| DOM pattern | Steady grind, accelerating | Spike-y | Very spike-y |
| Aggression | 1.5:1 to 3:1, building | 3:1 to 10:1 | 5:1 to 20:1 |
| Duration | 90 minutes | 30 minutes | 15 minutes |
| CHEX trigger | Yes | No | No |

**The 0DTE expiration spike:** In the last 15 minutes of the session, 0DTE options that are near-ATM can create violent price moves as they expire. This is NOT charm flow — it's expiration mechanics. Do not trade the last 15 minutes as a charm flow trade.

---

## 9. Win Rate and R:R Estimates

| CHEX Level | Regime | Win Rate | R:R | Expected Value |
|---|---|---|---|---|
| CHEX > $2B | A/B | 62-67% | 1.5:1 to 2:1 | +0.55R to +1.01R |
| CHEX > $2B | C | 62-67% | 2:1 to 3:1 | +0.86R to +1.68R |
| CHEX > $2B | D | 60-65% | 2.5:1 to 4:1 | +0.80R to +1.95R |
| CHEX $1B-$2B | A/B | 60-65% | 1:1 to 1.5:1 | +0.20R to +0.48R |
| CHEX $1B-$2B | C/D | 60-65% | 1.5:1 to 2.5:1 | +0.50R to +1.13R |
| CHEX $500M-$1B | Any | 58-63% | 1:1 to 1.5:1 | +0.16R to +0.45R |

**Note:** The win rate is slightly lower than vanna (60-65% vs 65-70%) because charm flows have higher magnitude uncertainty. The direction is reliable but the magnitude varies significantly.

---

## 10. Failure Modes

### Failure Mode 1: CHEX Too Small

CHEX is below $500M. The charm flow is too small to create a tradeable NQ move.

**Response:** Do not trade. The mechanical impact is insufficient.

### Failure Mode 2: Large 0DTE Trade Changes CHEX Direction

A large 0DTE options trade occurs after 2:30 PM that changes the net dealer delta structure. CHEX shifts direction. The charm flow reverses.

**Detection:** FlashAlpha shows CHEX shifting direction during the trade.
**Response:** Exit immediately. The mechanical trigger has reversed.

### Failure Mode 3: Opposing Directional Flow Overwhelms Charm

Strong directional flow (sweep cascade, dark pool attack) in the opposite direction of the charm flow overwhelms the mechanical rebalancing.

**Detection:** Massive shows strong opposing sweeps. DOM shows spike-y opposing aggression.
**Response:** Exit immediately. The directional flow is stronger than the mechanical charm flow.

### Failure Mode 4: 0DTE Expiration Spike Reversal

In the last 15 minutes, a 0DTE expiration spike occurs in the opposite direction of the charm flow. The spike is violent and can reverse the entire charm flow gain in minutes.

**Prevention:** Exit all charm flow positions by 3:55 PM ET. Do not hold into the last 5 minutes.

### Failure Mode 5: Regime Transition During Trade

A regime transition occurs during the charm flow trade (e.g., price crosses the gamma flip). The charm flow dynamics change.

**Response:** Re-evaluate the CHEX in the new regime. If CHEX is still in the same direction, hold. If CHEX has shifted, exit.

---

## 11. Example Scenarios

### Example 1: Strong Positive CHEX on OPEX Friday

**Setup:**
- NQ at 19,350 at 2:30 PM. OPEX Friday.
- FlashAlpha: GEX = $420M (Regime B). CHEX = +$2.4B (strong positive, dealers must buy as time passes).
- Massive: Call flow slightly positive. Net call premium +$8M. No strong sweeps.
- UW: Dark pool neutral. No institutional alerts.
- DOM at 2:30 PM: Market buys 1.6:1 over sells. Steady grind upward. No opposing icebergs.

**Conviction check:** STRUCTURE bullish (positive CHEX), FLOW neutral, DARK neutral, DOM bullish (steady grind), DERIVED bullish (OPEX Friday, maximum 0DTE OI). Score: +2 to +3. Moderate conviction.

**Entry:** Long at 19,350 at 2:32 PM (limit order after DOM confirms charm flow beginning).
**Stop:** 19,335 (15 ticks below entry).
**Target 1:** 19,375 (25 NQ points, CHEX estimate for $2.4B). Take 50% at 3:15 PM or when reached.
**Target 2:** Into close at 3:55 PM. Exit remaining 50%.
**Size:** 50% of maximum (CHEX > $2B, both flow and dark neutral).

**Result:** Price grinds from 19,350 to 19,378 by 3:15 PM (first partial, 28 ticks). Continues to 19,412 by 3:50 PM. Exit remaining 50% at 19,412 (62 ticks). Average exit: 45 ticks. Stop was 15 ticks. R:R achieved: 3:1.

### Example 2: Strong Negative CHEX in Regime D

**Setup:**
- NQ at 19,050 at 2:30 PM. Regular Wednesday.
- FlashAlpha: GEX = -$150M (Regime D). CHEX = -$1.8B (strong negative, dealers must sell as time passes).
- Massive: Put flow increasing. Net put premium -$10M.
- UW: Dark pool net selling. Net dark premium -$12M.
- DOM at 2:30 PM: Market sells 1.8:1 over buys. Steady grind downward.

**Conviction check:** STRUCTURE bearish (negative CHEX), FLOW bearish (put flow), DARK bearish (dark selling), DOM bearish (steady grind), DERIVED bearish (Regime D amplification). Score: -5. Maximum bearish conviction.

**Entry:** Short at 19,050 at 2:33 PM.
**Stop:** 19,068 (18 ticks above entry, Regime D adjustment).
**Target 1:** 19,020 (30 NQ points, CHEX estimate). Take 50%.
**Target 2:** Into close at 3:55 PM. Exit remaining 50%.
**Size:** 37% of maximum (CHEX $1B-$2B, both confirming, Regime D adjustment).

**Result:** Price grinds from 19,050 to 19,018 by 3:00 PM (first partial, 32 ticks). Continues to 18,985 by 3:50 PM. Exit at 18,985 (65 ticks). Average exit: 48.5 ticks. Stop was 18 ticks. R:R achieved: 2.7:1.

---

## 12. Anti-Patterns (When It Looks Like This Setup But Isn't)

### Anti-Pattern 1: End-of-Day Positioning Spike

A large institution repositions at the end of the day, creating a spike in the last 30 minutes. This looks like charm flow but it's a single large order, not a mechanical grind.

**Detection:** DOM shows a spike (sudden large move, high aggression imbalance) rather than a grind. The move is concentrated in a few bars rather than spread over 90 minutes.
**Response:** Do not trade as a charm flow. Consider the sweep cascade setup instead.

### Anti-Pattern 2: CHEX Below Threshold

CHEX is between -$500M and +$500M. The charm flow is too small to trade.

**Response:** Do not trade. The mechanical impact is insufficient.

### Anti-Pattern 3: Entry After 3:30 PM

Entering a charm flow trade after 3:30 PM. The charm flow is mostly complete by then. The remaining 30 minutes have high risk (0DTE expiration spikes) and low reward (most of the move has already happened).

**Response:** Do not enter charm flow trades after 3:30 PM. If already in a trade, consider taking profits rather than holding.

### Anti-Pattern 4: Charm Flow Opposing Strong Directional Flow

CHEX is positive (bullish charm) but there's a strong sweep cascade or dark pool attack in the bearish direction. The directional flow is stronger than the mechanical charm flow.

**Response:** Skip the charm flow trade. The directional flow will overwhelm the mechanical charm.

### Anti-Pattern 5: Charm Flow on Low-Volume Day

On a low-volume day (holiday-shortened session, summer Friday), the charm flow may be too small to trade even if CHEX is above threshold. The 0DTE OI is lower on low-volume days.

**Detection:** Total 0DTE volume is less than 50% of the 20-day average.
**Response:** Reduce position size by 50% on low-volume days.

---

## 13. Time-of-Day Considerations

**Before 2:30 PM:**
- Do not trade charm flow. The delta decay is too slow to create a tradeable move.
- Use this time to identify the CHEX level and prepare for the 2:30 PM entry.

**2:30-2:45 PM (Entry window):**
- Optimal entry window. Enter as soon as the DOM confirms the charm flow beginning.
- If the DOM doesn't show the charm flow by 2:45 PM, wait until 2:50 PM. If still not visible by 2:50 PM, skip the trade.

**2:45-3:15 PM (Early charm):**
- Charm flow is building. Aggression imbalance should be 1.5:1 to 2:1.
- Take first partial profit if the estimated target is reached.

**3:15-3:30 PM (Peak charm):**
- Charm flow is at its strongest. Aggression imbalance should be 2:1 to 3:1.
- Consider taking second partial profit.

**3:30-3:55 PM (Late charm):**
- Charm flow is decelerating (most of the delta decay has occurred).
- Exit remaining positions by 3:55 PM.
- Do not enter new charm flow trades after 3:30 PM.

**3:55-4:00 PM (Expiration window):**
- 0DTE options are expiring. Extreme volatility possible.
- All charm flow positions should be closed by 3:55 PM.
- Do not trade in the last 5 minutes of the session.

**OPEX Fridays:**
- The entire charm flow schedule is amplified.
- CHEX is at its maximum (maximum 0DTE OI).
- The move can be 2-3x the normal magnitude.
- Enter at 2:30 PM sharp (don't wait for DOM confirmation — the flow will be visible immediately).
- Exit by 3:50 PM (OPEX expiration spikes can be violent in the last 10 minutes).
