"""
equilibrium_module.py
=====================
Weekly + Daily GEX Synthetic Equilibrium Model for NQ futures.

Companion to confluence_server.py. Adds:
  - Strike-level GEX computation (Black-Scholes gamma per strike)
  - Synthetic Fair Value (SFV) = weighted blend of WeeklyZG + DailyZG + HVL
  - Volatility-adjusted Premium / Equilibrium / Discount bands
  - 4-regime classifier:
        Gamma Regime         (POSITIVE / NEGATIVE)
        Volatility Regime    (EXPANSION / CONTRACTION / STABLE)
        Trend Alignment      (BULLISH / BEARISH / NEUTRAL short-term)
        Institutional Bias   (FADE_PREMIUM / FOLLOW_MOMENTUM /
                              DEFEND_DISCOUNT / CAUTION / NEUTRAL)
  - 3-tier alert system (CRITICAL / WARNING / INFO)

Symbol: NQ futures, options chain on NDX (primary) with optional QQQ fallback
for daily/0DTE pressure (NDX has no 0DTE; QQQ does).

SFV math (default weights):
    SFV = 0.50 * WeeklyZeroGamma + 0.35 * DailyZeroGamma + 0.15 * HVL

Band math:
    upper_premium  = SFV + 1.5 * sigma
    lower_discount = SFV - 1.5 * sigma
    extreme_upper  = SFV + 2.5 * sigma
    extreme_lower  = SFV - 2.5 * sigma
where sigma = realized 30d daily vol scaled to next-week horizon

Author: Michael / Peak Asset Performance LLC
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

import httpx
from pydantic import BaseModel, Field

LOG = logging.getLogger("equilibrium")

# ============================================================
#  CONFIG
# ============================================================

# Symbols
PRIMARY_INDEX        = os.getenv("EQM_PRIMARY_INDEX",  "NDX")   # NDX for NQ futures
DAILY_PRESSURE_PROXY = os.getenv("EQM_DAILY_PROXY",    "QQQ")   # 0DTE proxy
USE_QQQ_FOR_DAILY    = os.getenv("EQM_USE_QQQ_DAILY",  "true").lower() == "true"

# NQ/NDX scale factor (NDX strikes are ~24-26x NQ futures price -- handled by mapping)
NDX_TO_NQ_RATIO_EST  = float(os.getenv("EQM_NDX_NQ_RATIO", "1.06"))  # rough multiplier

# SFV component weights (must sum to 1.0)
W_WEEKLY_ZG   = float(os.getenv("EQM_W_WEEKLY",  "0.50"))
W_DAILY_ZG    = float(os.getenv("EQM_W_DAILY",   "0.35"))
W_HVL         = float(os.getenv("EQM_W_HVL",     "0.15"))
assert abs(W_WEEKLY_ZG + W_DAILY_ZG + W_HVL - 1.0) < 1e-6, "SFV weights must sum to 1.0"

# Band sigmas
SIGMA_ZONE_K     = float(os.getenv("EQM_SIGMA_ZONE",    "1.5"))   # zone edges
SIGMA_EXTREME_K  = float(os.getenv("EQM_SIGMA_EXTREME", "2.5"))   # extreme edges

# Black-Scholes
RISK_FREE_RATE   = float(os.getenv("EQM_RF_RATE", "0.045"))       # 4.5% T-bill
CONTRACT_SIZE    = 100                                            # standard equity option

# Regime thresholds
GAMMA_THRESHOLD_NDX  = float(os.getenv("EQM_GAMMA_TH_NDX",  "2e9"))  # ±2B for NDX
GAMMA_THRESHOLD_QQQ  = float(os.getenv("EQM_GAMMA_TH_QQQ",  "5e8"))  # ±500M for QQQ
VOL_EXPANSION_RATIO  = float(os.getenv("EQM_VOL_EXPAND",    "1.2"))
VOL_CONTRACT_RATIO   = float(os.getenv("EQM_VOL_CONTRACT",  "0.8"))

# Massive endpoint (Polygon.io-compatible)
MASSIVE_BASE         = os.getenv("MASSIVE_BASE", "https://api.polygon.io")
MASSIVE_API_KEY      = os.getenv("MASSIVE_API_KEY", "")

# Top-K strikes to surface in histograms (for HUD rendering)
HISTOGRAM_TOP_K      = int(os.getenv("EQM_HIST_TOPK", "20"))


# ============================================================
#  PYDANTIC MODELS
# ============================================================

class StrikeBar(BaseModel):
    strike: float
    gex:    float                     # signed dollar GEX
    type:   Literal["CALL", "PUT", "NET"] = "NET"


class GexProfile(BaseModel):
    """One timeframe's worth of strike-level GEX data."""
    timeframe:   Literal["WEEKLY", "DAILY"]
    expiry_date: Optional[str] = None
    net_gex:     float = 0.0
    call_wall:   Optional[float] = None
    zero_gamma:  Optional[float] = None
    put_wall:    Optional[float] = None
    hvl:         Optional[float] = None        # High Vol Level (max abs strike gamma)
    histogram:   list[StrikeBar] = Field(default_factory=list)
    source:      str = "NDX"                    # "NDX" or "QQQ"
    stale:       bool = False
    source_ts:   Optional[str] = None


