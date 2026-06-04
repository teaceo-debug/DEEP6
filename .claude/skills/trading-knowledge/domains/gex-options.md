# GEX and Options Knowledge Domain

Last verified: 2026-05-12

---

## GEX-01: Gamma Exposure — What It Is and How It's Calculated

**Category**: GEX
**Tags**: gex, gamma_exposure, options_market_making, dealer_hedging, nq_proxy
**DEEP6 Signal(s)**: GEX-01..06
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\gex.py` (lines 218–305)

### Concept

GEX (Gamma Exposure) measures the total gamma held by options market makers (dealers) across all strikes and expirations. It quantifies how much dealers must buy or sell the underlying to stay delta-neutral as price moves.

The formula per strike:
```
GEX = gamma × open_interest × 100 × spot²
```

- `gamma`: rate of change of delta per $1 move in underlying
- `open_interest`: number of open contracts at that strike
- `100`: shares per contract (equity options convention)
- `spot²`: scales GEX to dollar terms

**Call GEX is positive**: Dealers who sold calls are long gamma. When price rises, their delta increases, so they SELL the underlying to hedge. When price falls, they BUY. This creates a dampening effect.

**Put GEX is negative**: Dealers who sold puts are short gamma. When price falls, their delta becomes more negative, so they SELL the underlying to hedge. When price rises, they BUY. This amplifies moves.

**Net GEX** = sum of all call GEX + put GEX across all strikes.

### Conditions / Setup

DEEP6 uses QQQ options as a proxy for NQ futures:
- QQQ tracks the Nasdaq-100 (same index as NQ)
- NQ ≈ QQQ × 40 (rough approximation; NQ is 100× NDX, QQQ tracks NDX)
- Data source: Massive.com / Polygon-compatible API
- Options chain fetched within ±10% of current spot price

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\gex.py
  Lines 218–305: _compute_gex() — full GEX computation from options chain
  Lines 232–259: Per-contract GEX calculation (call positive, put negative)
  Lines 244–246: GEX formula: gamma × oi × 100 × spot × spot
  Lines 193–216: _fetch_options_chain() — Polygon API call with pagination
  Lines 109–133: fetch_and_compute() — public entry point
```

### Academic Basis

- Dealer gamma hedging mechanics: Bollen & Whaley (2004), "Does Net Buying Pressure Affect the Shape of Implied Volatility Functions?"
- GEX as market regime indicator: Squeezemetrics (2017), "The Implied Order Book" (white paper)
- Gamma exposure and realized volatility: Derman & Kani (1994), "Riding on a Smile"

### Examples / Edge Cases

- **GEX calculation requires accurate OI**: Stale open interest data produces incorrect GEX levels. DEEP6 marks levels as stale after `staleness_seconds` and returns NEUTRAL regime.
- **QQQ proxy accuracy**: The NQ/QQQ ratio drifts over time. DEEP6 uses `nq_to_qqq_divisor` (configurable) for the conversion. Recalibrate quarterly.
- **Expiration effects**: GEX spikes near expiration as gamma increases for near-the-money options. OpEx weeks (monthly/quarterly) have elevated GEX effects.

---

## GEX-02: Positive GEX Regime — Mean-Reverting Market

**Category**: GEX
**Tags**: positive_gex, dampening, mean_reversion, dealer_long_gamma, absorption_boost
**DEEP6 Signal(s)**: GEX-03 (regime classification)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\gex.py` (lines 284–288)

### Concept

When spot price is ABOVE the gamma flip level, net GEX is positive. Dealers are net long gamma. Their hedging behavior creates a dampening effect:

- Price rises → dealers sell → price is pushed back down
- Price falls → dealers buy → price is pushed back up

This creates a mean-reverting, range-bound market. Absorption and exhaustion signals work best in this regime because dealer flow reinforces reversals.

Characteristics of positive GEX regime:
- Lower realized volatility
- Tighter intraday ranges
- Reversals at key levels are more reliable
- Breakouts are harder to sustain (dealers fade them)

### Conditions / Setup

- `spot > gamma_flip` → `GexRegime.POSITIVE_DAMPENING`
- DEEP6 boosts absorption/exhaustion weights: `gex_abs_mult = 1.3`
- DEEP6 suppresses momentum signals: `gex_momentum_mult = 0.8`

### Entry / Exit Rules

In positive GEX regime, DEEP6 favors:
- Absorption signals at resistance (dealers selling into price rise)
- Exhaustion signals at support (dealers buying into price fall)
- Fade setups at call wall and put wall

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\gex.py
  Lines 284–288: Regime classification (spot > gamma_flip → POSITIVE_DAMPENING)
  Lines 162–164: GexSignal direction = +1 in positive regime (favor fading)

C:\Users\Tea\DEEP6\deep6\scoring\scorer.py
  Lines 324–326: gex_abs_mult = 1.3, gex_momentum_mult = 0.8 in positive regime
  Lines 413–424: Applied to category weights
```

