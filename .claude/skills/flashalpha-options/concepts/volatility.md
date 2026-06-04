# Volatility Analytics — IV, VRP, Skew, Term Structure, SVI

Volatility is the central variable in options pricing. Understanding the relationship between implied and realized volatility, and how that relationship changes across strikes and expirations, is the foundation of options analytics.

---

## Implied Volatility (IV)

### Definition

Implied volatility is the volatility value that, when plugged into the Black-Scholes-Merton (BSM) model, produces the observed market price of an option.

```
market_price = BSM(S, K, T, r, σ_implied)
→ solve for σ_implied
```

IV is not a prediction of future volatility. It's the market's consensus expectation of future realized volatility, plus a risk premium.

### ATM IV

The most important single volatility number. ATM (at-the-money) options have the highest vega and are the most liquid, so their IV is the cleanest signal.

ATM IV ≈ the market's best estimate of future realized vol for that expiration.

**FlashAlpha field:** `atm_iv` in volatility response.

### IV surface

IV varies across two dimensions:
1. **Strike** (moneyness) — the "smile" or "skew"
2. **Expiration** — the "term structure"

The full IV surface is a 2D grid of IV values across all strikes and expirations. FlashAlpha provides this via the volatility endpoint.

---

## Realized Volatility (RV)

### Definition

Realized volatility is the actual historical price movement, computed as the annualized standard deviation of log returns over a rolling window.

```
RV_n = √(252/n × Σ(ln(S_t/S_{t-1})²))
```

Where n = number of trading days in the window.

### Common windows

| Window | Days | Use case |
|--------|------|----------|
| 5d RV | 5 | Very short-term, reactive to recent moves |
| 10d RV | 10 | Short-term baseline |
| 20d RV | 20 | Standard "1-month" realized vol |
| 30d RV | 30 | Matches 30-day IV for VRP comparison |
| 60d RV | 60 | Medium-term structural vol |

**FlashAlpha fields:** `rv_5d`, `rv_10d`, `rv_20d`, `rv_30d`, `rv_60d`

### RV vs. IV comparison

The most important comparison in volatility analytics. IV almost always exceeds RV over time — this is the volatility risk premium.

---

## VRP (Volatility Risk Premium)

### Definition

```
VRP = IV - RV
```

Specifically: `VRP = ATM_IV_30d - RV_30d` (matching the expiration window to the realized window).

VRP represents the premium that option buyers pay above expected realized volatility. It compensates option sellers for bearing gamma risk and providing liquidity.

### Historical context

VRP is structurally positive on average:
- S&P 500 historical average VRP: ~2-5 vol points
- QQQ/NQ tends to have slightly higher VRP due to tech event risk
- VRP is negative roughly 20-30% of the time (when realized vol exceeds implied)

### VRP regime

**Positive VRP (IV > RV):** Options are "rich." Premium sellers have a statistical edge. The market is overpaying for protection. Conditions favor short-vol strategies (selling straddles, iron condors, covered calls).

**Negative VRP (IV < RV):** Options are "cheap." The market is underpricing actual volatility. Conditions favor long-vol strategies (buying options, straddles, tail hedges).

**FlashAlpha fields:**
- `vrp` — current VRP value
- `vrp_regime` — "positive_vrp" or "negative_vrp"
- `vrp_zscore` — how extreme current VRP is vs. historical distribution (Alpha tier)

### GEX-conditioned VRP

In positive gamma regimes, dealers absorb spot moves, which mechanically reduces realized volatility. This means IV can be "fair" even when raw VRP looks high — the gamma regime is suppressing RV.

FlashAlpha's GEX-conditioned VRP adjusts for this:
```
vrp_gex_conditioned = VRP - gamma_regime_adjustment
```

A high raw VRP in positive gamma is less attractive than the same VRP in negative gamma, because the gamma regime itself is suppressing RV.

**FlashAlpha field:** `vrp_gex_conditioned` (Growth tier)

---

## IV Rank

### Definition

```
IV_Rank = (current_IV - 52w_low_IV) / (52w_high_IV - 52w_low_IV) × 100
```

Expresses current IV as a percentage of its 52-week range.

### Interpretation

| IV Rank | Meaning |
|---------|---------|
| > 80 | IV near yearly high. Options historically expensive. Sell premium. |
| 50-80 | Above average. Moderate premium-selling conditions. |
| 20-50 | Below average. Options relatively cheap. |
| < 20 | IV near yearly low. Options historically cheap. Buy options. |

IV Rank answers: "Is IV high or low relative to where it's been?"

**FlashAlpha field:** `iv_rank`

---

## IV Percentile

### Definition

```
IV_Percentile = (days in past year where IV < current_IV) / 252 × 100
```

The percentage of trading days in the past year where IV was lower than today.

### IV Rank vs. IV Percentile

These are different and both matter:

- **IV Rank** is sensitive to outliers. One extreme spike in the past year makes everything else look low.
- **IV Percentile** is more robust. It tells you how often IV was lower, regardless of the magnitude of past extremes.

Example: If IV spiked to 80 once last year but spent 200 days below 20, current IV of 25 would have:
- IV Rank: (25-15)/(80-15) = 15% (looks low because of the spike)
- IV Percentile: 200/252 = 79% (looks high because most days were below 25)

Use both together for a complete picture.

**FlashAlpha field:** `iv_percentile`

---

## Volatility Skew

### Definition

IV varies by strike. Puts typically have higher IV than calls at the same distance from ATM. This is the "volatility skew" or "volatility smile."

### Why skew exists