class RegimeQuad(BaseModel):
    gamma_regime:     Literal["POSITIVE", "NEGATIVE", "NEUTRAL"] = "NEUTRAL"
    gamma_label:      str = ""                                       # "Risk Off" / "Risk On"
    volatility_regime: Literal["EXPANSION", "CONTRACTION", "STABLE"] = "STABLE"
    vol_label:        str = ""
    trend_alignment:  Literal["BULLISH", "BEARISH", "NEUTRAL"] = "NEUTRAL"
    trend_label:      str = ""                                       # "Short Term"
    institutional_bias: Literal["FADE_PREMIUM", "FOLLOW_MOMENTUM",
                                "DEFEND_DISCOUNT", "CAUTION",
                                "NEUTRAL"] = "NEUTRAL"
    bias_label:       str = ""


class EquilibriumPayload(BaseModel):
    ts:           str
    symbol:       str = "NQ"
    proxy_index:  str = PRIMARY_INDEX
    price:        Optional[float] = None              # NQ last price (from NT8)
    price_ndx:    Optional[float] = None              # NDX spot (for ratio sanity)

    weekly:       GexProfile
    daily:        GexProfile

    sfv:                Optional[float] = None        # Synthetic Fair Value (in NQ points)
    sfv_components:     dict[str, float] = Field(default_factory=dict)

    upper_premium:      Optional[float] = None
    lower_discount:     Optional[float] = None
    extreme_upper:      Optional[float] = None
    extreme_lower:      Optional[float] = None
    sigma_points:       Optional[float] = None        # 1σ in NQ points

    current_zone:       Literal["PREMIUM", "EQUILIBRIUM",
                                "DISCOUNT", "UNKNOWN"] = "UNKNOWN"
    distance_to_sfv:    Optional[float] = None        # signed; +above SFV, −below

    regime:             RegimeQuad

    alerts:             list[dict] = Field(default_factory=list)


# ============================================================
#  BLACK-SCHOLES GAMMA
# ============================================================

def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """
    Black-Scholes gamma. Returns gamma (option price 2nd derivative w.r.t. spot).
    S=spot, K=strike, T=years to expiry, r=rf rate, sigma=IV (decimal).
    """
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return _norm_pdf(d1) / (S * sigma * math.sqrt(T))


