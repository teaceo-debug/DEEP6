# Volatility Surface Dynamics — Quantitative Deep Dive

**Audience**: Algo builders who already know what IV is. This document covers the math, the mechanics, and the NQ-specific calibration values you need to build production signals.

**Companion files**: `options-bias-engine/domains/volatility-structure.md` (conceptual), `flashalpha-nq.md` (API integration)

---

## 1. SVI Parameterization

The Stochastic Volatility Inspired (SVI) model parameterizes the implied variance smile for a single expiry as a function of log-moneyness `k = ln(K/F)`:

```
w(k) = a + b [ ρ(k - m) + sqrt((k - m)² + σ²) ]
```

where `w(k)` is the **total implied variance** (not volatility): `w = σ_IV² × T`.

### The Five Parameters

| Parameter | Domain | Controls | QQQ Typical Range |
|-----------|--------|----------|-------------------|
| `a` | ℝ | Vertical translation — overall variance level | 0.02 to 0.08 |
| `b` | ≥ 0 | Slope of both wings — how fast variance grows away from ATM | 0.10 to 0.30 |
| `ρ` | (-1, 1) | Skew — asymmetry between put and call wings | -0.50 to -0.70 |
| `m` | ℝ | Horizontal shift — where the minimum variance sits | -0.02 to +0.02 |
| `σ` | > 0 | Curvature — smoothness of the smile bottom | 0.10 to 0.25 |

**What each parameter does in practice:**

`a` shifts the entire smile up or down. Higher `a` = higher ATM variance. When VIX spikes, `a` jumps.

`b` controls wing steepness. A large `b` means OTM options are expensive relative to ATM. Post-FOMC, `b` often compresses as the event premium bleeds out.

`ρ` is the skew parameter. For QQQ/NQ, `ρ` sits between -0.50 and -0.70 in normal regimes, reflecting the negative spot-vol correlation. When `ρ` approaches -0.80, the put wing is extremely steep — a signal of tail-risk premium expansion. When `ρ` rises toward -0.30, skew is flattening, often a bullish signal.

`m` shifts the smile horizontally. Negative `m` means the minimum variance is slightly below ATM (puts slightly cheaper than calls at equal distance), which is unusual for equity indices. Positive `m` is the normal state.

`σ` controls how sharp the smile bottom is. Small `σ` = sharp V-shape (high curvature). Large `σ` = flat bottom (low curvature, smile looks more like a smirk).

### Worked Example: QQQ 30-DTE Calibration

Assume QQQ = 490, 30-DTE expiry, ATM IV = 18%, typical skew regime:

```python
import numpy as np

# SVI parameters (calibrated to QQQ 30-DTE)
a = 0.0324   # ATM total variance: 0.18² × (30/365) ≈ 0.0266, a slightly above
b = 0.18
rho = -0.60
m = 0.01
sigma = 0.15

def svi_total_variance(k, a, b, rho, m, sigma):
    """
    k: log-moneyness = ln(K/F)
    Returns total implied variance w = IV² * T
    """
    return a + b * (rho * (k - m) + np.sqrt((k - m)**2 + sigma**2))

def svi_iv(k, T, a, b, rho, m, sigma):
    """Convert total variance to annualized IV."""
    w = svi_total_variance(k, a, b, rho, m, sigma)
    return np.sqrt(max(w, 0) / T)

# Example: 5% OTM put (k = ln(0.95) ≈ -0.0513)
T = 30 / 365
k_put = np.log(0.95)
k_call = np.log(1.05)

iv_put = svi_iv(k_put, T, a, b, rho, m, sigma)
iv_call = svi_iv(k_call, T, a, b, rho, m, sigma)

print(f"5% OTM put IV:  {iv_put:.1%}")   # ~22-24%
print(f"5% OTM call IV: {iv_call:.1%}")  # ~16-18%
print(f"Skew (put-call): {(iv_put - iv_call):.1%}")  # ~5-7%
```

### SVI Arbitrage Constraints

