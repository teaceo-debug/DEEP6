# FlashAlpha API Reference — Complete Endpoint Reference

## Hosts

| Host | Purpose | Tier |
|------|---------|------|
| `https://lab.flashalpha.com` | Live data | All tiers |
| `https://historical.flashalpha.com` | Historical replay | Alpha only |

Historical requests require `?at=YYYY-MM-DDTHH:mm:ss` parameter (UTC).

## Authentication

```
X-Api-Key: YOUR_KEY
```

Or as query param: `?apiKey=YOUR_KEY`

Same key works for both hosts.

## Tier Access

| Tier | Monthly | Description |
|------|---------|-------------|
| Free | $0 | Exposure levels, Greeks compute |
| Basic | $29 | VEX, CHEX, max pain, screening |
| Growth | $49 | Full summary, 0DTE, volatility, narratives, simulation |
| Alpha | $149 | Historical API, SVI, VRP z-score, raw flow, advanced vol |

---

## 1. Exposure Analytics Endpoints

### GET /v1/exposure/levels/{symbol}

**Tier:** Free

Key structural levels derived from GEX.

**Response:**
```json
{
  "symbol": "QQQ",
  "spot": 480.5,
  "gamma_flip": 478.0,
  "call_wall": 490.0,
  "put_wall": 470.0,
  "zero_dte_magnet": 480.0,
  "net_gex_label": "positive",
  "timestamp": "2026-05-15T14:30:00Z"
}
```

**Fields:**
- `gamma_flip` — strike where cumulative GEX crosses zero
- `call_wall` — strike with highest net positive GEX (upside resistance in positive gamma)
- `put_wall` — strike with highest net negative GEX (downside support in positive gamma)
- `zero_dte_magnet` — highest-OI 0DTE strike near spot
- `net_gex_label` — "positive" or "negative"

---

### GET /v1/exposure/gex/{symbol}

**Tier:** Basic

Full GEX breakdown by strike and expiration.

**Response:**
```json
{
  "symbol": "QQQ",
  "net_gex": 2300000000,
  "net_gex_label": "positive",
  "gex_by_strike": [
    {"strike": 480, "gex": 450000000, "call_gex": 600000000, "put_gex": -150000000},
    {"strike": 485, "gex": 320000000, ...}
  ],
  "gex_by_expiry": [
    {"dte": 0, "gex": 800000000},
    {"dte": 7, "gex": 600000000}
  ]
}
```

---

### GET /v1/exposure/dex/{symbol}

**Tier:** Basic

Delta exposure breakdown.

**Response:**
```json
{
  "symbol": "QQQ",
  "net_dex": -120000000,
  "dex_by_strike": [...],
  "dealer_shares_to_trade_up": -850000,
  "dealer_shares_to_trade_down": 920000
}
```

**Fields:**
- `net_dex` — total dollar delta dealers must hedge
- `dealer_shares_to_trade_up` — shares dealers trade on +1% spot move (negative = sell)
- `dealer_shares_to_trade_down` — shares dealers trade on -1% spot move (positive = buy)

---

### GET /v1/exposure/vex/{symbol}

**Tier:** Basic

Vanna exposure — how dealer delta changes with IV.

**Response:**
```json
{
  "symbol": "QQQ",
  "net_vex": 45000000,
  "interpretation": "vol_down_dealers_buy",
  "vex_by_strike": [
    {"strike": 480, "vex": 8000000},
    {"strike": 475, "vex": -3000000}
  ]
}
```

**Interpretation values:**
- `"vol_up_dealers_sell"` — IV rising causes dealers to sell underlying
- `"vol_up_dealers_buy"` — IV rising causes dealers to buy underlying
- `"vol_down_dealers_buy"` — IV falling causes dealers to buy underlying (bullish vol crush)
- `"vol_down_dealers_sell"` — IV falling causes dealers to sell underlying (bearish vol crush)

---

### GET /v1/exposure/chex/{symbol}

**Tier:** Basic