def strike_gex(
    contract_type: str,  # "call" or "put"
    S: float,
    K: float,
    T: float,
    sigma: float,
    open_interest: float,
    r: float = RISK_FREE_RATE,
) -> float:
    """
    Dollar GEX for a single strike, in $/1% move.

    Formula:
        GEX_call =  + OI * 100 * gamma * S^2 * 0.01
        GEX_put  =  - OI * 100 * gamma * S^2 * 0.01

    The S^2 * 0.01 converts gamma (per-unit-spot) to dollar exposure per 1% spot move.
    The convention here follows SqueezeMetrics' dealer-side sign convention
    (calls are positive dealer gamma, puts are negative dealer gamma).
    """
    gamma = bs_gamma(S, K, T, r, sigma)
    raw = open_interest * CONTRACT_SIZE * gamma * (S * S) * 0.01
    return raw if contract_type.lower().startswith("c") else -raw


# ============================================================
#  OPTIONS CHAIN FETCHER (Massive)
# ============================================================

@dataclass
class ContractRow:
    contract_type: str         # "call" or "put"
    strike:        float
    expiry:        str         # ISO date
    open_interest: float
    implied_vol:   float
    days_to_exp:   int


async def fetch_chain(
    client: httpx.AsyncClient,
    ticker: str,
    spot_price: float,
) -> list[ContractRow]:
    """
    Pull full options chain snapshot for the underlying.

    Polygon options snapshot endpoint:
        GET {MASSIVE_BASE}/v3/snapshot/options/{ticker}?apiKey=...

    Pagination is driven by ``next_url`` and capped to 5 pages to avoid
    runaway chain fetches.
    """
    today = datetime.now(timezone.utc).date()
    out: list[ContractRow] = []

    url = f"{MASSIVE_BASE.rstrip('/')}/v3/snapshot/options/{ticker}"
    params: dict[str, str] = {"limit": "250"}
    if MASSIVE_API_KEY:
        params["apiKey"] = MASSIVE_API_KEY

    for _ in range(5):
        try:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            LOG.warning("fetch_chain(%s) failed: %s", ticker, e)
            return out

        contracts = data.get("results") or []

        for c in contracts:
            try:
                details = c.get("details") or {}
                greeks = c.get("greeks") or {}
                expiry_str = details.get("expiration_date") or c.get("expiration_date") or c.get("expiry")
                expiry_date = datetime.fromisoformat(expiry_str).date() if expiry_str else None
                if expiry_date is None:
                    continue
                days = max(0, (expiry_date - today).days)

                out.append(ContractRow(
                    contract_type = (details.get("contract_type") or c.get("contract_type") or c.get("type") or "").lower(),
                    strike        = float(details.get("strike_price") or c.get("strike_price") or c.get("strike") or 0),
                    expiry        = expiry_date.isoformat(),
                    open_interest = float(c.get("open_interest") or 0),
                    implied_vol   = float(c.get("implied_volatility") or greeks.get("iv") or greeks.get("implied_volatility") or 0),
                    days_to_exp   = days,
                ))
            except Exception:
                continue

        next_url = data.get("next_url")
        if not next_url:
            break

        url = next_url
        params = {"apiKey": MASSIVE_API_KEY} if MASSIVE_API_KEY else {}

    return out


async def fetch_underlying_spot(
    client: httpx.AsyncClient,
    ticker: str,
) -> Optional[float]:
    """Fetch previous close for an index/ETF via Polygon aggregates."""
    polygon_ticker = f"I:{ticker}" if ticker.isalpha() and len(ticker) <= 4 and ticker != "QQQ" else ticker
    url = f"{MASSIVE_BASE.rstrip('/')}/v2/aggs/ticker/{polygon_ticker}/prev"
    params = {"adjusted": "true"}
    if MASSIVE_API_KEY:
        params["apiKey"] = MASSIVE_API_KEY

    try:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        if results:
            close = results[0].get("c")
            return float(close) if close is not None else None
    except Exception as e:
        LOG.warning("fetch_underlying_spot(%s) failed: %s", ticker, e)
    return None


# ============================================================
#  GEX PROFILE COMPUTATION
# ============================================================

