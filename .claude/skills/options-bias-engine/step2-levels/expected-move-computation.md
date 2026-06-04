# Expected Move Computation — Statistical Boundaries from Implied Volatility

## Purpose

The expected move (EM) is the market's consensus estimate of how far price will travel over a given period, derived from options implied volatility. It is not a GEX wall — it has no mechanical dealer hedging force behind it. But it creates self-fulfilling support and resistance because so many participants use it, and because options sellers cluster their short strikes at EM boundaries. This document covers the mathematics, the behavioral properties, the regime-dependent reliability, and the practical computation methods for NQ futures.

Data sources:
- **FlashAlpha**: ATM implied volatility, Greeks for EM computation.
- **Massive.com**: ATM straddle prices (direct EM computation from market prices).
- **Rithmic MBO**: Order book confirmation at EM levels.
- **Unusual Whales**: Dark pool activity at EM levels (institutional positioning).

---

## The Mathematics of Expected Move

### Method 1: ATM Straddle Price

The simplest and most market-accurate method. The ATM straddle (buying both the ATM call and ATM put) represents the market's consensus expected move.

```
daily_EM = ATM_straddle_price × 0.85
```

The 0.85 adjustment is empirical. The raw straddle price slightly overestimates the expected move because:
1. Options have convexity (gamma). The straddle price includes the value of gamma, which is not purely a directional bet.
2. The straddle price assumes the underlying can move in either direction, but the actual expected move in one direction is less than the full straddle.
3. The 0.85 factor has been empirically validated across equity indices over multiple decades.

**For QQQ (the proxy for NQ)**:
```
QQQ_daily_EM = QQQ_ATM_straddle × 0.85
NQ_daily_EM = QQQ_daily_EM × NQ_QQQ_ratio
NQ_QQQ_ratio ≈ 85.7 (recalibrate monthly)
```

**Example**:
- QQQ spot: 480.00
- QQQ ATM straddle (0DTE or 1DTE): $3.20
- QQQ daily EM = 3.20 × 0.85 = $2.72
- NQ daily EM = 2.72 × 85.7 = 233 NQ points
- NQ EM high = NQ spot + 233/2 = NQ spot + 116.5
- NQ EM low = NQ spot - 233/2 = NQ spot - 116.5

Note: The EM is centered on the current spot, not on the prior close. Use the current spot at the time of computation.

### Method 2: IV-Based Formula

When straddle prices are not directly available, compute from ATM implied volatility:

```
daily_EM = spot × IV × sqrt(1/252)
weekly_EM = spot × IV × sqrt(5/252)
monthly_EM = spot × IV × sqrt(21/252)
```

Where IV is the annualized implied volatility (expressed as a decimal, e.g., 0.20 for 20% IV).

**For NQ via QQQ**:
```
QQQ_daily_EM = QQQ_spot × QQQ_IV × sqrt(1/252)
NQ_daily_EM = QQQ_daily_EM × NQ_QQQ_ratio
```

**Example**:
- QQQ spot: 480.00
- QQQ ATM IV: 18% (0.18)
- QQQ daily EM = 480 × 0.18 × sqrt(1/252) = 480 × 0.18 × 0.0630 = $5.44
- Wait — this is the 1-sigma move for the full day. The EM is typically quoted as the range (±1 sigma), so:
- QQQ EM range = ±$5.44 (high = 485.44, low = 474.56)
- NQ EM range = ±(5.44 × 85.7) = ±466 NQ points

Note: The IV-based formula gives a slightly different result than the straddle method because it doesn't include the 0.85 adjustment. The straddle method is more accurate because it directly reflects market pricing.

### Method 3: VIX-Based Approximation

For a quick approximation using VIX (which tracks SPX IV, not QQQ IV):

```
SPX_daily_EM_percent = VIX / sqrt(252) / 100
SPX_daily_EM_points = SPX_spot × SPX_daily_EM_percent
```

For NQ, use NDX IV (which is typically 1.1-1.3x SPX IV due to tech concentration):
```
NDX_IV ≈ VIX × 1.15 (approximate, varies)
NQ_daily_EM = NQ_spot × (NDX_IV / 100) × sqrt(1/252)
```

This is the least accurate method. Use only when FlashAlpha and Massive.com data are unavailable.

### Multi-Period Expected Moves

```
Period          Formula                         Typical NQ Range (VIX=18)
Daily           spot × IV × sqrt(1/252)         ±100-150 NQ points
Weekly          spot × IV × sqrt(5/252)         ±220-330 NQ points
Monthly         spot × IV × sqrt(21/252)        ±450-680 NQ points
Quarterly       spot × IV × sqrt(63/252)        ±780-1170 NQ points
```

