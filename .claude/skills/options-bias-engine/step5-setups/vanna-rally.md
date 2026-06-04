# Setup 4: Vanna Rally / Vanna Selloff

## Overview

The Vanna Rally (or Vanna Selloff) is a mechanical setup driven by mathematics, not human decisions. It happens because of the relationship between implied volatility and dealer delta hedging. When VIX moves, dealers must rebalance their hedges — and that rebalancing creates directional pressure on the underlying.

This is one of the most reliable setups in the system precisely because it's mechanical. It doesn't depend on sentiment, news, or human psychology. It depends on the math of options pricing and the obligation of dealers to maintain delta-neutral books.

Understanding vanna is essential. Vanna = d(delta)/d(IV). It measures how much a dealer's delta changes when implied volatility changes. When VIX drops, the delta of short puts decreases (puts become less in-the-money in volatility terms), so dealers who are short puts need to BUY less of the underlying to hedge. But they've already bought it — so they must SELL. Wait, that's wrong. Let's be precise:

Dealers are typically short puts (they sold puts to retail buyers). Short puts have negative delta (they lose value when the market falls). To hedge, dealers BUY the underlying. When VIX drops, the delta of those short puts decreases in magnitude (the puts are less sensitive to price moves). Dealers now have MORE delta than they need — they must SELL the underlying to reduce their hedge. But this is the vanna effect in the wrong direction.

The correct vanna mechanics for a VIX drop:

Dealers are short puts. Short puts have negative vanna (when IV drops, the delta of short puts becomes less negative — closer to zero). This means dealers' net delta from their short put position INCREASES (becomes less negative, i.e., more positive). To maintain delta neutrality, dealers must SELL the underlying to offset the increased positive delta. This creates SELLING pressure when VIX drops.

But wait — the empirical observation is that VIX drops are associated with market rallies. The reconciliation: the VIX drop is often CAUSED by the market rally (IV is a function of demand for options, which drops when the market is calm). The vanna flow is a SECONDARY effect that amplifies the rally, not the primary cause.

For practical trading: positive VEX + VIX dropping = bullish mechanical flow (dealers buying to hedge their short calls, which have increasing delta as IV drops). Negative VEX + VIX rising = bearish mechanical flow (dealers selling to hedge their short puts, which have increasing negative delta as IV rises).

VEX from FlashAlpha quantifies the total dollar-value of vanna exposure across all dealer positions. This is the key input.

---

## 1. Setup Name and Overview

**Name:** Vanna Rally / Vanna Selloff
**Type:** Mechanical VIX-driven dealer rebalancing
**Frequency:** 2-4 times per week (significant VIX moves); daily (minor vanna flows)
**Best variant:** Vanna Rally (positive VEX + VIX dropping 1+ points) in Regime A or B
**Worst variant:** Vanna Selloff in Regime E (negative gamma amplifies the move unpredictably)

The setup trades the mechanical dealer rebalancing that occurs when VIX moves by 1+ points in a sustained direction.

---

## 2. Regime Requirements

**Regime A (strong positive gamma):**
- Vanna flows are DAMPENED by the positive gamma environment
- The mechanical buying/selling is partially offset by the dealer gamma hedging
- Win rate: 65-70%
- R:R: 1:1 to 1.5:1 (smaller moves due to dampening)
- Best for: Vanna Rally (VIX dropping in positive gamma = steady, reliable upward drift)

**Regime B (moderate positive gamma):**
- Vanna flows are moderately dampened
- Win rate: 65-70%
- R:R: 1:1 to 2:1
- Good for both Vanna Rally and Vanna Selloff

**Regime C (weak positive gamma / near flip):**
- Vanna flows are less dampened
- Win rate: 65-70%
- R:R: 1.5:1 to 2:1
- A Vanna Selloff in Regime C can trigger a flip cross (see gamma-flip-cross.md)

**Regime D (negative gamma, controlled):**
- Vanna flows are AMPLIFIED by the negative gamma environment
- Win rate: 65-70%
- R:R: 2:1 to 3:1 (larger moves due to amplification)
- Higher risk: the amplification works both ways

**Regime E (negative gamma, crisis):**
- Vanna flows are maximally amplified
- Win rate: 60-65% (chaotic environment)
- R:R: 2:1 to 4:1 (very large moves possible)
- Reduce position size by 50% regardless of conviction

---

## 3. Entry Conditions (All Four Rivers + Derived)

### The VIX Trigger