Charm exposure — how dealer delta changes with time.

**Response:**
```json
{
  "symbol": "QQQ",
  "net_chex": 2100000,
  "interpretation": "time_decay_dealers_buy",
  "chex_by_strike": [...]
}
```

**Interpretation values:**
- `"time_decay_dealers_buy"` — time passing causes dealers to buy (supportive into close)
- `"time_decay_dealers_sell"` — time passing causes dealers to sell (pressure into close)

---

### GET /v1/exposure/summary/{symbol}

**Tier:** Growth

Comprehensive exposure summary combining all metrics with interpretations.

**Response:**
```json
{
  "symbol": "QQQ",
  "spot": 480.5,
  "net_gex": 2300000000,
  "net_gex_label": "positive",
  "gamma_flip": 478.0,
  "call_wall": 490.0,
  "put_wall": 470.0,
  "net_dex": -120000000,
  "net_vex": 45000000,
  "vex_interpretation": "vol_down_dealers_buy",
  "net_chex": 2100000,
  "chex_interpretation": "time_decay_dealers_buy",
  "dealer_shares_to_trade_up": -850000,
  "dealer_shares_to_trade_down": 920000,
  "oi_weighted_dte": 12.3,
  "zero_dte_magnet": 480.0,
  "regime_narrative": "Positive gamma regime. Dealers absorb moves. Range-bound behavior expected.",
  "timestamp": "2026-05-15T14:30:00Z"
}
```

---

### GET /v1/exposure/narrative/{symbol}

**Tier:** Growth

Human-readable narrative interpretation of current exposure state.

**Response:**
```json
{
  "symbol": "QQQ",
  "narrative": "QQQ is in a positive gamma regime with spot at 480.5, above the gamma flip at 478. Dealers are long gamma and will absorb moves. Call wall at 490 provides resistance; put wall at 470 provides support. VEX is positive — if IV compresses, expect mechanical buying. CHEX is positive — time decay supports price into the close.",
  "regime": "positive_gamma",
  "key_levels": [478.0, 480.0, 490.0, 470.0],
  "timestamp": "2026-05-15T14:30:00Z"
}
```

---

### GET /v1/exposure/max_pain/{symbol}

**Tier:** Basic

Max pain analysis and pin probability.

**Response:**
```json
{
  "symbol": "QQQ",
  "max_pain_strike": 479.0,
  "pin_probability": 0.34,
  "total_option_value_by_strike": [
    {"strike": 475, "total_value": 45000000},
    {"strike": 479, "total_value": 28000000},
    {"strike": 480, "total_value": 31000000}
  ],
  "nearest_expiry_max_pain": 480.0,
  "timestamp": "2026-05-15T14:30:00Z"
}
```

**Fields:**
- `max_pain_strike` — strike minimizing total option value at expiry
- `pin_probability` — probability of closing at/near max pain
- `nearest_expiry_max_pain` — max pain for the nearest expiration only

---

## 2. Zero-DTE Endpoints

### GET /v1/zero_dte/{symbol}

**Tier:** Growth

Complete 0DTE analytics package.

**Response:**
```json
{
  "symbol": "QQQ",
  "spot": 480.5,
  "implied_1sd_dollars": 4.20,
  "remaining_1sd_dollars": 2.85,
  "upper_bound": 483.35,
  "lower_bound": 477.65,
  "pin_score": 68,
  "magnet_strike": 480.0,
  "gamma_acceleration": 9.1,
  "net_theta_dollars": -12500000,
  "theta_per_hour_remaining": -3125000,
  "charm_regime": "time_decay_dealers_buy",
  "call_volume": 145000,
  "put_volume": 98000,
  "pc_ratio_volume": 0.68,
  "pc_ratio_oi": 1.12,
  "atm_volume_share_pct": 38.5,
  "net_chex_0dte": 1800000,
  "hours_remaining": 4.0,
  "timestamp": "2026-05-15T14:30:00Z"
}
```