### Examples / Edge Cases

- **Positive GEX + absorption at call wall**: Highest-quality short setup. Dealers are selling at the call wall AND absorption confirms selling pressure. DEEP6 gives this a +5 wall bonus AND 1.3× absorption weight.
- **Positive GEX + breakout attempt**: Breakouts in positive GEX regime often fail. The 0.8× momentum weight correctly suppresses these signals.

---

## GEX-03: Negative GEX Regime — Trending/Volatile Market

**Category**: GEX
**Tags**: negative_gex, amplifying, trending, dealer_short_gamma, momentum_boost
**DEEP6 Signal(s)**: GEX-03 (regime classification)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\gex.py` (lines 284–288)

### Concept

When spot price is BELOW the gamma flip level, net GEX is negative. Dealers are net short gamma. Their hedging behavior amplifies moves:

- Price falls → dealers sell more → price falls further
- Price rises → dealers buy more → price rises further

This creates a trending, high-volatility market. Momentum signals work better; absorption signals are less reliable because dealer flow adds to moves rather than fading them.

Characteristics of negative GEX regime:
- Higher realized volatility
- Wider intraday ranges
- Trends are more persistent
- Reversals are harder to sustain (dealers amplify moves)
- VIX tends to be elevated

### Conditions / Setup

- `spot < gamma_flip` → `GexRegime.NEGATIVE_AMPLIFYING`
- DEEP6 suppresses absorption/exhaustion weights: `gex_abs_mult = 0.7`
- DEEP6 boosts momentum signals: `gex_momentum_mult = 1.3`

### Entry / Exit Rules

In negative GEX regime, DEEP6 favors:
- Delta divergence signals (momentum exhaustion)
- Slingshot patterns (explosive directional moves)
- Trend-following setups

Absorption signals are penalized (0.7× weight) because dealer flow can overwhelm passive absorption.

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\gex.py
  Lines 284–288: Regime classification (spot < gamma_flip → NEGATIVE_AMPLIFYING)
  Lines 165–167: GexSignal direction = -1 in negative regime (favor momentum)

C:\Users\Tea\DEEP6\deep6\scoring\scorer.py
  Lines 327–329: gex_abs_mult = 0.7, gex_momentum_mult = 1.3 in negative regime
```

### Examples / Edge Cases

- **Negative GEX + absorption signal**: Absorption fires but gets 0.7× weight. Score may not reach TYPE_A threshold. This is correct — absorption in negative GEX has lower reliability.
- **Negative GEX + delta slingshot**: Slingshot gets 1.3× momentum weight. More likely to reach TYPE_B/A threshold. Correct — explosive moves in negative GEX are more sustained.
- **Transition from positive to negative**: The gamma flip crossing is itself a signal. Markets often accelerate after crossing below the flip.

---

## GEX-04: Call Wall — Structural Resistance

**Category**: GEX
**Tags**: call_wall, resistance, dealer_selling, structural_ceiling, options_oi
**DEEP6 Signal(s)**: GEX-04 (near_call_wall detection)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\gex.py` (lines 228–253)

### Concept

The call wall is the strike price with the largest call gamma × open interest. At this level, dealers have sold the most calls and must sell the underlying aggressively as price approaches from below (to hedge their increasing delta).

This creates a structural ceiling: as price approaches the call wall, dealer selling pressure increases, making it harder for price to break through.

The call wall is NOT a hard barrier — it can be broken, especially in negative GEX regime. But in positive GEX, it acts as a reliable resistance level.

### Conditions / Setup

Call wall is identified as:
```
max_call_strike = argmax(gamma × OI) across all call strikes
```

DEEP6 detects "near call wall" when:
```
|qqq_approx - call_wall| / call_wall < near_wall_pct (default 0.5%)
```

### Entry / Exit Rules

Near call wall + SHORT signal direction:
- `gex_near_wall_bonus = +5.0` added to score
- Rationale: dealer selling creates structural ceiling, reinforcing short signals

Near call wall + LONG signal direction:
- `gex_direction_conflict = True`
- TYPE_A and TYPE_B blocked (going long into massive dealer selling)
- Maximum tier: TYPE_C or QUIET

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\gex.py
  Lines 228–253: Call wall identification in _compute_gex()
  Lines 157–159: near_call detection in get_signal()
  Lines 172–173: Call wall detail string

C:\Users\Tea\DEEP6\deep6\scoring\scorer.py
  Lines 334–335: Near call wall + SHORT → +5.0 bonus
  Lines 339–340: Near call wall + LONG → gex_direction_conflict = True
  Lines 470–477: Direction conflict tier demotion
```

