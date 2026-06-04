"""Volume-Synchronized Probability of Informed Trading."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass
class VPINResult:
    value: float  # 0.0 to 1.0
    multiplier: float  # For scorer chain


class VPINCalculator:
    def __init__(self, bucket_size: int = 500, window_size: int = 50) -> None:
        self._bucket_size = bucket_size
        self._window_size = window_size
        self._current_bucket_buy: int = 0
        self._current_bucket_sell: int = 0
        self._current_bucket_vol: int = 0
        self._buckets: deque[tuple[int, int]] = deque(maxlen=window_size)
        self._last_vpin: float = 0.0

    def add_volume(self, buy_vol: int, sell_vol: int) -> VPINResult | None:
        """Add classified volume. Returns VPIN when bucket completes."""
        self._current_bucket_buy += buy_vol
        self._current_bucket_sell += sell_vol
        self._current_bucket_vol += buy_vol + sell_vol

        if self._current_bucket_vol >= self._bucket_size:
            self._buckets.append((self._current_bucket_buy, self._current_bucket_sell))
            self._current_bucket_buy = 0
            self._current_bucket_sell = 0
            self._current_bucket_vol = 0
            return self._calculate()
        return None

    def _calculate(self) -> VPINResult:
        """Calculate VPIN from completed buckets."""
        if not self._buckets:
            return VPINResult(value=0.0, multiplier=1.0)

        total_imbalance = sum(abs(b - s) for b, s in self._buckets)
        total_volume = sum(b + s for b, s in self._buckets)

        if total_volume == 0:
            vpin = 0.0
        else:
            vpin = total_imbalance / total_volume

        self._last_vpin = vpin

        if vpin > 0.7:
            mult = 1.1
        elif vpin > 0.5:
            mult = 1.05
        else:
            mult = 1.0

        return VPINResult(value=vpin, multiplier=mult)

    @property
    def current_vpin(self) -> float:
        return self._last_vpin

    def get_multiplier(self) -> float:
        """Get VPIN multiplier for scorer chain."""
        if self._last_vpin > 0.7:
            return 1.1
        if self._last_vpin > 0.5:
            return 1.05
        return 1.0


__all__ = ["VPINCalculator", "VPINResult"]
