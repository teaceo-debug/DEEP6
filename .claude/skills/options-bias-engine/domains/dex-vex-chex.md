# DEX, VEX, and CHEX: The Full Greek Chain Beyond Gamma

## Overview: Why GEX Alone Is Insufficient

GEX tells you how much dealer hedging occurs per unit of price move. But price isn't the only thing that changes. Implied volatility changes. Time passes. These changes also shift dealer delta, requiring additional hedging that GEX doesn't capture.

The full picture requires three additional Greek exposures:

- **DEX (Delta Exposure)**: The current aggregate directional tilt of all dealer hedges
- **VEX (Vanna Exposure)**: How dealer delta shifts when implied volatility changes
- **CHEX (Charm Exposure)**: How dealer delta shifts as time passes

Together with GEX, these four metrics form a complete model of mechanical dealer flow. An AI that understands all four can predict not just whether the market will be stable or volatile (GEX), but also the DIRECTION of mechanical pressure (DEX), how VIX moves translate to equity flows (VEX), and what time-of-day flows to expect (CHEX).

---

## DEX: Delta Exposure

### Formula and Derivation

DEX measures the aggregate dollar-delta of all dealer hedges across the entire options chain:

```
DEX = sum over all strikes K of:
      [call_delta(K) × call_OI(K) - put_delta(K) × put_OI(K)] × 100 × spot

Where:
  call_delta(K) = Black-Scholes delta of calls at strike K (positive, 0 to 1)
  call_OI(K)    = open interest in calls at strike K
  put_delta(K)  = absolute value of Black-Scholes delta of puts at strike K (positive, 0 to 1)
  put_OI(K)     = open interest in puts at strike K
  100           = shares per contract
  spot          = current underlying price
```

The subtraction (call minus put) reflects the opposing nature of call and put hedges. Calls require long delta hedges; puts require short delta hedges.

### The Counterintuitive Sign Convention

This is the most important thing to understand about DEX: **the sign is counterintuitive.**

When DEX is POSITIVE:
- Calls dominate the OI (more call OI than put OI, weighted by delta)
- Dealers are net LONG delta (from their short call hedges)
- Dealers need to SELL on rallies to reduce their long delta
- This creates BEARISH mechanical pressure

When DEX is NEGATIVE:
- Puts dominate the OI (more put OI than put OI, weighted by delta)
- Dealers are net SHORT delta (from their short put hedges)
- Dealers need to BUY on dips to reduce their short delta
- This creates BULLISH mechanical pressure

**Positive DEX = bearish mechanical flow. Negative DEX = bullish mechanical flow.**

The reason: The dealer's hedge OPPOSES their inventory. A dealer short calls (positive inventory from the customer's perspective) holds long delta as a hedge. That long delta must be sold on rallies. The dealer is a natural seller into strength.

### DEX as a Directional Signal

DEX is most useful as a CHANGE signal, not an absolute level signal.

**DEX becoming more negative (decreasing):**
- Dealers are accumulating more short delta (more put buying by customers)
- Dealers will need to buy more aggressively on dips
- Bullish mechanical pressure is building
- This often precedes a rally or a stabilization of a decline

**DEX becoming more positive (increasing):**
- Dealers are accumulating more long delta (more call buying by customers)
- Dealers will need to sell more aggressively on rallies
- Bearish mechanical pressure is building
- This often precedes a pullback or a capping of a rally

**DEX crossing zero:**
- The balance of call vs. put OI (weighted by delta) has shifted
- A regime change in the directional tilt of dealer hedging
- Can be a significant signal when combined with GEX regime

### DEX and Price Levels

DEX is not just a directional signal; it also implies specific price levels where the mechanical pressure is strongest.

The delta of an option is highest near the strike price. So the DEX contribution from a given strike is highest when spot is near that strike. As spot moves away from a strike, the delta of that option changes (calls go toward 0 or 1, puts go toward 0 or -1), and the DEX contribution from that strike changes.

This means DEX is dynamic: it changes as spot moves, even without any change in OI. The DEX at any given price level reflects the aggregate directional tilt of dealer hedges AT THAT PRICE.

### DEX in the Data Rivers

