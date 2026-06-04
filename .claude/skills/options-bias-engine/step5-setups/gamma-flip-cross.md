# Setup 3: Gamma Flip Cross

## Overview

The Gamma Flip Cross is the biggest setup in the Options Bias Engine. It trades the transition between positive and negative gamma regimes — the moment when the market's mechanical behavior fundamentally changes. When price crosses the gamma flip level and holds, the entire dealer hedging dynamic reverses. What was a stabilizing force becomes a destabilizing one, and vice versa.

The payoff is 3:1 to 5:1 R:R. The win rate is 60-65%. These are the trades that pay for many small losses. A single confirmed gamma flip cross, properly traded, can generate 150-300 NQ ticks.

The biggest risk is the false cross. Price pokes below the flip, triggers panic, then reclaims it. The 2-bar confirmation rule filters most false crosses but not all. This is why the win rate is 60-65% rather than higher — the false cross is a real and recurring failure mode.

This setup IS the regime transition. Trading it means trading the moment when Regime A/B/C becomes D/E (bearish cross) or when D/E becomes C/B/A (bullish cross).

---

## 1. Setup Name and Overview

**Name:** Gamma Flip Cross (Regime Transition Trade)
**Type:** Momentum continuation through structural regime change
**Frequency:** 1-3 times per week (significant crosses); 3-5 times per week (minor crosses)
**Best variant:** Bearish cross (above → below flip) in Regime C with dark pool confirmation (highest conviction, clearest setup)
**Worst variant:** Bullish cross in Regime E (chaotic, hard to time, high false cross rate)

The setup enters after price crosses the gamma flip level and holds on the new side for 2+ confirmed bars, trading the continuation in the direction of the cross.

---

## 2. Regime Requirements

This setup IS the regime transition. The entry regime is the one being exited.

**Bearish Cross (Regime A/B/C → D/E):**
- Starting regime: A, B, or C (positive gamma)
- Price crosses below the gamma flip level
- After 2 confirmed bars below the flip, enter short
- The new regime is D or E (negative gamma)
- The mechanical behavior has reversed: dealers now sell dips and buy rips (destabilizing)

**Bullish Cross (Regime D/E → C/B/A):**
- Starting regime: D or E (negative gamma)
- Price crosses above the gamma flip level
- After 2 confirmed bars above the flip, enter long
- The new regime is C, B, or A (positive gamma)
- The mechanical behavior has reversed: dealers now buy dips and sell rips (stabilizing)

**The most powerful cross:** Regime C → D (bearish). In Regime C, the flip is close and the put wall is the last defense. When the put wall breaks AND the flip is crossed, the regime transition is confirmed and the move is amplified by the new negative gamma environment.

**The most dangerous cross:** Regime E → D (bullish). In Regime E (crisis), the bullish cross is often a dead-cat bounce. The regime may transition back to E quickly. Require 5/5 conviction and reduce size by 50%.

---

## 3. Entry Conditions (All Four Rivers + Derived)

### The 2-Bar Confirmation Rule

Before checking any other condition, the 2-bar confirmation rule must be satisfied:

- Price must close BELOW the gamma flip level on TWO consecutive 1-minute bars (bearish cross)
- Price must close ABOVE the gamma flip level on TWO consecutive 1-minute bars (bullish cross)
- The bars must be consecutive — a bar that closes back on the wrong side resets the count
- The bars must close by at least 5 NQ ticks beyond the flip (not just touching the flip)

This rule filters the majority of false crosses. A single bar below the flip is often a wick or a temporary penetration. Two consecutive bars below the flip with 5+ tick closes indicates genuine regime transition.

### FlashAlpha (Structure) — Required
- The gamma flip level is clearly identified (not ambiguous — there should be a clear zero-crossing in the GEX curve)
- Price has crossed the flip by at least 10 NQ ticks (not just touching it)
- GEX is transitioning: for bearish cross, GEX is moving from positive toward zero or negative. For bullish cross, GEX is moving from negative toward zero or positive.
- DEX has shifted in the direction of the cross (confirming the structural change)
- The flip level itself: note the exact price. This becomes the stop reference.

**Quantitative threshold:** The flip level must be at least 0.2% away from the nearest wall (call wall for bearish cross, put wall for bullish cross). If the flip and the wall are within 0.1% of each other, the setup is ambiguous — the wall break and flip cross are happening simultaneously, making it harder to confirm.

