"""
confluence_server.py
====================
Institutional Confluence Middleware for DEEP6 ATLAS / NT8

Aggregates three orthogonal data layers into a single unified endpoint:

  Layer 1 (STRUCTURE):  FlashAlpha    -> GEX levels (Flip, Call Wall, Put Wall, HVL)
  Layer 2 (FLOW):       Massive       -> Raw QQQ TRF off-exchange prints
                        quantsynth    -> AI-filtered dark pool block prints
  Layer 3 (NARRATIVE):  quantsynth    -> Macro regime + composite trade setup

NT8 InstitutionalConfluence.cs indicator polls /confluence/nq every 15s
and renders the HUD + GEX lines + MTF zones on the NQ chart.

Scoring philosophy: DP-DOMINANT
  score = 0.40 * dp_signal + 0.25 * gex_signal + 0.20 * regime_signal + 0.15 * mtf_signal

Conflict alerts ("STOP_BUYING", "STOP_SELLING", "FULL_SEND_*") fire when layers
diverge or align hard. NT8 surfaces these in the HUD bottom panel.

Author: Michael / Peak Asset Performance LLC
Stack:  FastAPI + httpx + Pydantic v2 + uvicorn
Deploy: uvicorn confluence_system.confluence_server:app --host 127.0.0.1 --port 8767
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Literal, Optional

import httpx
import nq_atlas.server as atlas_server
from fastapi import FastAPI, Query
from flashalpha import FlashAlpha as _FlashAlphaSDK
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Equilibrium Model extension (Phase 5)
from confluence_system.equilibrium_module import (
    EquilibriumInputs,
    EquilibriumPayload,
    compute_equilibrium,
)

# ============================================================
#  CONFIG
# ============================================================

LOG = logging.getLogger("confluence")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)

# API keys from environment (NEVER hardcode)
MASSIVE_API_KEY      = os.getenv("MASSIVE_API_KEY",     "")
FLASHALPHA_API_KEY   = os.getenv("FLASHALPHA_API_KEY",  "")

# Endpoints
MASSIVE_BASE         = os.getenv("MASSIVE_BASE",        "https://api.massive.io/v1")
FLASHALPHA_BASE      = os.getenv("FLASHALPHA_BASE",     "https://api.flashalpha.com/v1")

# Refresh cadences (seconds) -- tune for rate limits + freshness
REFRESH_GEX_SEC      = int(os.getenv("REFRESH_GEX_SEC",      300))   # 5 min
REFRESH_MASSIVE_SEC  = int(os.getenv("REFRESH_MASSIVE_SEC",   15))   # 15 s
REFRESH_REGIME_SEC   = int(os.getenv("REFRESH_REGIME_SEC",   900))   # 15 min
REFRESH_SETUP_SEC    = int(os.getenv("REFRESH_SETUP_SEC",    300))   # 5 min

# Scoring weights (DP-DOMINANT per Michael's choice)
W_DP        = 0.40
W_GEX       = 0.25
W_REGIME    = 0.20
W_MTF       = 0.15
assert abs(W_DP + W_GEX + W_REGIME + W_MTF - 1.0) < 1e-6, "weights must sum to 1.0"

# HTTP client settings
HTTP_TIMEOUT_SEC     = 10.0
HTTP_RETRIES         = 2

# Target symbol (QQQ used as NQ dark pool proxy)
DP_PROXY_SYMBOL      = "QQQ"

# Last-known NQ price — updated per request so GEX scaling stays current
_last_nq_price: float = 21000.0

# Latest FlashAlpha zero_dte flow snapshot — updated by fetch_flashalpha_gex()
_fa_flow_snapshot: Optional[dict] = None

# FlashAlpha SDK singleton — created once at startup (not per-call)
_fa_sdk: Optional[Any] = None


# ============================================================
#  PYDANTIC MODELS  (the unified payload schema)
# ============================================================

class GexLayer(BaseModel):
    flip:       Optional[float] = None
    call_wall:  Optional[float] = None
    put_wall:   Optional[float] = None
    hvl:        Optional[float] = None
    net_gex:    Optional[float] = None
    bias:       Literal["BULLISH", "BEARISH", "NEUTRAL"] = "NEUTRAL"
    stale:      bool = False
    source_ts:  Optional[str] = None


class DarkPoolBlock(BaseModel):
    px:    float
    sz:    float
    ts:    Optional[str] = None


class DarkPoolLayer(BaseModel):
    raw_offex_pct:   Optional[float] = None      # from Massive TRF: off-exchange volume / total
    blocks_24h:      list[DarkPoolBlock] = Field(default_factory=list)
    dp_vwap:         Optional[float] = None
    total_block_val: Optional[float] = None
    bias:            Literal["BULLISH", "BEARISH", "NEUTRAL"] = "NEUTRAL"
    confidence:      float = 0.0                  # quantsynth 0..1
    stale:           bool = False
    source_ts:       Optional[str] = None


class RegimeLayer(BaseModel):
    macro:        Literal["RISK_ON", "RISK_OFF", "NEUTRAL"] = "NEUTRAL"
    vol_regime:   Literal["LOW", "NORMAL", "ELEVATED", "EXTREME"] = "NORMAL"
    thesis_trend: Literal["BUILDING", "FADING", "FLAT", "BREAKING"] = "FLAT"
    pcr_bias:     Literal["CALL_HEAVY", "PUT_HEAVY", "NEUTRAL"] = "NEUTRAL"
    stale:        bool = False
    source_ts:    Optional[str] = None


class CompositeLayer(BaseModel):
    qqq_setup_score: float = 0.0    # quantsynth 0..10
    narrative:       str = ""
    opus_verdict:    Literal["BULL", "BEAR", "NEUTRAL", "UNKNOWN"] = "UNKNOWN"
    stale:           bool = False
    source_ts:       Optional[str] = None


class MtfLayer(BaseModel):
    """Calculated NT8-side and posted as query params; included in payload for HUD display."""
    daily:   Literal["PREMIUM", "EQUILIBRIUM", "DISCOUNT", "UNKNOWN"] = "UNKNOWN"
    h4:      Literal["PREMIUM", "EQUILIBRIUM", "DISCOUNT", "UNKNOWN"] = "UNKNOWN"
    chart:   Literal["PREMIUM", "EQUILIBRIUM", "DISCOUNT", "UNKNOWN"] = "UNKNOWN"


class UnifiedPayload(BaseModel):
    ts:               str
    symbol:           str = "NQ"
    proxy:            str = DP_PROXY_SYMBOL
    price:            Optional[float] = None     # NQ last price from NT8

    gex:              GexLayer
    darkpool:         DarkPoolLayer
    regime:           RegimeLayer
    composite:        CompositeLayer
    mtf:              MtfLayer

    # Fused output
    dp_signal:        float = 0.0      # [-1, +1]
    gex_signal:       float = 0.0      # [-1, +1]
    regime_signal:    float = 0.0      # [-1, +1]
    mtf_signal:       float = 0.0      # [-1, +1]
    confluence_score: int   = 0        # [-5, +5]
    alert:            Optional[str] = None
    alert_reason:     Optional[str] = None
    weights:          dict[str, float] = Field(
        default_factory=lambda: {
            "dp": W_DP, "gex": W_GEX, "regime": W_REGIME, "mtf": W_MTF
        }
    )


# ============================================================
#  TTL CACHE
# ============================================================

class TtlCache:
    """Thread-safe TTL cache with per-key staleness tracking."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float, float]] = {}  # key -> (value, set_ts, ttl)
        self._lock = asyncio.Lock()

    async def set(self, key: str, value: Any, ttl: float) -> None:
        async with self._lock:
            self._store[key] = (value, time.time(), ttl)

    async def get(self, key: str) -> tuple[Optional[Any], bool]:
        """Returns (value, is_stale). value=None if never set."""
        async with self._lock:
            if key not in self._store:
                return None, True
            value, set_ts, ttl = self._store[key]
            is_stale = (time.time() - set_ts) > ttl
            return value, is_stale

    async def age(self, key: str) -> Optional[float]:
        async with self._lock:
            if key not in self._store:
                return None
            _, set_ts, _ = self._store[key]
            return time.time() - set_ts


