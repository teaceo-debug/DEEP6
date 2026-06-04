# Expiry Intent — What the Choice of Expiration Reveals About Trader Intent

## Purpose

The expiration date an options trader chooses is not arbitrary. It reveals the time horizon of their conviction, the type of exposure they're seeking, and the urgency of their bet. A $10M 0DTE call sweep and a $10M monthly call block are both bullish signals, but they have fundamentally different implications for intraday trading. This document covers the full expiry taxonomy, the signal weight by DTE, the DTE-adjusted gamma normalization, and the structural implications of each expiry class.

Data sources:
- **Massive.com**: Real-time flow tape with expiry data for each transaction.
- **Unusual Whales**: Block trades and dark pool prints with expiry data.
- **FlashAlpha**: GEX surface filtered by expiry (shows which expiry class dominates the GEX structure).
- **Rithmic MBO**: Order book context (expiry doesn't directly affect the order book, but the flow from each expiry class has different order book signatures).

---

## The Expiry Taxonomy

### 0DTE (Same-Day Expiry)

**Definition**: Options expiring on the current trading day. For SPX/NDX, 0DTE options are available Monday through Friday (daily expirations). For QQQ, 0DTE is available on Monday, Wednesday, and Friday.

**Gamma characteristics**:
- Gamma is at its theoretical maximum near expiry. For an ATM option, gamma approaches infinity as DTE approaches zero.
- In practice, gamma for 0DTE ATM options is 10-50x higher than equivalent monthly options.
- This means a 0DTE option's delta changes dramatically with small price moves.
- A 0DTE ATM call with spot at 480 might have a delta of 0.50 and a gamma of 0.15. A 1-point move in QQQ changes the delta by 0.15 — a 30% change in delta from a 0.2% price move.

**What 0DTE represents**:
- Maximum leverage per dollar of premium.
- The highest-conviction intraday bet available.
- "I believe price moves in this direction TODAY, and I want maximum exposure."
- The buyer is not hedging. They're speculating with maximum leverage.

**Signal weight for intraday bias**: 1.0 (maximum). 0DTE flow is the dominant intraday signal.

**Volume statistics**: 0DTE options represent approximately 40-50% of total SPX/NDX daily options volume. This is not a niche product — it's the dominant force in the options market on any given day.

**Structural implications**:
- 0DTE OI creates ephemeral intraday walls that don't exist tomorrow.
- These walls must be tracked separately from multi-expiry walls.
- By 2:00 PM ET, 0DTE walls are often the dominant force, overriding the multi-expiry walls from FlashAlpha.
- At 4:00 PM ET, all 0DTE OI expires. The GEX structure resets to multi-expiry only.

**Decay characteristics**:
- Theta (time decay) is at its maximum for 0DTE options.
- An ATM 0DTE option loses approximately 50% of its value in the first half of the trading day.
- By 2:00 PM ET, an ATM 0DTE option has lost approximately 70% of its morning value.
- This means 0DTE buyers must be right FAST. The option is decaying rapidly.

**Trading implication**: A 0DTE sweep is the most urgent signal. The buyer is paying maximum theta to get maximum gamma. They expect a move TODAY. Weight this signal at 1.0 for intraday bias.

---

### Weekly (1-5 DTE)

**Definition**: Options expiring within the current week. For QQQ, weekly options expire on Friday. For SPX/NDX, weekly options expire on Monday, Wednesday, and Friday.

**Gamma characteristics**:
- Gamma is elevated but not as extreme as 0DTE.
- For a 5DTE ATM option, gamma is approximately 2.4x a monthly option.
- For a 1DTE ATM option, gamma is approximately 5.5x a monthly option.

**What weekly represents**:
- Short-term directional conviction.
- "I believe price moves in this direction THIS WEEK."
- The buyer has a defined risk (the premium paid) and a defined time horizon (this week).
- Weekly options are the most common vehicle for institutional short-term directional bets.

**Signal weight for intraday bias**: 0.7 (moderate). Weekly flow is a strong signal but not as urgent as 0DTE.

**Structural implications**:
- Weekly OI creates walls that persist through the week.
- These walls are visible in FlashAlpha's weekly filter.
- The weekly call wall is often the "ceiling for the week." The weekly put wall is often the "floor for the week."
- On Friday (weekly expiry), weekly OI expires and the GEX structure resets.

**The "weekly range" concept**: The weekly expected move (computed from weekly IV) defines the expected range for the week. The weekly call wall and put wall often coincide with the weekly EM boundaries. This creates a self-reinforcing range.

**Trading implication**: A weekly sweep is a strong signal for the next 1-5 days. For intraday trading, weight at 0.7. For multi-day positioning, weight at 1.0.

---

### Monthly (6-30 DTE)

**Definition**: Options expiring in the current or next calendar month. Monthly options expire on the third Friday of each month.

**Gamma characteristics**:
- Gamma is moderate. Monthly options have approximately 1.0x the gamma of the baseline (by definition — monthly is the baseline).
- The gamma effect is real but not as explosive as 0DTE or weekly.

**What monthly represents**:
- Institutional positioning. Hedging. Portfolio construction.
- "I'm positioned for the next 2-4 weeks."
- Monthly options are the primary vehicle for institutional hedging (portfolio protection).
- Monthly call OI is often covered calls (institutions selling upside) or synthetic longs (institutions building leveraged long positions).
- Monthly put OI is often portfolio hedges (institutions buying insurance against a decline).

**Signal weight for intraday bias**: 0.4 (low). Monthly flow is not an intraday signal. But it creates the structural backdrop.

**Signal weight for structural levels**: 1.0 (maximum). Monthly OI creates the most persistent GEX walls. These walls persist for weeks.

**Structural implications**:
- Monthly OI creates the dominant GEX structure. The call wall and put wall in FlashAlpha are primarily driven by monthly OI.
- Monthly OPEX (third Friday) is when this OI expires and creates regime resets.
- The week before monthly OPEX, the GEX structure is at its most stable (maximum OI, maximum gamma effect).
- The week after monthly OPEX, the GEX structure is at its most unstable (minimum OI, minimum gamma effect).

**Put OI in monthlies = institutional hedges**:
- When institutions buy monthly puts, they're buying insurance against a decline.
- This is NOT a directional bet. They're long the underlying and buying puts as protection.
- The put buying creates put OI at the strike, which strengthens the put wall.
- But the institution's actual position is LONG (they own the underlying).
- Misclassifying monthly put buying as bearish is a common error.

**Call OI in monthlies = covered calls or synthetic longs**:
- Covered calls: Institutions who own the underlying sell calls to generate income. This creates call OI at the strike, which strengthens the call wall.
- Synthetic longs: Institutions buy calls + sell puts to create a synthetic long position. This creates call OI (bullish) and put OI (bearish) simultaneously.

**Trading implication**: Monthly flow is not an intraday signal. But monthly OI creates the structural levels that define the intraday trading range. Use monthly OI to identify the dominant walls. Use 0DTE and weekly flow for intraday direction.

---

### Quarterly (30-90 DTE)

**Definition**: Options expiring in the next 1-3 months. Quarterly options expire in March, June, September, and December.

**Gamma characteristics**:
- Gamma is low. Quarterly options have approximately 0.5-0.7x the gamma of monthly options.
- The gamma effect is real but slow-moving.

**What quarterly represents**:
- Big money. Pension funds. Macro hedges. Portfolio construction.
- "I'm positioned for the next quarter."
- Quarterly options are the primary vehicle for macro hedging (hedging against a recession, a Fed policy change, a geopolitical event).
- Quarterly call OI is often LEAPS-like positioning (long-term bullish bets).
- Quarterly put OI is often macro hedges (protection against a significant decline).

**Signal weight for intraday bias**: 0.2 (very low). Quarterly flow is not an intraday signal.

**Signal weight for structural levels**: 0.7 (high). Quarterly OI creates persistent background levels that change slowly.

**Structural implications**:
- Quarterly OI creates the "background" GEX structure. These levels change slowly and persist for months.
- Quarterly OPEX (March/June/Sept/Dec) = "quad witching" — maximum volatility and regime disruption.
- Quad witching occurs when quarterly options, monthly options, and futures all expire simultaneously.
- The week of quad witching is the most volatile week of the quarter.

**Quad witching dynamics**:
- The week before quad witching: Maximum OI, maximum gamma effect, maximum stability.
- Quad witching day: Massive OI expiration. GEX structure resets dramatically.
- The week after quad witching: Minimum OI, minimum gamma effect, maximum instability.
- New quarterly OI begins building in the week after quad witching.

**Trading implication**: Quarterly flow is not an intraday signal. But quarterly OI creates the backdrop for the entire quarter. Use quarterly OI to understand the macro positioning. Use 0DTE and weekly flow for intraday direction.

---

### LEAPS (90+ DTE)

**Definition**: Long-term options with more than 90 days to expiry. LEAPS can have up to 2-3 years to expiry.

**Gamma characteristics**:
- Gamma is very low. LEAPS have approximately 0.2-0.4x the gamma of monthly options.
- The gamma effect is minimal for intraday purposes.

**What LEAPS represent**:
- Portfolio construction. Tax strategy. Long-term directional bets.
- "I'm positioned for the next year or more."
- LEAPS are used by institutions for long-term hedging, by retail traders for leveraged long-term bets, and by tax-aware investors for tax-efficient positioning.

**Signal weight for intraday bias**: 0.0 (none). LEAPS are not an intraday signal. Ignore entirely for intraday trading.

**Signal weight for structural levels**: 0.3 (low). LEAPS OI creates very persistent background levels but with minimal gamma effect.

**Trading implication**: Ignore LEAPS for intraday trading. They are portfolio construction tools, not trading signals.

---

## DTE-Adjusted Gamma Normalization

To compare flow signals across different expiries, normalize by DTE-adjusted gamma. This converts all flow signals to a common unit: "equivalent monthly gamma."

### The Normalization Formula

```
gamma_scaling_factor(DTE) = 1 / sqrt(DTE / 21)

# Where 21 DTE is the baseline (monthly)

DTE = 0: factor = infinity (use DTE = 0.5 for practical computation)
DTE = 0.5: factor = sqrt(21/0.5) = sqrt(42) = 6.5
DTE = 1: factor = sqrt(21/1) = sqrt(21) = 4.6
DTE = 5: factor = sqrt(21/5) = sqrt(4.2) = 2.0
DTE = 10: factor = sqrt(21/10) = sqrt(2.1) = 1.4
DTE = 21: factor = 1.0 (baseline)
DTE = 45: factor = sqrt(21/45) = sqrt(0.47) = 0.68
DTE = 90: factor = sqrt(21/90) = sqrt(0.23) = 0.48
```

### Normalized Signal Weight

```
normalized_signal = raw_signal × gamma_scaling_factor(DTE)

# Example:
# 0DTE call sweep: $5M premium, DTE = 0.5
# normalized_signal = 5M × 6.5 = 32.5M equivalent monthly gamma units

# Monthly call sweep: $5M premium, DTE = 21
# normalized_signal = 5M × 1.0 = 5M equivalent monthly gamma units

# The 0DTE sweep is 6.5x more significant for intraday bias
```

### Practical Application

When comparing flow signals across expiries, use the normalized signal:

```python
def normalize_flow_signal(premium, dte):
    """
    Normalize a flow signal to equivalent monthly gamma units.
    """
    if dte < 0.5:
        dte = 0.5  # Minimum DTE for computation
    gamma_factor = (21 / dte) ** 0.5
    return premium * gamma_factor

# Example:
# 0DTE sweep: $3M premium
# normalize_flow_signal(3_000_000, 0.5) = 3M × 6.5 = 19.5M normalized

# Weekly sweep: $8M premium, 3 DTE
# normalize_flow_signal(8_000_000, 3) = 8M × 2.6 = 20.8M normalized

# These two signals are approximately equal in normalized terms
```

---

## Expiry-Specific Behavioral Patterns

### 0DTE Behavioral Patterns

**The morning 0DTE setup**:
- 0DTE options begin trading at 9:30 AM ET.
- The first 30 minutes of 0DTE flow is often hedging (institutions adjusting overnight positions).
- The directional 0DTE flow begins around 10:00 AM ET.
- By 11:00 AM ET, the 0DTE walls are established.

**The afternoon 0DTE squeeze**:
- As 0DTE options approach expiry (2:00-4:00 PM ET), gamma increases dramatically.
- Small price moves create large delta changes, which require large hedging trades.
- This creates a self-reinforcing dynamic: price moves → delta hedging → more price moves.
- The afternoon 0DTE squeeze is the most volatile period of the trading day.

**The 0DTE pin**:
- Near expiry, 0DTE options with high OI create a pin effect.
- Price gravitates toward the strike with the highest 0DTE OI.
- The pin is strongest in the last 2 hours of trading.
- See `../step2-levels/level-hierarchy.md` for pin regime details.

**The 0DTE expiry cascade**:
- At 4:00 PM ET, all 0DTE options expire.
- Options that are ITM are exercised (or cash-settled for index options).
- Options that are OTM expire worthless.
- The delta hedging that was maintaining the 0DTE walls is removed.
- This can cause a sharp move in the last few minutes of trading as hedges are unwound.

### Weekly Behavioral Patterns

**The weekly range establishment**:
- Monday morning: Weekly options begin trading. The weekly range is established.
- The weekly call wall and put wall define the expected range for the week.
- Price tends to oscillate within the weekly range until a catalyst breaks it.

**The Thursday/Friday squeeze**:
- As weekly options approach expiry (Thursday-Friday), gamma increases.
- The weekly pin effect becomes significant.
- Price gravitates toward the weekly pin strike.
- The weekly squeeze is less violent than the 0DTE squeeze but more persistent.

**The Friday close**:
- Weekly options expire at 4:00 PM ET on Friday.
- The last 30 minutes of Friday trading is dominated by weekly option expiry dynamics.
- Avoid trading the last 30 minutes of Friday unless you understand the weekly OI structure.

### Monthly Behavioral Patterns

**The OPEX week dynamics**:
- The week before monthly OPEX: Maximum OI, maximum gamma effect, maximum stability.
- OPEX Monday-Wednesday: Positions are being closed or rolled. GEX structure is stable.
- OPEX Thursday: Gamma is increasing. The monthly pin effect begins.
- OPEX Friday: Maximum gamma. The monthly pin is strongest. Avoid directional trades.
- Post-OPEX: GEX structure resets. New monthly OI begins building.

**The monthly wall migration**:
- Monthly walls migrate slowly throughout the month as new OI is created.
- Track the direction of monthly wall migration as a multi-day directional signal.
- A rising monthly call wall = bullish (market pricing in higher prices).
- A falling monthly put wall = bearish (market pricing in lower prices).

---

## Expiry Weighting in the Bias Engine

For the bias engine, weight flow signals by expiry:

```python
def expiry_weight(dte):
    """
    Weight a flow signal by expiry for intraday bias.
    """
    if dte <= 0.5:  # 0DTE
        return 1.0
    elif dte <= 5:  # Weekly
        return 0.7
    elif dte <= 21:  # Monthly
        return 0.4
    elif dte <= 90:  # Quarterly
        return 0.2
    else:  # LEAPS
        return 0.0

def compute_flow_bias(sweeps):
    """
    Compute directional bias from a list of sweeps, weighted by expiry.
    """
    total_weight = 0
    weighted_direction = 0
    
    for sweep in sweeps:
        weight = expiry_weight(sweep.dte) * sweep.premium / 1_000_000
        direction = +1 if sweep.type == 'call' else -1
        weighted_direction += direction * weight
        total_weight += weight
    
    if total_weight == 0:
        return 0  # No signal
    
    return weighted_direction / total_weight  # Range: -1 to +1
```

---

## The Key Insight: Weight Signals by Expiry

A $10M 0DTE call sweep is 3x more significant for intraday bias than a $10M monthly call block. This is not intuitive — the dollar amounts are the same. But the gamma is 4.6x higher for 0DTE, and the time horizon is completely different.

The 0DTE buyer is saying "I need this exposure TODAY." The monthly buyer is saying "I'm positioned for the next few weeks." For intraday NQ trading, the 0DTE buyer's conviction is far more relevant.

**The normalization principle**: Always normalize flow signals by DTE-adjusted gamma before comparing them. A $3M 0DTE sweep and a $15M monthly block are approximately equal in normalized terms. Without normalization, you would incorrectly weight the monthly block 5x higher.

---

## Cross-Reference

- For flow state classification: `flow-interpretation.md`
- For sweep analysis: `sweep-analysis.md`
- For opening vs closing: `opening-vs-closing.md`
- For dark pool reading: `dark-pool-reading.md`
- For 0DTE wall computation: `../step2-levels/level-hierarchy.md`
- For OPEX regime dynamics: `../step1-regimes/`