**FlashAlpha**: Provides DEX directly. Track the daily DEX value and its direction of change.

**Massive.com**: Large call sweeps increase call OI → increase DEX (more positive). Large put sweeps increase put OI → decrease DEX (more negative). Massive flow is a leading indicator of DEX changes.

**Unusual Whales**: UW's put/call ratio by strike provides the raw data that drives DEX. High put OI at strikes below spot = negative DEX contribution from those strikes.

**Rithmic MBO**: When DEX is negative (bullish mechanical pressure), watch for large buy orders appearing at dips. These are dealers buying to maintain their short delta hedge. The Rithmic feed captures this as aggressive bids or large market buys.

---

## VEX: Vanna Exposure

### What Vanna Is

Vanna is a second-order Greek that measures the sensitivity of delta to changes in implied volatility:

```
Vanna = d(delta)/d(IV) = d(vega)/d(spot)
```

Vanna is positive for calls and negative for puts (in the standard convention). For a call option:
- When IV increases, the call's delta increases (the option becomes more likely to expire ITM)
- When IV decreases, the call's delta decreases

For a put option:
- When IV increases, the put's delta becomes more negative (more likely to expire ITM)
- When IV decreases, the put's delta becomes less negative

### The VEX Formula

```
VEX = sum over all strikes K of:
      [call_vanna(K) × call_OI(K) - put_vanna(K) × put_OI(K)] × 100

Where:
  call_vanna(K) = vanna of calls at strike K
  put_vanna(K)  = absolute value of vanna of puts at strike K
  100           = shares per contract
```

VEX is expressed in "dollars of delta change per 1 vol point change in IV."

### The Key Insight: VIX as an Equity Driver

VEX is the mathematical bridge between VIX and equity prices. This is one of the most important and underappreciated relationships in options market structure.

**When VIX drops:**

1. Implied volatility across the options chain decreases
2. Put deltas become less negative (OTM puts are less likely to expire ITM)
3. Dealers holding short delta hedges (from short puts) find their required hedge has decreased
4. Dealers must BUY the underlying to reduce their short delta position
5. This buying is mechanical, algorithmic, and immediate
6. Result: VIX drops → mechanical buying → stocks/futures go up

**When VIX rises:**

1. Implied volatility across the options chain increases
2. Put deltas become more negative (OTM puts are more likely to expire ITM)
3. Dealers holding short delta hedges find their required hedge has increased
4. Dealers must SELL the underlying to increase their short delta position
5. This selling is mechanical, algorithmic, and immediate
6. Result: VIX rises → mechanical selling → stocks/futures go down

This is the "vanna rally" and "vanna selloff" mechanism. It explains why VIX and equity prices are so tightly correlated: it's not just sentiment, it's mechanical hedging.

### Quantifying Vanna Flow

```
Vanna_flow = VEX × delta_IV

Where:
  VEX      = vanna exposure (dollars of delta per vol point)
  delta_IV = change in implied volatility (in vol points)
```

**Concrete example:**

```
VEX = -$500M per vol point (negative because put OI dominates)
VIX drops 1 point (IV decreases by 1 vol point)
Vanna_flow = -$500M × (-1) = +$500M of buying

Dealers must buy $500M of stock/futures to reduce their short delta.
```

That's $500 million of mechanical buying from a single 1-point VIX drop. In a market where QQQ trades $20-30B per day, this is 1.5-2.5% of daily volume. Significant.

**Larger VIX move:**

```
VEX = -$500M per vol point
VIX drops 3 points (common in a recovery from a fear spike)
Vanna_flow = -$500M × (-3) = +$1.5B of buying
```

$1.5 billion of mechanical buying. This is why VIX drops from elevated levels (25+ to 20) are accompanied by powerful equity rallies. The vanna unwind is a massive mechanical force.

### Vanna Timing: When Does It Matter?

Vanna effects are strongest when:

1. **VIX moves are large (1+ point)**: Small VIX wiggles (0.1-0.2 points) don't trigger significant rebalancing because dealers hedge discretely. The threshold for rebalancing is typically 0.5-1 vol point.

2. **VEX is large in magnitude**: If VEX is small (low put OI), even large VIX moves create minimal vanna flow. VEX is largest when there's been heavy put buying (fear/hedging periods).