CACHE = TtlCache()


# ============================================================
#  HTTP HELPERS
# ============================================================

async def http_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
    label: str = "http",
) -> Optional[dict]:
    """GET with retry + structured logging. Returns None on failure."""
    last_exc: Optional[Exception] = None
    for attempt in range(HTTP_RETRIES + 1):
        try:
            r = await client.get(url, headers=headers or {}, params=params or {})
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_exc = e
            LOG.warning("%s attempt %d failed: %s", label, attempt + 1, e)
            await asyncio.sleep(0.5 * (attempt + 1))
    LOG.error("%s permanently failed: %s", label, last_exc)
    return None


# ============================================================
#  DATA SOURCE CLIENTS
# ============================================================

async def fetch_flashalpha_gex(client: httpx.AsyncClient) -> GexLayer:
    """
    FlashAlpha GEX levels via Python SDK (QQQ proxy → NQ-scaled prices).
    The SDK returns QQQ-denominated strikes; we scale to NQ price space using
    the ratio: NQ_ref / QQQ_underlying_price.
    """
    if not FLASHALPHA_API_KEY:
        return GexLayer(stale=True)

    try:
        loop = asyncio.get_running_loop()
        # Use module-level singleton to avoid creating a new instance per call
        global _fa_sdk
        if _fa_sdk is None:
            _fa_sdk = _FlashAlphaSDK(FLASHALPHA_API_KEY)
        fa = _fa_sdk

        # Run sync SDK calls in thread pool
        levels_raw, summary_raw, zero_dte_raw = await asyncio.gather(
            loop.run_in_executor(None, fa.exposure_levels,  DP_PROXY_SYMBOL),
            loop.run_in_executor(None, fa.exposure_summary, DP_PROXY_SYMBOL),
            loop.run_in_executor(None, fa.zero_dte,         DP_PROXY_SYMBOL),
        )

        # Store flow snapshot for compute_dp_from_options()
        global _fa_flow_snapshot
        _fa_flow_snapshot = zero_dte_raw.get("flow") if isinstance(zero_dte_raw, dict) else None

        lvls         = levels_raw.get("levels", {})
        qqq_price    = float(levels_raw.get("underlying_price", 0) or 0)

        # Scale QQQ strike prices → NQ equivalent using last-known NQ price
        ratio = (_last_nq_price / qqq_price) if qqq_price > 0 else 1.0

        def _scale(v):
            if v is None:
                return None
            return float(v) * ratio

        net_gex_raw = float(summary_raw.get("net_gamma", 0) or 0)
        # Net GEX is already in $ terms — keep as-is
        bias: Literal["BULLISH", "BEARISH", "NEUTRAL"] = (
            "BULLISH" if net_gex_raw > 1e6 else "BEARISH" if net_gex_raw < -1e6 else "NEUTRAL"
        )

        return GexLayer(
            flip      = _scale(lvls.get("gamma_flip")),
            call_wall = _scale(lvls.get("call_wall")),
            put_wall  = _scale(lvls.get("put_wall")),
            hvl       = _scale(lvls.get("max_positive_gamma")),
            net_gex   = net_gex_raw,
            bias      = bias,
            stale     = False,
            source_ts = levels_raw.get("as_of"),
        )
    except Exception as exc:
        LOG.warning("fetch_flashalpha_gex SDK error: %s", exc)
        return GexLayer(stale=True)