### Massive.com (Flow) — Required
- Flow has SHIFTED in the direction of the cross
- Bearish cross: put flow is increasing, call flow is declining. Net premium moving negative.
- Bullish cross: call flow is increasing, put flow is declining. Net premium moving positive.
- The shift must be RECENT (within the last 30 minutes). Stale flow from 2 hours ago doesn't count.
- Sweeps in the direction of the cross (put sweeps for bearish, call sweeps for bullish)
- The flow shift should be ACCELERATING, not decelerating. If flow is declining as price crosses the flip, the cross may be temporary.

### Unusual Whales (Dark) — Required (non-negotiable)
- Dark pool MUST confirm the direction of the cross
- Bearish cross: dark pool is selling. Net dark premium negative. Institutional selling alerts.
- Bullish cross: dark pool is buying. Net dark premium positive. Institutional buying alerts.
- This is the most important confirmation for the gamma flip cross. Without institutional confirmation, the cross is likely driven by retail or algorithmic flow and has a high probability of reversing.

**Quantitative threshold:** Net dark premium must be at least $15M in the direction of the cross. Below $15M, the institutional conviction is insufficient.

### Rithmic MBO (DOM) — Required
- Aggressive market orders in the direction of the cross (not just passive drift)
- Bearish cross: market sells dominating (at least 2.5:1 over market buys)
- Bullish cross: market buys dominating (at least 2.5:1 over market sells)
- Book is thinning on the losing side (bids pulling for bearish cross, offers pulling for bullish cross)
- Icebergs appearing on the winning side (hidden buyers for bullish cross, hidden sellers for bearish cross)
- The flip level itself: after the cross, the flip level should show new resting orders on the opposite side (new resistance for bearish cross, new support for bullish cross)

### Derived — Supporting
- The expected move range supports the cross direction (bearish cross: EM low is below the flip; bullish cross: EM high is above the flip)
- Max pain is in the direction of the cross
- 0DTE walls have shifted in the direction of the cross (the 0DTE structure is now aligned with the new regime)
- VIX is moving in the direction consistent with the cross (rising for bearish, falling for bullish)

---

## 4. Entry Execution

**Entry timing:** After the 2-bar confirmation rule is satisfied AND all required conditions are met.

**Entry technique:** Market order or aggressive limit order (1-2 ticks inside the current bid/ask). This is not a setup where you wait for a pullback — the gamma flip cross is a momentum trade and the move can be fast.

**Exception:** If the 2-bar confirmation happens and then price immediately pulls back toward the flip, wait for the pullback to complete before entering. Enter on the bounce off the flip level (which is now resistance for bearish cross, support for bullish cross).

**Entry price reference:**
- Bearish cross: Enter at or near the close of the second confirmation bar below the flip
- Bullish cross: Enter at or near the close of the second confirmation bar above the flip

**Do NOT:** Enter before the 2-bar confirmation is complete. The first bar below the flip is not an entry signal. Wait for the second bar.

**Do NOT:** Enter if the 2-bar confirmation happened more than 10 minutes ago and price has already moved significantly. The opportunity has passed.

---

## 5. Stop Loss Rules

**Primary stop:** Back above the gamma flip level (bearish cross) or back below the gamma flip level (bullish cross).

- Bearish cross (short): Stop is 8-12 ticks ABOVE the gamma flip level. If price closes above the flip, the cross has failed.
- Bullish cross (long): Stop is 8-12 ticks BELOW the gamma flip level. If price closes below the flip, the cross has failed.

**Why 8-12 ticks:** The flip level can be temporarily reclaimed without the cross being false. An 8-12 tick buffer filters temporary reclaims. Beyond 12 ticks, the cross has definitively failed.

**The false cross stop:** If the 2-bar confirmation is satisfied but price immediately reclaims the flip on the third bar, exit immediately. The false cross is confirmed. Do not wait for the price-based stop.

**Regime-specific adjustments:**
- Regime C → D (bearish): Stop 10-12 ticks above flip (most important cross, give it room)
- Regime A/B → D/E (bearish): Stop 8-10 ticks above flip
- Regime D/E → C/B (bullish): Stop 8-10 ticks below flip
- Regime E → D (bullish): Stop 6-8 ticks below flip (most dangerous cross, tightest stop)

---

## 6. Profit Target Rules

**Bearish cross targets:**
- Primary: Put wall (the nearest significant put OI concentration below the flip)
- Secondary: Expected move low
- Tertiary: Next put wall below the primary (if the primary breaks)