def compute_gex_profile(
    contracts: list[ContractRow],
    spot: float,
    expiry_filter,                # callable: (days_to_exp) -> bool
    timeframe: Literal["WEEKLY", "DAILY"],
    source: str,
    strike_window_pct: float = 0.15,
) -> GexProfile:
    """
    Compute a single-timeframe GEX profile from a contract list.

    Args:
        contracts:        all contracts from fetch_chain
        spot:             underlying spot price
        expiry_filter:    function selecting which expiries to include
        timeframe:        "WEEKLY" or "DAILY" (label only)
        source:           "NDX" or "QQQ"
        strike_window_pct: ignore strikes more than this % away from spot
    """
    selected = [c for c in contracts if expiry_filter(c.days_to_exp)]
    if not selected:
        return GexProfile(timeframe=timeframe, source=source, stale=True)

    lower_k = spot * (1.0 - strike_window_pct)
    upper_k = spot * (1.0 + strike_window_pct)

    # Aggregate by strike
    strike_gex_map: dict[float, float] = {}

    for c in selected:
        if not (lower_k <= c.strike <= upper_k):
            continue
        if c.open_interest <= 0 or c.implied_vol <= 0:
            continue
        T = max(1.0 / 365.0, c.days_to_exp / 365.0)
        g = strike_gex(c.contract_type, spot, c.strike, T, c.implied_vol,
                       c.open_interest)
        strike_gex_map[c.strike] = strike_gex_map.get(c.strike, 0.0) + g

    if not strike_gex_map:
        return GexProfile(timeframe=timeframe, source=source, stale=True)

    sorted_strikes = sorted(strike_gex_map.items(), key=lambda x: x[0])

    # Net GEX
    net = sum(g for _, g in sorted_strikes)

    # Call Wall = max positive single-strike GEX
    pos_strikes = [(k, g) for k, g in sorted_strikes if g > 0]
    neg_strikes = [(k, g) for k, g in sorted_strikes if g < 0]
    call_wall = max(pos_strikes, key=lambda x: x[1])[0] if pos_strikes else None
    put_wall  = min(neg_strikes, key=lambda x: x[1])[0] if neg_strikes else None

    # HVL = strike with greatest absolute single-strike gamma
    hvl_pair = max(strike_gex_map.items(), key=lambda x: abs(x[1]))
    hvl = hvl_pair[0]

    # Zero Gamma = strike where cumulative GEX (descending from highest strike)
    # crosses zero. Standard method: walk strikes low-to-high; find sign flip
    # in cumulative.
    zero_gamma = _find_zero_gamma(sorted_strikes)

    # Histogram for HUD (top-K by absolute GEX)
    top = sorted(sorted_strikes, key=lambda x: abs(x[1]), reverse=True)[:HISTOGRAM_TOP_K]
    histogram = [StrikeBar(strike=k, gex=g, type="NET")
                 for k, g in sorted(top, key=lambda x: x[0])]

    # Source timestamp = max contract expiry date in selected set (rough proxy)
    expiry_set = {c.expiry for c in selected}
    expiry_date = min(expiry_set) if expiry_set else None

    return GexProfile(
        timeframe   = timeframe,
        expiry_date = expiry_date,
        net_gex     = net,
        call_wall   = call_wall,
        zero_gamma  = zero_gamma,
        put_wall    = put_wall,
        hvl         = hvl,
        histogram   = histogram,
        source      = source,
        stale       = False,
        source_ts   = datetime.now(timezone.utc).isoformat(),
    )


def _find_zero_gamma(sorted_strikes: list[tuple[float, float]]) -> Optional[float]:
    """Walk strikes low-to-high; find first sign flip in cumulative GEX (interpolated)."""
    cum = 0.0
    prev_strike = None
    prev_cum = None
    for k, g in sorted_strikes:
        cum += g
        if prev_cum is not None and prev_cum * cum < 0:
            # Linear interpolation between prev_strike (prev_cum) and k (cum)
            ratio = abs(prev_cum) / (abs(prev_cum) + abs(cum))
            return prev_strike + ratio * (k - prev_strike)
        prev_strike, prev_cum = k, cum
    return None