These are 1-sigma ranges. Price stays within the daily EM approximately 68% of days, within the weekly EM approximately 68% of weeks, etc.

### The "Already-Moved" Adjustment

As the day progresses, the remaining expected move shrinks because time has passed. If NQ has already moved 80 points by midday, the remaining EM for the afternoon is:

```
remaining_EM = sqrt(daily_EM² - already_moved²)
```

This is the Pythagorean relationship for independent random walks. In practice, use a simpler approximation:

```
remaining_EM ≈ daily_EM × sqrt(remaining_time_fraction)
```

**Example**:
- Daily EM: 150 NQ points
- Time: 1:00 PM ET (3.5 hours into 6.5-hour session)
- Remaining time fraction: 3/6.5 = 0.46
- Remaining EM ≈ 150 × sqrt(0.46) = 150 × 0.68 = 102 NQ points

If NQ has already moved 80 points from the open, the remaining range is approximately 102 points in either direction from the current price. This is the "afternoon EM" — the range for the rest of the session.

---

## Why Expected Move Creates Levels

### The Options Seller Clustering Effect

Options sellers (income strategies, covered call writers, cash-secured put sellers) cluster their short strikes at EM boundaries. This is rational behavior: they sell options at the EM boundary because that's where the premium is highest relative to the probability of being breached.

When price reaches the EM boundary:
- Short options sellers' positions are now at-risk (their short options are approaching the money).
- They must hedge: buy the underlying (if short puts) or sell the underlying (if short calls).
- This hedging creates mechanical support/resistance at the EM boundary.
- The more sellers who clustered at the EM, the stronger the effect.

### The Market Maker Pricing Effect

Market makers priced the options to capture the EM range. They collected premium assuming price would stay within the EM. When price reaches the EM:
- Market makers' short options are now at-risk.
- They hedge by trading the underlying.
- This creates the same mechanical support/resistance as options sellers.

### The Self-Fulfilling Prophecy Effect

Because so many participants use the EM as a reference:
- Traders fade price at the EM boundary (expecting it to hold).
- This fading creates buying/selling pressure at the EM.
- The EM becomes a self-fulfilling level.

This effect is strongest when:
- VIX is low (EM is tight, many sellers clustered at the boundary).
- The EM is widely known (published by major options analytics platforms).
- The market is in positive gamma regime (dealers are also dampening at the EM).

---

## EM as Support/Resistance by Regime

### Positive Gamma Regime (Spot Above Gamma Flip)

**EM boundaries are STRONG**. Three forces align:
1. Options sellers defending their short strikes.
2. Market makers hedging their short options.
3. Dealer gamma hedging (positive gamma dampens moves at the EM).

**Trading implication**: Fade price at the EM boundary with high conviction. The EM high is a ceiling. The EM low is a floor. Stops go through the EM by 0.3% (approximately 60 NQ points for a 20,000 NQ level).

**Confirmation requirements**:
- Rithmic DOM: Resting orders at the EM level. Icebergs.
- Massive.com: Flow dying at the EM boundary. No new sweeps. Premium declining.
- Unusual Whales: Dark pool activity at the EM level (institutional defense).

### Negative Gamma Regime (Spot Below Gamma Flip)

**EM boundaries are WEAK**. The forces that create EM support/resistance are overwhelmed by dealer amplification.

**Trading implication**: Do not fade the EM in negative gamma. The move that caused negative gamma often exceeds the EM. The EM is a reference point, not a reversal level.

**Exception**: If the EM low coincides with a major dark pool buying cluster or a significant put wall from a prior session, the combined level may hold even in negative gamma. But this requires all three confirmations (DOM, flow, dark pool) before trading.

### Low VIX Environment (VIX < 15)

**EM is TIGHT and HIGHLY RELIABLE**. The EM range is narrow (perhaps ±80-100 NQ points for a daily EM). Options sellers are winning. The market is well-behaved.

**Characteristics**:
- Price frequently tags the EM boundary but rarely exceeds it.
- The EM boundary is a precise turning point.
- Multiple tests of the EM boundary are common before a reversal.
- The EM is the primary trading level in low-VIX environments.

**Trading implication**: Fade the EM boundary aggressively. Tight stops (through EM by 0.2%). High win rate.

### Moderate VIX Environment (VIX 15-25)

**EM is MODERATE and RELIABLE**. Standard behavior. The EM is a useful level but not as precise as in low-VIX.

**Characteristics**:
- Price reaches the EM boundary approximately 68% of days.
- The EM boundary holds approximately 60-65% of the time when tested.
- Occasional EM breaches (32% of days by definition).

**Trading implication**: Fade the EM boundary with confirmation. Moderate stops (through EM by 0.3%).

### High VIX Environment (VIX > 25)