**Key fields:**
- `pin_score` — 0-100 composite pin risk (> 70 = strong pin)
- `magnet_strike` — gravitational center for 0DTE pinning
- `gamma_acceleration` — 0DTE gamma vs. 7DTE gamma ratio
- `charm_regime` — "time_decay_dealers_buy" or "time_decay_dealers_sell"
- `remaining_1sd_dollars` — expected move scaled to time remaining

---

## 3. Flow Analytics Endpoints (Simulation-Aware)

These endpoints use simulation to account for path-dependent dealer hedging.

### GET /v1/flow/levels/{symbol}

**Tier:** Growth

Simulation-adjusted key levels (more accurate than static GEX levels).

**Response:**
```json
{
  "symbol": "QQQ",
  "spot": 480.5,
  "sim_gamma_flip": 477.5,
  "sim_call_wall": 491.0,
  "sim_put_wall": 469.0,
  "sim_pin_strike": 480.0,
  "confidence": 0.82,
  "timestamp": "2026-05-15T14:30:00Z"
}
```

---

### GET /v1/flow/pin_risk/{symbol}

**Tier:** Growth

Detailed pin risk analysis with simulation.

**Response:**
```json
{
  "symbol": "QQQ",
  "pin_score": 68,
  "magnet_strike": 480.0,
  "oi_concentration_score": 72,
  "proximity_score": 85,
  "time_score": 60,
  "gamma_magnitude_score": 55,
  "pin_probability": 0.41,
  "timestamp": "2026-05-15T14:30:00Z"
}
```

---

### GET /v1/flow/summary/{symbol}

**Tier:** Growth

Simulation-aware flow summary combining pin risk, dealer positioning, and expected move.

---

### GET /v1/flow/gex/{symbol}

**Tier:** Growth

Simulation-adjusted GEX (accounts for path-dependent hedging).

---

### GET /v1/flow/dex/{symbol}

**Tier:** Growth

Simulation-adjusted DEX.

---

### GET /v1/flow/dealer_risk/{symbol}

**Tier:** Growth

Dealer hedging risk assessment — how much mechanical flow to expect from dealer rebalancing.

**Response:**
```json
{
  "symbol": "QQQ",
  "dealer_flow_risk_score": 45,
  "regime": "positive_gamma",
  "amplification_factor": 0.8,
  "estimated_daily_dealer_volume": 2400000,
  "timestamp": "2026-05-15T14:30:00Z"
}
```

---

### GET /v1/flow/oi/{symbol}

**Tier:** Basic

Open interest breakdown by strike and expiration.

**Response:**
```json
{
  "symbol": "QQQ",
  "total_call_oi": 4500000,
  "total_put_oi": 5200000,
  "pc_ratio_oi": 1.16,
  "oi_by_strike": [
    {"strike": 480, "call_oi": 85000, "put_oi": 72000},
    {"strike": 485, "call_oi": 120000, "put_oi": 45000}
  ],
  "oi_by_expiry": [
    {"dte": 0, "call_oi": 450000, "put_oi": 380000},
    {"dte": 7, "call_oi": 620000, "put_oi": 540000}
  ],
  "oi_weighted_dte": 12.3
}
```

---

### GET /v1/flow/live/{symbol}

**Tier:** Growth

Real-time flow updates (polling endpoint for live dealer positioning).

---

## 4. Raw Flow Data (Alpha Tier)

### GET /v1/flow/tape/{symbol}

**Tier:** Alpha

Raw options tape — every trade with size, price, IV, Greeks.

**Response:**
```json
{
  "trades": [
    {
      "timestamp": "2026-05-15T14:30:01.234Z",
      "symbol": "QQQ",
      "expiry": "2026-05-15",
      "strike": 480,
      "option_type": "call",
      "size": 500,
      "price": 2.45,
      "iv": 0.182,
      "delta": 0.52,
      "gamma": 0.089,
      "side": "buy",
      "exchange": "CBOE"
    }
  ]
}
```

---

### GET /v1/flow/stock_tape/{symbol}