async def fetch_massive_trf(client: httpx.AsyncClient) -> dict:
    """
    Massive (Polygon-based) raw TRF off-exchange prints for QQQ.
    Returns {raw_offex_pct, dp_vwap} dict (merged into DarkPoolLayer downstream).
    """
    url = f"{MASSIVE_BASE}/trf/{DP_PROXY_SYMBOL}/summary"
    headers = {"X-API-Key": MASSIVE_API_KEY} if MASSIVE_API_KEY else {}
    data = await http_get(client, url, headers=headers, label="massive")
    if not data:
        return {"raw_offex_pct": None, "dp_vwap": None, "stale": True}

    return {
        "raw_offex_pct": data.get("off_exchange_pct"),
        "dp_vwap":       data.get("trf_vwap"),
        "stale":         False,
        "source_ts":     data.get("timestamp"),
    }


def _atlas_timestamp_to_iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _get_atlas_state() -> Any:
    return getattr(atlas_server, "atlas_state", None)


def _extract_contracts(state: Any) -> list[Any]:
    chain = getattr(state, "chain", None)
    if chain is None:
        return []
    contracts = getattr(chain, "contracts", None)
    if contracts is not None:
        return list(contracts)
    if isinstance(chain, dict):
        return list(chain.get("contracts", []))
    return []


def _compute_pcr_oi_metrics(state: Any) -> tuple[Optional[float], Optional[float], Optional[float]]:
    contracts = _extract_contracts(state)
    if not contracts:
        return None, None, None

    total_call_oi = 0.0
    total_put_oi = 0.0
    for contract in contracts:
        call_put = str(getattr(contract, "call_put", "") or getattr(contract, "contract_type", "")).lower()
        oi = getattr(contract, "oi", None)
        if oi is None and isinstance(contract, dict):
            oi = contract.get("oi", contract.get("open_interest", 0))
        oi_value = float(oi or 0)
        if call_put == "call":
            total_call_oi += oi_value
        elif call_put == "put":
            total_put_oi += oi_value

    total_oi = total_call_oi + total_put_oi
    if total_oi == 0:
        return None, None, None

    pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 2.0
    oi_skew = (total_call_oi - total_put_oi) / total_oi
    return pcr, oi_skew, total_oi


def _extract_gamma_flip(state: Any) -> Optional[float]:
    gex = getattr(state, "gex", None)
    if gex is not None:
        flip_level = getattr(gex, "flip_level", None)
        if flip_level:
            return float(flip_level)

    nq_levels = getattr(state, "nq_levels", None)
    if nq_levels is not None:
        gex_flip = getattr(nq_levels, "gex_flip", None)
        if gex_flip:
            return float(gex_flip)

    flashalpha = getattr(state, "flashalpha", None)
    if isinstance(flashalpha, dict):
        levels = flashalpha.get("levels", {}) or {}
        nested_levels = levels.get("levels", {}) if isinstance(levels, dict) else {}
        for candidate in (
            flashalpha.get("flip"),
            levels.get("flip") if isinstance(levels, dict) else None,
            levels.get("gamma_flip") if isinstance(levels, dict) else None,
            nested_levels.get("gamma_flip") if isinstance(nested_levels, dict) else None,
            nested_levels.get("flip") if isinstance(nested_levels, dict) else None,
        ):
            if candidate:
                return float(candidate)

    return None


def _infer_nq_price(state: Any) -> Optional[float]:
    spots = getattr(state, "spots", None)
    if isinstance(spots, dict):
        for key in ("NQ", "NQ1!", "MNQ", "QQQ"):
            value = spots.get(key)
            if value:
                return float(value)

    chain = getattr(state, "chain", None)
    if chain is not None:
        spot_price = getattr(chain, "spot_price", None)
        if spot_price:
            return float(spot_price)

    gex = getattr(state, "gex", None)
    if gex is not None:
        spot = getattr(gex, "spot", None)
        if spot:
            return float(spot)

    return None