### Examples / Edge Cases

- **Call wall as magnet**: Price often gravitates toward the call wall before reversing. The wall is a target, not just a barrier.
- **Call wall break**: If price breaks above the call wall with strong momentum, dealers must buy aggressively to hedge (gamma squeeze). This can create explosive upside moves.
- **Multiple call walls**: The options chain may have several high-OI call strikes. DEEP6 uses the single highest-GEX strike. In practice, a cluster of nearby strikes creates a broader resistance zone.

---

## GEX-05: Put Wall — Structural Support

**Category**: GEX
**Tags**: put_wall, support, dealer_buying, structural_floor, options_oi
**DEEP6 Signal(s)**: GEX-05 (near_put_wall detection)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\gex.py` (lines 228–259)

### Concept

The put wall is the strike price with the largest put gamma × open interest. At this level, dealers have sold the most puts and must buy the underlying aggressively as price approaches from above (to hedge their increasing negative delta).

This creates a structural floor: as price approaches the put wall, dealer buying pressure increases, making it harder for price to break through.

### Conditions / Setup

Put wall is identified as:
```
max_put_strike = argmax(gamma × OI) across all put strikes
```

DEEP6 detects "near put wall" when:
```
|qqq_approx - put_wall| / put_wall < near_wall_pct (default 0.5%)
```

### Entry / Exit Rules

Near put wall + LONG signal direction:
- `gex_near_wall_bonus = +5.0` added to score
- Rationale: dealer buying creates structural floor, reinforcing long signals

Near put wall + SHORT signal direction:
- `gex_direction_conflict = True`
- TYPE_A and TYPE_B blocked (going short into massive dealer buying)
- Maximum tier: TYPE_C or QUIET

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\gex.py
  Lines 254–259: Put wall identification in _compute_gex()
  Lines 159:     near_put detection in get_signal()

C:\Users\Tea\DEEP6\deep6\scoring\scorer.py
  Lines 336–337: Near put wall + LONG → +5.0 bonus
  Lines 341–342: Near put wall + SHORT → gex_direction_conflict = True
```

### Examples / Edge Cases

- **Put wall as bounce level**: In positive GEX, the put wall is a reliable bounce level. Absorption at the put wall = highest-quality long setup.
- **Put wall break**: If price breaks below the put wall, dealers must sell aggressively (gamma squeeze to the downside). This can create explosive downside moves — especially dangerous in negative GEX.
- **Put wall migration**: As the market falls, put walls can migrate lower as traders roll their puts. Track the put wall daily.

---

## GEX-06: Gamma Flip Level — The Regime Boundary

**Category**: GEX
**Tags**: gamma_flip, zero_gamma, regime_boundary, transition_zone, hvl
**DEEP6 Signal(s)**: GEX-06 (gamma_flip)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\gex.py` (lines 264–288)

### Concept

The gamma flip (also called "zero gamma" or "zero GEX") is the price level where net GEX crosses zero. Above it: positive GEX (dampening). Below it: negative GEX (amplifying).

The gamma flip is computed via linear interpolation between the two adjacent strikes where net GEX changes sign:
```
gamma_flip = s1 + (s2 - s1) × |g1| / (|g1| + |g2|)
```

The gamma flip is the most important GEX level for regime classification. Crossing it changes the entire market dynamic.

### Conditions / Setup

- Requires at least two adjacent strikes with opposite-sign net GEX
- If no sign change found: `GexRegime.NEUTRAL`
- `spot > gamma_flip` → POSITIVE_DAMPENING
- `spot < gamma_flip` → NEGATIVE_AMPLIFYING

DEEP6 also exposes `GexLevels.zero_gamma` as an alias for `gamma_flip` (D-29 naming alias).

### Entry / Exit Rules

The gamma flip itself is a key reference level:
- Price approaching gamma flip from above: watch for regime change to negative
- Price approaching gamma flip from below: watch for regime change to positive
- Price oscillating around gamma flip: NEUTRAL regime, mixed signals

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\gex.py
  Lines 264–275: Gamma flip interpolation
  Lines 284–288: Regime classification from gamma flip
  Lines 58–67:   GexLevels.zero_gamma property (alias for gamma_flip)
  Lines 290–305: GexLevels construction with gamma_flip field
```

### Examples / Edge Cases