The primary trigger for this setup is a sustained VIX move of 1+ points. "Sustained" means:
- VIX has moved 1+ points from its session open or from a recent pivot
- The move has been sustained for at least 15 minutes (not just an intraday spike)
- VIX is not oscillating — it's trending in one direction

**Quantitative threshold:**
- Minimum VIX move: 1.0 points (e.g., VIX from 18.0 to 17.0 = bullish vanna trigger)
- Strong vanna trigger: 1.5+ points
- Extreme vanna trigger: 2.0+ points (rare, but creates the largest mechanical flows)

### FlashAlpha (Structure) — Required
- VEX is clearly positive or negative (not near zero)
- Positive VEX: VIX dropping = bullish vanna flow. Negative VEX: VIX rising = bearish vanna flow.
- VEX magnitude: At least $500M absolute value for a meaningful vanna flow. Below $500M, the mechanical impact on NQ is too small to trade.
- The VEX direction must be consistent with the VIX move direction (positive VEX + VIX dropping = aligned bullish)
- GEX regime: note the regime for amplitude adjustment

**Estimating NQ point impact:**
VEX × VIX_change / NQ_price × 85.7 (QQQ/NDX to NQ ratio) ≈ estimated NQ point impact

Example: VEX = $2B, VIX drops 1.5 points, NQ at 19,500
Impact = $2B × 1.5 / 19,500 × 85.7 ≈ 13.2 NQ points

This is a rough estimate. Actual impact varies based on the distribution of the VEX across strikes and expiries. Use as a minimum target estimate, not a precise prediction.

### Massive.com (Flow) — Supporting (not required)
- Vanna flows are MECHANICAL — they happen regardless of directional options buying
- Flow may or may not confirm the vanna direction
- If flow confirms: higher conviction, larger position size
- If flow is neutral: standard position size
- If flow opposes: reduce position size by 25% (the vanna flow may be offset by directional flow)

**Note:** This is the only setup where flow is not required. The mechanical nature of vanna means it happens even without directional options buying. However, flow confirmation increases the probability and magnitude of the move.

### Unusual Whales (Dark) — Supporting (not required)
- Dark pool confirmation increases conviction
- Dark pool opposing the vanna direction: reduce position size by 25%
- Dark pool neutral: standard position size
- Dark pool confirming: increase position size by 25% (up to maximum)

### Rithmic MBO (DOM) — Required
- The DOM must show the mechanical nature of the vanna flow: steady, persistent directional pressure
- Vanna flows are NOT spike-y. They're a grind. The DOM should show:
  - Consistent market orders in the vanna direction (not a single large sweep)
  - Steady aggression imbalance (1.5:1 to 2:1, not 5:1)
  - No large opposing icebergs (which would indicate someone is fighting the vanna flow)
- If the DOM shows a spike (sudden large move) rather than a grind, it's not a vanna flow — it's a different setup

**Distinguishing vanna flow from other flows:**
- Vanna: Steady grind, consistent direction, moderate aggression imbalance, no large sweeps
- Sweep cascade: Spike-y, large sweeps, high aggression imbalance
- Charm flow: Starts around 2:30 PM, builds into close
- Distribution/accumulation: Absorption visible, price not moving proportionally to volume

### Derived — Required
- VIX is moving in the direction consistent with the vanna trade (dropping for bullish, rising for bearish)
- The VIX move is sustained (not a single-bar spike)
- IV rank is in a range where vanna flows are meaningful (20-70% IV rank). At very low IV rank (<20%), vanna flows are small. At very high IV rank (>70%), vanna flows can be large but are also more volatile.

---

## 4. Entry Execution

**Entry timing:** After confirming the VIX move is sustained (15+ minutes) AND the DOM shows the mechanical grind beginning.

**Entry technique:** Limit order in the direction of the vanna flow, placed at the current market price or 1-2 ticks better. This is not a setup where you wait for a pullback — the vanna flow is a grind and there may not be a clean pullback.

**Alternative entry:** If the vanna flow has already been running for 30+ minutes and price has moved significantly, wait for a minor pullback (5-10 ticks) before entering. The grind will continue but entering at a better price improves R:R.

**Do NOT:** Enter before the VIX move is confirmed as sustained (15+ minutes). A VIX spike that reverses within 5 minutes is not a vanna trigger.

**Do NOT:** Enter if the DOM shows a spike rather than a grind. Spikes are not vanna flows.

---