def compute_dp_from_options(state: Any) -> DarkPoolLayer:
    """
    Derive institutional flow signal from FlashAlpha zero_dte flow data.
    Reads from _fa_flow_snapshot (updated by background refresher).
    Falls back to nq_atlas AtlasState if unavailable.
    """
    # --- Primary: FlashAlpha flow snapshot (set by fetch_flashalpha_gex) ---
    snap = _fa_flow_snapshot
    if snap:
        pcr = float(snap.get("pc_ratio_oi", 1.0) or 1.0)
        call_oi = float(snap.get("call_oi", 0) or 0)
        put_oi  = float(snap.get("put_oi",  0) or 0)
        total_oi = call_oi + put_oi

        if pcr < 0.9:
            bias: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "BULLISH"
        elif pcr > 1.1:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        confidence = min(1.0, abs(pcr - 1.0) / 0.5)
        return DarkPoolLayer(
            raw_offex_pct=None, dp_vwap=None, total_block_val=total_oi,
            bias=bias, confidence=confidence, stale=False,
        )

    # --- Fallback: nq_atlas AtlasState ---
    try:
        pcr, oi_skew, total_oi = _compute_pcr_oi_metrics(state)
        if pcr is None:
            return DarkPoolLayer(stale=True)
        if pcr < 0.9:
            bias = "BULLISH"
        elif pcr > 1.1:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"
        confidence = min(1.0, abs(pcr - 1.0) / 0.5)
        return DarkPoolLayer(
            raw_offex_pct=None, dp_vwap=None, total_block_val=total_oi,
            bias=bias, confidence=confidence, stale=False,
        )
    except Exception as e:
        LOG.warning("compute_dp_from_options failed: %s", e)
        return DarkPoolLayer(stale=True)


def compute_regime_local(state: Any, nq_price: float) -> RegimeLayer:
    """Derive macro regime from GEX flip + PCR + VIX proxy state."""
    try:
        gamma_flip = _extract_gamma_flip(state)
        if gamma_flip and nq_price > 0:
            expected_move = nq_price * 0.015
            flip_score = max(-1.0, min(1.0, (nq_price - gamma_flip) / expected_move))
        else:
            flip_score = 0.0

        pcr, _, _ = _compute_pcr_oi_metrics(state)
        pcr_score = 0.0
        if pcr is not None:
            pcr_score = max(-1.0, min(1.0, (1.0 - pcr) / 0.5))

        vix_value = None
        spots = getattr(state, "spots", None)
        if isinstance(spots, dict):
            for key in ("VIX", "^VIX"):
                value = spots.get(key)
                if value is not None:
                    vix_value = float(value)
                    break

        vix_score = 0.0
        vol_regime: Literal["LOW", "NORMAL", "ELEVATED", "EXTREME"] = "NORMAL"
        if vix_value is not None:
            if vix_value < 15:
                vol_regime = "LOW"
                vix_score = 0.25
            elif vix_value < 22:
                vol_regime = "NORMAL"
            elif vix_value < 30:
                vol_regime = "ELEVATED"
                vix_score = -0.35
            else:
                vol_regime = "EXTREME"
                vix_score = -0.6

        regime_score = 0.45 * flip_score + 0.35 * pcr_score + 0.20 * vix_score

        if regime_score > 0.3:
            macro: Literal["RISK_ON", "RISK_OFF", "NEUTRAL"] = "RISK_ON"
        elif regime_score < -0.3:
            macro = "RISK_OFF"
        else:
            macro = "NEUTRAL"

        if pcr_score > 0.2:
            pcr_bias: Literal["CALL_HEAVY", "PUT_HEAVY", "NEUTRAL"] = "CALL_HEAVY"
        elif pcr_score < -0.2:
            pcr_bias = "PUT_HEAVY"
        else:
            pcr_bias = "NEUTRAL"

        if abs(flip_score) < 0.15:
            thesis_trend: Literal["BUILDING", "FADING", "FLAT", "BREAKING"] = "FLAT"
        elif flip_score > 0:
            thesis_trend = "BUILDING"
        else:
            thesis_trend = "BREAKING"

        return RegimeLayer(
            macro=macro,
            vol_regime=vol_regime,
            thesis_trend=thesis_trend,
            pcr_bias=pcr_bias,
            stale=False,
            source_ts=_atlas_timestamp_to_iso(getattr(state, "last_chain_ts", None)),
        )
    except Exception as e:
        LOG.warning("compute_regime_local failed: %s", e)
        return RegimeLayer(stale=True)


def compute_composite_neutral() -> CompositeLayer:
    """Neutral composite layer — external composite provider not configured."""
    return CompositeLayer(
        qqq_setup_score=0.0,
        narrative="quantsynth not configured",
        opus_verdict="UNKNOWN",
        stale=True,
    )