**Bullish cross targets:**
- Primary: Call wall (the nearest significant call OI concentration above the flip)
- Secondary: Expected move high
- Tertiary: Next call wall above the primary

**Target distance:** The primary target should be at least 50 NQ ticks from the entry. If the nearest wall is only 30 ticks away, the R:R is insufficient for this setup (stop is 10-12 ticks, target is 30 ticks = 2.5:1 R:R, which is below the 3:1 minimum for this setup).

**Partial profit taking:**
- Take 33% at the first significant level (HVL or mid-range)
- Take 33% at the primary target (put wall or call wall)
- Let remaining 33% run to the secondary target (EM boundary)
- Move stop to breakeven after taking first partial

**The cascade scenario:** In a bearish cross that triggers a regime transition to Regime E, the move can be much larger than the primary target. In this case, hold the remaining 33% with a trailing stop (trail by 20 NQ ticks) rather than a fixed target.

---

## 7. Position Sizing

| Conviction | Position Size | Notes |
|---|---|---|
| 5/5 (all conditions + dark confirmation + DOM icebergs) | 100% of max | Maximum conviction flip cross |
| 4/5 (all required conditions met) | 75% of max | Standard flip cross size |
| 3/5 (one required condition missing) | 50% of max | Only if dark pool confirms |
| 2/5 or below | 0% | Do not trade |

**Regime E bullish cross adjustment:** Reduce all sizes by 50%. The bullish cross in Regime E is the most dangerous variant.

**The 2-bar confirmation bonus:** If the 2-bar confirmation is clean (both bars close well beyond the flip, no wicks back to the flip), add 25% to the position size. Clean confirmations have higher win rates.

---

## 8. Order Book Confirmation

**Pre-cross DOM signals (anticipate the cross):**
- Bids pulling at the flip level (buyers retreating before the bearish cross)
- Offers pulling at the flip level (sellers retreating before the bullish cross)
- Aggression imbalance building in the cross direction
- Icebergs disappearing on the losing side

**Post-cross DOM signals (confirm the cross is real):**
- The flip level is now acting as resistance (bearish cross) or support (bullish cross)
- New resting orders appearing on the opposite side of the flip from the entry
- Aggressive market orders continuing in the cross direction
- Book is thin in the direction of the cross (clear path to the target)

**False cross DOM signals (abort):**
- Bids reappearing at the flip level after a bearish cross (buyers defending the level)
- Offers reappearing at the flip level after a bullish cross (sellers defending the level)
- Aggression imbalance reversing (market orders going against the cross)
- Icebergs appearing on the opposite side of the cross

**The iceberg multiplier:** If an iceberg is detected on the winning side of the flip after the cross (hidden buyers above the flip for bullish cross, hidden sellers below the flip for bearish cross), this is the strongest possible DOM confirmation. Conviction +1 level.

---

## 9. Win Rate and R:R Estimates

| Variant | Win Rate | R:R | Expected Value |
|---|---|---|---|
| Bearish cross, Regime C→D, dark confirmed | 63-68% | 3:1 to 5:1 | +1.24R to +2.40R |
| Bearish cross, Regime B→D, dark confirmed | 60-65% | 3:1 to 4:1 | +1.00R to +1.60R |
| Bearish cross, Regime A→D, dark confirmed | 58-63% | 3:1 to 5:1 | +0.74R to +1.65R |
| Bullish cross, Regime D→C, dark confirmed | 60-65% | 3:1 to 4:1 | +1.00R to +1.60R |
| Bullish cross, Regime E→D, dark confirmed | 55-60% | 2.5:1 to 3.5:1 | +0.63R to +1.10R |

**Why the win rate is 60-65% and not higher:** The false cross is a real and recurring failure mode. Even with the 2-bar confirmation rule and dark pool confirmation, approximately 35-40% of crosses fail. The edge comes from the R:R — when the cross is real, the move is large enough to pay for multiple false crosses.

**Expected value calculation (Regime C→D, best variant):**
- Win rate: 65%, R:R: 4:1
- EV = 0.65 × 4 - 0.35 × 1 = 2.60 - 0.35 = +2.25R per trade
- This is the highest EV setup in the system

---

## 10. Failure Modes

### Failure Mode 1: False Cross (Most Common)

Price pokes below the flip, triggers panic selling and stop-outs, then reclaims the flip. The 2-bar confirmation rule filters most false crosses but not all. A determined buyer can push price back above the flip even after two bars below it.