- **Gamma flip as intraday pivot**: On days when price oscillates around the gamma flip, expect choppy, mean-reverting action. Neither positive nor negative regime dominates.
- **Gamma flip break with momentum**: When price breaks through the gamma flip with strong delta, the regime change amplifies the move. This is a high-conviction directional signal.
- **Gamma flip vs HVL**: The gamma flip is where net GEX = 0. HVL is where |net GEX| is maximum. These are different levels. HVL is often near the gamma flip but not identical.

---

## GEX-07: HVL — High Volatility Level

**Category**: GEX
**Tags**: hvl, high_volatility_level, peak_gex, transition_zone, volatility_anchor
**DEEP6 Signal(s)**: GEX-01 (hvl field in GexLevels)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\gex.py` (lines 277–278)

### Concept

HVL (High Volatility Level) is the strike with the highest absolute net GEX value. It represents the price level where dealer hedging activity is most intense — the "eye of the storm."

At HVL:
- Dealers have the most gamma to hedge
- Small price moves trigger large hedging flows
- Volatility is highest near this level
- Price can move rapidly through HVL in either direction

HVL is distinct from the gamma flip (where GEX = 0) and from the call/put walls (which are directional). HVL is the peak of the absolute GEX curve.

### Conditions / Setup

```
hvl_strike = argmax(|net_gex|) across all strikes
```

DEEP6 also tracks `largest_gamma_strike` (D-28): the peak raw call gamma × OI strike BEFORE put netting. This is used by CR-04 (Pin Regime) in confluence rules.

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\gex.py
  Lines 277–278: HVL computation (peak |net GEX| strike)
  Lines 42–44:   GexLevels.hvl and largest_gamma_strike fields
  Lines 295–299: D-28 comment explaining largest_gamma_strike vs hvl distinction
```

### Examples / Edge Cases

- **HVL as volatility magnet**: Price often gravitates toward HVL during high-volatility sessions. It's where the most dealer activity concentrates.
- **HVL near gamma flip**: When HVL and gamma flip are close together, the transition zone is narrow and regime changes are sharp.
- **Pin risk at expiration**: Near expiration, price often "pins" to the HVL or largest gamma strike as dealers aggressively hedge. This is the "max pain" phenomenon.

---

## GEX-08: Options Flow — Unusual Trades, Put/Call Ratio, Sweeps vs Blocks

**Category**: GEX
**Tags**: options_flow, unusual_options_activity, put_call_ratio, sweeps, blocks, dark_pool
**Python File**: N/A (conceptual — not yet implemented in DEEP6)

### Concept

Options flow analysis looks at the actual trades happening in the options market, not just open interest. Key metrics:

**Put/Call Ratio (PCR)**:
- PCR = put volume / call volume
- PCR > 1: more puts being bought → bearish sentiment or hedging
- PCR < 1: more calls being bought → bullish sentiment
- Extreme PCR values are contrarian indicators (too much one-sided positioning)

**Sweeps vs Blocks**:
- **Sweep**: Large options order that hits multiple exchanges simultaneously, taking all available liquidity. Indicates urgency — someone needs to get filled NOW. Often directional.
- **Block**: Large options order negotiated off-exchange (dark pool). May be hedging, not directional.
- Sweeps are more informative for directional bias than blocks.

**Unusual Options Activity (UOA)**:
- Volume significantly above average open interest at a specific strike
- Often precedes large moves (informed trading or hedging of known catalyst)
- For NQ/QQQ: watch for large call sweeps above current price (bullish) or large put sweeps below (bearish)

**Flow Toxicity**:
- VPIN (Volume-synchronized Probability of Informed Trading) measures whether options flow is informed
- High VPIN = informed traders dominating = higher probability of sustained directional move
- DEEP6 uses VPIN as a final score modifier (see STRAT-08)

### Conditions / Setup

DEEP6 currently uses GEX (open interest × gamma) rather than real-time options flow. Real-time flow would require a separate data feed (e.g., Unusual Whales, Market Chameleon, or direct options tape).

The GEX engine uses Massive.com / Polygon API for options chain snapshots, not real-time flow.

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\gex.py
  Lines 84–108:  GexEngine.__init__ — API configuration
  Lines 193–216: _fetch_options_chain() — snapshot fetch (not real-time flow)