**Tier:** Alpha

Stock tape with estimated dealer hedging trades flagged.

---

### GET /v1/flow/leaderboard

**Tier:** Alpha

Top symbols by unusual options activity, sorted by flow score.

**Response:**
```json
{
  "leaderboard": [
    {"symbol": "NVDA", "flow_score": 94, "call_put_ratio": 3.2, "unusual_volume_pct": 340},
    {"symbol": "SPY", "flow_score": 87, ...}
  ],
  "timestamp": "2026-05-15T14:30:00Z"
}
```

---

### GET /v1/flow/outliers

**Tier:** Alpha

Unusual options activity — large trades, sweeps, block trades.

**Response:**
```json
{
  "outliers": [
    {
      "symbol": "QQQ",
      "strike": 490,
      "expiry": "2026-05-17",
      "option_type": "call",
      "size": 5000,
      "premium": 1250000,
      "iv": 0.195,
      "outlier_type": "sweep",
      "sentiment": "bullish",
      "timestamp": "2026-05-15T14:28:00Z"
    }
  ]
}
```

---

## 5. Volatility Endpoints

### GET /v1/volatility/{symbol}

**Tier:** Growth

Complete volatility analytics package.

**Response:**
```json
{
  "symbol": "QQQ",
  "atm_iv": 0.182,
  "rv_5d": 0.145,
  "rv_10d": 0.158,
  "rv_20d": 0.162,
  "rv_30d": 0.165,
  "rv_60d": 0.171,
  "vrp": 0.017,
  "vrp_regime": "positive_vrp",
  "vrp_gex_conditioned": 0.012,
  "iv_rank": 42,
  "iv_percentile": 58,
  "skew_25d": -3.2,
  "skew_10d": -6.8,
  "term_structure": [
    {"dte": 7, "iv": 0.195},
    {"dte": 14, "iv": 0.188},
    {"dte": 30, "iv": 0.182},
    {"dte": 60, "iv": 0.178}
  ],
  "term_structure_slope": -0.00059,
  "term_structure_regime": "backwardation",
  "timestamp": "2026-05-15T14:30:00Z"
}
```

---

### GET /v1/adv_volatility/{symbol}

**Tier:** Alpha

Advanced volatility surface with SVI parameters, per-strike vanna/charm, and strategy scores.

**Response:**
```json
{
  "symbol": "QQQ",
  "svi_params_by_expiry": [
    {
      "dte": 7,
      "a": 0.0234,
      "b": 0.0891,
      "rho": -0.42,
      "m": 0.012,
      "sigma": 0.089,
      "arbitrage_flag": false
    }
  ],
  "svi_smoothed_iv_surface": [...],
  "variance_swap_fair_value": 0.0312,
  "vanna_surface": [...],
  "charm_surface": [...],
  "vrp_zscore": 1.2,
  "harvest_score": 67,
  "dealer_flow_risk": 45,
  "iron_condor_score": 72,
  "strangle_score": 58,
  "calendar_score": 41,
  "timestamp": "2026-05-15T14:30:00Z"
}
```

---

## 6. Greeks Compute Endpoint

### GET /v1/pricing/greeks

**Tier:** Free

Compute BSM Greeks for any option parameters.

**Query params:**
- `spot` — current spot price
- `strike` — option strike
- `dte` — days to expiry
- `rate` — risk-free rate (decimal, e.g., 0.05)
- `iv` — implied volatility (decimal, e.g., 0.18)
- `option_type` — "call" or "put"

**Response:**
```json
{
  "delta": 0.523,
  "gamma": 0.089,
  "theta": -0.052,
  "vega": 0.142,
  "rho": 0.031,
  "vanna": 0.0034,
  "charm": -0.0012,
  "vomma": 0.0089,
  "dual_delta": -0.498,
  "speed": 0.00012,
  "zomma": 0.00034,
  "color": -0.00089,
  "lambda": 9.8,
  "veta": -0.0023
}
```

---

