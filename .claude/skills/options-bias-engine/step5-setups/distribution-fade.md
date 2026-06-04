# Setup 6: Distribution / Accumulation Fade

## Overview

The Distribution/Accumulation Fade is the "smart money vs. dumb money" trade. It exploits the divergence between what is visible to the market (retail and algorithmic flow on lit exchanges) and what institutions are doing quietly in dark pools. When these two flows diverge, the institutional flow is almost always right.

This setup is the trading implementation of the analytical patterns described in step4-cross-validation/distribution-accumulation.md. That document covers the detection methodology in depth. This document focuses on the trade execution: when to enter, where to stop, how to size, and what the order book must show.

The setup has two variants:
- **Distribution Fade (short):** Visible flow is bullish, dark pool is bearish. Institutions are selling into retail buying.
- **Accumulation Fade (long):** Visible flow is bearish, dark pool is bullish. Institutions are buying into retail selling.

Win rate: 65-72%. R:R: 2:1 to 3:1. These are among the best statistics in the system.

---

## 1. Setup Name and Overview

**Name:** Distribution/Accumulation Fade (Smart Money Follow)
**Type:** Divergence fade — follow institutional dark pool, fade visible retail flow
**Frequency:** 2-4 times per week (clear distribution/accumulation patterns)
**Best variant:** Distribution Fade in Regime A or B (positive gamma dampens the visible bullish flow, making the distribution more obvious)
**Worst variant:** Accumulation Fade in Regime E (chaotic environment, hard to distinguish accumulation from capitulation)

The setup enters AFTER the distribution or accumulation period ends, on the first sign of visible weakness (distribution) or stabilization (accumulation).

---

## 2. Regime Requirements

**Regime A (strong positive gamma):**
- Distribution is most visible in Regime A because the positive gamma dampens the visible bullish flow. The distribution is happening but price isn't moving much — a clear sign that something is wrong.
- Win rate: 68-73% (distribution fade), 65-70% (accumulation fade)
- R:R: 2:1 to 3:1
- Target: Put wall (distribution) or call wall (accumulation)

**Regime B (moderate positive gamma):**
- Similar to Regime A but with slightly more price movement during the distribution/accumulation period
- Win rate: 65-70%
- R:R: 2:1 to 3:1

**Regime C (weak positive gamma / near flip):**
- Distribution in Regime C can trigger a flip cross (see gamma-flip-cross.md)
- Win rate: 65-70%
- R:R: 2.5:1 to 4:1 (if the distribution triggers a flip cross, the move is amplified)

**Regime D (negative gamma, controlled):**
- Distribution and accumulation are harder to identify in negative gamma (everything looks like distribution in a downtrend)
- Win rate: 60-65%
- R:R: 2:1 to 3:1
- Require 5/5 conviction in Regime D

**Regime E (negative gamma, crisis):**
- Accumulation fade is very difficult in Regime E (hard to distinguish from a dead-cat bounce)
- Distribution fade is more reliable (the distribution is amplified by negative gamma)
- Win rate: 58-63%
- Reduce position size by 50%

---

## 3. Entry Conditions (All Four Rivers + Derived)

### The Distribution/Accumulation Detection Phase

Before entering the trade, the distribution or accumulation pattern must be confirmed. This takes 30-90 minutes of observation. Do not rush the entry.

**Distribution confirmed when ALL FOUR of the following are present:**
1. Calls-at-bid > calls-at-ask by at least 1.5:1 on Massive (call selling dominant)
2. UW dark pool direction is net selling for at least 30 consecutive minutes
3. DOM shows icebergs on the ask side at or within 5 ticks of current price
4. Call OI declining on FlashAlpha (at least 5% decline from session high)

**Accumulation confirmed when ALL FOUR of the following are present:**
1. Puts-at-bid > puts-at-ask by at least 1.5:1 on Massive (put selling dominant)
2. UW dark pool direction is net buying for at least 30 consecutive minutes
3. DOM shows icebergs on the bid side at or within 5 ticks of current price
4. Put OI declining on FlashAlpha (at least 5% decline from session high)

Three of four = probable. Four of four = confirmed. Only trade confirmed patterns.

