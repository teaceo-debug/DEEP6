# Setup 1: Wall Bounce

## Overview

The Wall Bounce is the highest-frequency setup in the Options Bias Engine. It exploits the mechanical behavior of dealers who must buy at put walls and sell at call walls to maintain their delta hedges. In positive gamma regimes, these walls are actively defended — dealers are economically incentivized to prevent price from moving through them because doing so would increase their hedging costs.

The setup has two variants: the call wall short (fade the ceiling) and the put wall long (fade the floor). The put wall long in Regime C is the best variant in the system, with a 75-80% historical win rate when all conditions are met.

This is NOT a setup for negative gamma regimes. In Regime D or E, walls break routinely and the mechanical defense disappears. Trading wall bounces in negative gamma is one of the most common and costly mistakes in options-flow trading.

---

## 1. Setup Name and Overview

**Name:** Wall Bounce (Call Wall Short / Put Wall Long)
**Type:** Mean-reversion fade
**Frequency:** 2-5 times per week per wall
**Best variant:** Put wall long in Regime C (75-80% WR)
**Worst variant:** Any wall bounce in Regime D or E (do not trade)

The setup fades price as it approaches a GEX wall, anticipating that the wall will hold and price will reverse toward the center of the range (HVL or mid-range between walls).

---

## 2. Regime Requirements

**Valid regimes:** A, B, C ONLY.

**Regime A (strong positive gamma, GEX > $500M):**
- Both call wall and put wall are strongly defended
- Win rate: 70-75% at call wall, 72-78% at put wall
- Target: Full range to opposite wall or HVL
- Stop: 12-15 ticks beyond wall

**Regime B (moderate positive gamma, GEX $100M-$500M):**
- Walls are defended but with less mechanical force
- Win rate: 68-73% at call wall, 70-75% at put wall
- Target: HVL or mid-range (not necessarily opposite wall)
- Stop: 12-15 ticks beyond wall

**Regime C (weak positive gamma / near flip, GEX $0-$100M):**
- Put wall long is the best variant (75-80% WR) because the put wall is the last line of defense before regime transition
- Call wall short is less reliable (60-65% WR) because the call wall may not be strongly defended
- Target: HVL (conservative) or mid-range
- Stop: 10-12 ticks beyond wall (tighter because regime is less stable)
- Note: If price breaks the put wall in Regime C, the regime transitions to D or E. This is a critical level.

**NEVER trade in Regime D or E.** In negative gamma, walls break routinely. The mechanical defense that makes this setup work does not exist in negative gamma.

---

## 3. Entry Conditions (All Four Rivers + Derived)

All conditions must be met before entry. Missing any condition reduces the setup to a lower conviction level.

### FlashAlpha (Structure) — Required
- GEX is positive (Regime A, B, or C confirmed)
- The wall being traded is clearly identified (call wall or put wall with significant OI concentration)
- Price is within 10 NQ ticks of the wall
- DEX is in the direction that supports the bounce (negative DEX at put wall = dealers must buy; positive DEX at call wall = dealers must sell)
- The wall has not been tested and broken earlier in the session (a wall that has already been broken once is significantly weaker)

### Massive.com (Flow) — Required
- Flow is DECLINING as price approaches the wall. This is critical. If flow is INCREASING (accelerating sweeps, escalating premium), the wall may break. Declining flow means the momentum is exhausting.
- At call wall: call buying is declining (fewer sweeps, lower premium). The buyers are running out of conviction.
- At put wall: put buying is declining (fewer sweeps, lower premium). The sellers are running out of conviction.
- No sweep cascade in the direction of the wall approach (3+ sweeps in the same direction within 5 minutes = wall may break)
- Net premium is not aggressively one-sided (within $10M of neutral, or moving toward neutral)

### Unusual Whales (Dark) — Required
- Dark pool is NOT attacking the wall. Dark pool direction should be neutral or in the direction of the bounce.
- At call wall: dark pool should not be buying aggressively (dark buying at the call wall = institutional conviction that the wall will break)
- At put wall: dark pool should not be selling aggressively (dark selling at the put wall = institutional conviction that the wall will break)
- No institutional sweep alerts in the direction of the wall approach