### GET /v1/optionquote/{symbol}

**Tier:** Growth

Pre-computed Greeks for every listed contract.

**Response:**
```json
{
  "symbol": "QQQ",
  "contracts": [
    {
      "expiry": "2026-05-15",
      "strike": 480,
      "option_type": "call",
      "bid": 2.40,
      "ask": 2.50,
      "mid": 2.45,
      "iv": 0.182,
      "delta": 0.523,
      "gamma": 0.089,
      "theta": -0.052,
      "vega": 0.142,
      "rho": 0.031,
      "vanna": 0.0034,
      "charm": -0.0012,
      "lambda": 9.8,
      "open_interest": 85000,
      "volume": 12400
    }
  ],
  "timestamp": "2026-05-15T14:30:00Z"
}
```

---

## 7. Screening Endpoint

### GET /v1/screen

**Tier:** Basic

Screen 6,000+ symbols by exposure metrics.

**Query params:**
- `min_gex` — minimum net GEX
- `max_gex` — maximum net GEX
- `regime` — "positive" or "negative"
- `min_vrp` — minimum VRP
- `min_iv_rank` — minimum IV rank
- `min_pin_score` — minimum pin score
- `sort_by` — field to sort by
- `limit` — max results (default 20)

**Response:**
```json
{
  "results": [
    {
      "symbol": "QQQ",
      "net_gex": 2300000000,
      "regime": "positive",
      "vrp": 0.017,
      "iv_rank": 42,
      "pin_score": 68,
      "gamma_flip": 478.0
    }
  ],
  "count": 1,
  "timestamp": "2026-05-15T14:30:00Z"
}
```

---

## 8. Historical API (Alpha Tier)

All live endpoints are available on the historical host with `?at=` parameter.

**Base URL:** `https://historical.flashalpha.com`

**Required parameter:** `?at=YYYY-MM-DDTHH:mm:ss` (UTC)

### Examples

```python
# Historical exposure summary
GET https://historical.flashalpha.com/v1/exposure/summary/QQQ?at=2026-05-14T14:30:00

# Historical 0DTE analytics
GET https://historical.flashalpha.com/v1/zero_dte/QQQ?at=2026-05-14T14:30:00

# Historical option quotes with Greeks
GET https://historical.flashalpha.com/v1/optionquote/QQQ?at=2026-05-14T14:30:00

# Historical volatility
GET https://historical.flashalpha.com/v1/volatility/QQQ?at=2026-05-14T14:30:00
```

**Coverage:** Intraday snapshots available at 15-minute intervals. Full tick-level data for options tape.

**Supported symbols:** Same 6,000+ symbols as live API.

---

## 9. Python SDK

```python
from flashalpha import FlashAlpha

fa = FlashAlpha("YOUR_KEY")

# Exposure
levels   = fa.exposure_levels("QQQ")      # Free
gex      = fa.gex("QQQ")                  # Basic
dex      = fa.dex("QQQ")                  # Basic
vex      = fa.vex("QQQ")                  # Basic
chex     = fa.chex("QQQ")                 # Basic
summary  = fa.exposure_summary("QQQ")     # Growth
narrative = fa.narrative("QQQ")           # Growth

# 0DTE
zte      = fa.zero_dte("QQQ")             # Growth

# Flow
flow_levels = fa.flow_levels("QQQ")       # Growth
pin_risk    = fa.flow_pin_risk("QQQ")     # Growth
oi          = fa.flow_oi("QQQ")           # Basic

# Volatility
vol      = fa.volatility("QQQ")           # Growth
adv_vol  = fa.adv_volatility("QQQ")       # Alpha

# Greeks
greeks   = fa.compute_greeks(             # Free
    spot=480.0, strike=485.0, dte=7,
    rate=0.05, iv=0.18, option_type="call"
)
quotes   = fa.optionquote("QQQ")          # Growth

# Max pain
mp       = fa.max_pain("QQQ")             # Basic

# Screening
results  = fa.screen(regime="positive", min_pin_score=60)  # Basic

# Historical (Alpha)
hist_summary = fa.exposure_summary("QQQ", at="2026-05-14T14:30:00")
```

