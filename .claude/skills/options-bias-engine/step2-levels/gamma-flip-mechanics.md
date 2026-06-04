# Gamma Flip Mechanics — The Regime Boundary

## Purpose

The gamma flip is the single most important level in the options universe. It is not a support level, not a resistance level, not a wall. It is the boundary between two fundamentally different market regimes. Every other level's behavior changes based on which side of the flip spot is on. This document covers the mathematical definition, behavioral properties, crossing mechanics, movement dynamics, and order book signatures of the gamma flip.

Data sources:
- **FlashAlpha**: Primary source. Provides the gamma flip level directly, updated every 15-30 minutes.
- **Rithmic MBO**: Order book confirmation at the flip zone.
- **Massive.com**: Flow signals that precede a flip crossing.
- **Unusual Whales**: Dark pool activity at the flip level.

---

## Mathematical Definition

### The GEX Surface

For each strike K and expiry T, the gamma exposure (GEX) is:
```
gex(K, T) = gamma(K, T) × OI(K, T) × contract_multiplier × spot²
```

Where:
- `gamma(K, T)` = the option's gamma (second derivative of option price with respect to spot)
- `OI(K, T)` = open interest at that strike and expiry
- `contract_multiplier` = 100 for equity options
- `spot²` = included to convert from per-dollar to per-percent terms (some implementations omit this)

The sign convention:
- Call GEX is positive (dealers who sold calls are long gamma, they sell as price rises)
- Put GEX is negative (dealers who sold puts are short gamma, they buy as price falls)

### Net GEX by Strike

For each strike K, aggregate across all expiries:
```
net_gex(K) = sum over all T: call_gex(K, T) - |put_gex(K, T)|
```

This gives the net gamma exposure at each strike. Positive net_gex means calls dominate at that strike. Negative means puts dominate.

### Cumulative GEX

Sort strikes from lowest to highest. Compute the cumulative sum:
```
cumulative_gex(P) = sum of net_gex(K) for all K <= P
```

### The Gamma Flip

The gamma flip is the price P where cumulative_gex(P) crosses zero:
```
gamma_flip = P such that cumulative_gex(P) = 0
           = P where sum(net_gex(K) for K <= P) = 0
```

**Interpretation**: Below the gamma flip, the cumulative GEX is negative (puts dominate). Above the gamma flip, the cumulative GEX is positive (calls dominate). At the flip, the two forces are exactly balanced.

FlashAlpha computes this directly and reports it as a single price level. You do not need to compute it yourself — but understanding the math is essential for understanding why the flip behaves as it does.

### Why the Flip Creates a Regime Boundary

When spot is above the flip (positive cumulative GEX):
- Dealers are net long gamma across the entire options structure.
- When price rises, dealers must sell the underlying (delta hedging their long calls).
- When price falls, dealers must buy the underlying (delta hedging their long calls).
- This creates a DAMPENING effect. Dealers are always trading against the move.
- Result: Lower realized volatility. Mean-reverting price action. Walls hold.

When spot is below the flip (negative cumulative GEX):
- Dealers are net short gamma across the entire options structure.
- When price rises, dealers must buy the underlying (delta hedging their short puts).
- When price falls, dealers must sell the underlying (delta hedging their short puts).
- This creates an AMPLIFYING effect. Dealers are always trading with the move.
- Result: Higher realized volatility. Trending price action. Walls break.

---

## Why the Gamma Flip Is the Most Important Level

Every other level's behavior is conditional on the gamma flip. The flip is the meta-level that determines the rules.

### Call Wall Behavior by Flip Side

**Above the flip (positive gamma)**:
- Call wall is genuine resistance. Dealer selling creates mechanical headwind.
- Fade the call wall with high conviction.
- False breaks are common and quickly reversed.

**Below the flip (negative gamma)**:
- Call wall is weak resistance. Dealers are amplifying moves, not dampening them.
- Do not fade the call wall. It may hold briefly but the underlying dynamics are against it.
- If price approaches the call wall from below in negative gamma, it's likely to break through.

### Put Wall Behavior by Flip Side

**Above the flip (positive gamma)**:
- Put wall is genuine support. Dealer buying creates mechanical floor.
- Fade the put wall breakdown with high conviction.
- False breaks are common and quickly reversed.

**Below the flip (negative gamma)**:
- Put wall is a trapdoor. When price breaks through the put wall in negative gamma, dealers must SELL more (not buy) to hedge their now-deeper-in-the-money puts.
- The put wall break in negative gamma creates a cascade. Do not buy the put wall.

### HVL Behavior by Flip Side

**Above the flip**: HVL is a magnet. Price gravitates toward it. Mean reversion is reliable.