3. **The move is from elevated VIX levels**: A VIX drop from 30 to 27 creates more vanna flow than a drop from 15 to 12, because at higher VIX levels, more puts are near-the-money (higher delta, higher vanna).

4. **Morning sessions**: Morning VIX moves have more impact because there's a full day of uncertainty being resolved. Afternoon VIX moves have less impact because expiring options have less time for delta to matter.

### Vanna and the "VIX Crush" Rally

One of the most reliable patterns in options market structure is the "VIX crush rally." After a fear spike (VIX > 25), when VIX begins to normalize:

1. VIX drops from elevated levels
2. Vanna flow creates mechanical buying
3. Buying pushes prices up
4. Rising prices reduce fear further
5. VIX drops more
6. More vanna buying
7. Positive feedback loop until VIX normalizes

This is why recoveries from fear spikes are often faster and more powerful than the initial selloff. The vanna unwind is a mechanical accelerant to the upside.

### Vanna in the Data Rivers

**FlashAlpha**: Provides VEX directly. Track VEX magnitude and sign. Large negative VEX = large vanna buying on VIX drops.

**Massive.com**: Heavy put buying increases VEX magnitude. When Massive shows a surge in put sweeps, VEX is increasing, meaning future VIX drops will create larger vanna flows.

**Unusual Whales**: UW's put OI data by strike provides the raw input for VEX. High put OI at OTM strikes = high vanna sensitivity.

**Rithmic MBO**: Vanna flows appear as large, sudden buy orders in NQ when VIX drops. The Rithmic feed captures these as aggressive market orders or large limit orders placed at the bid. The timing correlates with VIX moves (watch VIX in real-time alongside Rithmic).

---

## CHEX: Charm Exposure

### What Charm Is

Charm (also called "delta decay") is a second-order Greek that measures the sensitivity of delta to the passage of time:

```
Charm = d(delta)/d(time) = -d(theta)/d(spot)
```

Charm is the rate at which delta changes just because time passes, holding everything else constant. It's the "time decay of delta."

For OTM options:
- As time passes, OTM options become less likely to expire ITM
- Their deltas decay toward 0
- Charm is negative for OTM calls (delta decreasing toward 0)
- Charm is positive for OTM puts (delta increasing toward 0, i.e., becoming less negative)

For ITM options:
- As time passes, ITM options become more certain to expire ITM
- Their deltas move toward 1.0 (calls) or -1.0 (puts)
- Charm is positive for ITM calls (delta increasing toward 1.0)
- Charm is negative for ITM puts (delta decreasing toward -1.0)

For ATM options:
- Charm is near zero (delta stays near 0.5 for calls, -0.5 for puts)
- But gamma is increasing, so the RATE of delta change per price move is increasing

### The CHEX Formula

```
CHEX = sum over all strikes K of:
       [call_charm(K) × call_OI(K) - put_charm(K) × put_OI(K)] × 100

Where:
  call_charm(K) = charm of calls at strike K (can be positive or negative)
  put_charm(K)  = charm of puts at strike K (can be positive or negative)
  100           = shares per contract
```

CHEX is expressed in "dollars of delta change per day" (or per hour, depending on the convention).

### The Key Insight: Predictable Mechanical Flows from Time Alone

CHEX creates PREDICTABLE, MECHANICAL flows that occur simply because time passes. Unlike GEX (which requires price moves) or VEX (which requires VIX moves), CHEX flows happen regardless of what the market does.

**The mechanism:**

As time passes, OTM option deltas decay toward 0. This means:
- Dealers holding long delta hedges (from short OTM calls) find their required hedge decreasing
- Dealers must SELL the underlying to reduce their long delta position
- This selling is predictable and time-based

Conversely:
- Dealers holding short delta hedges (from short OTM puts) find their required hedge decreasing (in magnitude)
- Dealers must BUY the underlying to reduce their short delta position
- This buying is predictable and time-based

The NET direction of CHEX flow depends on whether call OI or put OI dominates, and where the OI is concentrated relative to spot.

### CHEX Direction Prediction