---

## 10. Concept-to-Endpoint Mapping

| User asks about | Use endpoint | Tier |
|----------------|-------------|------|
| Gamma flip level | `/v1/exposure/levels/{symbol}` | Free |
| Call wall / put wall | `/v1/exposure/levels/{symbol}` | Free |
| Gamma regime (positive/negative) | `/v1/exposure/levels/{symbol}` | Free |
| Full GEX by strike | `/v1/exposure/gex/{symbol}` | Basic |
| Delta exposure | `/v1/exposure/dex/{symbol}` | Basic |
| Vanna exposure / VEX | `/v1/exposure/vex/{symbol}` | Basic |
| Charm exposure / CHEX | `/v1/exposure/chex/{symbol}` | Basic |
| Max pain | `/v1/exposure/max_pain/{symbol}` | Basic |
| Open interest breakdown | `/v1/flow/oi/{symbol}` | Basic |
| Everything at once | `/v1/exposure/summary/{symbol}` | Growth |
| Human-readable narrative | `/v1/exposure/narrative/{symbol}` | Growth |
| 0DTE pin risk | `/v1/zero_dte/{symbol}` | Growth |
| Expected move | `/v1/zero_dte/{symbol}` | Growth |
| Gamma acceleration | `/v1/zero_dte/{symbol}` | Growth |
| Simulation-adjusted levels | `/v1/flow/levels/{symbol}` | Growth |
| Dealer flow risk | `/v1/flow/dealer_risk/{symbol}` | Growth |
| IV, VRP, skew, term structure | `/v1/volatility/{symbol}` | Growth |
| Compute Greeks for any option | `/v1/pricing/greeks` | Free |
| Pre-computed Greeks per contract | `/v1/optionquote/{symbol}` | Growth |
| Screen symbols by exposure | `/v1/screen` | Basic |
| Historical data at timestamp | `historical.flashalpha.com/...?at=` | Alpha |
| SVI parameters | `/v1/adv_volatility/{symbol}` | Alpha |
| VRP z-score | `/v1/adv_volatility/{symbol}` | Alpha |
| Strategy scores (harvest, IC, etc.) | `/v1/adv_volatility/{symbol}` | Alpha |
| Raw options tape | `/v1/flow/tape/{symbol}` | Alpha |
| Unusual activity / outliers | `/v1/flow/outliers` | Alpha |
| Top symbols by flow | `/v1/flow/leaderboard` | Alpha |

---

## 11. Error Handling

```python
from flashalpha import FlashAlpha, FlashAlphaError

fa = FlashAlpha("YOUR_KEY")

try:
    summary = fa.exposure_summary("QQQ")
except FlashAlphaError as e:
    if e.status_code == 401:
        print("Invalid API key")
    elif e.status_code == 403:
        print("Endpoint requires higher tier")
    elif e.status_code == 429:
        print("Rate limit exceeded")
    elif e.status_code == 404:
        print("Symbol not found or no options data")
```

**Rate limits:**
- Free: 10 requests/minute
- Basic: 60 requests/minute
- Growth: 300 requests/minute
- Alpha: 1000 requests/minute

---

## 12. Anti-Hallucination Checklist

Before referencing any endpoint or field:

1. Is the endpoint listed in this document? If not, do not use it.
2. Is the field name exactly as shown in the response examples? If not, do not guess.
3. Is the tier correct? Flag Alpha-only features explicitly.
4. Are you mixing live and historical hosts? Never do this in the same request.
5. GEX sign: calls positive, puts negative. Net GEX = sum. Do not reverse.
6. VEX: positive VEX + falling IV = dealers BUY. Confirm before stating.
7. CHEX: positive CHEX = time decay causes dealers to BUY. Confirm before stating.
8. Pin score thresholds: > 70 = strong, 40-70 = moderate, < 40 = weak.