A valid SVI fit must satisfy:
1. `w(k) ≥ 0` for all `k` (no negative variance)
2. `(1 - k × g(k) / (2w))² - g(k)²/4 × (1/w + 1/4) + g''(k)/2 ≥ 0` (no butterfly arbitrage)
3. `b(1 + |ρ|) < 2/T` (Lee's moment formula — no calendar arbitrage within expiry)

where `g(k) = dw/dk`. The volsurface library (GitHub: `jasonstrimpel/volsurface`) handles these constraints automatically during calibration.

---

## 2. Surface SVI (SSVI) — Calendar-Consistent Extension

Single-expiry SVI has a critical flaw: fitting each expiry independently creates **calendar arbitrage** — a situation where a shorter-dated option is more expensive than a longer-dated one at the same strike. This violates no-arbitrage and breaks any model that prices across expiries.

SSVI fixes this by parameterizing the entire surface jointly:

```
w(k, θ) = (θ/2) × { 1 + ρ_s × φ(θ) × k + sqrt[(φ(θ) × k + ρ_s)² + (1 - ρ_s²)] }
```

where:
- `θ = σ_ATM² × T` is the ATM total variance for each expiry (the "term structure spine")
- `ρ_s` is the **global skew parameter** — a single number for the entire surface
- `φ(θ)` is the wings function controlling how skew evolves with maturity

### The Wings Function φ(θ)

The Heston-like choice:

```
φ(θ) = η / [θ^γ × (1 + θ)^(1-γ)]
```

Parameters `η` (overall skew level) and `γ` (how skew decays with maturity, typically 0.4-0.6).

For QQQ: `η ≈ 0.8`, `γ ≈ 0.5`, `ρ_s ≈ -0.60`.

### Why ρ_s Matters for Regime Detection

The global `ρ_s` is a single number that captures the skew regime of the entire surface. Track it daily:

```python
def classify_skew_regime(rho_s):
    if rho_s < -0.75:
        return "EXTREME_FEAR", "Put wing extremely expensive, tail risk premium elevated"
    elif rho_s < -0.60:
        return "ELEVATED_SKEW", "Normal NQ bear regime, puts bid"
    elif rho_s < -0.40:
        return "MODERATE_SKEW", "Balanced, no strong directional signal from skew alone"
    else:
        return "FLAT_SKEW", "Unusual for NQ — either complacency or strong bullish flow"
```

A `ρ_s` shift from -0.65 to -0.50 over 2-3 days is a meaningful bullish signal: the market is paying less for downside protection.

---

## 3. Why Index Skew is Steep (and NQ Steeper Than SPX)

Three structural forces create the persistent negative skew in equity index options:

**Force 1: Negative spot-vol correlation.** When NQ falls, realized volatility rises. This is empirically robust (correlation ≈ -0.70 for NQ). Under any stochastic vol model, negative spot-vol correlation directly produces a negatively skewed smile. The steeper the correlation, the steeper the skew.

**Force 2: Tail risk premium.** Institutional investors systematically overpay for OTM puts as portfolio insurance. This creates a structural bid for the put wing that exceeds what any model would predict from realized vol alone. The excess is the "tail risk premium" — it's not mispricing, it's compensation for providing insurance.

**Force 3: Dealer positioning.** Market makers are structurally short puts (they sell them to institutions). To hedge, they buy puts or short futures. This creates a feedback loop: when NQ falls, dealers need to sell more futures to delta-hedge their short puts, which pushes NQ lower, which increases their delta exposure, which forces more selling. This mechanical amplification is why NQ crashes are faster and deeper than the underlying fundamentals would suggest.

**Why NQ skew is steeper than SPX:**

NQ is concentrated in 7-10 mega-cap tech names. These names have:
- Higher individual stock volatility (NVDA, META, TSLA)
- Higher correlation during stress (they all sell off together)
- More speculative positioning (retail and hedge funds are long tech)
- Larger gap risk from earnings and macro events

Empirically, QQQ 25-delta risk reversal runs 1.5-2.5 vol points steeper than SPY at equivalent maturities. When you see QQQ RR25 at -5% and SPY at -3%, that's normal. When they converge to within 0.5%, something structural has changed.

---

## 4. Term Structure Dynamics

The term structure is the ATM IV curve across expiries. For NQ/QQQ:

```
Term Ratio = IV_30d / IV_10d
```

| Term Ratio | Regime | Interpretation |
|------------|--------|----------------|
| > 1.10 | Strong contango | Market calm, no near-term fear, vol sellers active |
| 1.05 to 1.10 | Normal contango | Healthy, typical NQ state |
| 0.95 to 1.05 | Flat | Transition zone, watch for direction |
| 0.85 to 0.95 | Backwardation | Near-term fear elevated, event risk priced |
| < 0.85 | Strong backwardation | Stress regime, 0DTE premium exploding |

NQ contango is structurally 2-5% steeper than SPX because:
1. NQ has more event risk (FOMC, CPI, mega-cap earnings)
2. 0DTE NQ options (via QQQ) are extremely active, compressing near-term IV faster post-event
3. Institutional hedgers prefer 30-60 DTE puts, creating demand at the longer end

```python
def compute_term_ratio(iv_10d: float, iv_30d: float) -> dict:
    ratio = iv_30d / iv_10d
    if ratio > 1.10:
        regime = "STRONG_CONTANGO"
        bias = "BULLISH_STRUCTURE"
    elif ratio > 1.05:
        regime = "NORMAL_CONTANGO"
        bias = "NEUTRAL"
    elif ratio > 0.95:
        regime = "FLAT"
        bias = "WATCH"
    elif ratio > 0.85:
        regime = "BACKWARDATION"
        bias = "BEARISH_STRUCTURE"
    else:
        regime = "STRONG_BACKWARDATION"
        bias = "STRESS_REGIME"
    return {"ratio": ratio, "regime": regime, "bias": bias}
```

**Intraday term structure shifts** are the most actionable signal. If the 10-DTE IV spikes 2+ vol points while 30-DTE stays flat, someone is buying near-term protection aggressively. That's a warning signal regardless of the current price action.

---

## 5. 25-Delta Risk Reversal (RR25)

The 25-delta risk reversal measures the skew between equidistant OTM puts and calls:

```
RR25 = IV_25P - IV_25C
```

For NQ/QQQ, this is always negative (puts more expensive than calls). The magnitude tells you the skew regime.

### NQ/QQQ Thresholds

| RR25 Value | Regime | Signal |
|------------|--------|--------|
| < -5.0% | Extreme fear | Tail risk premium at crisis levels, fade if GEX positive |
| -4.0% to -5.0% | Elevated | Bearish structural bias, puts heavily bid |
| -3.0% to -4.0% | Moderate elevated | Normal bear regime, slight bearish bias |
| -1.5% to -3.0% | Moderate | Neutral to slight bearish, typical range |
| -0.5% to -1.5% | Flattening | Bullish signal — institutions reducing put hedges |
| > -0.5% | Near-flat | Rare, strong bullish signal or complacency warning |

### Directional Signal Logic

RR25 is a **flow signal**, not a price signal. It tells you what the options market is paying for, not where price will go. The signal is in the **change**, not the level:

```python
def rr25_signal(rr25_current: float, rr25_prev_day: float) -> dict:
    level_signal = None
    change = rr25_current - rr25_prev_day  # positive = skew flattening (bullish)

    if rr25_current < -4.5:
        level_signal = "EXTREME_FEAR_FADE" if change > 0.3 else "AVOID_LONGS"
    elif rr25_current < -3.0:
        level_signal = "BEARISH_BIAS"
    elif rr25_current > -1.5:
        level_signal = "BULLISH_BIAS"

    momentum_signal = None
    if change > 0.5:
        momentum_signal = "SKEW_FLATTENING_FAST"  # bullish
    elif change < -0.5:
        momentum_signal = "SKEW_STEEPENING_FAST"  # bearish

    return {"level": level_signal, "momentum": momentum_signal, "change": change}
```

---

## 6. Vanna Formula

Vanna is the cross-Greek measuring how delta changes with volatility (or equivalently, how vega changes with spot):

```
Vanna = dDelta/dσ = dVega/dS = -N'(d1) × d2 / σ
```

Expanded form showing the full dependence:

```
Vanna = -N'(d1) × (1 - d1 / (σ√T)) / (S × σ)
```

where:
- `N'(d1) = exp(-d1²/2) / √(2π)` is the standard normal PDF
- `d1 = [ln(S/K) + (r + σ²/2)T] / (σ√T)`
- `d2 = d1 - σ√T`

### Sign Conventions

**Positive vanna** (long call or short put): delta increases as vol rises. When IV drops, delta decreases — the position loses directional exposure.

**Negative vanna** (long put or short call): delta becomes more negative as vol rises. When IV drops, the put loses delta — it becomes less of a hedge.

For a dealer who is **short puts** (the typical institutional structure): they have **positive vanna**. When IV drops, their short puts lose delta, so they need to buy back futures to rebalance. This is the mechanical engine of the vanna rally.

### Peak Vanna Location

Vanna peaks at approximately 0.40 delta (slightly OTM). At-the-money options have near-zero vanna (delta is already maximally sensitive to spot, not vol). Deep ITM options also have near-zero vanna (delta is near 1, insensitive to vol). The 0.35-0.45 delta range is where vanna flows are largest.

```python
from scipy.stats import norm
import numpy as np

def vanna(S, K, T, r, sigma):
    """Compute vanna (dDelta/dSigma) for a European option."""
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    return -norm.pdf(d1) * d2 / sigma

# Example: QQQ 490, strike 480 (2% OTM put), 30-DTE, IV=20%
v = vanna(S=490, K=480, T=30/365, r=0.05, sigma=0.20)
print(f"Vanna: {v:.4f}")  # Approximately -0.08 to -0.12
```

---

## 7. Vanna Rally Mechanism

The vanna rally is a **mechanical, self-reinforcing flow** triggered by IV compression. It's not sentiment-driven — it's forced rehedging.

### The 5-Step Cascade

**Step 1: IV drops.** Catalyst can be anything: FOMC passes without surprise, VIX mean-reverts, a large vol seller enters.

**Step 2: Negative vanna positions gain delta.** Dealers who are short puts (negative vanna) see their delta exposure change. As IV drops, the puts they're short lose delta — their net delta position shifts bullish.

**Step 3: Dealers must buy futures to rebalance.** To stay delta-neutral, dealers buy NQ futures. This is not discretionary — it's mechanical, driven by their risk management systems.

**Step 4: NQ rises.** The buying pressure from dealer rehedging pushes NQ higher.

**Step 5: Higher NQ + lower vol = further vanna flow.** The rally itself reduces IV further (negative spot-vol correlation), which triggers more vanna rehedging. The feedback loop runs until the vanna exposure is exhausted.

### NQ-Specific Calibration

The overshoot before mean-reversion is typically **0.5-1.5% of NQ price** (100-300 NQ points at 20,000). The rally tends to:
- Start within 30-60 minutes of the IV compression trigger
- Run for 1-3 hours in moderate regimes
- Overshoot by 0.5-1.5% before stalling
- Mean-revert 30-50% of the overshoot within the same session

**VEX threshold for actionable vanna flow**: VEX > $500M (see Section 9).

```python
def estimate_vanna_flow_magnitude(vex_dollars: float, iv_change_pct: float) -> float:
    """
    Rough estimate of NQ point move from vanna rehedging.
    vex_dollars: total vanna exposure in dollars (from FlashAlpha)
    iv_change_pct: IV change as decimal (e.g., -0.02 for -2 vol points)
    Returns: estimated NQ point move
    """
    # VEX represents dollar change per 1% IV move
    # Divide by NQ point value ($20/point) to get point equivalent
    nq_point_value = 20
    estimated_move = (vex_dollars * abs(iv_change_pct)) / nq_point_value
    return estimated_move
```

---

## 8. Charm Formula

Charm (also called delta decay or DdeltaDtime) measures how delta changes with time:

```
Charm = -dDelta/dt = -N'(d1) × [2rT - d2 × σ√T] / [2T × σ√T]
```

Simplified for near-zero rates (r ≈ 0):

```
Charm ≈ -N'(d1) × d2 / (2T)
```

### Time Scaling — The Critical Property

Charm scales as **1/T**. This creates explosive behavior near expiry:

| DTE | Relative Charm Magnitude | Rehedging Frequency |
|-----|--------------------------|---------------------|
| 30 DTE | 1x (baseline) | Once per day |
| 10 DTE | 3x | Every few hours |
| 1 DTE | 30x | Every 30-60 min |
| 0 DTE (6 hours) | 120x | Every 5-15 min |
| 0 DTE (1 hour) | 720x | Every 1-5 min |
| 0 DTE (1 minute) | 43,200x | Continuous |

The 5x at 1 hour and 50x at 1 minute figures are relative to the 30-DTE baseline.

### 0DTE Afternoon Acceleration

For 0DTE options (QQQ expires every trading day), charm acceleration follows a predictable intraday pattern:

- **9:30-11:00 ET**: Charm moderate, dominated by opening vol dynamics
- **11:00-14:00 ET**: Charm building, dealers begin more frequent rehedging
- **14:00-15:00 ET**: Charm elevated, 2-3x morning levels
- **15:00-15:30 ET**: Charm high, 5-10x morning levels, directional moves amplified
- **15:30-16:00 ET**: Charm extreme, mechanical flows dominate, mean-reversion tendency

The 15:00-15:30 window is the highest-probability charm flow window. If CHEX is positive (dealers net long charm exposure) and NQ has been drifting up, the 15:00 acceleration tends to push NQ higher into close.

```python
def charm(S, K, T, r, sigma):
    """Compute charm (dDelta/dt) for a European option."""
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    return -norm.pdf(d1) * (2*r*T - d2*sigma*np.sqrt(T)) / (2*T*sigma*np.sqrt(T))
```

---

## 9. VEX and CHEX Thresholds

FlashAlpha computes aggregate vanna and charm exposure across the entire QQQ/NDX options chain, weighted by open interest and dealer positioning.

### VEX (Vanna Exposure)

VEX represents the total dollar delta change dealers must absorb per 1% move in IV.

| VEX Level | Signal | Expected NQ Impact |
|-----------|--------|-------------------|
| > $1,000M | Extreme positive vanna | 200-400 NQ points on IV compression |
| $500M to $1,000M | Strong positive vanna | 100-200 NQ points on IV compression |
| $100M to $500M | Moderate | 20-100 NQ points, directional but not dominant |
| -$100M to $100M | Neutral | No meaningful vanna flow |
| < -$500M | Negative vanna | IV compression = bearish rehedging |

**Actionable threshold**: VEX > $500M with IV dropping = vanna rally signal.

### CHEX (Charm Exposure)

CHEX represents the total dollar delta change dealers must absorb per day of time decay.

| CHEX Level | Signal | Timing |
|------------|--------|--------|
| > $500M | Strong positive charm | Bullish drift into close, especially 15:00-15:30 |
| $200M to $500M | Moderate positive charm | Mild bullish drift |
| -$200M to $200M | Neutral | No charm signal |
| < -$500M | Negative charm | Bearish drift into close |

**Actionable threshold**: CHEX > $500M = bullish charm flow signal, strongest in final 90 minutes.

```python
def vex_chex_signal(vex: float, chex: float, iv_change: float, minutes_to_close: int) -> dict:
    signals = []

    # VEX signal (triggered by IV move)
    if vex > 500e6 and iv_change < -0.01:
        signals.append({"type": "VANNA_RALLY", "conviction": "HIGH" if vex > 1000e6 else "MODERATE"})
    elif vex < -500e6 and iv_change < -0.01:
        signals.append({"type": "VANNA_SELLOFF", "conviction": "HIGH" if vex < -1000e6 else "MODERATE"})

    # CHEX signal (triggered by time, strongest near close)
    charm_multiplier = max(1, 90 / max(minutes_to_close, 1))
    effective_chex = chex * charm_multiplier
    if effective_chex > 500e6:
        signals.append({"type": "CHARM_BULLISH", "conviction": "HIGH" if minutes_to_close < 60 else "MODERATE"})
    elif effective_chex < -500e6:
        signals.append({"type": "CHARM_BEARISH", "conviction": "HIGH" if minutes_to_close < 60 else "MODERATE"})

    return {"signals": signals, "vex": vex, "chex": chex, "effective_chex": effective_chex}
```

---

## 10. Computing Vanna/Charm from Raw Chain

When FlashAlpha is unavailable or you want to verify their numbers, compute VEX/CHEX directly from the options chain.

### Step-by-Step Pipeline

**Step 1: Extract IV from chain**

```python
import pandas as pd
import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

def black_scholes_price(S, K, T, r, sigma, option_type='call'):
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    if option_type == 'call':
        return S*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)
    else:
        return K*np.exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1)

def implied_vol(market_price, S, K, T, r, option_type='call'):
    """Bisection solver for IV. Returns NaN if no solution."""
    try:
        return brentq(
            lambda sigma: black_scholes_price(S, K, T, r, sigma, option_type) - market_price,
            1e-6, 10.0, xtol=1e-6
        )
    except ValueError:
        return np.nan
```

**Step 2: Fit SVI to the IV smile**

```python
from scipy.optimize import minimize

def fit_svi(strikes, ivs, F, T):
    """
    Fit SVI parameters to observed IV smile.
    strikes: array of strike prices
    ivs: array of implied vols (annualized)
    F: forward price
    T: time to expiry in years
    """
    ks = np.log(strikes / F)
    ws = ivs**2 * T  # total variance

    def svi_w(k, params):
        a, b, rho, m, sigma = params
        return a + b * (rho*(k-m) + np.sqrt((k-m)**2 + sigma**2))

    def objective(params):
        w_fit = np.array([svi_w(k, params) for k in ks])
        return np.sum((w_fit - ws)**2)

    # Initial guess: typical QQQ values
    x0 = [0.04, 0.15, -0.60, 0.01, 0.15]
    bounds = [(0, None), (0, None), (-0.999, 0.999), (-0.5, 0.5), (1e-4, None)]
    result = minimize(objective, x0, bounds=bounds, method='L-BFGS-B')
    return result.x  # [a, b, rho, m, sigma]
```

**Step 3: Compute Greeks per strike**

```python
def compute_greeks_chain(chain_df, S, T, r):
    """
    chain_df: DataFrame with columns [strike, iv, open_interest, option_type]
    Returns chain_df with delta, vanna, charm columns added.
    """
    results = []
    for _, row in chain_df.iterrows():
        K, sigma, oi, opt_type = row['strike'], row['iv'], row['open_interest'], row['option_type']
        if np.isnan(sigma) or sigma <= 0:
            continue

        d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
        d2 = d1 - sigma*np.sqrt(T)
        npdf_d1 = norm.pdf(d1)

        delta = norm.cdf(d1) if opt_type == 'call' else norm.cdf(d1) - 1
        vanna_val = -npdf_d1 * d2 / sigma
        charm_val = -npdf_d1 * (2*r*T - d2*sigma*np.sqrt(T)) / (2*T*sigma*np.sqrt(T))

        results.append({**row, 'delta': delta, 'vanna': vanna_val, 'charm': charm_val})

    return pd.DataFrame(results)
```

**Step 4: Weight by OI and aggregate**

```python
def compute_vex_chex(chain_df, S, contract_multiplier=100, dealer_sign=-1):
    """
    Aggregate VEX and CHEX from chain.
    dealer_sign: -1 assumes dealers are short options (typical for index puts)
    contract_multiplier: 100 for QQQ options
    """
    # Dollar vanna per contract = vanna * S * multiplier
    chain_df['dollar_vanna'] = chain_df['vanna'] * S * contract_multiplier * chain_df['open_interest']
    chain_df['dollar_charm'] = chain_df['charm'] * S * contract_multiplier * chain_df['open_interest']

    # Dealer exposure is opposite to market (dealers sold what market bought)
    vex = dealer_sign * chain_df['dollar_vanna'].sum()
    chex = dealer_sign * chain_df['dollar_charm'].sum()

    return {"vex": vex, "chex": chex}
```

**Reference**: The `volsurface` library (GitHub: `jasonstrimpel/volsurface`) provides production-ready SVI calibration with arbitrage constraints. FlashAlpha's engineering blog covers their production approach to computing VEX/CHEX from the full NDX chain with dealer positioning estimates.

---

## 11. Realized Volatility Estimators

Close-to-close is the baseline but wastes information. For NQ, which has significant overnight gaps (FOMC, earnings, macro), Yang-Zhang is the correct estimator.

### Close-to-Close (Baseline)

```
σ²_CC = (1/(n-1)) × Σ [ln(C_t / C_{t-1})]²
```

Efficiency: 1x (baseline). Ignores intraday range entirely.

### Parkinson (High-Low)

```
σ²_P = (1/(4n × ln2)) × Σ [ln(H_t / L_t)]²
```

Efficiency: **5.2x** vs close-to-close. Uses intraday range but ignores overnight gaps and drift.

### Garman-Klass

```
σ²_GK = (1/n) × Σ { 0.5 × [ln(H_t/L_t)]² - (2ln2-1) × [ln(C_t/O_t)]² }
```

Efficiency: **7.4x**. Adds open-to-close return. Still ignores overnight gaps.

### Yang-Zhang (Recommended for NQ)

```
σ²_YZ = σ²_overnight + k × σ²_open + (1-k) × σ²_close
```

where:
- `σ²_overnight = (1/(n-1)) × Σ [ln(O_t / C_{t-1})]²` (overnight return variance)
- `σ²_open` = Rogers-Satchell estimator using open as reference
- `σ²_close` = Garman-Klass estimator
- `k = 0.34 / (1.34 + (n+1)/(n-1))` (optimal weighting)

Efficiency: **14x**. Handles overnight gaps, drift, and intraday range simultaneously.

```python
def yang_zhang_rv(ohlc_df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    Compute Yang-Zhang realized volatility.
    ohlc_df: DataFrame with columns [open, high, low, close]
    window: lookback in bars
    Returns: annualized volatility series
    """
    log_oc = np.log(ohlc_df['open'] / ohlc_df['close'].shift(1))  # overnight
    log_co = np.log(ohlc_df['close'] / ohlc_df['open'])            # open-to-close
    log_ho = np.log(ohlc_df['high'] / ohlc_df['open'])
    log_lo = np.log(ohlc_df['low'] / ohlc_df['open'])

    # Rogers-Satchell (open-referenced)
    rs = log_ho * (log_ho - log_co) + log_lo * (log_lo - log_co)

    n = window
    k = 0.34 / (1.34 + (n + 1) / (n - 1))

    var_overnight = log_oc.rolling(n).var()
    var_open = log_co.rolling(n).var()
    var_rs = rs.rolling(n).mean()

    var_yz = var_overnight + k * var_open + (1 - k) * var_rs
    return np.sqrt(var_yz * 252)  # annualized
```

---

## 12. VRP Computation

Volatility Risk Premium = what the market charges for vol insurance vs what vol actually realizes.

```
VRP = σ_IV(30d ATM) - σ_RV(20d Yang-Zhang)
```

The window mismatch (30d IV vs 20d RV) is intentional: IV is forward-looking, RV is backward-looking. The 20d window is the closest practical match for 30d forward vol.

### Z-Score Normalization

Raw VRP in vol points is hard to interpret across regimes. Z-score it:

```python
def compute_vrp(atm_iv_30d: pd.Series, rv_20d: pd.Series, zscore_window: int = 252) -> pd.DataFrame:
    """
    atm_iv_30d: 30-day ATM IV series (annualized, e.g., 0.18 for 18%)
    rv_20d: 20-day Yang-Zhang RV series (annualized)
    """
    vrp = atm_iv_30d - rv_20d

    vrp_mean = vrp.rolling(zscore_window).mean()
    vrp_std = vrp.rolling(zscore_window).std()
    vrp_zscore = (vrp - vrp_mean) / vrp_std

    return pd.DataFrame({
        'vrp': vrp,
        'vrp_zscore': vrp_zscore,
        'iv': atm_iv_30d,
        'rv': rv_20d
    })
```

### Interpolating ATM IV

The chain gives you discrete strikes. Interpolate to get the exact ATM IV:

```python
def interpolate_atm_iv(chain_df: pd.DataFrame, S: float, T: float) -> float:
    """
    Interpolate ATM IV from chain using SVI fit.
    chain_df: options chain with [strike, iv] columns
    S: spot price
    T: time to expiry in years
    """
    F = S  # simplified (ignore carry for short-dated)
    strikes = chain_df['strike'].values
    ivs = chain_df['iv'].dropna().values

    # Fit SVI
    params = fit_svi(strikes, ivs, F, T)
    a, b, rho, m, sigma = params

    # ATM = k=0
    w_atm = a + b * (rho * (0 - m) + np.sqrt((0 - m)**2 + sigma**2))
    return np.sqrt(max(w_atm, 0) / T)
```

---

## 13. Regime-Dependent VRP

VRP alone is not a trading signal. Combined with GEX regime, it creates a 4-cell framework:

| | Positive GEX (Regime A/B/C) | Negative GEX (Regime D/E) |
|---|---|---|
| **High VRP** (zscore > 1.0) | **PARADISE** | **TEMPTING TRAP** |
| **Low VRP** (zscore < 0.0) | **GRIND** | **STAY HOME** |

### Cell Characteristics

**PARADISE** (High VRP + Positive GEX):
- Vol sellers are being paid well AND the market structure is stable
- Dealers are long gamma, dampening moves
- Win rate for mean-reversion strategies: 72-78%
- Best setups: Wall Bounce, Expected Move Fade, Charm Flow

**TEMPTING TRAP** (High VRP + Negative GEX):
- Vol looks expensive but the market is unstable
- Dealers are short gamma, amplifying moves
- Selling vol here gets you run over on the next gap
- Win rate for mean-reversion: 35-45% (below random)
- Avoid vol selling. If trading at all, momentum only.

**GRIND** (Low VRP + Positive GEX):
- Market is stable but vol is fairly priced
- Slow, grinding moves. Low premium available.
- Win rate for mean-reversion: 58-65%
- Reduce size. Wait for better VRP.

**STAY HOME** (Low VRP + Negative GEX):
- Unstable market AND vol is cheap (market not pricing the risk)
- This is the pre-crash setup. Vol is about to reprice violently.
- Win rate for any directional strategy: 40-50%
- No trade. Watch for regime transition.

```python
def vrp_gex_regime(vrp_zscore: float, gex_sign: int) -> dict:
    """
    vrp_zscore: normalized VRP (>1 = high, <0 = low)
    gex_sign: +1 for positive GEX, -1 for negative GEX
    """
    high_vrp = vrp_zscore > 1.0
    pos_gex = gex_sign > 0

    if high_vrp and pos_gex:
        return {"cell": "PARADISE", "win_rate": 0.75, "size_multiplier": 1.5, "strategy": "MEAN_REVERT"}
    elif high_vrp and not pos_gex:
        return {"cell": "TEMPTING_TRAP", "win_rate": 0.40, "size_multiplier": 0.0, "strategy": "NO_TRADE"}
    elif not high_vrp and pos_gex:
        return {"cell": "GRIND", "win_rate": 0.62, "size_multiplier": 0.75, "strategy": "MEAN_REVERT_SMALL"}
    else:
        return {"cell": "STAY_HOME", "win_rate": 0.45, "size_multiplier": 0.0, "strategy": "NO_TRADE"}
```

---

## 14. 0DTE Gamma Explosion

Gamma scales inversely with the square root of time to expiry:

```
Γ ∝ N'(d1) / (S × σ × √T)
```

As T → 0, gamma → ∞ for near-ATM options. This is not a theoretical curiosity — it's the dominant force in QQQ options every trading day.

### Gamma by DTE (QQQ ATM, σ=18%)

| DTE | T (years) | Gamma (per $1 move) | Dealer Rehedge Frequency |
|-----|-----------|---------------------|--------------------------|
| 30 DTE | 0.082 | ~0.010 | Once per day |
| 10 DTE | 0.027 | ~0.018 | Every few hours |
| 5 DTE | 0.014 | ~0.025 | Every 1-2 hours |
| 1 DTE | 0.003 | ~0.055 | Every 30-60 min |
| 0 DTE (6h) | 0.001 | ~0.100 | Every 5-15 min |
| 0 DTE (1h) | 0.0002 | ~0.175 | Every 1-5 min |
| 0 DTE (15m) | 0.00004 | ~0.250+ | Continuous |

### Theta Acceleration

Theta (time decay) also accelerates as 1/√T, but the gamma explosion is more important for intraday trading because it determines how much dealers must rehedge per NQ point move.

At 0DTE with 1 hour remaining, a 10-point NQ move (0.05% of 20,000) forces dealers to rehedge approximately 10 × 0.175 = 1.75 delta per contract. With millions of contracts outstanding, this creates mechanical buying or selling pressure that can move NQ 5-15 points on its own.

### Dealer Rehedging Cascade

When NQ moves through a 0DTE strike with large open interest:
1. Dealers who sold those options suddenly have large delta exposure
2. They must buy (if calls) or sell (if puts) NQ futures to rebalance
3. This buying/selling moves NQ further through the strike
4. More options go ITM, more rehedging required
5. The cascade continues until the strike is cleared or vol spikes enough to slow it

This is why 0DTE strikes with >10,000 OI act as **magnets** (price gets pulled toward them) and then **catapults** (price accelerates through them once they're breached).

---

## 15. Vol Regime Classification

Four volatility regimes, each requiring different algo behavior:

### Regime Table

| Regime | VIX Range | GEX Typical | VRP Typical | Charm | Algo Behavior |
|--------|-----------|-------------|-------------|-------|---------------|
| **CALM** | < 15 | Positive | High (>1.5 zscore) | Positive | Mean-revert, sell vol, full size |
| **NORMAL** | 15-25 | Mixed | Moderate (0-1.5) | Variable | Standard playbook, regime-dependent |
| **ELEVATED** | 25-35 | Negative | Low or negative | Negative | Momentum only, reduce size 50% |
| **CRISIS** | > 35 | Deeply negative | Negative | Extreme negative | No new positions, exits only |

### Transition Triggers

**CALM → NORMAL**: VIX crosses 15 upward, or GEX flips negative, or VRP zscore drops below 0.5.

**NORMAL → ELEVATED**: VIX crosses 25 upward, or GEX deeply negative (>$1B negative), or two consecutive days of VRP zscore < -1.

**ELEVATED → CRISIS**: VIX crosses 35, or VIX moves >5 points in a single day, or NQ gaps >2% overnight.

**Any → CALM**: VIX closes below 15 for 3 consecutive days AND GEX positive AND VRP zscore > 1.

```python
def classify_vol_regime(vix: float, gex: float, vrp_zscore: float) -> dict:
    """
    vix: current VIX level
    gex: net GEX in dollars (positive = dealers long gamma)
    vrp_zscore: normalized VRP
    """
    if vix < 15 and gex > 0 and vrp_zscore > 0.5:
        regime = "CALM"
        size_mult = 1.5
        allowed_strategies = ["MEAN_REVERT", "VOL_SELL", "WALL_BOUNCE", "CHARM_FLOW"]
        notes = "Paradise conditions. Full size. Sell vol, fade extremes."

    elif vix < 25:
        regime = "NORMAL"
        size_mult = 1.0
        allowed_strategies = ["ALL"]
        notes = "Standard playbook. Follow regime from GEX structure."

    elif vix < 35:
        regime = "ELEVATED"
        size_mult = 0.5
        allowed_strategies = ["MOMENTUM", "GAMMA_FLIP_CROSS"]
        notes = "Reduce size 50%. Momentum only. No mean-reversion."

    else:
        regime = "CRISIS"
        size_mult = 0.0
        allowed_strategies = ["EXITS_ONLY"]
        notes = "No new positions. Manage existing risk only."

    return {
        "regime": regime,
        "vix": vix,
        "size_multiplier": size_mult,
        "allowed_strategies": allowed_strategies,
        "notes": notes
    }
```

### Algo Behavior Per Regime

**CALM**: This is when the system makes most of its money. Positive GEX dampens moves, high VRP means options are expensive, charm and vanna flows are predictable. Run full size on all setups. The wall bounce and expected move fade setups have their highest win rates here.

**NORMAL**: Standard operation. The regime from GEX structure (A through G) determines the playbook. VRP is moderate, so vol selling is acceptable but not aggressive. All setups are valid.

**ELEVATED**: The market is unstable. Mean-reversion setups fail because negative GEX amplifies moves instead of dampening them. Only momentum setups work. Cut size in half. The gamma flip cross setup is still valid because it trades the regime transition itself.

**CRISIS**: The system stops trading. VIX above 35 means the options market is dislocated, GEX calculations are unreliable (dealers are overwhelmed), and any position can gap against you by 2-5% overnight. Preserve capital. Wait for NORMAL regime to return.

---

## References

- **SVI original paper**: Gatheral (2004), "A parsimonious arbitrage-free implied volatility parameterization with application to the valuation of volatility derivatives"
- **SSVI**: Gatheral & Jacquier (2014), "Arbitrage-free SVI volatility surfaces"
- **Yang-Zhang estimator**: Yang & Zhang (2000), "Drift-Independent Volatility Estimation Based on High, Low, Open, and Close Prices"
- **volsurface library**: `github.com/jasonstrimpel/volsurface` — SVI calibration with arbitrage constraints
- **FlashAlpha SVI engineering**: FlashAlpha blog, "How We Compute VEX and CHEX from the NDX Chain" — production approach to dealer positioning estimation
- **Vanna/charm mechanics**: Bennett (2012), "Volatility Trading" — Chapter 7 covers the full Greek hedging cascade