### Rithmic MBO (DOM) — Required (most critical)
- Resting orders at the wall that RELOAD after being hit. This is the single most important DOM condition. If the wall is not reloading, do not take the trade.
- At call wall: resting offers at the wall level that replenish after each fill. The sellers are defending the level.
- At put wall: resting bids at the wall level that replenish after each fill. The buyers are defending the level.
- Icebergs at the wall level (hidden orders that continuously replenish) are the strongest confirmation
- Aggression imbalance is NOT strongly in the direction of the wall approach (if market buys are 3:1 over market sells at the put wall, the wall may break)
- No absorption failure: price should not be advancing through the wall despite the resting orders

### Derived — Supporting
- Price is within the expected move range (not at or beyond the EM boundary)
- Max pain is on the bounce side (at put wall: max pain above current price; at call wall: max pain below)
- 0DTE wall positions confirm the GEX wall (the 0DTE call/put wall is at or near the GEX wall)

---

## 4. Entry Execution

**Entry technique:** Limit order at the wall level, or limit order 2-3 ticks inside the wall (slightly better price, slightly higher risk of not filling).

**Preferred entry:** Place a limit order at the exact wall level. If price touches the wall and the DOM shows defense (reloading orders, icebergs), the limit order fills at the best possible price.

**Alternative entry:** If price has already touched the wall and bounced 5-10 ticks, enter on the first pullback back toward the wall (within 5 ticks of the wall). This is a slightly worse price but confirms that the initial bounce was real.

**Do NOT:** Enter before price reaches the wall. The wall bounce only works AT the wall. Entering 20 ticks away in anticipation is a different trade with different risk/reward.

**Do NOT:** Chase the bounce if price has already moved 20+ ticks away from the wall. The opportunity has passed.

**Timing:** The best entries are in the first 30 minutes after the wall is first tested. Subsequent tests of the same wall in the same session have lower win rates (the wall is being worn down).

---

## 5. Stop Loss Rules

**Primary stop:** 12-15 NQ ticks beyond the wall level.

- At call wall (short): Stop is 12-15 ticks ABOVE the call wall. If price closes above the call wall by 12+ ticks, the wall has broken and the trade is wrong.
- At put wall (long): Stop is 12-15 ticks BELOW the put wall. If price closes below the put wall by 12+ ticks, the wall has broken and the trade is wrong.

**Why 12-15 ticks:** The wall can be temporarily penetrated by a sweep or a large market order without actually breaking. A 12-15 tick buffer filters out these temporary penetrations. Beyond 15 ticks, the wall has genuinely broken.

**Regime C adjustment:** Tighten to 10-12 ticks. The regime is less stable and a wall break in Regime C is more significant (it triggers a regime transition).

**DOM-based stop:** If the resting orders at the wall STOP reloading (the wall is being consumed without replenishment), exit immediately regardless of price. The wall is breaking. Do not wait for the price-based stop.

**Spoof detection stop:** If a large order appears at the wall on the OPPOSITE side of your trade and then pulls (spoof), reduce position size by 50% immediately. The spoof is designed to push price through your stop.

---

## 6. Profit Target Rules

**Primary target:** HVL (High Volume Level from the volume profile). This is the price level with the highest historical volume, which acts as a magnet for price.

**Secondary target:** Mid-range between the call wall and put wall. If the call wall is at 20,000 and the put wall is at 19,600, the mid-range is 19,800.

**Tertiary target (Regime A only):** Opposite wall. In strong positive gamma, price often oscillates between the call wall and put wall. A put wall bounce can target the call wall.

**Target selection by regime:**
- Regime A: Opposite wall (full range)
- Regime B: HVL or mid-range
- Regime C: HVL (conservative) — the regime may transition before price reaches mid-range