### FlashAlpha (Structure) — Required
- OI is shifting in the direction of the institutional flow (call OI declining for distribution, put OI declining for accumulation)
- The shift must be at least 5% from the session high/low
- GEX is consistent with the regime requirements above
- DEX is shifting in the direction of the institutional flow

### Massive.com (Flow) — Required
- The visible flow is in the OPPOSITE direction of the institutional flow (this is the divergence)
- Distribution: Call volume is elevated but calls-at-bid > calls-at-ask (visible bullish flow is actually selling)
- Accumulation: Put volume is elevated but puts-at-bid > puts-at-ask (visible bearish flow is actually selling)
- The visible flow must have been present for at least 30 minutes (not just a brief spike)

### Unusual Whales (Dark) — Required (most critical)
- Dark pool direction is OPPOSITE to the visible flow
- Distribution: Dark pool is net selling while visible flow appears bullish
- Accumulation: Dark pool is net buying while visible flow appears bearish
- Net dark premium must be at least $10M in the institutional direction
- Institutional sweep alerts confirming the dark pool direction
- The dark pool signal must have been present for at least 30 minutes

### Rithmic MBO (DOM) — Required
- Icebergs on the institutional side (ask for distribution, bid for accumulation)
- Absorption visible (price not moving proportionally to volume)
- Spoofed orders on the visible flow side (bids that pull for distribution, offers that pull for accumulation)
- Market orders in the visible flow direction being absorbed without price advancing

### Derived — Supporting
- Max pain is in the direction of the institutional flow (distribution: max pain below current price; accumulation: max pain above)
- 0DTE walls are in the direction of the institutional flow
- Expected move range: price is near the top of the EM range for distribution, near the bottom for accumulation

---

## 4. Entry Execution

**The critical rule: Do NOT enter during the distribution/accumulation period.**

During distribution, price is still supported by the institutional selling (they need the retail buying to absorb their exits). During accumulation, price is still pressured by the institutional buying (they need the retail selling to fill their positions). Entering during the process means fighting the institutional flow.

Enter AFTER the process ends, on the first sign of transition.

### Distribution Fade Entry (Short)

**Entry signal:** The FIRST red candle with above-average volume (at least 1.5x average) after the distribution period ends.

This candle represents the moment when:
- The institutional selling has finished (or paused)
- The retail buying has stopped (no more buyers to absorb the selling)
- The bid disappears (the spoofed support that was encouraging retail buying is gone)
- Price drops on its own weight

**Entry technique:** Limit order at the close of the first red candle, or market order on the open of the second red candle if the first was very large (indicating strong momentum).

**Alternative entry:** If the first red candle is very small (less than 5 ticks), wait for the second red candle to confirm the transition. A single small red candle may be noise.