```

Future enhancement: integrate real-time options flow (sweeps, blocks) as a separate signal category.

### Academic Basis

- Options order flow and price discovery: Pan & Poteshman (2006), "The Information in Option Volume for Future Stock Prices"
- Put/call ratio as sentiment indicator: Blau et al. (2014), "Short Selling and Put Option Activity"
- Informed trading in options: Easley et al. (1998), "Option Volume and Stock Prices: Evidence on Where Informed Traders Trade"

### Examples / Edge Cases

- **Large call sweep before earnings**: Often indicates informed buying ahead of a positive catalyst. Not always — can be hedging.
- **PCR spike at market bottom**: Extreme put buying at market lows is a contrarian bullish signal. Everyone is hedging, which means the move is likely exhausted.
- **Dark pool blocks**: Large block trades in options are often institutional hedges, not directional bets. Don't over-interpret them.

---

## GEX-09: GEX Staleness Handling

**Category**: GEX
**Tags**: gex_staleness, data_freshness, neutral_fallback, gex_06
**DEEP6 Signal(s)**: GEX-06 (staleness handling)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\gex.py` (lines 140–152)

### Concept

GEX data has a shelf life. Options chains change throughout the day as trades occur and OI updates. DEEP6 marks GEX levels as stale after `staleness_seconds` and falls back to NEUTRAL regime.

This prevents the system from making regime-based decisions on outdated data.

### Conditions / Setup

- `GexLevels.age_seconds()` computes time since last fetch
- If `age > staleness_seconds`: `levels.stale = True`
- Stale GEX → `GexSignal` with `GexRegime.NEUTRAL`, all walls at 0, strength 0
- API errors: return stale levels if available, otherwise empty levels

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\gex.py
  Lines 51–56:   GexLevels.age_seconds() — accepts optional now override for replay
  Lines 140–152: get_signal() staleness check
  Lines 128–133: fetch_and_compute() error handling (return stale or empty)
  Lines 307–308: _empty_levels() — returns stale=True GexLevels
```

### Examples / Edge Cases

- **Replay mode**: `age_seconds()` accepts an optional `now` parameter so replay can pass `state.clock.now()` instead of `time.time()`. This prevents all historical GEX data from appearing stale during replay.
- **API outage**: If the Polygon/Massive API is down, DEEP6 continues with NEUTRAL regime. Absorption/exhaustion signals still fire but without GEX regime modification.

---

## GEX-10: DEEP6 GEX Integration Summary

**Category**: GEX
**Tags**: gex_integration, scoring_impact, regime_modifier, wall_bonus, direction_conflict
**Python File**: `C:\Users\Tea\DEEP6\deep6\scoring\scorer.py` (lines 316–342)

### Concept

GEX integrates into DEEP6's scoring cascade at three points:

1. **Category weight modification** (lines 413–424): Absorption/exhaustion weights multiplied by `gex_abs_mult`; delta/imbalance weights multiplied by `gex_momentum_mult`. Applied before base score computation.

2. **Wall bonus** (lines 334–337): +5.0 points when price is near a wall AND signal direction aligns with dealer flow. Applied after base score, before IB multiplier.

3. **Direction conflict** (lines 339–342, 470–477): When signal direction fights dealer flow (LONG at call wall, SHORT at put wall), TYPE_A and TYPE_B are blocked. Maximum tier becomes TYPE_C or QUIET.

The GEX modifier is applied BEFORE the VPIN modifier in the pipeline order.

### Conditions / Setup

Full GEX impact on scoring:

| Regime | Absorption/Exhaustion | Delta/Imbalance | Wall Bonus | Direction Conflict |
|---|---|---|---|---|
| POSITIVE_DAMPENING | ×1.3 | ×0.8 | +5 if aligned | Blocks TYPE_A/B if misaligned |
| NEGATIVE_AMPLIFYING | ×0.7 | ×1.3 | +5 if aligned | Blocks TYPE_A/B if misaligned |
| NEUTRAL | ×1.0 | ×1.0 | None | None |

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\scoring\scorer.py
  Lines 316–342: Full GEX modifier block
  Lines 413–424: Weight application
  Lines 427:     Score formula includes gex_near_wall_bonus
  Lines 470–477: Direction conflict tier demotion

C:\Users\Tea\DEEP6\deep6\engines\gex.py
  Lines 135–191: get_signal() — converts GexLevels to GexSignal for scorer
  Lines 71–82:   GexSignal dataclass fields
```

### Examples / Edge Cases

- **No GEX data**: `gex_signal is None` → all GEX modifiers are 1.0, no wall bonus, no direction conflict. System operates as if GEX is neutral.
- **GEX + IB multiplier**: Both can apply simultaneously. A TYPE_A signal in the first 60 bars with positive GEX and absorption at put wall gets: 1.3× absorption weight + 1.25× confluence mult + 5.0 wall bonus + 1.15× IB mult. This can push scores well above 80.
- **Regime change mid-session**: GEX is fetched periodically. If regime changes from positive to negative mid-session, the scorer immediately adjusts weights on the next bar.