# ============================================================
#  CACHED ACCESSORS  (always return cached if not expired)
# ============================================================

async def get_gex(client: httpx.AsyncClient) -> GexLayer:
    cached, stale = await CACHE.get("gex")
    if cached is not None and not stale:
        return cached
    fresh = await fetch_flashalpha_gex(client)
    await CACHE.set("gex", fresh, REFRESH_GEX_SEC)
    return fresh


async def get_darkpool(client: httpx.AsyncClient) -> DarkPoolLayer:
    # Massive TRF (raw flow) refresh
    cached_m, stale_m = await CACHE.get("massive_trf")
    if cached_m is None or stale_m:
        cached_m = await fetch_massive_trf(client)
        await CACHE.set("massive_trf", cached_m, REFRESH_MASSIVE_SEC)

    state = _get_atlas_state()
    cached_local, stale_local = await CACHE.get("dp")
    if cached_local is None or stale_local:
        cached_local = compute_dp_from_options(state)
        await CACHE.set("dp", cached_local, REFRESH_MASSIVE_SEC)

    # stale = only based on local FlashAlpha-derived DP data
    # (Massive TRF endpoint is best-effort; its failure doesn't invalidate the DP signal)
    return DarkPoolLayer(
        raw_offex_pct   = cached_m.get("raw_offex_pct"),
        dp_vwap         = cached_m.get("dp_vwap"),
        total_block_val = cached_local.total_block_val,
        bias            = cached_local.bias,
        confidence      = cached_local.confidence,
        stale           = cached_local.stale,
        source_ts       = cached_local.source_ts or cached_m.get("source_ts"),
    )


async def get_regime(client: httpx.AsyncClient) -> RegimeLayer:
    cached, stale = await CACHE.get("regime")
    if cached is not None and not stale:
        return cached
    state = _get_atlas_state()
    fresh = compute_regime_local(state, _infer_nq_price(state) or 0.0)
    await CACHE.set("regime", fresh, REFRESH_REGIME_SEC)
    return fresh


async def get_composite(client: httpx.AsyncClient) -> CompositeLayer:
    cached, stale = await CACHE.get("composite")
    if cached is not None and not stale:
        return cached
    fresh = compute_composite_neutral()
    await CACHE.set("composite", fresh, REFRESH_SETUP_SEC)
    return fresh


# ============================================================
#  SIGNAL NORMALIZATION + SCORING
# ============================================================

def normalize_gex(gex: GexLayer, price: Optional[float]) -> float:
    """
    Map GEX state to [-1, +1].
      +1 = positive gamma, price below call wall (squeeze setup, dealer hedging buys dips)
      -1 = negative gamma, price above put wall (downside acceleration risk)
       0 = neutral / no data
    """
    if gex.stale or gex.net_gex is None:
        return 0.0

    # Base from net_gex sign
    base = max(-1.0, min(1.0, gex.net_gex / 5e6))   # ~+/-1 at 5M net_gex

    # Price location adjustment
    if price and gex.flip and gex.call_wall and gex.put_wall:
        if price > gex.call_wall:
            base -= 0.3   # above call wall = vol risk, dampen long bias
        elif price < gex.put_wall:
            base += 0.3   # below put wall = oversold, dampen short bias
        elif price > gex.flip:
            base += 0.15  # above flip in positive gamma = stable bullish
        else:
            base -= 0.15  # below flip = negative gamma regime
        base = max(-1.0, min(1.0, base))

    return base


def normalize_dp(dp: DarkPoolLayer, price: Optional[float]) -> float:
    """
    Dark pool signal: combines quantsynth bias (confidence-weighted) with
    Massive raw off-exchange % skew and DP VWAP relative to price.

    +1 = institutional accumulation (DP VWAP below price + bullish bias)
    -1 = institutional distribution (DP VWAP above price + bearish bias)
    """
    if dp.stale:
        return 0.0

    # Component 1: quantsynth bias * confidence
    bias_score = {"BULLISH": 1.0, "BEARISH": -1.0, "NEUTRAL": 0.0}[dp.bias]
    qs_component = bias_score * dp.confidence

    # Component 2: DP VWAP location vs. price (accumulation indicator)
    # If DP VWAP is below price -> insti got fills below market -> bullish
    vwap_component = 0.0
    if price and dp.dp_vwap:
        diff_pct = (price - dp.dp_vwap) / price
        # ~0.5% diff = full +/- signal
        vwap_component = max(-1.0, min(1.0, diff_pct / 0.005))

    # Component 3: raw off-exchange % (high = elevated insti activity, neutral on direction)
    # Used as confidence multiplier, not direction
    activity_mult = 1.0
    if dp.raw_offex_pct is not None:
        # Above 40% off-ex = strong insti footprint, amplify signal
        activity_mult = 0.8 + min(0.4, dp.raw_offex_pct - 0.30)  # 0.8 .. 1.2 range

    fused = 0.6 * qs_component + 0.4 * vwap_component
    fused *= activity_mult
    return max(-1.0, min(1.0, fused))


