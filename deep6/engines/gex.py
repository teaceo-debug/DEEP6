"""GEX (Gamma Exposure) calculator from options chain data.

Computes institutional-grade GEX levels from raw options chain:
- Call wall (largest call OI × gamma strike)
- Put wall (largest put OI × gamma strike)
- Gamma flip level (net GEX crosses zero)
- HVL (High Volatility Level — peak absolute GEX)
- GEX regime (positive = mean-reverting, negative = amplifying)

Data source: Massive.com / Polygon-compatible API
Proxy: QQQ options → NQ futures (standard industry approach)

Per GEX-01..06: ingestion, display, regime classification,
signal weighting modification, confluence scoring, staleness handling.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import numpy as np
import requests

from deep6.engines.signal_config import GexConfig


class GexRegime(Enum):
    POSITIVE_DAMPENING = auto()   # Above gamma flip — mean-reverting, favor fading
    NEGATIVE_AMPLIFYING = auto()  # Below gamma flip — trending, favor momentum
    NEUTRAL = auto()


@dataclass
class GexLevels:
    """Computed GEX levels for the current session."""
    call_wall: float = 0.0          # Strike with largest call gamma × OI
    put_wall: float = 0.0           # Strike with largest put gamma × OI
    gamma_flip: float = 0.0         # Price where net GEX crosses zero
    hvl: float = 0.0                # High volatility level (peak |GEX|)
    # D-28 (Phase 15): peak raw call γ × OI strike BEFORE put netting.
    # Distinct from ``hvl`` (peak |net GEX|). Consumed by CR-04 (Pin Regime).
    largest_gamma_strike: float = 0.0
    regime: GexRegime = GexRegime.NEUTRAL
    net_gex_at_spot: float = 0.0    # Net GEX value at current spot price
    timestamp: float = 0.0          # When levels were last computed
    stale: bool = False             # True if data > staleness threshold
    strikes: dict[float, float] = field(default_factory=dict)  # strike → net GEX

    def age_seconds(self, now: float | None = None) -> float:
        # Phase 13-01: accept an optional ``now`` override so replay can pass
        # ``state.clock.now()``. Default remains ``time.time()`` — live
        # callers are unchanged.
        ref = now if now is not None else time.time()  # live-only fallback
        return ref - self.timestamp if self.timestamp > 0 else float('inf')

    @property
    def zero_gamma(self) -> float:
        """D-29 alias: ``zero_gamma`` ≡ ``gamma_flip``.

        Naming alias only — no separate computation. Downstream confluence
        rules may address ZERO_GAMMA as a distinct LevelKind so the API
        layer stays explicit about intent, but the price is the same
        interpolated zero-net-GEX strike.
        """
        return self.gamma_flip


@dataclass
class GexSignal:
    """GEX-derived signal for confluence scoring."""
    regime: GexRegime
    direction: int              # +1 if positive gamma (fade), -1 if negative (trend)
    call_wall: float
    put_wall: float
    gamma_flip: float
    near_call_wall: bool        # Price within 0.5% of call wall
    near_put_wall: bool         # Price within 0.5% of put wall
    strength: float             # 0-1
    detail: str


class GexEngine:
    """Fetches options chain and computes GEX levels.

    Uses Massive.com (Polygon-compatible) API for QQQ options chain.
    QQQ is the standard NQ proxy at retail price points.
    """

    def __init__(
        self,
        api_key: str,
        config: GexConfig | None = None,
        base_url: str = "https://api.polygon.io",
        underlying: str | None = None,
        staleness_seconds: float | None = None,
        spot_price: float = 0.0,
    ):
        self.config = config or GexConfig()
        self.api_key = api_key
        self.base_url = base_url
        # Legacy kwargs override config (backward compat)
        self.staleness_seconds = staleness_seconds if staleness_seconds is not None else self.config.staleness_seconds
        self.underlying = underlying if underlying is not None else self.config.underlying
        self._levels: Optional[GexLevels] = None
        self._last_fetch: float = 0.0

    def fetch_and_compute(self, spot_price: float) -> GexLevels:
        """Fetch options chain snapshot and compute GEX levels.

        Args:
            spot_price: Current underlying price (QQQ spot, not NQ)

        Returns:
            GexLevels with all computed values
        """
        try:
            chain = self._fetch_options_chain(spot_price)
            if not chain:
                return self._empty_levels()

            levels = self._compute_gex(chain, spot_price)
            self._levels = levels
            self._last_fetch = time.time()
            return levels

        except Exception as e:
            # Return stale levels if available, otherwise empty
            if self._levels:
                self._levels.stale = True
                return self._levels
            return self._empty_levels()

    def get_signal(self, nq_price: float) -> GexSignal:
        """Get GEX signal for current NQ price.

        Converts NQ price to approximate QQQ equivalent for level comparison.
        NQ ≈ QQQ × 40 (rough approximation — NQ is 100× NDX, QQQ tracks NDX)
        """
        if self._levels is None or self._levels.stale:
            return GexSignal(
                GexRegime.NEUTRAL, 0, 0, 0, 0, False, False, 0,
                "GEX: no data or stale",
            )

        levels = self._levels

        # Check staleness
        if levels.age_seconds() > self.staleness_seconds:
            levels.stale = True
            return GexSignal(GexRegime.NEUTRAL, 0, 0, 0, 0, False, False, 0, "GEX: stale data")

        # QQQ proxy price (approximate)
        qqq_approx = nq_price / self.config.nq_to_qqq_divisor

        # Near wall detection (within near_wall_pct)
        near_call = abs(qqq_approx - levels.call_wall) / levels.call_wall < self.config.near_wall_pct if levels.call_wall > 0 else False
        near_put = abs(qqq_approx - levels.put_wall) / levels.put_wall < self.config.near_wall_pct if levels.put_wall > 0 else False

        # Regime determines direction preference
        if levels.regime == GexRegime.POSITIVE_DAMPENING:
            direction = +1  # Mean-reverting — favor fading/absorption
            detail = f"GEX POSITIVE — dampening regime, favor absorption signals"
        elif levels.regime == GexRegime.NEGATIVE_AMPLIFYING:
            direction = -1  # Trending — favor momentum
            detail = f"GEX NEGATIVE — amplifying regime, favor momentum signals"
        else:
            direction = 0
            detail = "GEX NEUTRAL"

        if near_call:
            detail += f" | AT CALL WALL {levels.call_wall:.2f}"
        if near_put:
            detail += f" | AT PUT WALL {levels.put_wall:.2f}"

        strength = 0.0
        if levels.net_gex_at_spot != 0:
            strength = min(abs(levels.net_gex_at_spot) / self.config.gex_normalize_divisor, 1.0)  # Normalize

        return GexSignal(
            regime=levels.regime,
            direction=direction,
            call_wall=levels.call_wall,
            put_wall=levels.put_wall,
            gamma_flip=levels.gamma_flip,
            near_call_wall=near_call,
            near_put_wall=near_put,
            strength=strength,
            detail=detail,
        )

    def _fetch_options_chain(self, spot_price: float) -> list[dict]:
        """Fetch QQQ options chain snapshot from Massive/Polygon API."""
        url = f"{self.base_url}/v3/snapshot/options/{self.underlying}"
        params = {
            "apiKey": self.api_key,
            "limit": 250,
            "strike_price.gte": spot_price * 0.90,
            "strike_price.lte": spot_price * 1.10,
        }

        all_contracts = []
        while url:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code != 200:
                return []
            data = r.json()
            all_contracts.extend(data.get("results", []))
            # T-05-02: Guard against infinite pagination from malformed next_url
            if len(all_contracts) > 10000:
                break
            url = data.get("next_url")
            params = {"apiKey": self.api_key}  # next_url has other params built in

        return all_contracts

    def _compute_gex(self, chain: list[dict], spot: float) -> GexLevels:
        """Compute GEX levels from options chain snapshot.

        GEX per strike = gamma × open_interest × 100 × spot²
        Call GEX is positive (dealers long gamma → dampening)
        Put GEX is negative (dealers short gamma → amplifying)
        Net GEX = sum of all call GEX + put GEX
        """
        strike_gex: dict[float, float] = {}
        max_call_gex = 0.0
        max_call_strike = 0.0
        max_put_gex = 0.0
        max_put_strike = 0.0

        for contract in chain:
            details = contract.get("details", {})
            greeks = contract.get("greeks", {})
            day = contract.get("day", {})

            strike = details.get("strike_price", 0)
            contract_type = details.get("contract_type", "")
            gamma = greeks.get("gamma", 0)
            oi = contract.get("open_interest", 0) or day.get("open_interest", 0)

            if strike == 0 or gamma == 0 or oi == 0:
                continue

            # GEX = gamma × OI × 100 (shares per contract) × spot²
            gex = gamma * oi * 100 * spot * spot

            if contract_type == "call":
                # Dealers are long calls → positive gamma → dampening
                strike_gex[strike] = strike_gex.get(strike, 0) + gex
                if gex > max_call_gex:
                    max_call_gex = gex
                    max_call_strike = strike
            elif contract_type == "put":
                # Dealers are short puts → negative gamma → amplifying
                strike_gex[strike] = strike_gex.get(strike, 0) - gex
                if gex > max_put_gex:
                    max_put_gex = gex
                    max_put_strike = strike

        if not strike_gex:
            return self._empty_levels()

        # Find gamma flip (where net GEX crosses zero)
        sorted_strikes = sorted(strike_gex.keys())
        gamma_flip = spot  # Default to spot
        sign_change_found = False
        for i in range(len(sorted_strikes) - 1):
            s1, s2 = sorted_strikes[i], sorted_strikes[i + 1]
            g1, g2 = strike_gex[s1], strike_gex[s2]
            if g1 * g2 < 0:  # Sign change
                # Linear interpolation
                gamma_flip = s1 + (s2 - s1) * abs(g1) / (abs(g1) + abs(g2))
                sign_change_found = True
                break

        # HVL: strike with highest absolute GEX
        hvl_strike = max(strike_gex, key=lambda s: abs(strike_gex[s]))

        # Net GEX at spot
        closest_strike = min(sorted_strikes, key=lambda s: abs(s - spot))
        net_gex_at_spot = strike_gex.get(closest_strike, 0)

        # Regime
        if not sign_change_found:
            regime = GexRegime.NEUTRAL
        else:
            regime = GexRegime.POSITIVE_DAMPENING if spot > gamma_flip else GexRegime.NEGATIVE_AMPLIFYING

        return GexLevels(
            call_wall=max_call_strike,
            put_wall=max_put_strike,
            gamma_flip=gamma_flip,
            hvl=hvl_strike,
            regime=regime,
            net_gex_at_spot=net_gex_at_spot,
            timestamp=time.time(),
            stale=False,
            strikes=strike_gex,
        )

    def _empty_levels(self) -> GexLevels:
        return GexLevels(stale=True)


def create_gex_engine(api_key: str) -> GexEngine:
    """Factory for GEX engine with Massive.com API."""
    return GexEngine(api_key=api_key)
