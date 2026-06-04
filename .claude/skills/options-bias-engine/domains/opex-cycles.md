# OPEX Cycles: Expiration Calendar, Market Structure Effects, and Level Recalibration

## The Expiration Calendar: A Hierarchy of Events

Options expiration is not a single event. It's a hierarchy of overlapping cycles, each with different OI magnitudes, different market impacts, and different implications for GEX structure.

### Daily: 0DTE (Every Trading Day)

Since 2022, SPX and NDX offer 0DTE options every trading day. QQQ 0DTE is also available daily. This has fundamentally changed intraday market structure.

- OI magnitude: Moderate (builds throughout the day, expires at close)
- Market impact: Intraday pinning, gamma explosion in final hours
- GEX contribution: Significant intraday, zero post-close
- Frequency: Every trading day
- See zero-dte-mechanics.md for full treatment

### Weekly: Standard Weekly Options (Every Friday)

Standard weekly options expire every Friday (except when a monthly or quarterly OPEX falls on that Friday). These are the "bread and butter" of retail options trading.

- OI magnitude: Moderate to significant (builds over the week)
- Market impact: Friday pinning, weekly wall dynamics
- GEX contribution: Meaningful throughout the week, peaks on Friday
- Frequency: Every Friday (except monthly/quarterly OPEX Fridays)

Weekly options create a weekly rhythm in market structure:
- Monday: New weekly options begin trading. Initial OI is thin.
- Tuesday-Wednesday: OI builds. Walls begin to form.
- Thursday: Walls are established. Pinning pressure begins.
- Friday: Expiration. Gamma explosion, pinning, potential break.

### Monthly: Standard Monthly Options (3rd Friday)

Standard monthly options expire on the third Friday of each month. These carry the largest institutional OI of any regular expiration.

- OI magnitude: Large (months of accumulated institutional positions)
- Market impact: Strong pinning in OPEX week, significant unwind at expiry
- GEX contribution: Dominant during OPEX week, major structural reset at expiry
- Frequency: Once per month (12 times per year)

Monthly OPEX is the most important regular expiration event. Institutional hedges, covered call programs, and structured products all use monthly options. The OI at monthly strikes can be 10-50x the OI at weekly strikes.

### Quarterly: Quad Witching (March, June, September, December 3rd Friday)

Quarterly OPEX (the third Friday of March, June, September, and December) is the most significant expiration event of the year. Four classes of derivatives expire simultaneously:

1. Stock index options (SPX, NDX, QQQ)
2. Stock options (individual equities)
3. Stock index futures (ES, NQ)
4. Stock futures (individual equity futures)

- OI magnitude: Maximum (quarterly positions + monthly positions + weekly positions + 0DTE)
- Market impact: Maximum pinning Thursday/Friday morning, maximum volatility Friday afternoon
- GEX contribution: Dominant for the entire quarter, massive reset at expiry
- Frequency: 4 times per year (March, June, September, December)

Quad witching is the single most important event in the options calendar. The OI at quarterly strikes can be 100x the OI at a typical weekly strike. The GEX structure during quad witching week is the most powerful pinning force in the market.

---

## OPEX Week Dynamics: Day-by-Day

### Monday of OPEX Week

The week begins with the expiring options still having 5 days of life. The GEX structure is dominated by the expiring month's OI.

**What happens:**
- Early positioning adjustments. Institutions that want to roll (close current month, open next month) begin doing so.
- The roll is not a directional signal. It's maintenance. But it creates volume spikes at specific strikes.
- The roll pattern: Sell the current month's strike, buy the same (or nearby) strike in the next month.
- This creates apparent "selling" at the current month's strike and "buying" at the next month's strike.

**Market behavior:**
- Generally quiet. The expiring OI is still large, creating strong pinning.
- The market often drifts toward the max pain level (the strike where the most options expire worthless).
- Watch for early roll activity in Massive.com: large spreads (selling one expiry, buying another) are rolls, not directional bets.