**Positive CHEX (net buying pressure from charm):**
- Put OI dominates, especially OTM puts below spot
- As time passes, OTM put deltas decay toward 0
- Dealers holding short delta hedges (from short puts) must buy back
- Net mechanical buying pressure throughout the day

**Negative CHEX (net selling pressure from charm):**
- Call OI dominates, especially OTM calls above spot
- As time passes, OTM call deltas decay toward 0
- Dealers holding long delta hedges (from short calls) must sell
- Net mechanical selling pressure throughout the day

### CHEX Timing: The Afternoon Acceleration

Charm effects are not uniform throughout the day. They accelerate as expiration approaches:

```
Charm ≈ -N'(d1) × [2r × T - d2 × sigma] / (2 × T × sigma × sqrt(T))
```

As T approaches 0, charm increases in magnitude. This means:

- **9:30-11:00 AM**: Charm flows are moderate. 0DTE options have 5-6 hours to expiry.
- **11:00 AM-1:00 PM**: Charm flows increasing. 0DTE options have 3-5 hours to expiry.
- **1:00-2:30 PM**: Charm flows significant. 0DTE options have 1.5-3 hours to expiry.
- **2:30-3:30 PM**: Charm flows strong. 0DTE options have 30-90 minutes to expiry.
- **3:30-4:00 PM**: Charm flows maximum. 0DTE options have less than 30 minutes to expiry.

The last 90 minutes of the session (2:30-4:00 PM ET) is when CHEX flows are most significant. This is why the afternoon session often has a directional drift that seems disconnected from news or fundamentals: it's charm-driven mechanical flow.

### CHEX on OPEX Fridays

On monthly and quarterly OPEX Fridays, CHEX is dramatically amplified because:

1. The expiring OI is much larger than a typical 0DTE day (months of accumulated positions)
2. All that OI is expiring simultaneously
3. The charm flows from all those positions converge in the final hours

OPEX Friday afternoon CHEX flows can be 5-10x larger than a typical 0DTE afternoon. This is a major driver of OPEX Friday volatility.

### Charm and Vanna Interaction

Charm and vanna can reinforce or oppose each other:

**Reinforcing (both bullish):**
- CHEX positive (charm buying) + VIX dropping (vanna buying)
- Both forces push the same direction
- Strong mechanical tailwind for the afternoon session
- Common in recovery rallies: VIX drops (vanna buying) + afternoon charm buying

**Reinforcing (both bearish):**
- CHEX negative (charm selling) + VIX rising (vanna selling)
- Both forces push the same direction
- Strong mechanical headwind for the afternoon session
- Common in selloffs: VIX rises (vanna selling) + afternoon charm selling

**Opposing:**
- CHEX positive (charm buying) + VIX rising (vanna selling)
- Forces cancel. The net direction depends on magnitudes.
- Common in "confused" afternoons where the market oscillates without clear direction

**Practical rule**: When charm and vanna agree, the afternoon directional drift is strong and reliable. When they disagree, the afternoon is choppy and unpredictable.

### CHEX in the Data Rivers

**FlashAlpha**: Provides CHEX directly. Track CHEX sign and magnitude. Large positive CHEX = strong afternoon buying pressure from charm.

**Massive.com**: The OI distribution that drives CHEX is visible in Massive's OI data. Heavy OTM put OI below spot = positive CHEX (charm buying as puts decay). Heavy OTM call OI above spot = negative CHEX (charm selling as calls decay).

**Unusual Whales**: UW's OI by strike and expiration provides the raw data for CHEX. Filter for today's expiration to see the 0DTE CHEX contribution.

**Rithmic MBO**: CHEX flows appear as steady, directional order flow in the afternoon. Unlike GEX flows (which are triggered by price moves) or VEX flows (triggered by VIX moves), CHEX flows are time-triggered. They appear as a steady stream of orders in one direction, typically starting around 2:00-2:30 PM ET and accelerating into the close.

---

## The Full Greek Chain: Integrated View

### How the Four Exposures Interact

GEX, DEX, VEX, and CHEX are not independent. They interact and sometimes reinforce or oppose each other.

**GEX** sets the volatility regime:
- Positive GEX: Moves are dampened. The market has a "home base."
- Negative GEX: Moves are amplified. The market has no anchor.