**Partial profit taking:**
- Take 50% of position at HVL
- Let remaining 50% run to mid-range or opposite wall
- Move stop to breakeven after taking first partial

**Time-based exit:** If the trade has not reached the first target within 45 minutes (Regime A/B) or 30 minutes (Regime C), exit at market. The wall bounce is a short-duration trade. If it's not working within the expected timeframe, the setup has failed.

---

## 7. Position Sizing

Based on conviction level from the conviction matrix (see step4-cross-validation/conviction-matrix.md):

| Conviction | Position Size | Notes |
|---|---|---|
| 5/5 (all conditions met + DOM icebergs) | 100% of max | Rare. Requires iceberg confirmation. |
| 4/5 (all required conditions met) | 75% of max | Standard wall bounce size |
| 3/5 (one required condition missing) | 50% of max | Reduce target to HVL only |
| 2/5 or below | 0% | Do not trade |

**Maximum position size for wall bounce:** 2 NQ contracts per $100,000 of account equity (standard risk management). Adjust based on account size and risk tolerance.

**Regime C adjustment:** Reduce all sizes by 25% due to regime instability. A 4/5 conviction trade in Regime C is sized at 56% of max (75% × 75%).

---

## 8. Order Book Confirmation

The DOM is the most critical confirmation for the wall bounce. Without DOM confirmation, do not take the trade regardless of what the other rivers show.

**Required DOM conditions:**

1. **Resting orders at the wall that reload:** The single most important condition. Watch the DOM for 60-90 seconds before entry. If the resting orders at the wall level are being hit and NOT reloading, the wall is being consumed. Do not enter.

2. **Iceberg detection:** If an iceberg is present at the wall level (small visible quantity that continuously replenishes), this is the strongest possible DOM confirmation. Conviction +1 (see conviction-matrix.md).

3. **Aggression imbalance NOT strongly against the bounce:** If market orders are 3:1 or more in the direction of the wall approach, the wall may break. The aggression imbalance should be less than 2:1 against the bounce direction.

4. **No absorption failure:** Price should not be advancing through the wall despite the resting orders. If price is slowly grinding through the wall tick by tick, the wall is failing. Do not enter.

**DOM check timing:** Check the DOM 60-90 seconds before entry, at entry, and every 30 seconds while in the trade. The DOM can change rapidly.

**The "no reload" rule:** If the resting orders at the wall stop reloading at any point — before entry or while in the trade — exit immediately. This is the most reliable signal that the wall is breaking.

---

## 9. Win Rate and R:R Estimates

| Variant | Regime | Win Rate | R:R | Expected Value |
|---|---|---|---|---|
| Put wall long | A | 72-78% | 1.5:1 to 2.5:1 | +0.83R to +1.20R |
| Put wall long | B | 70-75% | 1.5:1 to 2:1 | +0.75R to +1.00R |
| Put wall long | C | 75-80% | 1:1 to 1.5:1 | +0.50R to +0.90R |
| Call wall short | A | 70-75% | 1.5:1 to 2.5:1 | +0.75R to +1.13R |
| Call wall short | B | 68-73% | 1.5:1 to 2:1 | +0.70R to +0.96R |
| Call wall short | C | 60-65% | 1:1 to 1.5:1 | +0.20R to +0.48R |

**Why the put wall long in Regime C is the best variant:**
In Regime C, the put wall is the last line of defense before regime transition. Dealers have the strongest incentive to defend it because a break would trigger a cascade of hedging activity. The mechanical defense is at its maximum at this level. Additionally, the risk/reward is favorable because the stop is tight (10-12 ticks) and the bounce, if it happens, is often sharp.

---

## 10. Failure Modes

### Failure Mode 1: Sweep Cascade Overwhelms the Wall

A cascade of 3+ sweeps in the direction of the wall approach within 5 minutes. The sweeps represent urgent, large-scale buying or selling that can overwhelm even a well-defended wall. A $20M sweep can consume the resting orders at a wall in seconds.