**Below the flip**: HVL is a potential target for a recovery rally, but it's not a magnet in the same way. Price can overshoot HVL in negative gamma.

### Expected Move Behavior by Flip Side

**Above the flip**: EM boundaries are reliable. Options sellers are winning. Fade price at EM.

**Below the flip**: EM boundaries are unreliable. The move that caused negative gamma often exceeds EM. Do not trust EM as a reversal level.

---

## Gamma Flip Distance as a Signal

The distance between spot and the gamma flip is a continuous signal, not a binary one. The closer spot is to the flip, the more unstable the regime.

### Distance Thresholds (NQ equivalent points)

**Spot 200+ points above flip**: Deep positive gamma. Maximum regime stability. Walls are reliable. Volatility is suppressed. This is the "safe zone" for range-bound strategies.

**Spot 100-200 points above flip**: Comfortable positive gamma. Normal regime. Levels are reliable. Standard playbook applies.

**Spot 50-100 points above flip**: Moderate positive gamma. Normal but watch for flip approach. Begin monitoring flip distance at each FlashAlpha poll.

**Spot 20-50 points above flip**: Close to regime transition. Caution zone. Reduce position size. Walls are less reliable. The flip could be tested intraday.

**Spot within 20 points of flip**: DANGER ZONE. Regime transition is imminent. The flip is being tested. Do not add new positions. Prepare for either a bounce (flip holds) or a cascade (flip breaks).

**Spot at the flip**: Maximum instability. The regime is undefined. Dealers are balanced between dampening and amplifying. This is the most dangerous moment to be in a position.

**Spot 1-50 points below flip**: Negative gamma, shallow. The regime has just flipped. This is the most dangerous zone because the flip may be reclaimed (false break) or confirmed (genuine regime change). Wait for confirmation before trading.

**Spot 50-100 points below flip**: Confirmed negative gamma. The regime has changed. Apply negative gamma playbook. Do not fade moves.

**Spot 100+ points below flip**: Deep negative gamma. Maximum regime instability. Volatility is amplified. Only trade with the trend. The only reversal signal is a confirmed reclaim of the flip.

### Distance as a Volatility Predictor

The flip distance is inversely correlated with realized volatility:
```
expected_realized_vol ∝ 1 / (flip_distance + epsilon)
```

When flip distance is large (spot far above flip), realized vol is low. When flip distance is small (spot near flip), realized vol is high. When spot is below the flip, realized vol is highest.

This relationship is not linear — it's convex. The last 20 points of flip distance before the crossing are the most dangerous.

---

## The Flip CROSSING Event

The flip crossing is the most dangerous moment in options-driven markets. It requires a specific protocol.

### Crossing from Above to Below (Positive to Negative Gamma)

This is the "floor disappearing" event. Everything that was support becomes a trapdoor.

**Phase 1: Approach (spot within 20 points of flip)**
- Reduce all long positions by 50%.
- Tighten stops on remaining longs.
- Begin monitoring Massive.com for put sweeps (the flow that will drive the crossing).
- Check Rithmic DOM: Is the book bid-heavy or ask-heavy near the flip?
- Check Unusual Whales: Is dark pool buying or selling near the flip?

**Phase 2: Test (spot touches the flip)**
- The flip is being tested. This is a binary moment.
- If the book is bid-heavy and dark pool is buying: The flip may hold. Wait.
- If the book is ask-heavy and dark pool is selling: The flip is breaking. Exit remaining longs.

**Phase 3: Crossing (spot closes a 5-minute bar below the flip)**
- The regime has changed. Apply negative gamma playbook immediately.
- The put wall is now a trapdoor. Do not buy it.
- The call wall is now weak resistance. Do not fade it.
- The HVL is now a potential recovery target, not a magnet.
- Expected move boundaries are now unreliable.
- The only bullish signal is a confirmed reclaim of the flip.

**Phase 4: Cascade (spot accelerates below the flip)**
- This is the most dangerous phase. Dealers are now selling as price falls (amplifying the move).
- Do not try to catch the falling knife.
- The cascade typically runs until one of: (a) a major support level (dark pool cluster, prior session low), (b) a significant put wall at a lower strike, or (c) a news catalyst reversal.
- The cascade can be 100-300+ NQ points in a single session.

**Phase 5: Stabilization**
- Price finds a level and stops falling.
- Flow shifts: Put buying slows. Call buying begins.
- Dark pool: Buying prints appear.
- DOM: Bids start stacking.
- This is the potential reversal setup, but it requires flip reclaim confirmation.

### Crossing from Below to Above (Negative to Positive Gamma)

This is the recovery signal. But it must be confirmed — false crosses back above that fail are devastating.