**DEX** sets the directional tilt:
- Positive DEX: Bearish mechanical pressure (dealers selling into rallies)
- Negative DEX: Bullish mechanical pressure (dealers buying dips)

**VEX** translates VIX moves to equity flows:
- Negative VEX (typical): VIX drops = buying, VIX rises = selling
- The magnitude scales with VEX and the size of the VIX move

**CHEX** creates time-based directional drift:
- Positive CHEX: Afternoon buying pressure (charm-driven)
- Negative CHEX: Afternoon selling pressure (charm-driven)

### A Complete Session Analysis

**Morning (9:30-11:00 AM):**
- GEX regime determines whether moves are dampened or amplified
- DEX determines the directional tilt of any moves
- VEX is relevant if VIX makes a significant move at the open
- CHEX is minimal (too early for charm to matter)

**Midday (11:00 AM-2:00 PM):**
- GEX and DEX continue to dominate
- VEX matters if VIX continues to move
- CHEX begins to contribute (moderate charm flows)

**Afternoon (2:00-4:00 PM):**
- CHEX becomes the dominant force (charm flows accelerating)
- VEX remains relevant if VIX is moving
- GEX still sets the volatility regime
- DEX may shift as 0DTE OI changes throughout the day

**The integrated signal:**

```
Afternoon_bias = sign(CHEX) × magnitude(CHEX)
              + sign(VEX × delta_VIX) × magnitude(VEX × delta_VIX)
              + sign(-DEX) × magnitude(DEX) × (price_move / spot)
```

When all three point the same direction, the afternoon drift is strong and reliable. When they conflict, the afternoon is choppy.

### Regime Matrix

| GEX | DEX | VEX (VIX dropping) | CHEX | Expected Behavior |
|-----|-----|---------------------|------|-------------------|
| Positive | Negative | Positive (buying) | Positive | Strong bull session. Dips bought, rallies orderly. Afternoon drift up. |
| Positive | Positive | Positive (buying) | Positive | Mixed. Vanna/charm bullish but DEX capping rallies. Range-bound with upward bias. |
| Negative | Negative | Positive (buying) | Positive | Volatile but with bullish mechanical support. Dips bought aggressively. |
| Negative | Positive | Negative (selling) | Negative | Worst case. All forces bearish. Amplified decline with afternoon acceleration. |

---

## Practical Application for NQ

### Daily Checklist

**Pre-market:**
1. Pull FlashAlpha: Get GEX (regime), DEX (directional tilt), VEX (vanna sensitivity), CHEX (charm direction)
2. Note VIX level and direction (is VIX rising or falling pre-market?)
3. Compute expected vanna flow: VEX × expected VIX change
4. Note CHEX sign: Will the afternoon drift be bullish or bearish?

**During session:**
1. Monitor VIX in real-time. Each 0.5+ point move triggers vanna flow.
2. Watch Rithmic MBO for large orders that match the predicted vanna/charm direction.
3. After 2:00 PM, weight CHEX heavily. The afternoon drift is often charm-driven.
4. Cross-reference with Massive.com: Are new sweeps changing the OI distribution (shifting DEX/VEX/CHEX)?

**Key thresholds:**

```
VEX significance threshold: |VEX| > $200M per vol point
  Below this: VIX moves have minimal mechanical impact
  Above this: Every 0.5 VIX point matters

CHEX significance threshold: |CHEX| > $100M per day
  Below this: Charm flows are noise
  Above this: Afternoon drift is mechanically driven

DEX significance threshold: |DEX| > $1B
  Below this: Directional tilt is weak
  Above this: Dealers have meaningful directional pressure
```

### The Vanna-Charm Afternoon Playbook

When both VEX and CHEX point the same direction in the afternoon:

1. Identify the direction (both bullish or both bearish)
2. Wait for the 2:00-2:30 PM window (charm flows beginning to accelerate)
3. Enter in the direction of the combined flow
4. Target the close (charm flows peak in the last 30 minutes)
5. Exit before 3:45 PM (gamma explosion from 0DTE can overwhelm charm/vanna)

This is one of the most reliable mechanical patterns in the market. It's not based on price action or fundamentals; it's based on the mathematical certainty of time passing and IV normalizing.
