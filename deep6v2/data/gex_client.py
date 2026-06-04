"""GEX data from massive.com API. NQ via QQQ/NDX proxy."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class GEXLevels:
    call_wall: float
    put_wall: float
    gamma_flip: float
    hvl: float  # Highest Volume Level
    timestamp: float


class GEXClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.massive.com",
    ) -> None:
        self._api_key = api_key or os.environ.get("MASSIVE_API_KEY", "")
        self._base_url = base_url
        self._last_levels: GEXLevels | None = None

    async def fetch_levels(self) -> GEXLevels | None:
        """Fetch GEX levels. Returns None if API unavailable."""
        if not self._api_key:
            return None
        # In production: httpx.AsyncClient GET to massive.com
        # For now: stub
        return self._last_levels

    def calculate_zone_bonus(self, price: float, levels: GEXLevels | None) -> float:
        """Zone bonus when price is near GEX walls. Returns 0-8."""
        if levels is None:
            return 0.0
        for wall in [levels.call_wall, levels.put_wall]:
            distance = abs(price - wall)
            if distance <= 5.0:  # Within 5 NQ points
                return min(8.0, 8.0 * (1.0 - distance / 5.0))
        return 0.0

    def calculate_gex_mult(self, price: float, levels: GEXLevels | None) -> float:
        """GEX multiplier for scorer chain. 1.0 = neutral."""
        if levels is None:
            return 1.0
        if price > levels.gamma_flip:
            return 1.05
        return 1.0

    @property
    def last_levels(self) -> GEXLevels | None:
        return self._last_levels


__all__ = ["GEXClient", "GEXLevels"]
