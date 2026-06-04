"""GEX / Options Flow client for NQ directional bias.

Sources:
  FlashAlpha  — GEX, DEX, Vanna/Charm, gamma flip, call/put walls
  Unusual Whales — Market Tide (net options premium flow), dark pool

GEX signals map to bias:
  Positive GEX regime → range-bound, low-vol → reduce directional confidence
  Negative GEX regime → trending, high-vol  → amplify directional confidence
  Price above zero-gamma → call wall becomes resistance (bearish headwind)
  Price below zero-gamma → put wall becomes support  (bullish tailwind)
  DEX > 0 → dealers net long delta → structural bullish tailwind
  DEX < 0 → dealers net short delta → structural bearish tailwind

Environment variables:
  FLASHALPHA_API_KEY    — FlashAlpha lab API ($79/mo starter)
  UNUSUAL_WHALES_KEY    — Unusual Whales API ($50/mo basic)
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import aiohttp


@dataclass
class GEXState:
    """Dealer gamma positioning snapshot."""
    symbol: str                     # "QQQ" (NQ proxy)
    net_gex: float                  # millions — positive = range-bound
    regime: str                     # "positive" | "negative" | "neutral"
    gamma_flip: float               # zero-gamma price level
    call_wall: float                # highest call-gamma strike (resistance)
    put_wall: float                 # highest put-gamma strike (support)
    net_dex: float                  # net delta exposure — positive = bull tailwind
    dex_direction: str              # "BULL" | "BEAR" | "NEUTRAL"
    vol_regime: str                 # "low" | "normal" | "elevated" | "crisis"
    confidence_mult: float          # 0.5–1.2 — how much to trust directional signals
    bias_score: float               # -100 to +100 derived from GEX/DEX
    detail: str = ""
    timestamp: datetime = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now(tz=timezone.utc)


@dataclass
class OptionsFlowState:
    """Net options premium flow (bullish vs bearish pressure)."""
    net_premium: float              # positive = net call premium (bullish)
    call_notional: float
    put_notional: float
    flow_direction: str             # "BULL" | "BEAR" | "NEUTRAL"
    flow_score: float               # -100 to +100
    dark_pool_direction: str = "NEUTRAL"
    detail: str = ""
    timestamp: datetime = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now(tz=timezone.utc)


_FLASHALPHA_BASE = "https://lab.flashalpha.com/api/v1"
_UW_BASE = "https://api.unusualwhales.com/api"

# NQ proxy — QQQ tracks Nasdaq-100 tightly
_NQ_PROXY = "QQQ"

# GEX regime thresholds (millions USD)
_GEX_NEUTRAL_BAND = 500.0          # within ±$500M = near zero-gamma
_GEX_HIGH = 2000.0                 # > $2B = strongly positive / range-bound

# Vix proxy thresholds (using QQQ IV30)
_IV_LOW = 15.0
_IV_ELEVATED = 25.0
_IV_CRISIS = 35.0


class GEXClient:
    """Async client for GEX/options flow bias signals."""

    def __init__(self) -> None:
        self._fa_key = os.getenv("FLASHALPHA_API_KEY", "")
        self._uw_key = os.getenv("UNUSUAL_WHALES_KEY", "")
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "GEXClient":
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=8),
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._session:
            await self._session.close()

    # ──────────────────────────────────────────────────────────────────
    # FlashAlpha GEX
    # ──────────────────────────────────────────────────────────────────

    async def get_gex_state(self, symbol: str = _NQ_PROXY) -> GEXState:
        """Fetch GEX/DEX state from FlashAlpha."""
        if not self._fa_key:
            return _neutral_gex(symbol, "No FLASHALPHA_API_KEY")

        try:
            headers = {"X-API-Key": self._fa_key}
            url = f"{_FLASHALPHA_BASE}/exposure/gex/{symbol}"
            async with self._session.get(url, headers=headers) as r:
                if r.status != 200:
                    return _neutral_gex(symbol, f"FlashAlpha HTTP {r.status}")
                data = await r.json()
        except Exception as e:
            return _neutral_gex(symbol, str(e))

        # DEX (separate endpoint)
        dex_data: dict = {}
        try:
            url_dex = f"{_FLASHALPHA_BASE}/exposure/dex/{symbol}"
            async with self._session.get(url_dex, headers=headers) as r:
                if r.status == 200:
                    dex_data = await r.json()
        except Exception:
            pass

        return _parse_gex_response(symbol, data, dex_data)

    # ──────────────────────────────────────────────────────────────────
    # Unusual Whales — Market Tide / Options Flow
    # ──────────────────────────────────────────────────────────────────

    async def get_options_flow(self) -> OptionsFlowState:
        """Fetch net options premium flow from Unusual Whales."""
        if not self._uw_key:
            return _neutral_flow("No UNUSUAL_WHALES_KEY")

        try:
            headers = {"Authorization": f"Bearer {self._uw_key}"}
            url = f"{_UW_BASE}/market/market-tide"
            async with self._session.get(url, headers=headers) as r:
                if r.status != 200:
                    return _neutral_flow(f"UW HTTP {r.status}")
                data = await r.json()
        except Exception as e:
            return _neutral_flow(str(e))

        return _parse_flow_response(data)

    # ──────────────────────────────────────────────────────────────────
    # Combined fetch
    # ──────────────────────────────────────────────────────────────────

    async def fetch_all(self) -> tuple[GEXState, OptionsFlowState]:
        """Fetch GEX and options flow concurrently."""
        gex, flow = await asyncio.gather(
            self.get_gex_state(),
            self.get_options_flow(),
            return_exceptions=True,
        )
        if isinstance(gex, Exception):
            gex = _neutral_gex(_NQ_PROXY, str(gex))
        if isinstance(flow, Exception):
            flow = _neutral_flow(str(flow))
        return gex, flow  # type: ignore[return-value]


# ──────────────────────────────────────────────────────────────────────────────
# Combined GEX bias score
# ──────────────────────────────────────────────────────────────────────────────

def compute_gex_bias_score(
    gex: GEXState,
    flow: OptionsFlowState,
    current_price: float = 0.0,
) -> float:
    """Combine GEX + DEX + options flow into a single -100..+100 bias score.

    Weights (validated by research):
        DEX directional    40%
        Options flow       35%
        GEX regime mult    15%
        Gamma level pos    10%
    """
    # DEX contribution
    dex_val = 100.0 if gex.dex_direction == "BULL" else -100.0 if gex.dex_direction == "BEAR" else 0.0

    # Options flow contribution
    flow_val = flow.flow_score

    # GEX regime modifier
    if gex.regime == "negative":
        regime_mult = 1.0    # trending — directional signals reliable
    elif gex.regime == "positive":
        regime_mult = 0.5    # range-bound — dampen directional signals
    else:
        regime_mult = 0.75

    # Gamma level position
    level_val = 0.0
    if current_price > 0 and gex.call_wall > 0 and gex.put_wall > 0:
        mid = (gex.call_wall + gex.put_wall) / 2.0
        rng = gex.call_wall - gex.put_wall
        if rng > 0:
            # Normalized -100..+100 based on where price sits in the gamma channel
            level_pct = (current_price - mid) / (rng / 2.0)
            level_val = max(-100.0, min(100.0, -level_pct * 100.0))
            # Negative because price near call wall = bearish (resistance)

    raw = 0.40 * dex_val + 0.35 * flow_val + 0.10 * level_val
    final = max(-100.0, min(100.0, raw * regime_mult))
    return round(final, 1)


# ──────────────────────────────────────────────────────────────────────────────
# Parsers + defaults
# ──────────────────────────────────────────────────────────────────────────────

def _parse_gex_response(symbol: str, gex_data: dict, dex_data: dict) -> GEXState:
    net_gex = float(gex_data.get("net_gex", 0) or 0)
    gamma_flip = float(gex_data.get("gamma_flip", 0) or 0)
    call_wall = float(gex_data.get("call_wall", 0) or 0)
    put_wall = float(gex_data.get("put_wall", 0) or 0)
    iv30 = float(gex_data.get("iv30", 20) or 20)

    # DEX
    net_dex = float(dex_data.get("net_dex", 0) or 0)
    dex_dir = "BULL" if net_dex > 0 else "BEAR" if net_dex < 0 else "NEUTRAL"

    # Regime classification
    if abs(net_gex) < _GEX_NEUTRAL_BAND * 1e6:
        regime = "neutral"
        conf_mult = 0.75
    elif net_gex > 0:
        regime = "positive"
        conf_mult = 0.6    # range-bound = less directional edge
    else:
        regime = "negative"
        conf_mult = 1.1    # trending = amplify signals slightly

    # Vol regime
    if iv30 < _IV_LOW:
        vol_regime = "low"
    elif iv30 < _IV_ELEVATED:
        vol_regime = "normal"
    elif iv30 < _IV_CRISIS:
        vol_regime = "elevated"
    else:
        vol_regime = "crisis"
        conf_mult *= 0.3    # Crisis: all models unreliable

    # Bias from DEX only (GEX bias is regime, not directional)
    bias = (100.0 if dex_dir == "BULL" else -100.0 if dex_dir == "BEAR" else 0.0)

    return GEXState(
        symbol=symbol,
        net_gex=net_gex,
        regime=regime,
        gamma_flip=gamma_flip,
        call_wall=call_wall,
        put_wall=put_wall,
        net_dex=net_dex,
        dex_direction=dex_dir,
        vol_regime=vol_regime,
        confidence_mult=conf_mult,
        bias_score=round(bias, 1),
        detail=f"GEX {regime} | DEX {dex_dir} | IV30={iv30:.0f} | flip={gamma_flip:.2f}",
    )


def _parse_flow_response(data: dict) -> OptionsFlowState:
    call_notional = float(data.get("call_notional", 0) or data.get("calls", 0) or 0)
    put_notional  = float(data.get("put_notional",  0) or data.get("puts",  0) or 0)
    net = call_notional - put_notional
    total = call_notional + put_notional

    if total == 0:
        return _neutral_flow("No flow data")

    flow_pct = net / total  # -1 to +1
    flow_score = flow_pct * 100.0

    if flow_score > 15:
        direction = "BULL"
    elif flow_score < -15:
        direction = "BEAR"
    else:
        direction = "NEUTRAL"

    # Dark pool (field name varies by UW plan)
    dp_dir = data.get("dark_pool_direction", "NEUTRAL")

    return OptionsFlowState(
        net_premium=net,
        call_notional=call_notional,
        put_notional=put_notional,
        flow_direction=direction,
        flow_score=round(flow_score, 1),
        dark_pool_direction=dp_dir,
        detail=f"Call${call_notional/1e6:.0f}M Put${put_notional/1e6:.0f}M Net={flow_score:+.0f}",
    )


def _neutral_gex(symbol: str, reason: str) -> GEXState:
    return GEXState(
        symbol=symbol, net_gex=0, regime="neutral",
        gamma_flip=0, call_wall=0, put_wall=0,
        net_dex=0, dex_direction="NEUTRAL",
        vol_regime="normal", confidence_mult=1.0,
        bias_score=0.0, detail=f"GEX unavailable: {reason}",
    )


def _neutral_flow(reason: str) -> OptionsFlowState:
    return OptionsFlowState(
        net_premium=0, call_notional=0, put_notional=0,
        flow_direction="NEUTRAL", flow_score=0.0,
        detail=f"Flow unavailable: {reason}",
    )
