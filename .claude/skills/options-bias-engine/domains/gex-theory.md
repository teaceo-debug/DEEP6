# GEX Theory: Mathematical Framework, Profile Shapes, and Regime Mechanics

## The GEX Formula: Derivation from First Principles

GEX (Gamma Exposure) is not an arbitrary metric. It derives directly from the Black-Scholes framework and represents the dollar value of dealer hedging required per 1% move in the underlying.

### Step 1: Black-Scholes Gamma Per Share

Under Black-Scholes, the gamma of a European option is:

```
gamma_per_share = N'(d1) / (spot × sigma × sqrt(T))

Where:
  N'(d1) = standard normal PDF evaluated at d1
  d1     = [ln(spot/K) + (r + sigma^2/2) × T] / (sigma × sqrt(T))
  spot   = current underlying price
  K      = strike price
  sigma  = implied volatility (annualized)
  T      = time to expiration (years)
  r      = risk-free rate
```

This gamma is in units of "delta change per $1 move in spot." If spot moves $1, the option's delta changes by gamma_per_share.

### Step 2: Scale to Contract Level

Each standard equity option contract covers 100 shares:

```
gamma_per_contract = gamma_per_share × 100
```

### Step 3: Scale to Open Interest

The total gamma at a given strike is the per-contract gamma multiplied by the number of open contracts:

```
gamma_at_strike = gamma_per_contract × OI(K)
                = gamma_per_share × 100 × OI(K)
```

This is the total delta change across all contracts at strike K when spot moves $1.

### Step 4: Convert to Dollar Terms

The delta change is in "shares" (or contracts). To convert to dollars, multiply by the spot price:

```
dollar_delta_change = gamma_at_strike × spot
```

This gives the dollar value of hedging required when spot moves $1.

### Step 5: Scale to "Per 1% Move" Convention

SpotGamma and FlashAlpha express GEX as "dollars of hedging per 1% move in spot." A 1% move in spot equals spot × 0.01 dollars. So:

```
GEX_K = gamma_per_share × 100 × OI(K) × spot × (spot × 0.01)
       = gamma_per_share × OI(K) × 100 × spot^2 × 0.01
```

This is the standard GEX formula. The spot^2 term is why GEX grows rapidly as the underlying price increases.

### Step 6: Sign Convention

Call options: Dealers are typically SHORT calls (customers buy calls). Dealer short call = dealer long delta hedge. As spot rises, delta increases, dealer buys more. This is pro-cyclical (negative gamma regime). But the CONVENTION in GEX is to express call GEX as POSITIVE because it represents the magnitude of hedging that STABILIZES when dealers are LONG gamma (customers short calls). The sign depends on who is long/short.

FlashAlpha's convention:
- Call GEX: Positive when dealers are net short calls (customers long calls) = NEGATIVE gamma regime
- Put GEX: Negative when dealers are net short puts (customers long puts) = NEGATIVE gamma regime
- Net GEX = Call_GEX - |Put_GEX|

Wait, this is where it gets confusing. Let's be precise:

**SpotGamma/FlashAlpha convention:**
- Calls contribute POSITIVE GEX (regardless of who is long/short)
- Puts contribute NEGATIVE GEX (regardless of who is long/short)
- The assumption is that dealers are SHORT options (customers are long)
- Positive total GEX = calls dominate = dealers short calls = dealers long delta = counter-cyclical hedging
- Negative total GEX = puts dominate = dealers short puts = dealers short delta = pro-cyclical hedging

This is the standard interpretation. When total GEX is positive, the market is in a stabilizing regime. When negative, destabilizing.

---

## FlashAlpha's Computation

FlashAlpha computes GEX from the full options chain across all strikes and expirations:

```
Total_GEX = sum over all K, all T of: GEX(K, T)
          = sum over all K, all T of: gamma(K,T) × OI(K,T) × 100 × spot^2 × 0.01
```

FlashAlpha returns:
- **Total GEX**: The aggregate dollar-hedging per 1% move. Sign indicates regime.
- **GEX by strike**: The GEX profile, showing where gamma is concentrated.
- **Gamma flip**: The strike where net GEX crosses from positive to negative.
- **Call wall**: The strike with the highest positive GEX (strongest call concentration).
- **Put wall**: The strike with the highest negative GEX (strongest put concentration).
- **HVL (High Volume Level)**: The strike with the highest total options volume (not necessarily the highest GEX).

Update frequency: FlashAlpha updates intraday, but the underlying OI data is from the previous day's settlement. Intraday GEX is an estimate that incorporates today's volume to adjust OI. The walls (high-OI strikes) are reliable because large OI positions don't change much intraday. The total GEX is less reliable intraday because it depends on aggregate OI that may have shifted.