# ============================================================
#  SFV + BANDS
# ============================================================

def compute_sfv(weekly: GexProfile, daily: GexProfile) -> tuple[Optional[float], dict]:
    """
    Synthetic Fair Value = weighted blend of Weekly ZG + Daily ZG + Weekly HVL.
    Returns (sfv, components_dict).

    If any component missing, redistributes its weight proportionally to the rest.
    """
    components: dict[str, float] = {}
    weights: dict[str, float] = {}

    if weekly.zero_gamma is not None:
        components["weekly_zg"] = weekly.zero_gamma
        weights["weekly_zg"]    = W_WEEKLY_ZG
    if daily.zero_gamma is not None:
        components["daily_zg"]  = daily.zero_gamma
        weights["daily_zg"]     = W_DAILY_ZG
    if weekly.hvl is not None:
        components["hvl"]       = weekly.hvl
        weights["hvl"]          = W_HVL

    if not components:
        return None, {}

    # Renormalize weights to sum to 1.0
    w_total = sum(weights.values())
    if w_total <= 0:
        return None, {}
    weights = {k: v / w_total for k, v in weights.items()}

    sfv = sum(components[k] * weights[k] for k in components)
    return sfv, {**components, **{f"w_{k}": v for k, v in weights.items()}}


def compute_bands(sfv: float, sigma_points: float) -> dict:
    """Volatility-adjusted Premium / Discount / Extreme bands."""
    return {
        "upper_premium":  sfv + SIGMA_ZONE_K    * sigma_points,
        "lower_discount": sfv - SIGMA_ZONE_K    * sigma_points,
        "extreme_upper":  sfv + SIGMA_EXTREME_K * sigma_points,
        "extreme_lower":  sfv - SIGMA_EXTREME_K * sigma_points,
        "sigma_points":   sigma_points,
    }


def classify_zone(price: float, bands: dict) -> str:
    """Map price to PREMIUM / EQUILIBRIUM / DISCOUNT zone."""
    if price >= bands["upper_premium"]:
        return "PREMIUM"
    if price <= bands["lower_discount"]:
        return "DISCOUNT"
    return "EQUILIBRIUM"


# ============================================================
#  4-REGIME CLASSIFIER
# ============================================================