**DOM confirmation at entry:**
- Bids pulling (the spoofed support is disappearing)
- Offers holding or reloading (sellers are not retreating)
- Icebergs on the ask disappearing (the institutional selling is complete — they don't need to hide anymore)
- Market sells beginning to dominate (retail longs are starting to exit)

### Accumulation Fade Entry (Long)

**Entry signal:** The FIRST green candle with above-average volume (at least 1.5x average) after the accumulation period ends.

**Entry technique:** Limit order at the close of the first green candle, or market order on the open of the second green candle.

**DOM confirmation at entry:**
- Offers pulling (the spoofed resistance is disappearing)
- Bids holding or reloading
- Icebergs on the bid disappearing
- Market buys beginning to dominate

---

## 5. Stop Loss Rules

**Distribution Fade (Short) Stop:**
New high above the distribution zone. If price makes a new high above the highest price during the distribution period, the distribution pattern has failed.

Stop distance: Typically 15-25 NQ ticks above the distribution zone high. The exact distance depends on the size of the distribution zone.

**Accumulation Fade (Long) Stop:**
New low below the accumulation zone. If price makes a new low below the lowest price during the accumulation period, the accumulation pattern has failed.

Stop distance: Typically 15-25 NQ ticks below the accumulation zone low.

**Why these stops:** The distribution/accumulation zone is the price range where the institutional activity occurred. If price returns to a new extreme within that zone, the institutional activity was not distribution/accumulation — it was something else (genuine buying/selling, hedging, etc.). The trade is wrong.

**DOM-based stop:** If the icebergs on the institutional side RETURN after the entry (the institution is still active), exit immediately. The distribution/accumulation may not be complete.

**Regime C adjustment:** Tighten stop by 20% (the regime is less stable and a failed distribution/accumulation in Regime C can trigger a violent reversal).

---

## 6. Profit Target Rules

**Distribution Fade (Short) Targets:**
- Primary: Put wall (the nearest significant put OI concentration below current price)
- Secondary: HVL (High Volume Level from the volume profile)
- Tertiary: Gamma flip level (if below current price)

**Accumulation Fade (Long) Targets:**
- Primary: Call wall
- Secondary: HVL
- Tertiary: Gamma flip level (if above current price)

**Target selection:** Use the nearest target that is at least 2x the stop distance away. If the put wall is 30 ticks away and the stop is 20 ticks, the R:R is 1.5:1 — insufficient. Wait for a better entry or skip the trade.

**Partial profit taking:**
- Take 50% at the primary target
- Let remaining 50% run to the secondary target
- Move stop to breakeven after taking first partial

**The cascade scenario:** Distribution fades often trigger a cascade of retail stop-outs. The initial move to the put wall may be followed by a further move as the stop-outs create additional selling. In this case, hold the remaining 50% with a trailing stop (trail by 20 NQ ticks) rather than a fixed target.

---

## 7. Position Sizing

| Conviction | Position Size | Notes |
|---|---|---|
| 4/4 confirmed (all four signals) + DOM transition | 75% of max | Highest conviction distribution/accumulation |
| 4/4 confirmed (all four signals) | 50% of max | Standard distribution/accumulation |
| 3/4 probable | 37% of max | Reduced conviction |
| 2/4 or below | 0% | Do not trade |

**Regime adjustments:**
- Regime A/B: Standard sizes (most reliable)
- Regime C: Standard sizes (but be ready for flip cross amplification)
- Regime D: Reduce all sizes by 25%
- Regime E: Reduce all sizes by 50%

**The "cascade bonus":** If the distribution/accumulation is confirmed AND the regime is C (near flip), increase position size by 25%. The potential for a flip cross amplifies the expected move.

---

## 8. Order Book Confirmation

**During the distribution/accumulation period (observation phase):**
- Icebergs on the institutional side (ask for distribution, bid for accumulation)
- Absorption visible (price not moving proportionally to volume)
- Spoofed orders on the visible flow side
- Market orders in the visible flow direction being absorbed

**At the transition moment (entry phase):**
- Icebergs disappearing (the institution has finished)
- Spoofed orders pulling (the fake support/resistance is gone)
- Market orders shifting to the institutional direction
- Aggression imbalance shifting

**After entry (trade management phase):**
- Market orders in the trade direction dominating
- No icebergs on the opposite side of the trade
- Book thinning in the trade direction (clear path to target)
- Retail stop-outs visible (large market orders in the trade direction as stops are hit)

**The "stop-out cascade" DOM signature:** As retail longs (distribution) or shorts (accumulation) get stopped out, the DOM shows a series of large market orders in the trade direction. These are the stop-outs. Each stop-out creates more momentum. The DOM aggression imbalance increases sharply during the stop-out cascade.

---

## 9. Win Rate and R:R Estimates

| Variant | Regime | Win Rate | R:R | Expected Value |
|---|---|---|---|---|
| Distribution Fade | A | 68-73% | 2:1 to 3:1 | +1.04R to +1.65R |
| Distribution Fade | B | 65-70% | 2:1 to 3:1 | +0.95R to +1.40R |
| Distribution Fade | C | 65-70% | 2.5:1 to 4:1 | +1.28R to +2.10R |
| Distribution Fade | D | 60-65% | 2:1 to 3:1 | +0.60R to +1.00R |
| Accumulation Fade | A | 68-73% | 2:1 to 3:1 | +1.04R to +1.65R |
| Accumulation Fade | B | 65-70% | 2:1 to 3:1 | +0.95R to +1.40R |
| Accumulation Fade | C | 65-70% | 2.5:1 to 4:1 | +1.28R to +2.10R |
| Accumulation Fade | D | 60-65% | 2:1 to 3:1 | +0.60R to +1.00R |

**Why the R:R is 2:1 to 3:1:** The reversal after distribution/accumulation is amplified by retail stop-outs. The retail longs (distribution) or shorts (accumulation) all have stops in roughly the same place. When those stops are hit, they create additional momentum in the trade direction. This stop-out cascade is what drives the 2:1 to 3:1 R:R.

---

## 10. Failure Modes

### Failure Mode 1: New Buyers/Sellers Overwhelm the Pattern

A large new participant enters the market and overwhelms the institutional activity. Price makes a new extreme beyond the distribution/accumulation zone.

**Detection:** Price makes a new high above the distribution zone (distribution fade) or a new low below the accumulation zone (accumulation fade).
**Response:** Exit immediately. The stop is at the new extreme for exactly this reason.

### Failure Mode 2: The Pattern Was Hedging, Not Distribution/Accumulation

The visible flow and dark pool activity was legitimate hedging, not distribution/accumulation. The institution is not exiting their position — they're protecting it.

**Prevention:** Apply the hedging vs. distribution/accumulation discriminators from step4-cross-validation/distribution-accumulation.md. Far OTM, long-dated options = hedging. Near-ATM, short-dated options = directional.

### Failure Mode 3: Premature Entry (During the Pattern)

Entering the trade during the distribution/accumulation period rather than after it ends. The institutional activity is still ongoing and the price is still supported/pressured.

**Prevention:** Wait for the transition signal (first red/green candle with above-average volume). Do not enter during the pattern.

### Failure Mode 4: Regime Transition Reversal

A regime transition occurs that reverses the expected move. For example, a distribution fade (short) in Regime C is entered, but the regime transitions to D/E in the wrong direction (price rallies through the flip).

**Detection:** Price crosses the gamma flip in the opposite direction of the trade.
**Response:** Exit immediately. The regime transition overrides the distribution/accumulation pattern.

### Failure Mode 5: Dark Pool Data Lag

UW dark pool data has a 5-15 minute reporting lag. The dark pool signal that appears to be current may actually be 15 minutes old. In fast-moving markets, the dark pool direction may have already reversed.

**Prevention:** Check the timestamp of the UW data. If the most recent dark pool data is more than 20 minutes old, treat it as stale and reduce conviction by one level.

---

## 11. Example Scenarios

### Example 1: Distribution Fade in Regime B

**Setup:**
- NQ has rallied from 19,400 to 19,650 over the morning session. It's now 11:30 AM.
- FlashAlpha: GEX = $280M (Regime B). Call OI at 19,650 strike has declined from 48,000 to 41,000 contracts (15% decline). DEX shifting positive.
- Massive: Call volume is 2.5x average but 62% of calls are at the bid (selling). Net premium slightly positive but declining.
- UW: Dark pool net selling for 75 minutes. Net dark premium -$22M. Institutional selling alerts present.
- DOM: Iceberg on the ask at 19,650. Market buys being absorbed. Bids at 19,630 have pulled twice when tested.

**Distribution confirmed:** All four signals present. 4/4 confirmed.

**Observation phase:** 10:00 AM to 11:30 AM (90 minutes of distribution).

**Transition signal:** At 11:42 AM, first red candle with 2.1x average volume. Bids at 19,630 pull simultaneously. Iceberg on ask disappears.

**Entry:** Short at 19,645 (limit order at close of first red candle).
**Stop:** 19,675 (25 ticks above distribution zone high of 19,650).
**Target 1:** Put wall at 19,500 (145 ticks). Take 50%.
**Target 2:** HVL at 19,420 (225 ticks). Let remaining 50% run.
**Size:** 50% of maximum (4/4 confirmed, standard size).

**Result:** Price drops from 19,645 to 19,498 over 45 minutes (first partial, 147 ticks). Stop-out cascade visible in DOM. Price continues to 19,435 (second partial, 210 ticks). Average exit: 178.5 ticks. Stop was 30 ticks. R:R achieved: 5.95:1.

### Example 2: Accumulation Fade in Regime C

**Setup:**
- NQ has fallen from 19,300 to 19,050 over the morning session. It's now 12:15 PM.
- FlashAlpha: GEX = $55M (Regime C, near flip at 19,000). Put OI at 19,050 strike has declined from 52,000 to 44,000 contracts (15% decline). DEX shifting negative.
- Massive: Put volume is 2x average but 58% of puts are at the bid (selling). Net premium slightly negative but improving.
- UW: Dark pool net buying for 60 minutes. Net dark premium +$18M. Institutional buying alerts present.
- DOM: Iceberg on the bid at 19,050. Market sells being absorbed. Offers at 19,070 have pulled twice when tested.

**Accumulation confirmed:** All four signals present. 4/4 confirmed.

**Transition signal:** At 12:28 PM, first green candle with 1.8x average volume. Offers at 19,070 pull simultaneously. Iceberg on bid disappears.

**Entry:** Long at 19,055 (limit order at close of first green candle).
**Stop:** 19,025 (30 ticks below accumulation zone low of 19,050).
**Target 1:** Call wall at 19,200 (145 ticks). Take 50%.
**Target 2:** HVL at 19,280 (225 ticks). Let remaining 50% run.
**Size:** 62% of maximum (4/4 confirmed, Regime C cascade bonus applied: 50% × 1.25).

**Result:** Price rallies from 19,055 to 19,205 over 50 minutes (first partial, 150 ticks). Short-squeeze cascade visible. Price continues to 19,275 (second partial, 220 ticks). Average exit: 185 ticks. Stop was 30 ticks. R:R achieved: 6.2:1.

---

## 12. Anti-Patterns (When It Looks Like This Setup But Isn't)

### Anti-Pattern 1: Genuine Bullish Flow Mistaken for Distribution

Strong call buying that is genuinely bullish (calls at ask, new OI building, dark pool buying) is mistaken for distribution because the call volume is high.

**Key discriminator:** Calls at ask = genuine buying. Calls at bid = distribution. Always check the bid/ask side.

### Anti-Pattern 2: Hedging Mistaken for Distribution

Far OTM, long-dated put buying is mistaken for distribution. The institution is hedging their long position, not exiting it.

**Key discriminator:** Near-ATM, short-dated = directional. Far OTM, long-dated = hedging.

### Anti-Pattern 3: Entering During the Pattern

Entering the short during the distribution period (while price is still supported). The institutional selling is still ongoing and the retail buying is still absorbing it. Price may continue higher before reversing.

**Prevention:** Wait for the transition signal. Do not enter during the pattern.

### Anti-Pattern 4: Dark Pool Data Is Stale

The UW dark pool data is 20+ minutes old and the dark pool direction has already reversed. The "distribution" signal is based on stale data.

**Prevention:** Check the timestamp of UW data. If stale, reduce conviction and wait for updated data.

### Anti-Pattern 5: Distribution in Regime E

Attempting a distribution fade in Regime E. In Regime E, everything looks like distribution (the market is in crisis). The pattern is too noisy to trade reliably.

**Response:** Do not trade distribution/accumulation fades in Regime E. The regime is too chaotic.

---

## 13. Time-of-Day Considerations

**9:30-10:00 AM (Opening):**
- Distribution/accumulation patterns rarely develop in the first 30 minutes (not enough time)
- Use the opening to observe and identify potential patterns
- Do not trade this setup in the first 30 minutes

**10:00 AM-12:00 PM (Morning session):**
- Best time for distribution/accumulation patterns to develop
- 90-minute patterns are common in this window
- The transition signal often occurs between 11:00 AM and 12:00 PM

**12:00-1:30 PM (Lunch lull):**
- Distribution/accumulation patterns can develop during the lunch lull
- The low volume makes the pattern easier to see (less noise)
- The transition signal may be delayed until the afternoon session begins

**1:30-3:00 PM (Afternoon session):**
- Distribution/accumulation patterns that developed in the morning often resolve in the afternoon
- The transition signal may occur as afternoon volume picks up
- Good time for distribution/accumulation fade entries

**3:00-4:00 PM (Power hour):**
- Distribution/accumulation patterns that haven't resolved by 3:00 PM may resolve violently in the last hour
- Charm flows can accelerate the resolution
- Reduce position size by 25% for entries after 3:00 PM (less time for the trade to develop)
- Do not enter distribution/accumulation fades after 3:30 PM (insufficient time)

**OPEX Fridays:**
- Distribution is most common on OPEX Fridays (institutions rolling positions)
- The transition signal on OPEX Friday is often sharp and clear
- Increase position size by 25% on OPEX Friday distribution/accumulation fades