**Detection:** After the 2-bar confirmation, price reclaims the flip on the third or fourth bar.
**Response:** Exit immediately. The stop (back above the flip) should trigger. Do not hold hoping for a re-cross.

**Frequency:** Approximately 35-40% of crosses are false. This is the primary reason the win rate is 60-65%.

### Failure Mode 2: Dark Pool Not Confirming

The cross happens with strong visible flow but dark pool is neutral or opposing. The institutional conviction is absent. The cross is likely driven by retail or algorithmic flow.

**Detection:** UW dark pool direction is neutral or opposing the cross direction.
**Response:** Do not enter. Wait for dark pool to confirm. If it doesn't confirm within 15 minutes, the cross is likely false.

### Failure Mode 3: Regime Transition Fails to Materialize

Price crosses the flip but GEX doesn't transition to negative (bearish cross). The OI structure is such that the flip level is not where the actual gamma zero-crossing is. This can happen when FlashAlpha's flip calculation is based on stale OI data.

**Detection:** After the bearish cross, FlashAlpha still shows positive GEX. The regime hasn't transitioned.
**Response:** Reduce position size by 50%. The mechanical amplification of negative gamma won't occur. The move may still happen but will be smaller.

### Failure Mode 4: Macro Event Reversal

A macro event (Fed announcement, economic data, geopolitical news) occurs during the trade and reverses the cross. The fundamental driver overwhelms the options structure.

**Detection:** Sudden reversal with no options-flow explanation. News event visible on the tape.
**Response:** Exit immediately. Macro events override options structure. Do not hold through macro reversals.

### Failure Mode 5: Exhaustion at the Target

Price reaches the primary target (put wall or call wall) and bounces strongly. The move is over. If holding the remaining 33% with a trailing stop, the trailing stop gets hit.

**Response:** This is not a failure — it's a successful trade. The trailing stop is designed to capture the remaining move while protecting profits. Accept the trailing stop exit.

---

## 11. Example Scenarios

### Example 1: Bearish Cross, Regime C → D (Best Variant)

**Setup:**
- NQ at 19,180. Gamma flip at 19,150. GEX = $45M (Regime C, very near flip).
- Put wall at 19,200 (already broken earlier — see wall-break.md).
- FlashAlpha: GEX positive but declining rapidly. Flip at 19,150. DEX shifting positive.
- Massive: Put flow accelerating. Net put premium -$28M. Put sweeps 6:1 over calls. New put OI building at 19,000 and 18,800 strikes.
- UW: Dark pool net selling. Net dark premium -$32M. Multiple institutional put sweep alerts.
- DOM: Market sells 4:1 over buys. Bids pulling at 19,150. Book thin below 19,150. Icebergs on the ask at 19,155.

**Bar 1:** NQ closes at 19,142 (8 ticks below flip). First confirmation bar.
**Bar 2:** NQ closes at 19,135 (15 ticks below flip). Second confirmation bar. 2-bar rule satisfied.

**Conviction check:** STRUCTURE bearish (flip crossed, GEX transitioning), FLOW bearish (accelerating put flow), DARK bearish (institutional selling, $32M), DOM bearish (4:1 sells, icebergs on ask), DERIVED bearish (EM low at 19,050, max pain at 19,000). Score: -5. Maximum bearish conviction. Iceberg multiplier: +1 level. Effective conviction: Maximum.

**Entry:** Short at 19,135 (market order at close of second confirmation bar).
**Stop:** 19,162 (12 ticks above flip at 19,150).
**Target 1:** HVL at 19,080 (55 ticks). Take 33% here.
**Target 2:** Next put wall at 19,000 (135 ticks). Take 33% here.
**Target 3:** EM low at 18,950 (185 ticks). Trail remaining 33% with 20-tick trailing stop.
**Size:** 100% of maximum (maximum conviction).

**Result:** Price drops from 19,135 to 19,075 (first partial, 60 ticks). Continues to 18,995 (second partial, 140 ticks). Trailing stop hit at 19,020 (third partial, 115 ticks). Average exit: 105 ticks. Stop was 27 ticks. R:R achieved: 3.9:1.

### Example 2: Bullish Cross, Regime D → C

**Setup:**
- NQ at 19,020. Gamma flip at 19,050. GEX = -$120M (Regime D).
- FlashAlpha: GEX negative but improving. Flip at 19,050. DEX shifting negative.
- Massive: Call flow accelerating. Net call premium +$22M. Call sweeps 5:1 over puts.
- UW: Dark pool net buying. Net dark premium +$25M. Institutional call sweep alerts.
- DOM: Market buys 3.5:1 over sells. Offers pulling at 19,050. Book thin above 19,050. Icebergs on the bid at 19,045.

