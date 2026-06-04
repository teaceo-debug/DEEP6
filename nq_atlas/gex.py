from __future__ import annotations

from datetime import date
from typing import Optional

from nq_atlas.types import ChainSnapshot, GEXResult, OptionsContract


GEX_SCALE = 100 * 0.001


class GEXEngine:
    """Compute gamma exposure metrics from a QQQ options chain snapshot."""

    def compute(self, chain: ChainSnapshot) -> GEXResult:
        """Compute net GEX, flip level, walls, and expiry buckets."""
        spot = chain.spot_price
        gex_by_strike: dict[float, float] = {}
        total_gex = 0.0

        for contract in chain.contracts:
            contract_gex = self._contract_gex(contract, spot)
            if contract_gex is None:
                continue

            gex_by_strike[contract.strike] = gex_by_strike.get(contract.strike, 0.0) + contract_gex
            total_gex += contract_gex

        if 1 < len(gex_by_strike) < 10:
            return GEXResult(spot=spot, net_gex=total_gex, regime_sign=0)

        flip_level = self._compute_flip_level(gex_by_strike)
        call_wall = self._compute_call_wall(gex_by_strike)
        put_wall = self._compute_put_wall(gex_by_strike)
        regime_sign = 1 if total_gex > 0 else (-1 if total_gex < 0 else 0)
        by_expiry = self._compute_by_expiry(chain.contracts, spot)

        return GEXResult(
            spot=spot,
            flip_level=flip_level,
            call_wall=call_wall,
            put_wall=put_wall,
            net_gex=total_gex,
            regime_sign=regime_sign,
            by_expiry=by_expiry,
        )

    def _contract_gex(self, contract: OptionsContract, spot: float) -> float | None:
        if contract.gamma is None:
            return None

        self._clamped_years_to_expiry(contract.expiry)

        sign = self._option_sign(contract.call_put)
        if sign is None:
            return None

        return sign * contract.gamma * (contract.oi or 0) * GEX_SCALE * (spot**2)

    def _compute_flip_level(self, gex_by_strike: dict[float, float]) -> Optional[float]:
        cumulative = 0.0
        prev_strike: float | None = None
        prev_cumulative: float | None = None

        for strike in sorted(gex_by_strike):
            prev_cumulative = cumulative
            cumulative += gex_by_strike[strike]

            if prev_cumulative is not None and prev_strike is not None:
                crossed_zero = (prev_cumulative < 0 < cumulative) or (prev_cumulative > 0 > cumulative)
                if crossed_zero:
                    denom = cumulative - prev_cumulative
                    if denom != 0:
                        t = -prev_cumulative / denom
                        return prev_strike + t * (strike - prev_strike)

            prev_strike = strike

        return None

    def _compute_call_wall(self, gex_by_strike: dict[float, float]) -> float | None:
        call_gex = {strike: value for strike, value in gex_by_strike.items() if value > 0}
        if not call_gex:
            return None
        return float(max(call_gex, key=call_gex.get))

    def _compute_put_wall(self, gex_by_strike: dict[float, float]) -> float | None:
        put_gex = {strike: value for strike, value in gex_by_strike.items() if value < 0}
        if not put_gex:
            return None
        return float(max(put_gex, key=lambda strike: abs(put_gex[strike])))

    def _compute_by_expiry(self, contracts: list[OptionsContract], spot: float) -> dict[str, float]:
        by_expiry: dict[str, float] = {"0DTE": 0.0, "1-7": 0.0, "8-30": 0.0, "31+": 0.0}

        for contract in contracts:
            if contract.gamma is None or contract.oi is None:
                continue

            sign = self._option_sign(contract.call_put)
            if sign is None:
                continue

            contract_gex = sign * contract.gamma * contract.oi * GEX_SCALE * (spot**2)
            days = self._days_to_expiry(contract.expiry)
            if days is None:
                continue

            if days == 0:
                bucket = "0DTE"
            elif days <= 7:
                bucket = "1-7"
            elif days <= 30:
                bucket = "8-30"
            else:
                bucket = "31+"

            by_expiry[bucket] += contract_gex

        return by_expiry

    def _option_sign(self, call_put: str) -> int | None:
        normalized = call_put.lower()
        if normalized == "call":
            return 1
        if normalized == "put":
            return -1
        return None

    def _days_to_expiry(self, expiry: str) -> int | None:
        if not expiry:
            return None
        return (date.fromisoformat(expiry) - date.today()).days

    def _clamped_years_to_expiry(self, expiry: str) -> float | None:
        days = self._days_to_expiry(expiry)
        if days is None:
            return None
        return max(days / 365.0, 1.0 / 365.0)


__all__ = ["GEXEngine"]
