"""Swing equilibrium — weighted average of dark pool clusters + GEX flip."""
from __future__ import annotations

import logging
from typing import Optional

from gex_terminal.schemas_institutional import SwingEquilibrium

logger = logging.getLogger(__name__)


class SwingEquilibriumEngine:
    """Computes swing equilibrium from dark pool + GEX data."""

    def __init__(self, dp_weight: float = 0.5, gex_weight: float = 0.3, vp_weight: float = 0.2) -> None:
        self._dp_weight = dp_weight
        self._gex_weight = gex_weight
        self._vp_weight = vp_weight
        self._history: list[float] = []
        self._period_days = 4

    def compute(
        self,
        dp_level_centers: list[float],
        dp_level_premiums: list[float],
        gamma_flip_nq: Optional[float] = None,
        hvl_nq: Optional[float] = None,
        period_days: int = 4,
    ) -> SwingEquilibrium:
        """Compute swing equilibrium from available data."""
        self._period_days = period_days
        components: list[float] = []
        weights: list[float] = []

        if dp_level_centers and dp_level_premiums and len(dp_level_centers) == len(dp_level_premiums):
            total_premium = sum(dp_level_premiums)
            if total_premium > 0:
                dp_center = sum(price * weight for price, weight in zip(dp_level_centers, dp_level_premiums)) / total_premium
                components.append(dp_center)
                weights.append(self._dp_weight)

        if gamma_flip_nq and gamma_flip_nq > 0:
            components.append(gamma_flip_nq)
            weights.append(self._gex_weight)

        if hvl_nq and hvl_nq > 0:
            components.append(hvl_nq)
            weights.append(self._vp_weight)

        if not components:
            logger.debug("Swing equilibrium has no contributing components")
            return SwingEquilibrium(price_nq=0.0, period_days=period_days, confidence=0.0)

        total_weight = sum(weights)
        equilibrium_price = sum(component * weight for component, weight in zip(components, weights)) / total_weight
        confidence = round(len(components) / 3.0, 2)

        self._history.append(equilibrium_price)
        max_history = max(1, period_days * 30)
        if len(self._history) > max_history:
            self._history = self._history[-max_history:]

        if len(self._history) > 1:
            trailing = self._history[-min(10, len(self._history)):]
            equilibrium_price = sum(trailing) / len(trailing)

        return SwingEquilibrium(
            price_nq=round(equilibrium_price, 2),
            period_days=period_days,
            confidence=confidence,
        )


__all__ = ["SwingEquilibriumEngine"]