def normalize_regime(regime: RegimeLayer) -> float:
    """Macro regime signal to [-1, +1]."""
    if regime.stale:
        return 0.0

    macro = {"RISK_ON": 0.8, "RISK_OFF": -0.8, "NEUTRAL": 0.0}[regime.macro]

    # Vol regime as risk dampener
    vol_mult = {"LOW": 1.0, "NORMAL": 1.0, "ELEVATED": 0.7, "EXTREME": 0.4}[regime.vol_regime]

    # Thesis trend tilt
    trend_adj = {"BUILDING": 0.15, "FADING": -0.15, "FLAT": 0.0, "BREAKING": -0.25}[regime.thesis_trend]

    # PCR overlay
    pcr_adj = {"CALL_HEAVY": 0.1, "PUT_HEAVY": -0.1, "NEUTRAL": 0.0}[regime.pcr_bias]

    score = (macro + trend_adj + pcr_adj) * vol_mult
    return max(-1.0, min(1.0, score))


def normalize_mtf(mtf: MtfLayer) -> float:
    """
    MTF Premium/Discount signal to [-1, +1].
    Premium = -1 (mean revert short bias), Discount = +1 (long bias), Eq = 0.
    Weighted: Daily 50%, 4H 30%, Chart 20%.
    """
    weights = {"daily": 0.50, "h4": 0.30, "chart": 0.20}
    zone_map = {"PREMIUM": -1.0, "EQUILIBRIUM": 0.0, "DISCOUNT": 1.0, "UNKNOWN": 0.0}

    score = (
        weights["daily"] * zone_map[mtf.daily] +
        weights["h4"]    * zone_map[mtf.h4] +
        weights["chart"] * zone_map[mtf.chart]
    )
    return score


def fuse(dp_s: float, gex_s: float, regime_s: float, mtf_s: float) -> int:
    """Fuse signals -> integer confluence score in [-5, +5]."""
    raw = W_DP * dp_s + W_GEX * gex_s + W_REGIME * regime_s + W_MTF * mtf_s
    scaled = round(raw * 5)
    return max(-5, min(5, int(scaled)))


def detect_alert(
    score: int,
    gex: GexLayer,
    dp: DarkPoolLayer,
    regime: RegimeLayer,
    composite: CompositeLayer,
    mtf: MtfLayer,
    price: Optional[float],
) -> tuple[Optional[str], Optional[str]]:
    """
    Conflict + conviction alert engine.
    Returns (alert_code, human_reason) or (None, None).
    """
    # CONFLICT ALERTS (highest priority -- counter-trend warnings)
    if (gex.bias == "BULLISH" and dp.bias == "BEARISH" and
        dp.confidence > 0.5 and mtf.daily == "PREMIUM"):
        return ("STOP_BUYING",
                "GEX bullish BUT premium zone + dark pool selling")

    if (gex.bias == "BEARISH" and dp.bias == "BULLISH" and
        dp.confidence > 0.5 and mtf.daily == "DISCOUNT"):
        return ("STOP_SELLING",
                "GEX bearish BUT discount zone + dark pool accumulation")

    # REGIME DIVERGENCE
    if composite.qqq_setup_score >= 7.0 and composite.opus_verdict == "BEAR" and score > 1:
        return ("REGIME_DIVERGENCE",
                f"Opus BEAR (score {composite.qqq_setup_score:.1f}) vs local confluence +{score}")
    if composite.qqq_setup_score >= 7.0 and composite.opus_verdict == "BULL" and score < -1:
        return ("REGIME_DIVERGENCE",
                f"Opus BULL (score {composite.qqq_setup_score:.1f}) vs local confluence {score}")

    # FULL CONVICTION ALIGNMENT
    if score >= 3 and gex.bias == "BULLISH" and dp.bias == "BULLISH" and regime.macro == "RISK_ON":
        return ("FULL_SEND_LONG", "All 4 layers aligned bullish")
    if score <= -3 and gex.bias == "BEARISH" and dp.bias == "BEARISH" and regime.macro == "RISK_OFF":
        return ("FULL_SEND_SHORT", "All 4 layers aligned bearish")

    # STAND DOWN (low conviction)
    if abs(score) == 0 and regime.macro == "NEUTRAL":
        return ("STAND_DOWN", "Zero confluence + neutral regime -- no edge")

    return (None, None)


# ============================================================
#  FASTAPI APP
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    LOG.info("Confluence server starting | weights DP=%.2f GEX=%.2f REG=%.2f MTF=%.2f",
             W_DP, W_GEX, W_REGIME, W_MTF)
    app.state.http = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC)
    app.state.refresh_task = asyncio.create_task(background_refresher(app.state.http))
    try:
        yield
    finally:
        app.state.refresh_task.cancel()
        await app.state.http.aclose()
        LOG.info("Confluence server shutdown complete")