**Detection:** Massive shows 3+ sweeps in the same direction within 5 minutes, escalating in size.
**Response:** Do not enter. If already in the trade, exit immediately. The wall is breaking.

### Failure Mode 2: Dark Pool Attack

Institutional dark pool activity in the direction of the wall approach. If UW shows institutional buying at the call wall or institutional selling at the put wall, the institution has conviction that the wall will break.

**Detection:** UW shows dark pool direction in the direction of the wall approach, with net dark premium > $15M.
**Response:** Do not enter. The institutional conviction overrides the mechanical defense.

### Failure Mode 3: Stale Wall (OI Has Shifted)

The GEX wall was computed from yesterday's OI, but today's flow has shifted the OI. The wall exists on paper but nobody is defending it.

**Detection:** DOM shows no resting orders at the wall level, or resting orders that do not reload. FlashAlpha shows declining OI at the wall strike.
**Response:** Do not enter. The wall is stale. Consider a wall break trade instead.

### Failure Mode 4: Regime Transition During Trade

Price breaks the put wall in Regime C, triggering a transition to Regime D or E. The mechanical defense disappears and the move accelerates.

**Detection:** Price closes 12+ ticks below the put wall in Regime C. FlashAlpha GEX drops below zero.
**Response:** Exit immediately. The regime has changed and the wall bounce setup no longer applies.

### Failure Mode 5: Second or Third Test of the Same Wall

A wall that has been tested multiple times in the same session is progressively weaker. Each test consumes some of the resting orders. By the third test, the wall may have insufficient defense to hold.

**Detection:** This is the second or third approach to the same wall in the same session.
**Response:** Reduce position size by 50% for the second test. Do not trade the third test.

---

## 11. Example Scenarios

### Example 1: Put Wall Long in Regime C (Best Variant)

**Setup:**
- NQ at 19,250. Put wall at 19,200 (large put OI concentration). GEX = $80M (Regime C).
- FlashAlpha: GEX positive but weak. Put wall at 19,200 with 65,000 contracts OI. DEX negative (dealers must buy).
- Massive: Put flow declining as price approaches 19,200. Net put premium was -$12M at 10 AM, now -$8M at 11:30 AM. No sweep cascade.
- UW: Dark pool neutral. No institutional selling alerts.
- DOM: Resting bids at 19,200 (500 contracts visible). Bids reload after each hit. Iceberg detected (quantity resets to 500 after each fill).
- Derived: Max pain at 19,350 (above current price). EM low at 19,150 (below the put wall).

**Conviction score:** STRUCTURE bullish (+1), FLOW bullish (+1, declining put flow), DARK neutral (0), DOM bullish (+1, iceberg), DERIVED bullish (+1). Score: +4. High conviction. Iceberg multiplier: +1 level. Effective conviction: Maximum.

**Entry:** Limit order at 19,200. Filled as price touches the put wall.
**Stop:** 19,188 (12 ticks below put wall).
**Target 1:** HVL at 19,320 (120 ticks). Take 50% here.
**Target 2:** Mid-range at 19,400 (200 ticks). Let remaining 50% run.
**Size:** 100% of maximum (maximum conviction).

**Result:** Price bounces from 19,200 to 19,340 over 25 minutes. First partial taken at 19,320 (120 ticks). Stop moved to breakeven (19,200). Price continues to 19,390. Second partial taken at 19,390 (190 ticks). Average exit: 155 ticks. Stop was 12 ticks. R:R achieved: 12.9:1.

### Example 2: Call Wall Short in Regime A

**Setup:**
- NQ at 19,980. Call wall at 20,000. GEX = $650M (Regime A).
- FlashAlpha: Strong positive GEX. Call wall at 20,000 with 80,000 contracts OI. DEX positive (dealers must sell).
- Massive: Call flow declining as price approaches 20,000. Call sweeps were 4:1 over puts at 10 AM, now 1.5:1 at 2 PM. No sweep cascade.
- UW: Dark pool neutral. No institutional buying alerts at 20,000.
- DOM: Resting offers at 20,000 (800 contracts visible). Offers reload after each hit. No iceberg but consistent reload.
- Derived: Max pain at 19,800 (below current price). EM high at 20,050 (above the call wall).