For NQ: FlashAlpha computes for QQQ and NDX. Apply the conversion ratio (see nq-options-proxy.md) to translate levels to NQ prices.

---

## GEX Profile Shapes and Their Meaning

The GEX profile is a bar chart of GEX by strike. The shape of this profile is as important as the total GEX number. Different shapes imply different market dynamics.

### Shape 1: Tall Narrow Spike Near ATM

```
GEX
 |
 |        |||
 |        |||
 |   |    |||    |
 |   |    |||    |
 +---+----+++----+----> Strike
        ATM
```

Characteristics:
- Concentrated OI at 1-3 strikes near current price
- Very high GEX at the spike strike, low GEX at adjacent strikes
- Example: 50,000 OI at the $520 QQQ strike, less than 5,000 at $519 and $521

What it means:
- STRONG pinning tendency at the spike strike
- The market has a gravitational center. Price will be pulled toward the spike.
- Moves away from the spike face immediate counter-hedging
- The pin is strong but brittle: if a catalyst overwhelms it, the break is violent because there's no distributed support

When it occurs:
- Low-volatility, range-bound periods
- After a period of concentrated options selling at a specific strike
- Common in the week before monthly OPEX when the market has been stable

Trading implication:
- Fade moves away from the spike strike
- Expect mean reversion to the spike
- Be cautious of pin breaks (they're fast and violent)

### Shape 2: Broad Positive Dome

```
GEX
 |
 |      |||||||
 |    |||||||||||||
 |   |||||||||||||||
 |  |||||||||||||||||
 +--+++++++++++++++++--> Strike
         ATM
```

Characteristics:
- Positive GEX distributed across 20+ strikes around spot
- No single dominant strike, but a broad region of positive GEX
- Total GEX is high, but no single strike has extreme concentration

What it means:
- Diffuse stabilization across a RANGE, not at a single point
- The market is cushioned across a wide zone
- Harder for price to break out because there's no single weak point in the defense
- Moves within the dome face continuous counter-hedging from multiple strikes
- The dome's edges are the effective range boundaries

When it occurs:
- Strong bull trends with distributed call OI (many strikes have been sold against long stock)
- After a period of steady upward drift with options selling at each new high
- Common in low-vol bull markets (VIX < 15)

Trading implication:
- Range-bound behavior within the dome
- Sell volatility (options selling strategies work well)
- Breakouts from the dome are significant and tend to be sustained (the distributed support is gone)

### Shape 3: Negative Left Tail

```
GEX
 |
 |              |||||||
 |           ||||||||||||
 |        |||||||||||||||
 |  |||   |||||||||||||||
 +--+++---+++++++++++++++-> Strike
   neg    ATM    pos
```

Characteristics:
- Positive GEX above spot (stabilizing)
- Negative GEX below spot (destabilizing)
- The gamma flip is below current price

What it means:
- Above the flip: market is cushioned. Rallies are dampened.
- Below the flip: market is exposed. Declines are amplified.
- "Everything's fine until it isn't" profile
- The flip level is the critical threshold. If price drops below it, regime changes instantly.

When it occurs:
- Bull markets with put hedging below current price
- Institutions are buying downside protection (puts) while the market is above
- Common in late-stage bull markets where smart money is hedging but not yet selling

Trading implication:
- Above the flip: treat as positive gamma regime (range-bound, fade moves)
- Below the flip: treat as negative gamma regime (trend-following, don't fade)
- The flip level is the most important level on the chart
- A break below the flip is a regime change signal, not just a support break

### Shape 4: Deep Negative Profile

```
GEX
 |
 |
 |
 |
 +--+++++++++++++++++++--> Strike
    |||||||||||||||||||
    |||||||||||||||||||
    |||||||||||||||||||
    |||||||||||||||||||
   neg              neg
```

Characteristics:
- Negative GEX across most strikes, especially near and below spot
- Dealers are massively short gamma (lots of put buying by customers)
- Total GEX is deeply negative (e.g., -$10B or more)

What it means:
- Any move is amplified. Up moves are amplified (dealers buying to cover short delta). Down moves are amplified (dealers selling to increase short delta).
- But the asymmetry: put buying creates more negative GEX below spot, so down moves are MORE amplified than up moves.
- Crash risk is elevated. A 2% decline can cascade into 5%+ because dealer hedging accelerates the move.
- Realized volatility will be significantly higher than implied volatility (dealers are adding vol, not absorbing it).

When it occurs:
- Selloffs and corrections (VIX > 25)
- After a large gap down that triggers put buying
- During macro uncertainty events (Fed meetings, geopolitical events)
- When the market has been falling and put hedging demand has spiked

Trading implication:
- Do NOT fade moves. Trend-following only.
- Expect larger-than-normal moves in both directions
- Options are expensive (IV elevated). Buying options is costly.
- The regime can persist for days to weeks until put hedging demand subsides

### Shape 5: Split Profile (Bimodal)

```
GEX
 |
 |  |||              |||
 |  |||              |||
 |  |||              |||
 +--+++--+--+--+--+--+++-> Strike
   neg  flip ATM      pos
```

Characteristics:
- Positive GEX above spot, negative GEX below spot
- The gamma flip is very close to current price (within 0.5-1%)
- A gap or low-GEX zone near the flip

What it means:
- "Knife edge" regime. The market is balanced on the boundary between stabilizing and destabilizing.
- Small move up: positive gamma regime, stabilizing
- Small move down: negative gamma regime, destabilizing
- Maximum uncertainty about which regime will prevail
- The gap near the flip means there's no cushion at the transition point

When it occurs:
- Regime transitions (market recovering from a selloff, or beginning a selloff from a bull market)
- After a large move that has brought price near the gamma flip
- Common in the first few days after a significant macro event

Trading implication:
- Extreme caution. The regime can flip multiple times in a single session.
- Wait for price to establish clearly above or below the flip before committing to a directional bias
- The flip level itself is a magnet (price will test it repeatedly)
- When the flip finally breaks decisively, the move is often large

---

## GEX Regime Mechanics in Detail

### The Dampening Constant

In a positive gamma regime, the dampening effect can be quantified:

```
Dampening_ratio = GEX / (ADV × spot)

Where:
  ADV = average daily volume of the underlying (in shares/contracts)
  spot = current price
```

A dampening ratio of 0.1 means dealer hedging represents 10% of average daily volume per 1% move. This is significant. A dampening ratio of 0.5 means dealer hedging is 50% of ADV per 1% move, which creates very strong pinning.

For QQQ with GEX = +$5B and ADV = 80M shares at $520:
```
Dampening_ratio = $5B / (80M × $520) = $5B / $41.6B = 0.12
```

So dealer hedging is 12% of ADV per 1% move. Meaningful but not overwhelming.

For a high-GEX day with GEX = +$15B:
```
Dampening_ratio = $15B / $41.6B = 0.36
```

36% of ADV per 1% move. Very strong pinning. The market will struggle to move more than 0.5-1% in either direction.

### GEX and Realized Volatility

The empirical relationship between GEX and realized volatility:

- High positive GEX (dampening ratio > 0.3): Realized vol is typically 20-35% LOWER than implied vol. Options sellers profit.
- Moderate positive GEX (dampening ratio 0.1-0.3): Realized vol is roughly equal to implied vol. Neutral.
- Negative GEX (dampening ratio < 0): Realized vol is typically 30-60% HIGHER than implied vol. Options buyers profit.

This relationship is not guaranteed but holds empirically across thousands of trading days. The mechanism is clear: positive gamma creates counter-cyclical hedging that absorbs volatility. Negative gamma creates pro-cyclical hedging that generates volatility.

### GEX and Trend Interaction

GEX doesn't exist in isolation. It interacts with the existing trend:

**Uptrend + Positive GEX:**
- Moves are orderly. Pullbacks are shallow (dealers buy dips). Rallies are gradual (dealers sell into strength).
- The trend continues but at a measured pace.
- This is the "melt-up" regime: slow, steady, low-volatility appreciation.

**Uptrend + Negative GEX:**
- Moves are disorderly. Rallies can be explosive (dealers chasing). Pullbacks can be sharp (dealers selling).
- The trend may continue but with high volatility.
- This is the "volatile bull" regime: fast moves, frequent reversals, high realized vol.

**Downtrend + Positive GEX:**
- Unusual but possible. The market is falling but dealer hedging is counter-cyclical.
- Declines are orderly. Bounces are frequent (dealers buying dips).
- This is the "grinding bear" regime: slow, steady decline with frequent bounces.

**Downtrend + Negative GEX:**
- The most dangerous regime. Declines are amplified by dealer hedging.
- Bounces are weak (dealers selling into them). Declines are fast.
- This is the "crash" regime: rapid, disorderly decline with minimal bouncing.

---

## GEX Staleness and Reliability

### The OI Lag Problem

Open interest is reported by the OCC (Options Clearing Corporation) after the close of each trading day. This means:

- Monday's GEX computation uses Friday's OI data
- Intraday GEX is an ESTIMATE based on previous day's OI + assumptions about today's volume

FlashAlpha attempts to estimate intraday OI changes by:
1. Starting with previous day's OI
2. Adding estimated new positions from today's volume (assuming some fraction of volume is new OI vs. closing)
3. Adjusting for known large trades (block trades, sweeps visible in the tape)

The reliability of intraday GEX:
- **Wall positions (high-OI strikes)**: Very reliable. Large OI positions don't change much intraday. A strike with 100,000 OI won't drop to 50,000 in a single session.
- **Total GEX**: Less reliable. The aggregate can shift meaningfully if there's heavy options activity.
- **Gamma flip**: Moderately reliable. The flip is determined by the balance of call vs. put OI, which is relatively stable intraday.

### When to Trust vs. Distrust Intraday GEX

Trust intraday GEX when:
- The session is quiet (low options volume, no large sweeps)
- The market is near the center of the GEX profile (not near the flip)
- It's mid-cycle (not OPEX week, not post-OPEX Monday)

Distrust intraday GEX when:
- There's been a large sweep or block trade (OI may have shifted significantly)
- It's OPEX week (OI is rolling, changing rapidly)
- The market has made a large move (options may have been exercised or closed)
- It's post-OPEX Monday (previous day's OI is now stale by definition)

---

## The Gamma Flip: Regime Boundary

The gamma flip is the price level where net GEX crosses from positive to negative. It's not just a price level; it's a regime boundary.

### Computing the Flip

The flip is found by scanning the GEX profile from high strikes to low strikes and finding where cumulative GEX crosses zero:

```
Cumulative_GEX(K) = sum of GEX(K') for all K' >= K

Flip = K where Cumulative_GEX(K) crosses from positive to negative
```

FlashAlpha computes this directly and reports it as the "gamma flip" or "zero gamma level."

### Flip Dynamics

The flip is not static. It moves as:
1. OI changes (new positions established, old positions closed)
2. Spot moves (gamma at each strike changes as spot moves relative to strikes)
3. Time passes (gamma at each strike changes as expiration approaches)

In a stable market, the flip moves slowly (a few points per day). In a volatile market, the flip can move significantly intraday.

### Flip as a Trading Level

The flip is the most important single level in the GEX framework:
- Above the flip: positive gamma regime, counter-cyclical hedging, stabilizing
- Below the flip: negative gamma regime, pro-cyclical hedging, destabilizing
- At the flip: maximum uncertainty, regime transition

Price behavior near the flip:
- The flip acts as a magnet (price is drawn to it from both sides)
- Price often oscillates around the flip before committing to one side
- A decisive break through the flip (with volume and momentum) signals a regime change
- A false break (price crosses flip but quickly reverses) is common and should be treated as noise

The flip in the data rivers:
- FlashAlpha reports the flip directly
- Rithmic MBO: Watch for absorption at the flip level (large orders being filled without price moving). Absorption at the flip = the flip is holding.
- Massive.com: Watch for large sweeps that push price through the flip. A sweep that crosses the flip is a regime change signal.

---

## Practical GEX Application for NQ

### Daily Workflow

1. **Pre-market**: Pull FlashAlpha GEX for QQQ and NDX. Note total GEX (regime), gamma flip, call wall, put wall. Convert to NQ levels.

2. **Market open**: Confirm price is above or below the flip. This sets the regime for the session.

3. **Intraday**: Monitor for regime changes (price crossing the flip). Update GEX estimate if there's been significant options activity.

4. **Post-market**: Note any large options trades that may shift tomorrow's GEX profile.

### Key Numbers to Track

```
Total GEX:
  > +$5B: Strong positive gamma. Expect range-bound, low-vol session.
  +$1B to +$5B: Moderate positive gamma. Slight dampening.
  -$1B to +$1B: Near-neutral. Regime unclear. Watch the flip.
  -$1B to -$5B: Moderate negative gamma. Elevated vol expected.
  < -$5B: Strong negative gamma. High vol, trend-following regime.

Dampening ratio (GEX / (ADV × spot)):
  > 0.3: Very strong pinning. Fade moves.
  0.1-0.3: Moderate pinning. Slight mean-reversion bias.
  < 0.1: Weak pinning. Trend-following viable.
  < 0: Amplification. Trend-following only.
```

### GEX and the Four Data Rivers

**FlashAlpha**: Primary source for GEX data. Provides total GEX, profile, flip, walls. Use for regime determination and level identification.

**Massive.com**: Provides the flow that CREATES GEX. Large sweeps in calls increase call OI → increases positive GEX. Large sweeps in puts increase put OI → increases negative GEX. Massive flow is a leading indicator of GEX changes.

**Unusual Whales**: Provides OI data and positioning context. UW's put/call OI ratio by strike helps validate the GEX profile. High put OI below spot = negative GEX below spot (consistent with negative left tail profile).

**Rithmic MBO**: Provides the EXECUTION of dealer hedging. When GEX predicts buying at a level, Rithmic should show absorption (large bids being filled) at that level. When GEX predicts selling, Rithmic should show distribution (large offers being filled). The Rithmic data validates whether the GEX-predicted hedging is actually occurring.
