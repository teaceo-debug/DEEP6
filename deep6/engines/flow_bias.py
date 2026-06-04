"""Intraday flow domain for v3 market bias scoring."""
from __future__ import annotations

from datetime import datetime, time as dt_time
from typing import Optional
import time
from zoneinfo import ZoneInfo

from deep6.engines.bias_contracts import DomainScore
from deep6.engines.signal_config import IntradayFlowConfig

ET = ZoneInfo("America/New_York")
RTH_START_HOUR = 9
RTH_START_MIN = 30
RTH_END_HOUR = 16


class IntradayFlowDomain:
    """Scores NQ intraday directional pressure from CVD, TICK, and VWAP."""

    MAX_RANGE = 2
    DOMAIN = "flow"

    def __init__(self, config: Optional[IntradayFlowConfig] = None) -> None:
        self._config = config or IntradayFlowConfig()

    def compute(
        self,
        tick_value: Optional[float],
        cvd_slope: Optional[float],
        price: Optional[float],
        vwap: Optional[float],
        now_et: Optional[datetime] = None,
    ) -> DomainScore:
        """Return the intraday flow domain score clamped to -2..+2."""
        current_et = self._normalize_now(now_et)
        if not self._is_rth(current_et):
            return DomainScore(
                domain=self.DOMAIN,
                score=0,
                max_range=self.MAX_RANGE,
                available=False,
                stale=True,
                detail={"reason": "outside RTH"},
                updated_at=time.time(),
            )

        cvd_component = 0
        if cvd_slope is not None:
            if cvd_slope > self._config.cvd_slope_threshold:
                cvd_component = 1
            elif cvd_slope < -self._config.cvd_slope_threshold:
                cvd_component = -1

        tick_component = 0
        if tick_value is not None:
            if tick_value > self._config.tick_thrust_threshold:
                tick_component = 1
            elif tick_value < -self._config.tick_thrust_threshold:
                tick_component = -1

        vwap_component = 0
        if price is not None and vwap is not None:
            if price > vwap:
                vwap_component = 1
            elif price < vwap:
                vwap_component = -1

        raw_score = cvd_component + tick_component + vwap_component
        score = max(-self.MAX_RANGE, min(self.MAX_RANGE, raw_score))
        available = any(
            (
                cvd_slope is not None,
                tick_value is not None,
                price is not None and vwap is not None,
            )
        )

        return DomainScore(
            domain=self.DOMAIN,
            score=score,
            max_range=self.MAX_RANGE,
            available=available,
            stale=False,
            detail={
                "cvd_component": cvd_component,
                "tick_component": tick_component,
                "vwap_component": vwap_component,
                "raw_score": raw_score,
                "rth": True,
            },
            updated_at=time.time(),
        )

    def _is_rth(self, now_et: datetime) -> bool:
        """Return True when the ET time is inside 9:30-16:00 regular hours."""
        current = now_et.astimezone(ET).time()
        return dt_time(RTH_START_HOUR, RTH_START_MIN) <= current < dt_time(RTH_END_HOUR, 0)

    def _normalize_now(self, now_et: Optional[datetime]) -> datetime:
        if now_et is None:
            return datetime.now(ET)
        if now_et.tzinfo is None:
            return now_et.replace(tzinfo=ET)
        return now_et.astimezone(ET)