**Bar 1:** NQ closes at 19,058 (8 ticks above flip). First confirmation bar.
**Bar 2:** NQ closes at 19,065 (15 ticks above flip). Second confirmation bar. 2-bar rule satisfied.

**Entry:** Long at 19,065 (market order).
**Stop:** 19,038 (12 ticks below flip at 19,050).
**Target 1:** HVL at 19,120 (55 ticks). Take 33%.
**Target 2:** Call wall at 19,200 (135 ticks). Take 33%.
**Target 3:** EM high at 19,280 (215 ticks). Trail remaining 33%.
**Size:** 75% of maximum (high conviction, not maximum because Regime D→C is less reliable than C→D).

**Result:** Price rallies from 19,065 to 19,125 (first partial, 60 ticks). Continues to 19,195 (second partial, 130 ticks). Trailing stop hit at 19,220 (third partial, 155 ticks). Average exit: 115 ticks. Stop was 27 ticks. R:R achieved: 4.3:1.

---

## 12. Anti-Patterns (When It Looks Like This Setup But Isn't)

### Anti-Pattern 1: Flip Cross Without Dark Pool Confirmation

Price crosses the flip with strong visible flow but dark pool is neutral. This looks like a flip cross but the institutional conviction is absent. The cross is likely driven by retail or algorithmic flow and has a high probability of reversing.

**Response:** Do not trade. The dark pool confirmation is non-negotiable for this setup.

### Anti-Pattern 2: Flip Cross on Low Volume

Price crosses the flip on below-average volume. Low-volume crosses are almost always false. The cross needs volume to be sustained.

**Quantitative threshold:** Volume on the confirmation bars must be at least 1.5x the 20-bar average. Below this, treat as a potential false cross.

### Anti-Pattern 3: Flip Cross Near End of Day (After 3:30 PM)

Flip crosses in the last 30 minutes are often driven by end-of-day positioning and 0DTE expiration, not genuine regime transitions. The cross may not carry over to the next session.

**Response:** Reduce position size by 75% for any flip cross after 3:30 PM. Do not hold overnight.

### Anti-Pattern 4: Flip Cross Without Structural Confirmation

Price crosses the flip but FlashAlpha doesn't show GEX transitioning. The flip level may be stale (computed from yesterday's OI). The actual flip may be at a different price.

**Response:** Require FlashAlpha to show GEX moving toward zero (for bearish cross) or away from zero (for bullish cross) before entering.

### Anti-Pattern 5: Multiple Flip Crosses in the Same Session

If the flip has been crossed multiple times in the same session (price oscillating around the flip), the flip level is not a clean structural boundary. The regime is genuinely ambiguous.

**Response:** Do not trade flip crosses when the flip has been crossed more than twice in the same session. The structural clarity required for this setup is absent.

---

## 13. Time-of-Day Considerations

**9:30-10:00 AM (Opening):**
- Opening flip crosses are common but often false (opening range establishment)
- Wait for the opening range to establish before trading flip crosses
- If a flip cross occurs in the first 15 minutes, wait for the 2-bar confirmation AND for the opening range to confirm the cross direction

**10:00 AM-12:00 PM (Morning session):**
- Best time for flip cross trades
- Volume is high, dark pool data is current, DOM signals are reliable
- The 2-bar confirmation is clean and well-defined

**12:00-1:30 PM (Lunch lull):**
- Flip crosses during the lunch lull are often false (low volume, thin book)
- Avoid flip cross trades during this window
- If a cross occurs, wait for volume to confirm before entering

**1:30-3:00 PM (Afternoon session):**
- Flip crosses are reliable in this window
- Charm flows may accelerate a cross in the charm direction
- Good time for flip cross trades

**3:00-4:00 PM (Power hour):**
- Flip crosses in the last hour can be violent (0DTE expiration, charm flows)
- Reduce position size by 50%
- Take profits quickly — don't hold for extended targets
- The 2-bar confirmation may happen very fast (1-2 minutes per bar)

**OPEX Fridays:**
- Flip crosses on OPEX Friday are the most significant of the month
- Maximum OI means maximum mechanical force when the flip is crossed
- Increase position size by 25% on OPEX Friday flip crosses (if all conditions met)
- The move after an OPEX Friday flip cross can be 2-3x the normal magnitude