## 5. Stop Loss Rules

**Primary stop:** 15 NQ ticks against the entry.

The 15-tick stop is based on the nature of vanna flows: they're steady grinds. If price moves 15 ticks against the vanna direction, the flow is not working as expected. Either the VIX move has reversed, the vanna flow is being offset by opposing flows, or the setup was misidentified.

**VIX-based stop:** If VIX reverses by 0.5+ points from the trigger level, exit immediately. The vanna trigger has reversed. The mechanical flow will reverse with it.

**Regime-specific adjustments:**
- Regime A/B: Stop 15 ticks (dampened environment, smaller moves)
- Regime C: Stop 15 ticks
- Regime D: Stop 18 ticks (amplified environment, more volatility)
- Regime E: Stop 20 ticks (chaotic environment, wider stop needed)

**Time-based stop:** If the trade has not moved in the vanna direction within 20 minutes of entry, exit at market. Vanna flows are time-sensitive — they're strongest in the first 30 minutes after the VIX move (initial hedging burst) and then gradual. If the flow isn't showing up within 20 minutes, it may not materialize.

---

## 6. Profit Target Rules

**Primary target:** Estimated NQ point impact from the VEX calculation (see entry conditions).

**Secondary target:** The nearest structural level in the vanna direction (HVL, call wall for bullish, put wall for bearish).

**Time-based target:** Vanna flows are strongest in the first 30 minutes after the VIX move. After 30 minutes, the initial hedging burst is complete and the flow becomes a slower grind. Consider taking 50% of the position at the 30-minute mark regardless of price.

**Partial profit taking:**
- Take 50% at the estimated NQ point impact (VEX calculation)
- Let remaining 50% run to the nearest structural level
- Move stop to breakeven after taking first partial

**The "VIX continues" scenario:** If VIX continues to move in the trigger direction (e.g., VIX drops from 18.0 to 17.0 to 16.5), the vanna flow continues and the target should be extended. In this case, trail the remaining 50% with a 15-tick trailing stop.

---

## 7. Position Sizing

| Conviction | Position Size | Notes |
|---|---|---|
| Flow + Dark confirming | 75% of max | Highest conviction vanna trade |
| Flow confirming, Dark neutral | 50% of max | Standard vanna trade |
| Flow neutral, Dark neutral | 50% of max | Mechanical only, standard size |
| Flow opposing, Dark neutral | 37% of max | Reduced (opposing flow) |
| Flow opposing, Dark opposing | 25% of max | Minimum (both opposing) |

**Note:** The maximum position size for vanna trades is 75% of the wall bounce maximum. The magnitude uncertainty (vanna flows can be 5 NQ points or 50 NQ points) justifies a smaller maximum size.

**Regime D/E adjustment:** Reduce all sizes by 25% due to amplification risk. The move can be larger than expected in negative gamma.

---

## 8. Order Book Confirmation

**Vanna flow DOM signature:**
- Steady, consistent market orders in the vanna direction (not a single large sweep)
- Aggression imbalance: 1.5:1 to 2.5:1 (moderate, not extreme)
- No large opposing icebergs
- Price grinding in the vanna direction with minimal pullbacks
- Volume is moderate and consistent (not spiking)

**Distinguishing vanna from other flows:**

| Characteristic | Vanna Flow | Sweep Cascade | Charm Flow |
|---|---|---|---|
| Timing | After VIX move | Any time | 2:30-4:00 PM |
| DOM pattern | Steady grind | Spike-y | Steady grind |
| Aggression | 1.5:1 to 2.5:1 | 4:1 to 10:1 | 1.5:1 to 2:1 |
| Duration | 30-90 minutes | 5-15 minutes | 90 minutes |
| VIX trigger | Yes | No | No |

**The "vanna grind" pattern:** In the DOM, vanna flows appear as a steady stream of small market orders in one direction, with occasional small pullbacks that are quickly absorbed. The aggression imbalance is consistent but not extreme. This is the mechanical nature of dealer rebalancing — they're not in a hurry, they're just systematically adjusting their hedges.

---

## 9. Win Rate and R:R Estimates