async def background_refresher(client: httpx.AsyncClient) -> None:
    """
    Proactively refresh caches before TTL expiry so NT8 always gets warm data.
    Runs forever; gets cancelled in lifespan teardown.
    """
    LOG.info("Background refresher started")
    tick = 0
    while True:
        try:
            state = _get_atlas_state()
            nq_price = _infer_nq_price(state) or 0.0
            # Stagger refreshes -- not everything every cycle
            if tick % max(1, REFRESH_MASSIVE_SEC // 15) == 0:
                await CACHE.set("massive_trf", await fetch_massive_trf(client), REFRESH_MASSIVE_SEC)
                await CACHE.set("dp", compute_dp_from_options(state), REFRESH_MASSIVE_SEC)
            if tick % max(1, REFRESH_GEX_SEC // 15) == 0:
                await CACHE.set("gex", await fetch_flashalpha_gex(client), REFRESH_GEX_SEC)
            if tick % max(1, REFRESH_SETUP_SEC // 15) == 0:
                await CACHE.set("composite", compute_composite_neutral(), REFRESH_SETUP_SEC)
            if tick % max(1, REFRESH_REGIME_SEC // 15) == 0:
                await CACHE.set("regime", compute_regime_local(state, nq_price), REFRESH_REGIME_SEC)
        except Exception as e:
            LOG.exception("Background refresh error: %s", e)
        await asyncio.sleep(15)
        tick += 1


app = FastAPI(
    title="Institutional Confluence Middleware",
    version="1.0.0",
    description="Aggregates GEX + Dark Pool + Macro for DEEP6 ATLAS / NT8",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
#  ENDPOINTS
# ============================================================

@app.get("/confluence/nq", response_model=UnifiedPayload)
async def confluence_nq(
    price:     Optional[float] = Query(None, description="Current NQ price from NT8"),
    mtf_d:     Optional[str]   = Query(None, description="Daily MTF zone"),
    mtf_4h:    Optional[str]   = Query(None, description="4H MTF zone"),
    mtf_chart: Optional[str]   = Query(None, description="Chart MTF zone"),
) -> UnifiedPayload:
    """
    Main NT8 endpoint. Returns unified institutional confluence payload.

    Query params:
      price     = current NQ last price (used for GEX/DP location scoring)
      mtf_d     = "PREMIUM" | "EQUILIBRIUM" | "DISCOUNT" (Daily TF zone, NT8-calculated)
      mtf_4h    = same (4H)
      mtf_chart = same (Chart TF)
    """
    global _last_nq_price
    if price is not None and price > 1000:
        _last_nq_price = price

    client: httpx.AsyncClient = app.state.http

    # Fan out (sequential here since cached; concurrent fetch already done in background)
    gex       = await get_gex(client)
    darkpool  = await get_darkpool(client)
    regime    = await get_regime(client)
    composite = await get_composite(client)

    # Sanitize MTF inputs
    def _z(s: Optional[str]) -> str:
        if not s:
            return "UNKNOWN"
        s = s.upper()
        return s if s in ("PREMIUM", "EQUILIBRIUM", "DISCOUNT") else "UNKNOWN"

    mtf = MtfLayer(daily=_z(mtf_d), h4=_z(mtf_4h), chart=_z(mtf_chart))

    # Normalize signals
    dp_s     = normalize_dp(darkpool, price)
    gex_s    = normalize_gex(gex, price)
    regime_s = normalize_regime(regime)
    mtf_s    = normalize_mtf(mtf)

    # Fuse
    score = fuse(dp_s, gex_s, regime_s, mtf_s)

    # Alerts
    alert_code, alert_reason = detect_alert(
        score, gex, darkpool, regime, composite, mtf, price
    )

    return UnifiedPayload(
        ts        = datetime.now(timezone.utc).isoformat(),
        symbol    = "NQ",
        price     = price,
        gex       = gex,
        darkpool  = darkpool,
        regime    = regime,
        composite = composite,
        mtf       = mtf,
        dp_signal        = round(dp_s,     3),
        gex_signal       = round(gex_s,    3),
        regime_signal    = round(regime_s, 3),
        mtf_signal       = round(mtf_s,    3),
        confluence_score = score,
        alert            = alert_code,
        alert_reason     = alert_reason,
    )


@app.get("/confluence/nq/raw")
async def confluence_nq_raw() -> dict:
    """Returns all raw layer data without scoring. For debugging / manual review."""
    client: httpx.AsyncClient = app.state.http
    return {
        "gex":       (await get_gex(client)).model_dump(),
        "darkpool":  (await get_darkpool(client)).model_dump(),
        "regime":    (await get_regime(client)).model_dump(),
        "composite": (await get_composite(client)).model_dump(),
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


@app.get("/status")
async def status() -> dict:
    """Cache freshness per source. Used by NT8 'STALE' badge logic."""
    return {
        "cache_age_seconds": {
            "gex":        await CACHE.age("gex"),
            "massive":    await CACHE.age("massive_trf"),
            "dp":         await CACHE.age("dp"),
            "regime":     await CACHE.age("regime"),
            "composite":  await CACHE.age("composite"),
            "equilibrium": await CACHE.age("equilibrium"),
        },
        "ttl_seconds": {
            "gex":        REFRESH_GEX_SEC,
            "massive":    REFRESH_MASSIVE_SEC,
            "dp":         REFRESH_MASSIVE_SEC,
            "regime":     REFRESH_REGIME_SEC,
            "composite":  REFRESH_SETUP_SEC,
        },
        "weights": {"dp": W_DP, "gex": W_GEX, "regime": W_REGIME, "mtf": W_MTF},
        "ts": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================
#  EQUILIBRIUM MODEL ENDPOINT (Phase 5 extension)
# ============================================================

EQUILIBRIUM_TTL_SEC = int(os.getenv("REFRESH_EQUILIBRIUM_SEC", 60))


@app.get("/equilibrium/nq", response_model=EquilibriumPayload)
async def equilibrium_nq(
    price:    float          = Query(..., description="Current NQ futures price"),
    ndx:      Optional[float] = Query(None, description="Current NDX spot price"),
    rv5:      Optional[float] = Query(None, description="Realized vol 5d (daily, decimal)"),
    rv30:     Optional[float] = Query(None, description="Realized vol 30d (daily, decimal)"),
    iv_atm:   Optional[float] = Query(None, description="ATM IV (annualized, decimal)"),
    ema20:    Optional[float] = Query(None, description="NQ 20-period EMA"),
    ema50:    Optional[float] = Query(None, description="NQ 50-period EMA"),
) -> EquilibriumPayload:
    """
    Weekly + Daily GEX Synthetic Equilibrium Model for NQ.

    NT8 EquilibriumModel.cs indicator polls this every 60s, posting NQ price,
    NDX spot, and locally-computed realized vol + EMAs.

    Returns:
      - SFV (Synthetic Fair Value) target price
      - Premium / Equilibrium / Discount band edges (volatility-adjusted)
      - 4-regime classification (Gamma / Vol / Trend / Institutional Bias)
      - 3-tier alerts (CRITICAL / WARNING / INFO)
      - Strike-level GEX histograms for Weekly + Daily
    """
    client: httpx.AsyncClient = app.state.http

    # Cache by NQ price bucket (avoid re-fetching chain every poll if price moves <0.1%)
    ndx_bucket = round(ndx, 0) if ndx is not None else 0
    cache_key = f"equilibrium:{round(price, 0)}:{ndx_bucket}"
    cached, stale = await CACHE.get(cache_key)
    if cached is not None and not stale:
        return cached

    inputs = EquilibriumInputs(
        nq_price         = price,
        ndx_price        = ndx,
        realized_vol_5d  = rv5,
        realized_vol_30d = rv30,
        implied_vol_atm  = iv_atm,
        ema20_nq         = ema20,
        ema50_nq         = ema50,
    )

    payload = await compute_equilibrium(client, inputs)

    # Fallback: if options chain gave no SFV, derive from FlashAlpha GEX levels
    if payload.sfv is None:
        gex_layer, _ = await CACHE.get("gex")
        if gex_layer and not gex_layer.stale and gex_layer.flip:
            # SFV ≈ weighted blend of GEX levels (all already in NQ price space)
            flip      = gex_layer.flip
            call_wall = gex_layer.call_wall or flip
            put_wall  = gex_layer.put_wall  or flip
            hvl       = gex_layer.hvl       or flip
            sfv_fa = 0.50 * flip + 0.35 * ((call_wall + put_wall) / 2.0) + 0.15 * hvl
            sigma_pts = abs(call_wall - put_wall) / 2.0 if call_wall and put_wall else price * 0.005
            payload.sfv             = round(sfv_fa, 2)
            payload.sfv_components  = {"weekly_zg": flip, "daily_zg": (call_wall+put_wall)/2, "hvl": hvl}
            payload.sigma_points    = round(sigma_pts, 2)
            payload.upper_premium   = round(sfv_fa + 1.5 * sigma_pts, 2)
            payload.lower_discount  = round(sfv_fa - 1.5 * sigma_pts, 2)
            payload.extreme_upper   = round(sfv_fa + 2.5 * sigma_pts, 2)
            payload.extreme_lower   = round(sfv_fa - 2.5 * sigma_pts, 2)
            dist = price - sfv_fa
            payload.distance_to_sfv = round(dist, 2)
            if price >= payload.upper_premium:
                payload.current_zone = "PREMIUM"
            elif price <= payload.lower_discount:
                payload.current_zone = "DISCOUNT"
            else:
                payload.current_zone = "EQUILIBRIUM"
            LOG.info("SFV fallback from FlashAlpha: sfv=%.2f zone=%s", sfv_fa, payload.current_zone)

    await CACHE.set(cache_key, payload, EQUILIBRIUM_TTL_SEC)
    await CACHE.set("equilibrium", payload, EQUILIBRIUM_TTL_SEC)   # alias for /status
    return payload


@app.get("/equilibrium/nq/last")
async def equilibrium_nq_last() -> Optional[dict]:
    """Returns the most recent equilibrium payload (any price bucket). For debug."""
    payload, _ = await CACHE.get("equilibrium")
    return payload.model_dump() if payload else None


# ============================================================
#  ENTRY POINT
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "confluence_system.confluence_server:app",
        host="127.0.0.1",
        port=int(os.getenv("CONFLUENCE_PORT", "8767")),
        reload=False,
        log_level="info",
    )