1. **Crash risk premium:** Investors pay more for downside protection (puts) than upside participation (calls). This demand inflates put IV.
2. **Leverage effect:** Falling prices increase volatility (negative correlation between returns and vol). This makes downside options more valuable.
3. **Supply/demand imbalance:** More natural put buyers (hedgers) than put sellers.

### Measuring skew

**25-delta risk reversal:**
```
RR_25 = IV(25Δ put) - IV(25Δ call)
```

More negative = more bearish skew = more demand for downside protection.

Typical values:
- Normal market: -2 to -5 vol points
- Stressed market: -8 to -15 vol points
- Crisis: -20+ vol points

**FlashAlpha fields:**
- `skew_25d` — 25-delta risk reversal
- `skew_10d` — 10-delta risk reversal (more extreme strikes)
- `skew_slope` — rate of IV change per unit of moneyness

### Skew dynamics

Skew widens before uncertainty events (earnings, FOMC, CPI). It narrows after the event resolves (vol crush). Monitoring skew changes can signal positioning shifts before the event.

---

## IV Term Structure

### Definition

How IV varies across expirations for the same underlying. Typically plotted as ATM IV vs. days to expiry.

### Contango (normal)

Near-term IV < longer-term IV. The market expects more uncertainty in the future than the present. This is the normal state in calm markets.

```
IV_7d < IV_30d < IV_60d < IV_90d
```

Contango term structure: premium sellers prefer near-term options (higher theta relative to vega). Calendar spreads (sell near, buy far) are attractive.

### Backwardation (inverted)

Near-term IV > longer-term IV. The market expects more uncertainty NOW than in the future. This occurs during:
- Active crises (COVID crash, 2008)
- Imminent event risk (earnings, FOMC)
- Sudden volatility spikes

```
IV_7d > IV_30d > IV_60d
```

Backwardation signals elevated near-term fear. It often precedes or accompanies sharp moves.

### Term structure slope

```
term_structure_slope = (IV_30d - IV_7d) / (30 - 7)
```

Positive slope = contango. Negative slope = backwardation.

**FlashAlpha fields:**
- `term_structure` — array of {dte, iv} pairs
- `term_structure_slope` — computed slope
- `term_structure_regime` — "contango" or "backwardation"

---

## SVI (Stochastic Volatility Inspired)

### What it is

SVI is a parametric model for fitting the entire implied volatility smile. It was introduced by Jim Gatheral and is widely used by market makers for arbitrage-free vol surface construction.

### The formula

```
σ²(k) = a + b(ρ(k - m) + √((k - m)² + σ_SVI²))
```

Where:
- k = log-moneyness = ln(K/F) (K = strike, F = forward price)
- a = overall variance level
- b = slope/curvature parameter
- ρ = correlation (skew parameter, -1 to 1)
- m = ATM shift
- σ_SVI = smile curvature

### Why SVI matters

Raw market IV quotes are noisy. SVI fits a smooth, arbitrage-free surface through the observed quotes. This gives:
1. **Cleaner Greeks** — SVI-smoothed IV produces more stable delta, gamma, vanna, charm
2. **Arbitrage detection** — SVI flags calendar spreads and butterfly spreads that violate no-arbitrage conditions
3. **Variance swap pricing** — the integral of SVI gives the fair value of variance swaps

### FlashAlpha SVI (Alpha tier)

- `svi_params` — raw {a, b, rho, m, sigma} per expiration
- `svi_arbitrage_flag` — boolean, true if surface has arbitrage violations
- `svi_smoothed_iv` — the fitted IV at each strike (cleaner than raw market quotes)
- `variance_swap_fair_value` — computed from SVI integral

---

## Strategy Scores (Alpha Tier)

FlashAlpha computes composite scores for common volatility strategies:

### Harvest score

Composite premium-selling attractiveness. High when:
- VRP is positive and elevated
- Gamma regime is positive (dealers absorb moves, suppressing RV)
- Vol-of-vol is low (stable IV = predictable premium decay)
- IV rank > 50

**FlashAlpha field:** `harvest_score` (0-100)

### Dealer flow risk

How much dealer hedging amplifies moves. High when:
- Negative gamma regime
- Large absolute GEX
- High gamma acceleration (0DTE heavy)

High dealer flow risk = premium selling is riskier (moves can be violent).

**FlashAlpha field:** `dealer_flow_risk` (0-100)

### Iron condor score

Suitability for range-bound premium selling (sell OTM call + OTM put). High when:
- Positive gamma regime (range-bound behavior)
- High VRP (options rich)
- Low skew (symmetric wings)
- Low term structure slope (near-term IV not elevated)

**FlashAlpha field:** `iron_condor_score` (0-100)

### Strangle score

Suitability for selling ATM straddle/strangle. High when:
- High IV rank (options expensive)
- Positive VRP
- Low gamma acceleration (no 0DTE dominance)

**FlashAlpha field:** `strangle_score` (0-100)

### Calendar score

Suitability for calendar spreads (sell near, buy far). High when:
- Contango term structure (near-term IV elevated vs. far)
- Near-term event risk resolved
- Stable underlying trend

**FlashAlpha field:** `calendar_score` (0-100)

---

## Volatility Regime Summary

| Condition | VRP | IV Rank | Skew | Term Structure | Regime |
|-----------|-----|---------|------|----------------|--------|
| Calm bull market | High positive | Low | Moderate negative | Contango | Premium selling |
| Pre-event | Moderate | Rising | Widening | Flattening | Wait |
| Post-event (vol crush) | Spike positive | Falling | Narrowing | Steepening | VEX rally |
| Crisis | Negative | Very high | Very negative | Backwardation | Buy options |
| Recovery | Positive | Falling | Normalizing | Returning to contango | Harvest |
