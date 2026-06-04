from __future__ import annotations

import math
from datetime import date

from scipy.stats import norm

from nq_atlas.types import ChainSnapshot, OptionsContract, VannaCharmResult

RISK_FREE_RATE = 0.05
CONTRACT_MULTIPLIER = 100
MIN_TIME_TO_EXPIRY_YEARS = 1.0 / 365.0
MIXED_SIGNAL_NEUTRALITY_RATIO = 0.10


class VannaCharmEngine:
    """Compute dealer vanna/charm exposures from a QQQ options chain."""

    def compute(self, chain: ChainSnapshot) -> VannaCharmResult:
        spot = chain.spot_price
        if spot <= 0:
            return VannaCharmResult()

        net_vanna = 0.0
        net_charm = 0.0
        valid_count = 0

        for contract in chain.contracts:
            if contract.oi is None or contract.oi <= 0:
                continue

            greeks = self._resolve_contract_greeks(contract=contract, spot=spot, as_of=chain.timestamp.date())
            if greeks is None:
                continue

            vanna_value, charm_value = greeks
            dealer_vanna = -vanna_value
            dealer_charm = -charm_value

            scale = contract.oi * CONTRACT_MULTIPLIER * spot
            net_vanna += dealer_vanna * scale
            net_charm += dealer_charm * scale
            valid_count += 1

        if valid_count == 0:
            return VannaCharmResult()

        return VannaCharmResult(
            net_vanna_exposure=net_vanna,
            net_charm_exposure=net_charm,
            dealer_hedge_direction=self._dealer_hedge_direction(net_vanna, net_charm),
            vanna_per_iv_bp=net_vanna * 0.0001,
        )

    def _resolve_contract_greeks(
        self,
        contract: OptionsContract,
        spot: float,
        as_of: date,
    ) -> tuple[float, float] | None:
        vanna_value = contract.vanna
        charm_value = contract.charm

        if vanna_value is not None and charm_value is not None:
            return vanna_value, charm_value

        if contract.iv is None or contract.iv <= 0 or contract.strike <= 0:
            return None

        try:
            expiry = date.fromisoformat(contract.expiry)
        except ValueError:
            return None

        days_to_expiry = (expiry - as_of).days
        time_to_expiry = max(days_to_expiry / 365.0, MIN_TIME_TO_EXPIRY_YEARS)
        sqrt_t = math.sqrt(time_to_expiry)
        sigma = contract.iv

        denominator = sigma * sqrt_t
        if denominator <= 0:
            return None

        d1 = (
            math.log(spot / contract.strike)
            + (RISK_FREE_RATE + 0.5 * sigma**2) * time_to_expiry
        ) / denominator
        d2 = d1 - denominator
        pdf_d1 = norm.pdf(d1)

        if vanna_value is None:
            vanna_value = -pdf_d1 * d2 / sigma

        if charm_value is None:
            charm_base = abs(-pdf_d1 * (
                (2 * RISK_FREE_RATE * time_to_expiry) - (d2 * sigma * sqrt_t)
            ) / (2 * time_to_expiry * sigma * sqrt_t))
            option_side = contract.call_put.strip().lower()
            if option_side == "call":
                charm_value = -charm_base
            elif option_side == "put":
                charm_value = charm_base
            else:
                return None

        return vanna_value, charm_value

    def _dealer_hedge_direction(self, net_vanna: float, net_charm: float) -> int:
        vanna_direction = self._sign(net_vanna)
        charm_direction = self._sign(net_charm)

        if vanna_direction == charm_direction:
            return vanna_direction

        larger = max(abs(net_vanna), abs(net_charm))
        if larger == 0:
            return 0

        if abs(abs(net_vanna) - abs(net_charm)) / larger <= MIXED_SIGNAL_NEUTRALITY_RATIO:
            return 0

        return vanna_direction if abs(net_vanna) > abs(net_charm) else charm_direction

    @staticmethod
    def _sign(value: float) -> int:
        if value > 0:
            return 1
        if value < 0:
            return -1
        return 0


__all__ = ["VannaCharmEngine"]