def classify_regime(
    weekly: GexProfile,
    daily: GexProfile,
    price: Optional[float],
    realized_vol_5d: Optional[float],
    realized_vol_30d: Optional[float],
    implied_vol_atm: Optional[float],
    ema20: Optional[float],
    ema50: Optional[float],
    current_zone: str,
) -> RegimeQuad:
    """Decompose institutional state into 4 orthogonal regimes."""

    # 1) GAMMA REGIME -- based on weekly net GEX
    if weekly.source == "NDX":
        gamma_th = GAMMA_THRESHOLD_NDX
    else:
        gamma_th = GAMMA_THRESHOLD_QQQ

    if weekly.net_gex >= gamma_th:
        gamma_regime, gamma_label = "POSITIVE", "Risk On"
    elif weekly.net_gex <= -gamma_th:
        gamma_regime, gamma_label = "NEGATIVE", "Risk Off"
    else:
        gamma_regime, gamma_label = "NEUTRAL", "Mixed"

    # 2) VOLATILITY REGIME
    vol_regime: Literal["EXPANSION", "CONTRACTION", "STABLE"] = "STABLE"
    vol_label = "Neutral"
    if realized_vol_5d and realized_vol_30d:
        ratio = realized_vol_5d / realized_vol_30d
        if ratio >= VOL_EXPANSION_RATIO:
            vol_regime, vol_label = "EXPANSION", "Vol Expanding"
        elif ratio <= VOL_CONTRACT_RATIO:
            vol_regime, vol_label = "CONTRACTION", "Vol Compressing"
    # Cross-check with IV
    if implied_vol_atm and realized_vol_30d:
        if realized_vol_30d > implied_vol_atm * 1.1 and vol_regime == "STABLE":
            vol_regime, vol_label = "EXPANSION", "RV > IV"

    # 3) TREND ALIGNMENT
    trend: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "NEUTRAL"
    trend_label = "Range"
    if price and ema20 and ema50:
        if price > ema20 > ema50:
            trend, trend_label = "BULLISH", "Short Term"
        elif price < ema20 < ema50:
            trend, trend_label = "BEARISH", "Short Term"

    # 4) INSTITUTIONAL BIAS -- composite verdict
    bias: Literal["FADE_PREMIUM", "FOLLOW_MOMENTUM",
                  "DEFEND_DISCOUNT", "CAUTION", "NEUTRAL"]
    bias_label: str

    if current_zone == "PREMIUM" and gamma_regime == "NEGATIVE":
        bias, bias_label = "FADE_PREMIUM", "Caution / Mean Revert"
    elif current_zone == "DISCOUNT" and gamma_regime == "POSITIVE":
        bias, bias_label = "DEFEND_DISCOUNT", "Dealer Absorb / Long Setup"
    elif current_zone == "EQUILIBRIUM" and gamma_regime == "POSITIVE" and trend != "NEUTRAL":
        bias, bias_label = "FOLLOW_MOMENTUM", f"Trend-with-Dealer ({trend.title()})"
    elif vol_regime == "EXPANSION" and gamma_regime == "NEGATIVE":
        bias, bias_label = "CAUTION", "Vol Expand + Negative Gamma"
    else:
        bias, bias_label = "NEUTRAL", "No edge"

    return RegimeQuad(
        gamma_regime       = gamma_regime,
        gamma_label        = gamma_label,
        volatility_regime  = vol_regime,
        vol_label          = vol_label,
        trend_alignment    = trend,
        trend_label        = trend_label,
        institutional_bias = bias,
        bias_label         = bias_label,
    )


# ============================================================
#  3-TIER ALERTS
# ============================================================

def build_alerts(
    price: float,
    bands: dict,
    weekly: GexProfile,
    daily: GexProfile,
    regime: RegimeQuad,
    current_zone: str,
) -> list[dict]:
    """Emit a list of alert dicts ordered by severity."""
    required_band_keys = ("upper_premium", "lower_discount", "extreme_upper", "extreme_lower")
    if (
        price is None
        or bands is None
        or weekly is None
        or daily is None
        or regime is None
        or any(bands.get(key) is None for key in required_band_keys)
    ):
        return []

    alerts: list[dict] = []

    # CRITICAL
    if price >= bands["extreme_upper"]:
        alerts.append({"severity": "CRITICAL", "icon": "▼",
                       "msg": "Price above EXTREME premium band — high reversion risk"})
    elif price <= bands["extreme_lower"]:
        alerts.append({"severity": "CRITICAL", "icon": "▲",
                       "msg": "Price below EXTREME discount band — high bounce risk"})

    if regime.gamma_regime == "NEGATIVE" and regime.volatility_regime == "EXPANSION":
        alerts.append({"severity": "CRITICAL", "icon": "⚠",
                       "msg": "Negative gamma + vol expansion — trend continuation likely"})

    # WARNING
    if weekly.call_wall and price >= weekly.call_wall * 0.995:
        alerts.append({"severity": "WARNING", "icon": "!",
                       "msg": f"Approaching Weekly Call Wall ({weekly.call_wall:.2f})"})
    if weekly.put_wall and price <= weekly.put_wall * 1.005:
        alerts.append({"severity": "WARNING", "icon": "!",
                       "msg": f"Approaching Weekly Put Wall ({weekly.put_wall:.2f})"})
    if daily.call_wall and price >= daily.call_wall * 0.998:
        alerts.append({"severity": "WARNING", "icon": "!",
                       "msg": f"Approaching Daily Call Wall ({daily.call_wall:.2f})"})

    # INFO
    if current_zone == "PREMIUM" and regime.institutional_bias == "FADE_PREMIUM":
        alerts.append({"severity": "INFO", "icon": "i",
                       "msg": "Watch for mean reversion at dealer defense"})
    if current_zone == "DISCOUNT" and regime.institutional_bias == "DEFEND_DISCOUNT":
        alerts.append({"severity": "INFO", "icon": "i",
                       "msg": "Dealer long gamma — discount likely absorbed"})

    return alerts