**Conviction score:** STRUCTURE bearish (+1 for short), FLOW bearish (+1, declining call flow), DARK neutral (0), DOM bearish (+1, reloading offers), DERIVED bearish (+1, max pain below). Score: +4 bearish. High conviction.

**Entry:** Limit order at 20,000. Filled as price touches the call wall.
**Stop:** 20,015 (15 ticks above call wall).
**Target 1:** HVL at 19,850 (150 ticks). Take 50% here.
**Target 2:** Mid-range at 19,750 (250 ticks). Let remaining 50% run.
**Size:** 75% of maximum (high conviction, not maximum because no iceberg).

**Result:** Price touches 20,000, bounces to 19,840 over 35 minutes. First partial at 19,850 (150 ticks). Stop moved to breakeven. Price reaches 19,780. Second partial at 19,780 (220 ticks). Average exit: 185 ticks. Stop was 15 ticks. R:R achieved: 12.3:1.

---

## 12. Anti-Patterns (When It Looks Like This Setup But Isn't)

### Anti-Pattern 1: Wall Approach with Sweep Cascade

Price approaches the wall AND there are 3+ sweeps in the same direction within 5 minutes. This LOOKS like a wall bounce setup (price at wall) but the sweep cascade signals that the wall will break. Do not trade.

### Anti-Pattern 2: Wall Approach in Negative Gamma

Price approaches a "wall" level in Regime D or E. The level may have had significant OI in the past, but in negative gamma, the mechanical defense is absent. The level will likely break. Do not trade.

### Anti-Pattern 3: Wall Approach with Dark Pool Attack

Price approaches the wall AND UW shows institutional dark pool activity in the direction of the approach. The institution has conviction that the wall will break. Do not trade.

### Anti-Pattern 4: Wall Approach with No DOM Defense

Price approaches the wall but the DOM shows no resting orders, or resting orders that do not reload. The wall is stale or undefended. Do not trade.

### Anti-Pattern 5: Third Test of the Same Wall

Price approaches the wall for the third time in the same session. The wall has been worn down by the previous two tests. Win rate drops to 45-55%. Do not trade (or trade at 25% size maximum).

---

## 13. Time-of-Day Considerations

**9:30-10:00 AM (Opening):**
- Walls are often tested immediately at the open
- High volatility makes DOM signals less reliable
- Avoid wall bounce trades in the first 15 minutes
- Best to wait for the opening range to establish before trading walls

**10:00 AM-12:00 PM (Morning session):**
- Best time for wall bounce trades
- Volume is high, DOM signals are reliable
- Walls are freshly established and well-defended
- Win rate is at its highest during this window

**12:00-1:30 PM (Lunch lull):**
- Volume drops significantly
- DOM signals are less reliable (thin book)
- Wall bounces can still work but with lower conviction
- Reduce position size by 25% during this window

**1:30-3:00 PM (Afternoon session):**
- Volume picks up again
- Charm flows begin to influence price (see step5-setups/charm-flow.md)
- Wall bounces are reliable but may be shorter in duration (charm flows can override)
- Good time for wall bounce trades

**3:00-4:00 PM (Power hour):**
- Charm flows are strongest
- 0DTE options are expiring, creating mechanical flows
- Wall bounces can be very sharp and fast
- Reduce target to HVL only (don't hold for mid-range in the last hour)
- Tighten stops by 20% (faster moves in both directions)

**OPEX Fridays:**
- Walls are most strongly defended (maximum OI, maximum dealer hedging)
- Put wall long is the highest-conviction trade of the month on OPEX Friday
- Win rate can reach 80-85% on OPEX Friday put wall long in Regime A or B
- Increase position size by 25% on OPEX Friday (if all conditions met)