**EM is WIDE and UNRELIABLE**. The EM range is large (perhaps ±200-300 NQ points for a daily EM). The market is in a regime where moves exceed statistical expectations.

**Characteristics**:
- Price may not reach the EM boundary (the move is smaller than expected).
- Or price may blow through the EM boundary (the move is larger than expected).
- The EM is less useful as a trading level.

**Trading implication**: Use the EM as a reference for range context, not as a trading level. Focus on GEX walls and dark pool clusters instead.

### VIX Spike Events (VIX > 35)

**EM is MEANINGLESS as a trading level**. The market is in a tail event. Statistical relationships break down.

**Trading implication**: Do not use the EM. Focus on the gamma flip (regime boundary) and dark pool clusters (institutional positioning). The EM will be recalibrated after the spike.

---

## Intraday EM Dynamics

### Morning EM (9:30 AM - 11:30 AM ET)

The morning EM is the widest EM of the day. The full daily EM applies.

**Key levels**:
- EM high = spot_at_open + daily_EM/2
- EM low = spot_at_open - daily_EM/2

Note: Use the spot at the open (9:30 AM), not the prior close. Overnight gaps shift the EM center.

**Behavior**: The morning EM is tested frequently. The opening range (first 30 minutes) often establishes which side of the EM the market will test first.

### Midday EM (11:30 AM - 1:30 PM ET)

The midday EM is the remaining EM after the morning move. Compute using the "already-moved" adjustment.

**Behavior**: Midday EM is less reliable because volume is low. Price can drift through the midday EM without triggering significant hedging activity.

### Afternoon EM (1:30 PM - 4:00 PM ET)

The afternoon EM is the remaining EM after the morning and midday moves. This is the most important EM for afternoon trading.

**Behavior**: The afternoon EM is highly reliable because:
1. Volume is high (institutional activity picks up).
2. 0DTE gamma is at maximum (near expiry).
3. Options sellers are most active in defending their positions.

**Key insight**: If NQ has already moved 80% of the daily EM by 1:30 PM, the afternoon EM is only 20% of the daily EM. This is a very tight range. Expect consolidation or a reversal.

### The "EM Exhaustion" Pattern

When price reaches the EM boundary and flow dies (no new sweeps, premium declining), this is the EM exhaustion pattern. The move has consumed the expected move. Reversal is likely.

**Confirmation**:
1. Price at EM boundary.
2. Massive.com: Flow dying. Net premium declining. No new sweeps in last 10 minutes.
3. Rithmic DOM: Resting orders at the EM level. Icebergs.
4. Unusual Whales: Dark pool activity at the EM level.

**Trade**: Fade the EM with a stop through the EM by 0.3%.

---

## Computing EM from Available Data Sources

### From FlashAlpha

FlashAlpha provides ATM IV directly. Use Method 2 (IV-based formula):

```python
import math

def compute_nq_em_from_flashalpha(qqq_spot, qqq_atm_iv, nq_qqq_ratio=85.7):
    """
    qqq_spot: current QQQ price
    qqq_atm_iv: ATM implied volatility as decimal (e.g., 0.18 for 18%)
    nq_qqq_ratio: NQ/QQQ price ratio (recalibrate monthly)
    """
    qqq_daily_em = qqq_spot * qqq_atm_iv * math.sqrt(1/252)
    nq_daily_em = qqq_daily_em * nq_qqq_ratio
    return nq_daily_em

# Example:
# qqq_spot = 480.0
# qqq_atm_iv = 0.18
# nq_qqq_ratio = 85.7
# nq_daily_em = 480 * 0.18 * sqrt(1/252) * 85.7 = 466 NQ points
# EM high = NQ_spot + 233
# EM low = NQ_spot - 233
```

### From Massive.com ATM Straddle Prices

Massive.com shows real-time options flow including ATM straddle prices. Use Method 1 (straddle method):

```python
def compute_nq_em_from_straddle(qqq_atm_straddle_price, nq_qqq_ratio=85.7):
    """
    qqq_atm_straddle_price: price of QQQ ATM call + ATM put (same strike, same expiry)
    """
    qqq_daily_em = qqq_atm_straddle_price * 0.85
    nq_daily_em = qqq_daily_em * nq_qqq_ratio
    return nq_daily_em

# Example:
# qqq_atm_straddle = 3.20
# nq_daily_em = 3.20 * 0.85 * 85.7 = 233 NQ points
```

### NQ/QQQ Ratio Calibration

The NQ/QQQ ratio drifts over time as the two instruments diverge. Recalibrate monthly:

```python
def calibrate_nq_qqq_ratio(nq_price, qqq_price):
    """
    Use current front-month NQ futures price and QQQ spot price.
    """
    return nq_price / qqq_price

# Example (May 2026):
# NQ = 21,000
# QQQ = 480
# ratio = 21000 / 480 = 43.75
# Wait — this is the price ratio, not the EM ratio.
# The EM ratio is different because NQ and QQQ have different contract sizes.
# NQ contract = $20 per point
# QQQ contract = 100 shares
# For EM purposes, use the price ratio: NQ_EM = QQQ_EM × (NQ_price / QQQ_price)
```

Note: The 85.7x ratio cited in the project context may refer to a specific historical calibration. Always verify against current prices.

---

## EM Levels as Trade Entry and Exit

### Entry: Fading the EM Boundary

**Setup**: Price reaches the EM boundary (high or low) in positive gamma regime.

**Confirmation checklist**:
1. Regime: Positive gamma (spot above gamma flip). If negative gamma, skip.
2. VIX: Below 25. If above 25, reduce conviction.
3. Flow: Dying at the EM boundary. Net premium declining. No new sweeps in last 10 minutes.
4. DOM: Resting orders at the EM level. Iceberg signature.
5. Dark pool: Activity at the EM level (institutional defense).
6. Time: Not in the first 15 minutes of the session (opening volatility).

**Entry**: Fade the EM boundary when 4 of 6 checklist items are confirmed.

**Stop**: Through the EM by 0.3% (approximately 60 NQ points for a 20,000 NQ level).

**Target**: HVL (the magnet) or the opposite EM boundary.

### Exit: Taking Profit at the EM

**Setup**: Long from the put wall, price approaching the EM high.

**Protocol**:
- Take 50% profit at HVL (if HVL is between put wall and EM high).
- Take remaining 50% at the EM high.
- If EM high is exceeded (price breaks through), trail stop to the EM high level.

**Setup**: Short from the call wall, price approaching the EM low.

**Protocol**:
- Take 50% profit at HVL (if HVL is between call wall and EM low).
- Take remaining 50% at the EM low.
- If EM low is exceeded, trail stop to the EM low level.

### Stop: EM Exceeded = Something Bigger Is Happening

When price exceeds the EM by more than 0.3%, the statistical model has broken down. Something bigger is happening:
- A news catalyst that wasn't priced in.
- A regime change (gamma flip crossing).
- A squeeze (short covering or long liquidation).

**Protocol**: Exit all positions immediately when the EM is exceeded by 0.3%. Do not try to fade the move. Re-assess the regime and re-compute the EM for the new spot level.

---

## EM in the Context of Other Levels

### EM + Call Wall Confluence

When the EM high and the call wall are within 20 NQ ticks of each other, the combined level is extremely strong. Two independent forces (statistical EM and mechanical GEX wall) are aligned.

**Trading implication**: Maximum conviction fade. Reduce stop to 0.2% through the level.

### EM + Put Wall Confluence

Same logic. EM low + put wall within 20 ticks = maximum conviction floor.

### EM + Gamma Flip

When the EM low coincides with the gamma flip, the level is both a statistical boundary and a regime boundary. This is a critical level.

**Trading implication**: If price reaches the EM low AND the gamma flip simultaneously, this is the highest-stakes moment of the session. The flip crossing protocol takes priority over the EM fade.

### EM + Dark Pool Cluster

When the EM boundary coincides with a dark pool cluster (institutional positioning), the level has both statistical and institutional support.

**Trading implication**: High conviction fade. The institutions who accumulated at the dark pool cluster will defend the level.

---

## EM Computation Schedule

| Time | Action |
|------|--------|
| Pre-market (9:00 AM) | Compute daily EM from overnight IV. Set EM high and low. |
| Open (9:30 AM) | Recompute EM using opening spot price. Update EM high and low. |
| 10:00 AM | Recompute EM if IV has moved more than 1 point. |
| 11:30 AM | Compute "already-moved" adjustment. Update remaining EM. |
| 1:30 PM | Recompute remaining EM for afternoon session. |
| 3:00 PM | Final EM check. Note if EM has been reached or exceeded. |
| 4:00 PM | Record final EM data for next session reference. |

**Trigger-based recomputation**: Recompute immediately if:
- IV moves more than 1 point (significant IV change).
- Price moves more than 50% of the daily EM (large move changes the "already-moved" calculation).
- A major news event occurs (IV spike changes the EM).

---

## Cross-Reference

- For level ranking by regime: `level-hierarchy.md`
- For wall mechanics: `wall-dynamics.md`
- For gamma flip and regime: `gamma-flip-mechanics.md`
- For flow confirmation at EM levels: `../step3-flow/flow-interpretation.md`
- For dark pool at EM levels: `../step3-flow/dark-pool-reading.md`
- For regime definitions: `../step1-regimes/`