**Phase 1: Approach from below (spot within 20 points of flip)**
- The market is attempting to reclaim positive gamma.
- Monitor flow: Is there sustained call buying? Are sweeps bullish?
- Monitor dark pool: Is institutional money buying?
- Monitor DOM: Are bids stacking near the flip?

**Phase 2: The Cross (spot closes a 5-minute bar above the flip)**
- The regime may have changed. But this is NOT confirmed yet.
- Confirmation requirements:
  1. Massive.com: Net call premium positive for the last 15 minutes. No put sweeps.
  2. Unusual Whales: Dark pool net buying for the last 30 minutes.
  3. Rithmic DOM: Bid-heavy book above the flip. Icebergs on the bid.
  4. FlashAlpha: Next poll confirms the flip level has not risen above spot (the flip itself hasn't moved up to invalidate the cross).

**Phase 3: Confirmed Reclaim**
- All four confirmation requirements met.
- Apply positive gamma playbook.
- The first target is HVL (the magnet).
- The put wall is now genuine support again.
- The call wall is now genuine resistance again.

**Phase 4: Failed Reclaim**
- Spot crosses above the flip but fails to hold.
- Price falls back below the flip within 1-3 bars.
- This is a BULL TRAP. The most dangerous scenario for longs.
- Exit immediately. The failed reclaim often leads to an accelerated decline.
- The market tested the flip, failed, and is now in confirmed negative gamma with momentum.

---

## Gamma Flip MOVEMENT

The flip level itself moves as OI changes. Tracking flip movement is a secondary directional signal.

### Rising Flip (Flip Moving Toward Spot from Below)

**Mechanism**: Put OI is building at higher strikes. The cumulative GEX zero-crossing is moving up.

**Visible in FlashAlpha**: The flip level increases between polls.

**Visible in Massive.com**: Put buying at strikes above the current flip level.

**Directional signal**: BEARISH. The regime boundary is approaching spot. The market is pricing in a regime transition. Institutions are buying protection at higher levels, which shifts the flip upward.

**Velocity thresholds**:
- Flip rising < 10 NQ points/hour: Normal drift. Background noise.
- Flip rising 10-25 NQ points/hour: Moderate. Note the direction.
- Flip rising 25-50 NQ points/hour: Significant. Reduce long exposure.
- Flip rising 50+ NQ points/hour: Rapid. High probability of regime transition. Exit longs.

### Falling Flip (Flip Moving Away from Spot Below)

**Mechanism**: Call OI is building at lower strikes, or put OI at higher strikes is being closed. The cumulative GEX zero-crossing is moving down.

**Visible in FlashAlpha**: The flip level decreases between polls.

**Visible in Massive.com**: Call buying at lower strikes, or put selling (closing) at higher strikes.

**Directional signal**: BULLISH. The regime boundary is moving away from spot. Positive gamma is strengthening. The market is becoming more stable.

### Flip and Spot Converging

When the flip is rising and spot is falling (or spot is falling toward a stationary flip), the two are converging. This is the most dangerous configuration.

**Convergence rate**:
```
convergence_rate = (flip_velocity_up + spot_velocity_down) / time
```

If the convergence rate implies the flip and spot will meet within 2 hours, the regime transition is imminent. Reduce exposure immediately.

---

## Order Book at the Gamma Flip

The flip level is a mathematical construct, not a single strike with huge OI. This means it doesn't have the same order book signature as a GEX wall. But the zone around the flip has distinctive order book characteristics.

### Bid/Ask Imbalance Near the Flip

The order book near the flip reflects the battle between positive and negative gamma forces.

**Bid-heavy book near the flip (more resting bids than offers)**:
- Dealers are defending positive gamma. They're buying dips near the flip.
- The flip is likely to hold.
- Bullish signal.

**Ask-heavy book near the flip (more resting offers than bids)**:
- Dealers are not defending. They may be positioning for negative gamma.
- The flip is at risk.
- Bearish signal.

**Balanced book near the flip**:
- The regime is genuinely contested. Neither side has conviction.
- Wait for flow to break the tie.

### Iceberg Detection Near the Flip

Icebergs near the flip tell you who's fighting for the regime.

**Icebergs on the bid near the flip**: Institutional buyers defending positive gamma. The flip is likely to hold.

**Icebergs on the ask near the flip**: Institutional sellers positioning for negative gamma. The flip is at risk.

**No icebergs near the flip**: Nobody is defending the regime boundary. The flip is vulnerable to a crossing on any significant flow event.

### Depth Stacking Near the Flip

In positive gamma regime, the book near the flip shows depth stacking on the bid side (dealers buying dips). In negative gamma regime, the book shows depth stacking on the ask side (dealers selling rallies).

The transition from bid-heavy to ask-heavy depth near the flip is a leading indicator of a regime crossing. It happens before the price crosses because dealers are repositioning in anticipation.

---

## Gamma Flip in Different Market Conditions

### Low VIX Environment (VIX < 15)

- The flip is typically far below spot (100-300+ NQ points below).
- Positive gamma is deep and stable.
- The flip is a background reference, not an active trading level.
- Regime transitions are rare.
- Focus on walls and HVL for trading levels.

### Moderate VIX Environment (VIX 15-25)

- The flip is closer to spot (50-150 NQ points below).
- Positive gamma is moderate.
- The flip is an active monitoring level.
- Regime transitions occur occasionally, especially around macro events.
- Monitor flip distance at each FlashAlpha poll.

### High VIX Environment (VIX > 25)

- The flip may be near spot or even above spot.
- Negative gamma is possible or likely.
- The flip is the primary trading level.
- Regime transitions are frequent and violent.
- Reduce position size. Increase monitoring frequency.

### VIX Spike Events (VIX > 35)

- The flip is almost certainly above spot (negative gamma regime).
- The market is in maximum amplification mode.
- Do not trade against the trend.
- The only signal that matters is a confirmed flip reclaim.
- These events are rare but devastating for unprepared traders.

### OPEX Week

- Monthly OPEX (third Friday) causes a GEX reset.
- The flip level can shift dramatically as monthly OI expires.
- The week before OPEX: Flip is most stable (monthly OI is at maximum).
- OPEX day: Flip can shift 50-100+ NQ points as monthly OI expires.
- Post-OPEX: New flip level established. Re-poll FlashAlpha after 10:00 AM on OPEX Friday.

---

## Gamma Flip Computation from Raw Data

If FlashAlpha is unavailable, the flip can be estimated from raw options data.

### Data Requirements

- Strike prices for all listed options (calls and puts)
- Open interest at each strike and expiry
- Implied volatility at each strike (for gamma computation)
- Current spot price

### Gamma Computation

For each option (strike K, expiry T, type):
```
d1 = (ln(spot/K) + (r + 0.5 × IV²) × T) / (IV × sqrt(T))
gamma = N'(d1) / (spot × IV × sqrt(T))
```

Where N'(d1) is the standard normal PDF evaluated at d1.

### GEX Computation

```
call_gex(K, T) = gamma(K, T) × call_OI(K, T) × 100
put_gex(K, T) = -gamma(K, T) × put_OI(K, T) × 100
net_gex(K) = sum over T: call_gex(K, T) + put_gex(K, T)
```

### Flip Computation

```
Sort strikes K from lowest to highest
cumulative_gex = 0
for each K in sorted order:
    cumulative_gex += net_gex(K)
    if cumulative_gex crosses zero:
        gamma_flip = interpolate between K_prev and K
        break
```

This computation requires options chain data (available from CBOE, or from Massive.com's options data feed). FlashAlpha automates this and provides the result directly.

---

## Practical Protocol for Gamma Flip Monitoring

### At Session Open (9:30 AM ET)

1. Poll FlashAlpha for current flip level.
2. Compute flip distance: `flip_distance = spot - flip_level`
3. Determine regime: positive (flip_distance > 0) or negative (flip_distance < 0).
4. Apply appropriate regime playbook from `../step1-regimes/`.
5. Set alert: If flip_distance < 30 NQ points, increase monitoring frequency.

### Every 30 Minutes During Session

1. Poll FlashAlpha for updated flip level.
2. Compute new flip distance.
3. Compute flip velocity: `flip_velocity = (new_flip - old_flip) / 30 minutes`
4. If flip is rising toward spot at > 25 NQ points/hour: Reduce long exposure.
5. If flip distance has decreased by > 20 NQ points since last poll: Increase caution.

### At Flip Crossing

1. Immediately apply crossing protocol (see above).
2. Poll FlashAlpha every 15 minutes until regime is confirmed.
3. Monitor Massive.com for flow confirmation.
4. Monitor Rithmic DOM for order book confirmation.
5. Do not add new positions until regime is confirmed.

### At Session Close (4:00 PM ET)

1. Record final flip level and distance.
2. Note direction of flip movement during the session.
3. This is the starting point for the next session's analysis.

---

## Cross-Reference

- For level ranking by regime: `level-hierarchy.md`
- For wall behavior in each regime: `wall-dynamics.md`
- For flow signals at the flip: `../step3-flow/flow-interpretation.md`
- For dark pool at the flip: `../step3-flow/dark-pool-reading.md`
- For regime definitions and playbooks: `../step1-regimes/`