# ============================================================
#  TOP-LEVEL PIPELINE
# ============================================================

@dataclass
class EquilibriumInputs:
    """Inputs from the caller (NT8) plus computed locally."""
    nq_price:           float
    ndx_price:          float
    realized_vol_5d:    Optional[float] = None    # daily vol, decimal (e.g., 0.012)
    realized_vol_30d:   Optional[float] = None
    implied_vol_atm:    Optional[float] = None
    ema20_nq:           Optional[float] = None
    ema50_nq:           Optional[float] = None


async def compute_equilibrium(
    client: httpx.AsyncClient,
    inputs: EquilibriumInputs,
) -> EquilibriumPayload:
    """
    Run the full Equilibrium Model pipeline.

    Pipeline:
        1. Fetch NDX chain (Weekly structure)
        2. Optionally fetch QQQ chain (Daily pressure / 0DTE)
        3. Compute Weekly + Daily GEX profiles
        4. Compute SFV (in NDX points), translate to NQ points via ratio
        5. Compute volatility bands
        6. Classify current zone
        7. Run 4-regime classifier
        8. Build alerts
    """

    ndx_spot = inputs.ndx_price if inputs.ndx_price is not None else 0.0
    if ndx_spot <= 0:
        fetched_ndx_spot = await fetch_underlying_spot(client, PRIMARY_INDEX)
        if fetched_ndx_spot and fetched_ndx_spot > 0:
            ndx_spot = fetched_ndx_spot

    # ----- 1) NDX weekly chain
    ndx_contracts = await fetch_chain(client, PRIMARY_INDEX, ndx_spot)
    weekly_source = PRIMARY_INDEX
    weekly_spot = ndx_spot

    if not ndx_contracts and PRIMARY_INDEX != DAILY_PRESSURE_PROXY:
        qqq_fallback_spot = await fetch_underlying_spot(client, DAILY_PRESSURE_PROXY)
        if not qqq_fallback_spot or qqq_fallback_spot <= 0:
            qqq_fallback_spot = ndx_spot / 40.0 if ndx_spot > 0 else 0.0
        qqq_fallback_contracts = await fetch_chain(client, DAILY_PRESSURE_PROXY, qqq_fallback_spot)
        if qqq_fallback_contracts:
            ndx_contracts = qqq_fallback_contracts
            weekly_source = DAILY_PRESSURE_PROXY
            weekly_spot = qqq_fallback_spot

    weekly = compute_gex_profile(
        ndx_contracts, weekly_spot,
        expiry_filter = lambda d: 1 <= d <= 9,        # 1-9 day window = "this week"
        timeframe     = "WEEKLY",
        source        = weekly_source,
    )

    # ----- 2) Daily pressure chain (NDX or QQQ)
    if USE_QQQ_FOR_DAILY:
        qqq_spot = await fetch_underlying_spot(client, DAILY_PRESSURE_PROXY)
        if not qqq_spot or qqq_spot <= 0:
            qqq_spot = ndx_spot / 40.0 if ndx_spot > 0 else 0.0
        qqq_contracts = await fetch_chain(client, DAILY_PRESSURE_PROXY, qqq_spot)
        # QQQ ≈ NDX/40 historically; use that as rough spot estimate
        # In production NT8 sends qqq_price separately
        spot_for_qqq = qqq_spot if qqq_contracts else ndx_spot
        daily = compute_gex_profile(
            qqq_contracts, spot_for_qqq,
            expiry_filter = lambda d: d <= 1,         # 0DTE + 1DTE
            timeframe     = "DAILY",
            source        = DAILY_PRESSURE_PROXY,
        )
    else:
        daily = compute_gex_profile(
            ndx_contracts, ndx_spot,
            expiry_filter = lambda d: d <= 2,
            timeframe     = "DAILY",
            source        = PRIMARY_INDEX,
        )

    # ----- 3) Compute SFV (in NDX points if weekly is NDX-based)
    sfv_ndx, sfv_components = compute_sfv(weekly, daily)

    # Translate SFV from NDX scale to NQ scale (if needed)
    sfv_nq = None
    if sfv_ndx is not None:
        if weekly.source == PRIMARY_INDEX:
            # NQ ≈ NDX * ratio (current ~1.06; we use a dynamic per-poll ratio)
            ratio = (inputs.nq_price / ndx_spot) if ndx_spot > 0 else NDX_TO_NQ_RATIO_EST
            sfv_nq = sfv_ndx * ratio
        elif weekly.source == DAILY_PRESSURE_PROXY:
            qqq_spot_est = weekly_spot if weekly_spot > 0 else (ndx_spot / 40.0 if ndx_spot > 0 else 0.0)
            ratio = (inputs.nq_price / qqq_spot_est) if qqq_spot_est > 0 else NDX_TO_NQ_RATIO_EST * 40.0
            sfv_nq = sfv_ndx * ratio
        else:
            sfv_nq = sfv_ndx

    # ----- 4) Volatility bands (in NQ points)
    bands = {"upper_premium": None, "lower_discount": None,
             "extreme_upper": None, "extreme_lower": None, "sigma_points": None}

    if sfv_nq is not None and inputs.realized_vol_30d is not None:
        # 30d daily vol -> next-week horizon (5 trading days)
        sigma_pct = inputs.realized_vol_30d * math.sqrt(5.0)
        sigma_points = inputs.nq_price * sigma_pct
        bands = compute_bands(sfv_nq, sigma_points)

    # ----- 5) Classify zone
    current_zone = "UNKNOWN"
    if bands["upper_premium"] is not None:
        current_zone = classify_zone(inputs.nq_price, bands)

    # ----- 6) Regime classifier
    regime = classify_regime(
        weekly, daily,
        price            = inputs.nq_price,
        realized_vol_5d  = inputs.realized_vol_5d,
        realized_vol_30d = inputs.realized_vol_30d,
        implied_vol_atm  = inputs.implied_vol_atm,
        ema20            = inputs.ema20_nq,
        ema50            = inputs.ema50_nq,
        current_zone     = current_zone,
    )

    # ----- 7) Alerts
    alerts = build_alerts(inputs.nq_price, bands, weekly, daily, regime, current_zone)

    # ----- 8) Distance to SFV
    distance = (inputs.nq_price - sfv_nq) if sfv_nq is not None else None

    payload = EquilibriumPayload(
        ts             = datetime.now(timezone.utc).isoformat(),
        symbol         = "NQ",
        proxy_index    = PRIMARY_INDEX,
        price          = inputs.nq_price,
        price_ndx      = ndx_spot,
        weekly         = weekly,
        daily          = daily,
        sfv            = sfv_nq,
        sfv_components = sfv_components,
        upper_premium  = bands["upper_premium"],
        lower_discount = bands["lower_discount"],
        extreme_upper  = bands["extreme_upper"],
        extreme_lower  = bands["extreme_lower"],
        sigma_points   = bands["sigma_points"],
        current_zone   = current_zone,
        distance_to_sfv = distance,
        regime         = regime,
        alerts         = alerts,
    )
    return payload