| Variant | Regime | Win Rate | R:R | Expected Value |
|---|---|---|---|---|
| Vanna Rally (VIX drop) | A/B | 65-70% | 1:1 to 1.5:1 | +0.33R to +0.55R |
| Vanna Rally (VIX drop) | C | 65-70% | 1.5:1 to 2:1 | +0.63R to +1.05R |
| Vanna Rally (VIX drop) | D | 65-70% | 2:1 to 3:1 | +0.95R to +1.75R |
| Vanna Selloff (VIX rise) | A/B | 65-70% | 1:1 to 1.5:1 | +0.33R to +0.55R |
| Vanna Selloff (VIX rise) | C | 65-70% | 1.5:1 to 2:1 | +0.63R to +1.05R |
| Vanna Selloff (VIX rise) | D/E | 60-65% | 2:1 to 4:1 | +0.60R to +1.95R |

**Note:** The win rate is consistent across regimes (65-70%) because the mechanical nature of vanna flows doesn't depend on regime. The R:R varies because the amplitude of the move is amplified in negative gamma and dampened in positive gamma.

---

## 10. Failure Modes

### Failure Mode 1: VIX Reversal

The VIX move that triggered the setup reverses. The vanna flow reverses with it. This is the most common failure mode.

**Detection:** VIX reverses by 0.5+ points from the trigger level.
**Response:** Exit immediately. The mechanical trigger has reversed.

### Failure Mode 2: VEX Near Zero

The VEX is too small to create a meaningful vanna flow. The VIX moves but the NQ impact is negligible.

**Detection:** VEX absolute value is less than $500M.
**Response:** Do not trade. The vanna flow is too small to be tradeable.

### Failure Mode 3: Opposing Directional Flow Overwhelms Vanna

Strong directional flow (sweep cascade, dark pool attack) in the opposite direction of the vanna flow overwhelms the mechanical rebalancing.

**Detection:** Massive shows strong opposing sweeps. DOM shows spike-y opposing aggression (not the steady grind of vanna).
**Response:** Exit immediately. The directional flow is stronger than the mechanical vanna flow.

### Failure Mode 4: Misidentifying the VEX Direction

Positive VEX + VIX dropping = bullish vanna. But if VEX is actually negative (misread from FlashAlpha), the trade is in the wrong direction.

**Prevention:** Double-check VEX sign before entry. Positive VEX = dealers are net long vanna (they benefit from IV increases). Negative VEX = dealers are net short vanna (they benefit from IV decreases).

### Failure Mode 5: Regime E Amplification

In Regime E, the vanna flow is amplified by negative gamma. The move can be much larger than the VEX calculation suggests, and it can reverse just as violently.

**Response:** Reduce position size by 50% in Regime E. Take profits at the first target. Do not hold for extended targets.

---

## 11. Example Scenarios

### Example 1: Vanna Rally in Regime B

**Setup:**
- NQ at 19,400. VIX at 18.5 and dropping. VEX = +$1.8B (positive, bullish vanna).
- FlashAlpha: GEX = $320M (Regime B). VEX = +$1.8B. VIX has dropped from 18.5 to 17.2 over 20 minutes (1.3 point drop, sustained).
- Estimated NQ impact: $1.8B × 1.3 / 19,400 × 85.7 ≈ 10.3 NQ points
- Massive: Call flow slightly positive but not strong. Net call premium +$5M. No sweeps.
- UW: Dark pool neutral. No institutional alerts.
- DOM: Steady market buys (1.8:1 over sells). No large opposing icebergs. Price grinding up 2-3 ticks per minute.

**Conviction check:** STRUCTURE bullish (positive VEX + VIX dropping), FLOW neutral (no strong flow), DARK neutral, DOM bullish (steady grind), DERIVED bullish (VIX dropping). Score: +2 to +3. Moderate conviction.

**Entry:** Long at 19,400 (limit order at current price).
**Stop:** 19,385 (15 ticks below entry).
**Target 1:** 19,410 (10 NQ points, VEX estimate). Take 50%.
**Target 2:** HVL at 19,450 (50 ticks). Let remaining 50% run.
**Size:** 50% of maximum (flow and dark neutral).

**Result:** Price grinds from 19,400 to 19,412 over 25 minutes (first partial, 12 ticks). VIX continues to drop to 16.8. Price reaches 19,445 over the next 30 minutes (second partial, 45 ticks). Average exit: 28.5 ticks. Stop was 15 ticks. R:R achieved: 1.9:1.

### Example 2: Vanna Selloff in Regime D