**Signal reliability:**
- GEX levels are reliable (OI is stable, not yet rolling significantly)
- Directional flow signals from Massive may be distorted by roll activity
- Treat Monday as a "setup" day, not a "signal" day

### Tuesday-Wednesday of OPEX Week

The gravitational pull toward max pain strengthens. Institutions are rolling positions. The expiring OI is still large.

**What happens:**
- Max pain gravitational pull is at its strongest. Price drifts toward the strike where the most options expire worthless.
- Max pain is computed as: the strike where the total dollar value of expiring options (both calls and puts) is minimized.
- Dealers benefit from max pain (they're short options, so they want options to expire worthless).
- The gravitational pull is not a conspiracy; it's the natural result of dealer hedging maintaining the pin.

**Max pain formula:**
```
Max_pain = argmin over all strikes K of:
           [sum over all call strikes K' <= K of: call_OI(K') × (K - K')]
         + [sum over all put strikes K' >= K of: put_OI(K') × (K' - K)]
```

This is the strike where the total payout to option holders is minimized (and therefore the total loss to option sellers is minimized).

**Market behavior:**
- Price tends to drift toward max pain throughout Tuesday and Wednesday.
- Moves away from max pain face counter-hedging from dealers.
- The drift is slow and grinding, not explosive.
- Volume is moderate (rolling activity continues).

**Signal reliability:**
- Max pain is a reliable gravitational center during OPEX week.
- GEX walls are reliable (OI is still large and stable).
- Directional flow signals are still somewhat distorted by roll activity.

### Thursday of OPEX Week

The day before expiration. Pinning pressure is at its maximum for the week.

**What happens:**
- The expiring options have 1 day of life. Gamma is elevated.
- Pinning is very strong. The market is gravitationally held near the max pain / pin strike.
- Roll activity is mostly complete. The remaining OI is "sticky" (positions that will hold to expiry).
- Volume is often lower than Tuesday-Wednesday (rolling is done, new positions not yet established).

**Market behavior:**
- Often the calmest day of OPEX week. Everything is pinned.
- Realized volatility is typically at its lowest for the week.
- The market oscillates in a narrow range around the pin strike.
- This is the "eye of the storm" before Friday's expiration volatility.

**For quad witching specifically:**
- Thursday before quad witching is often the calmest day of the quarter.
- The pinning force from quarterly OI is at maximum.
- Realized vol can be 30-50% below the weekly average.
- This calm is deceptive. Friday will be volatile.

**Signal reliability:**
- Maximum reliability for GEX levels. The walls are at peak strength.
- Max pain is the most reliable directional signal of the week.
- Fade any moves away from the pin. The gravitational pull is overwhelming.

### OPEX Friday: The Expiration Day

OPEX Friday is the most complex and important day of the month. It has three distinct phases.

**Morning (9:30 AM-12:00 PM): Maximum Pinning**

The expiring options have hours of life. Gamma is elevated. Pinning is at maximum.

- The GEX profile is dominated by the expiring month's OI.
- The pin strike (max pain / highest OI strike) is the gravitational center.
- Moves away from the pin are quickly reversed.
- This is the strongest pinning of the month.

**Midday (12:00-2:00 PM): The Roll and Close**

Institutions that haven't rolled yet are doing so now. OI at expiring strikes begins to drop.

- Roll activity creates volume spikes. Don't confuse rolls with directional bets.
- As OI drops at expiring strikes, the pinning force weakens.
- The GEX profile is changing in real-time as positions close.
- The gamma flip may shift as the balance of call vs. put OI changes.

**Afternoon (2:00-4:00 PM): The Unpin**

The expiring options are in their final hours. Gamma is exploding. But OI is also dropping as positions close.

- The net effect: gamma per remaining contract is very high, but the number of contracts is decreasing.
- The pinning force may be weakening even as gamma per contract is increasing.
- At some point, the remaining OI is too small to maintain the pin.
- When the pin breaks, the move is violent (escaping a gravitational field).

**The OPEX Friday afternoon pattern:**
1. 2:00-3:00 PM: Gamma explosion. Strong pinning if OI is still large.
2. 3:00-3:30 PM: OI dropping rapidly as positions close. Pinning weakening.
3. 3:30-3:45 PM: The "unpin" window. Price may break free from the pin.
4. 3:45-4:00 PM: MOC orders. Large imbalances can create a final directional move.

**The OPEX Friday volatility pattern:**
- Morning: Low volatility (strong pinning)
- Midday: Moderate volatility (rolling activity)
- Afternoon: High volatility (gamma explosion + unpin + MOC orders)
- The afternoon volatility is often the highest of the month.

---

## Post-OPEX Monday: The Most Important Day for Level Recalibration

Post-OPEX Monday is the single most important day for GEX level recalibration. A massive block of OI has just expired. The GEX profile looks completely different.

### Why Post-OPEX Monday Is Critical

On Friday at 4:00 PM, the expiring options cease to exist. Their OI goes to zero. The GEX profile that was dominated by those options is now gone.

The new GEX profile is based on:
- Next month's options (which have been building OI for weeks)
- Any new positions established in the final days before OPEX
- The 0DTE positions from Monday's trading

This new profile may look completely different from the previous week's profile:
- The gamma flip may be at a different level
- The call wall and put wall may be at different strikes
- The total GEX may be significantly different (positive vs. negative)

### The Post-OPEX Monday Move

Price often makes a significant directional move on post-OPEX Monday. The reason:

1. The previous week's GEX structure was holding price near the pin strike.
2. That structure is now gone.
3. Price is "freed" from the gravitational field.
4. The new GEX structure has different walls and a different flip.
5. Price moves toward the new structure's equilibrium.

The direction of the post-OPEX Monday move depends on:
- Where the new gamma flip is relative to current price
- Whether the new total GEX is positive or negative
- The directional bias from DEX, VEX, and CHEX in the new structure

**The rule: Do NOT trust Friday's levels on Monday. Wait for the new GEX profile.**

FlashAlpha's first poll Monday morning shows the new structure. This is the most important FlashAlpha reading of the month. The levels from this reading will be the structural framework for the next 3-4 weeks.

### Post-OPEX Monday Playbook

1. **Pre-market**: Pull FlashAlpha for the new GEX profile. Note the new gamma flip, call wall, put wall, total GEX.

2. **Compare to Friday's levels**: How different is the new structure? If the flip has moved significantly, expect a large move.

3. **Identify the new equilibrium**: Where does the new GEX structure want price to be? (Near the highest-GEX strike, above the flip if total GEX is positive)

4. **Trade the move toward the new equilibrium**: If price is below the new flip, expect a move up. If above, expect a move down.

5. **Be patient**: The post-OPEX move can take all of Monday to develop. Don't rush.

---

## Quarterly OPEX: Quad Witching in Detail

### Why Quad Witching Is Different

Quad witching (March, June, September, December 3rd Friday) is not just a larger version of monthly OPEX. It's qualitatively different because four classes of derivatives expire simultaneously.

The four classes:
1. **Stock index options** (SPX, NDX, QQQ): The largest by dollar value
2. **Stock options** (individual equities): The largest by contract count
3. **Stock index futures** (ES, NQ): Futures contracts, not options
4. **Stock futures** (individual equity futures): Smaller market

The simultaneous expiration of all four creates:
- Maximum OI concentration (quarterly positions + monthly positions + weekly positions + 0DTE)
- Maximum hedging activity (all four classes require hedging)
- Maximum potential for disorderly markets (all four classes unwinding simultaneously)

### The Quad Witching Week Pattern

**Monday-Wednesday**: Extreme pinning. The quarterly OI is so large that the market is essentially frozen near the pin strike. Realized vol is at its lowest of the quarter.

**Thursday**: The calmest day of the quarter. Everything is pinned. The market oscillates in a very narrow range. This is the "maximum calm before maximum storm" pattern.

**Friday morning**: Maximum pinning. The quarterly OI is still intact. The market is gravitationally held.

**Friday afternoon**: Maximum volatility. The quarterly OI is expiring. The unpin is violent. MOC orders are massive (index rebalancing, fund rebalancing, futures rolling all happen simultaneously). The final 30-60 minutes of quad witching Friday are often the most volatile of the quarter.

### The Week After Quad Witching

The week after quad witching is often the most directionally significant week of the quarter. The quarterly GEX structure has been reset. The market is finding its new equilibrium.

Historical pattern:
- If the market was pinned ABOVE the new gamma flip: expect a rally in the week after (market is in positive gamma territory, new structure is bullish)
- If the market was pinned BELOW the new gamma flip: expect a decline (market is in negative gamma territory, new structure is bearish)
- The magnitude of the post-quad-witching move is proportional to how far the market was from the new equilibrium during the pinning period

---

## The OPEX Cycle as a Signal Modulator

The OPEX cycle doesn't just create specific events. It modulates the reliability and interpretation of ALL signals throughout the month.

### OPEX Week: Increase Pin Risk Weight

During OPEX week:
- **Increase weight on**: Pin risk, pinning behavior, max pain, GEX walls
- **Decrease weight on**: Directional flow signals (price is being mechanically held, not trending)
- **Increase weight on**: Roll activity identification (don't confuse rolls with directional bets)
- **Decrease weight on**: Momentum signals (momentum is suppressed by pinning)

The market during OPEX week is not a free market. It's a mechanically constrained market. Treat it as such.

### Post-OPEX: Decrease Confidence in All Levels

In the first 1-2 days after OPEX:
- **Decrease confidence in**: All GEX levels (they've been reset)
- **Increase weight on**: The new FlashAlpha GEX profile
- **Increase weight on**: Exploration mode (look for where the new structure is forming)
- **Decrease weight on**: Previous week's walls and flip (they're stale)

The market post-OPEX is a free market finding its new equilibrium. Treat it as such.

### Mid-Cycle (2+ Weeks from Any OPEX): Maximum Signal Reliability

The period 2-3 weeks after OPEX and 1-2 weeks before the next OPEX is the most reliable period for all signals:
- GEX levels are stable (OI has been building for weeks, not changing rapidly)
- Walls are reliable (high-OI strikes are well-established)
- The regime is clear (positive or negative gamma is well-defined)
- Directional flow signals are not distorted by roll activity

This is the best period for the standard playbooks. The GEX structure is at its most reliable.

### The Monthly Cycle Summary

```
Week 1 (post-OPEX): Recalibration. Low signal reliability. Find the new structure.
Week 2: Building. OI accumulating. Levels becoming clearer.
Week 3: Stable. Maximum signal reliability. Standard playbooks work best.
Week 4 (OPEX week): Pinning. Increase pin risk weight. Decrease directional weight.
OPEX Friday: Maximum pinning → maximum volatility. Special rules apply.
Post-OPEX Monday: Reset. New structure. Most important FlashAlpha reading of the month.
```

---

## The Monthly OI Roll: What It Looks Like and How to Identify It

As the current month's OPEX approaches, institutional positions "roll" to the next month. This creates specific patterns in the data rivers.

### What a Roll Looks Like

A roll is a spread trade: simultaneously closing a position in the current month and opening the same (or similar) position in the next month.

**Example roll:**
- Close: Sell 1,000 QQQ $520 calls expiring this Friday
- Open: Buy 1,000 QQQ $520 calls expiring next month

In the options tape, this appears as:
- A large sell order in the current month's $520 calls
- A large buy order in the next month's $520 calls
- Both orders execute at approximately the same time
- The net premium is the "roll cost" (usually a debit for calls, credit for puts)

### Identifying Rolls in Massive.com

Rolls appear in Massive as:
- Two large orders in the same underlying, same strike, different expirations, executed within seconds of each other
- One is a sell (closing), one is a buy (opening)
- The sizes are approximately equal
- The timing is simultaneous or near-simultaneous

**Key distinction**: A roll is NOT a directional bet. It's maintenance. Do not interpret a large sell in the current month's calls as bearish. It's just a roll.

**How to identify**: Look for the paired trade. If you see a large sell in the current month followed immediately by a large buy in the next month at the same strike, it's a roll. If you see only the sell (no paired buy), it may be a directional close.

### Roll Impact on GEX

Rolls shift OI from the current month to the next month. This:
- Decreases the current month's GEX (OI at expiring strikes decreases)
- Increases the next month's GEX (OI at next month's strikes increases)
- The net effect on total GEX depends on the relative gamma of the two expirations

During OPEX week, as rolls accelerate, the current month's GEX decreases and the next month's GEX increases. This is why the GEX profile changes throughout OPEX week, even without new directional bets.

---

## OPEX and the Four Data Rivers

### FlashAlpha

FlashAlpha is the primary tool for tracking OPEX cycle effects:
- **OPEX week**: GEX profile is dominated by expiring OI. Walls are at their strongest.
- **OPEX Friday**: GEX profile changes in real-time as OI expires. Update frequently.
- **Post-OPEX Monday**: The new GEX profile is the most important reading of the month.
- **Mid-cycle**: GEX profile is stable. Levels are reliable.

Key FlashAlpha metrics to track through the OPEX cycle:
- Total GEX (regime)
- Gamma flip (regime boundary)
- Call wall and put wall (structural levels)
- Max pain (gravitational center during OPEX week)

### Massive.com

Massive is the primary tool for identifying roll activity:
- Filter by expiration to separate current month from next month
- Look for paired trades (simultaneous buy/sell at same strike, different expirations)
- Track the roll pace: how quickly is OI moving from current to next month?
- Identify genuine directional bets vs. rolls

### Unusual Whales

UW provides OI data that shows the OPEX cycle effects:
- OI by expiration: Shows how much OI is in each expiration
- OI changes: Shows when OI is rolling (decreasing in current month, increasing in next)
- Put/call ratio by expiration: Shows the directional tilt of each expiration's OI

### Rithmic MBO

The Rithmic feed captures the hedging activity associated with OPEX:
- **OPEX week**: Steady, directional order flow as dealers maintain hedges for large OI
- **OPEX Friday afternoon**: Burst orders as positions expire and hedges are unwound
- **Post-OPEX Monday**: Large directional orders as the market finds its new equilibrium
- **Roll activity**: Pairs of large orders (one buy, one sell) as dealers rebalance hedges for rolled positions

---

## Practical OPEX Calendar for NQ Trading

### Monthly Calendar Template

```
Day 1-5 (post-OPEX): Recalibration week
  - Pull new FlashAlpha GEX profile on Monday morning
  - Identify new gamma flip, walls, regime
  - Expect directional move as market finds new equilibrium
  - Low confidence in specific levels until new structure is clear

Day 6-10 (mid-cycle early): Building week
  - OI accumulating at key strikes
  - Levels becoming clearer
  - Standard playbooks beginning to work
  - Moderate confidence in GEX levels

Day 11-15 (mid-cycle peak): Maximum reliability week
  - OI is well-established
  - Walls are reliable
  - Regime is clear
  - Maximum confidence in GEX levels
  - Best period for standard playbooks

Day 16-20 (OPEX week): Pinning week
  - Increase weight on pin risk and max pain
  - Decrease weight on directional flow
  - Identify roll activity in Massive
  - Expect low volatility Monday-Thursday
  - Expect high volatility Friday afternoon

OPEX Friday: Special rules
  - Morning: Fade moves away from pin
  - Afternoon: Watch for unpin
  - Final 30 min: MOC orders may overwhelm pin
  - Do NOT carry positions into the close without a specific reason
```

### Quarterly Calendar Additions

For March, June, September, December:
- Add 1 week of "extreme pinning" before quad witching
- Add 1 week of "major recalibration" after quad witching
- The post-quad-witching move is often the largest directional move of the quarter
- The week before quad witching is often the calmest week of the quarter
