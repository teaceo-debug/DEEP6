"""Signed premium flow analytics for NQ ATLAS."""

from __future__ import annotations

import time
from collections import deque
from statistics import mean, stdev
from typing import Optional

from nq_atlas.types import FlowResult


class FlowEngine:
    """Tracks signed options premium flow via Lee-Ready classification."""

    WINDOW_5M_SEC = 300
    WINDOW_15M_SEC = 900
    BASELINE_SEC = 3600
    MIDPOINT_EPSILON = 1e-6
    NET_DIRECTION_THRESHOLD = 1000.0
    CONTRACT_MULTIPLIER = 100.0

    def __init__(self) -> None:
        self._trades: deque[tuple[float, float]] = deque()
        self._last_trade_price: Optional[float] = None

    def update(self, trade: dict) -> None:
        """Process a single options trade tick."""
        price = float(trade.get("price", 0) or 0)
        bid = float(trade.get("bid", 0) or 0)
        ask = float(trade.get("ask", 0) or 0)
        volume = int(trade.get("volume", 0) or 0)
        call_put = str(trade.get("call_put", "call") or "call").lower()

        if price <= 0 or volume <= 0:
            return

        aggressor_sign = self._classify_aggressor(
            price=price,
            bid=bid,
            ask=ask,
            prev_price=trade.get("prev_price"),
        )
        self._last_trade_price = price

        if aggressor_sign == 0:
            return

        option_sign = 1 if call_put == "call" else -1
        direction_sign = aggressor_sign * option_sign
        signed_premium = price * volume * self.CONTRACT_MULTIPLIER * direction_sign

        self._trades.append((time.time(), signed_premium))
        self._purge_old()

    def compute(self) -> FlowResult:
        """Return current rolling flow metrics."""
        self._purge_old()
        if not self._trades:
            return FlowResult()

        now = time.time()
        prem_5m = sum(premium for ts, premium in self._trades if ts >= now - self.WINDOW_5M_SEC)
        prem_15m = sum(premium for ts, premium in self._trades if ts >= now - self.WINDOW_15M_SEC)

        baseline_buckets = self._build_baseline_buckets(now)
        z_score = 0.0
        if len(baseline_buckets) >= 2:
            sigma = stdev(baseline_buckets)
            if sigma > self.MIDPOINT_EPSILON:
                z_score = (prem_5m - mean(baseline_buckets)) / sigma

        net_direction = 0
        if prem_5m > self.NET_DIRECTION_THRESHOLD:
            net_direction = 1
        elif prem_5m < -self.NET_DIRECTION_THRESHOLD:
            net_direction = -1

        return FlowResult(
            signed_premium_5m=prem_5m,
            signed_premium_15m=prem_15m,
            net_direction=net_direction,
            z_score=z_score,
        )

    def _classify_aggressor(
        self,
        *,
        price: float,
        bid: float,
        ask: float,
        prev_price: object,
    ) -> int:
        """Classify trade aggressor using midpoint then tick rule."""
        midpoint = (bid + ask) / 2 if bid > 0 and ask > 0 else price

        if price > midpoint + self.MIDPOINT_EPSILON:
            return 1
        if price < midpoint - self.MIDPOINT_EPSILON:
            return -1

        previous = self._coerce_prev_price(prev_price)
        if previous is None:
            previous = self._last_trade_price
        if previous is None:
            return 0
        if price > previous:
            return 1
        if price < previous:
            return -1
        return 0

    def _coerce_prev_price(self, prev_price: object) -> Optional[float]:
        if prev_price is None:
            return None
        try:
            value = float(prev_price)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    def _build_baseline_buckets(self, now: float) -> list[float]:
        buckets: list[float] = []
        for i in range(12):
            bucket_start = now - (i + 1) * self.WINDOW_5M_SEC
            bucket_end = now - i * self.WINDOW_5M_SEC
            bucket_sum = sum(
                premium
                for ts, premium in self._trades
                if bucket_start <= ts < bucket_end
            )
            buckets.append(bucket_sum)
        return buckets

    def _purge_old(self) -> None:
        """Remove trades outside the 60-minute baseline window."""
        cutoff = time.time() - self.BASELINE_SEC
        while self._trades and self._trades[0][0] < cutoff:
            self._trades.popleft()


__all__ = ["FlowEngine"]