**Setup:**
- NQ at 19,100. VIX at 22.0 and rising. VEX = -$2.2B (negative, bearish vanna).
- FlashAlpha: GEX = -$180M (Regime D). VEX = -$2.2B. VIX has risen from 22.0 to 23.5 over 25 minutes (1.5 point rise, sustained).
- Estimated NQ impact: $2.2B × 1.5 / 19,100 × 85.7 ≈ 14.8 NQ points (amplified by negative gamma)
- Massive: Put flow increasing. Net put premium -$12M. Put sweeps 2:1 over calls.
- UW: Dark pool net selling. Net dark premium -$15M.
- DOM: Steady market sells (2.2:1 over buys). Price grinding down 3-4 ticks per minute.

**Conviction check:** STRUCTURE bearish (negative VEX + VIX rising), FLOW bearish (put flow), DARK bearish (dark selling), DOM bearish (steady grind), DERIVED bearish (VIX rising). Score: -5. Maximum bearish conviction.

**Entry:** Short at 19,100 (limit order at current price).
**Stop:** 19,118 (18 ticks above entry, Regime D adjustment).
**Target 1:** 19,085 (15 NQ points, VEX estimate). Take 50%.
**Target 2:** Put wall at 19,000 (100 ticks). Let remaining 50% run.
**Size:** 56% of maximum (75% for high conviction × 75% for Regime D adjustment).

**Result:** Price grinds from 19,100 to 19,083 over 30 minutes (first partial, 17 ticks). VIX continues to rise to 24.2. Price reaches 19,015 over the next 45 minutes (second partial, 85 ticks). Average exit: 51 ticks. Stop was 18 ticks. R:R achieved: 2.8:1.

---

## 12. Anti-Patterns (When It Looks Like This Setup But Isn't)

### Anti-Pattern 1: VIX Spike Without Sustained Move

VIX spikes 1+ points in a single bar but immediately reverses. This is not a vanna trigger — it's a VIX spike (often caused by a large options trade or a brief news event).

**Detection:** VIX moves 1+ points in a single bar but reverses within 5 minutes.
**Response:** Do not trade. Wait for the VIX move to be sustained for 15+ minutes.

### Anti-Pattern 2: VEX Near Zero

VEX is less than $500M absolute value. The vanna flow is too small to be tradeable.

**Response:** Do not trade. The mechanical impact is insufficient.

### Anti-Pattern 3: DOM Shows Spike, Not Grind

The DOM shows a spike (sudden large move, high aggression imbalance) rather than a grind. This is a sweep cascade or a different setup, not a vanna flow.

**Response:** Do not trade as a vanna setup. Consider the sweep cascade setup instead (see step5-setups/sweep-cascade.md).

### Anti-Pattern 4: VIX Move Caused by Options Trade, Not Market Fear

A large options trade (e.g., a fund buying a massive put spread) can temporarily move VIX without reflecting genuine market fear. The VIX move is artificial and will reverse when the trade is complete.

**Detection:** VIX moves sharply but NQ doesn't move proportionally. The VIX move is not accompanied by any visible market stress.
**Response:** Wait for NQ to confirm the VIX move before entering. If NQ doesn't move in the vanna direction within 10 minutes, the VIX move is artificial.

---

## 13. Time-of-Day Considerations

**9:30-10:00 AM (Opening):**
- VIX is most volatile at the open
- Opening VIX moves are often temporary (opening range establishment)
- Wait for the VIX move to be sustained for 15+ minutes before trading
- Best to skip vanna trades in the first 15 minutes

**10:00 AM-12:00 PM (Morning session):**
- Best time for vanna trades
- VIX moves are more sustained and meaningful
- DOM signals are reliable

**12:00-1:30 PM (Lunch lull):**
- VIX is often stable during the lunch lull
- Vanna flows are minimal
- Skip vanna trades during this window unless VIX moves significantly

**1:30-3:00 PM (Afternoon session):**
- VIX moves in the afternoon are often driven by macro events or end-of-day positioning
- Vanna flows are reliable in this window
- Good time for vanna trades

**2:30-4:00 PM (Charm flow overlap):**
- Vanna flows and charm flows can overlap in this window
- If both vanna and charm are in the same direction, the combined mechanical flow is stronger
- Increase position size by 25% when vanna and charm align (see step5-setups/charm-flow.md)
- If vanna and charm are in opposite directions, skip both setups

**OPEX Fridays:**
- VEX is highest on OPEX Fridays (maximum OI)
- Vanna flows are strongest on OPEX Fridays
- A 1-point VIX move on OPEX Friday can create 2-3x the normal NQ impact
- Increase position size by 25% on OPEX Friday vanna trades
