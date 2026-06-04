"""PO3 daily bias gate — wraps the deep6 PO3 detector."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class PO3Gate:
    """Provides PO3 daily bias direction when the deep6 detector is available."""

    def __init__(self) -> None:
        self._detector = None
        self._last_state = "UNKNOWN"
        self._load_detector()

    def _load_detector(self) -> None:
        try:
            from deep6.bias_engine.po3_detector import PO3BiasDetector

            self._detector = PO3BiasDetector()
        except Exception as exc:  # pragma: no cover - defensive import guard
            logger.debug("PO3 detector unavailable: %s", exc)

    def update(self, daily_ohlc: dict[str, Any] | None = None) -> str:
        """Return PO3 direction: BULLISH | BEARISH | NEUTRAL | UNKNOWN."""
        if self._detector is None or daily_ohlc is None:
            return self._last_state

        try:
            prev_day = daily_ohlc.get("prev_day")
            if isinstance(prev_day, dict):
                pd_high = self._to_float(prev_day.get("high"))
                pd_low = self._to_float(prev_day.get("low"))
                pd_open = self._to_float(prev_day.get("open"))
                pd_close = self._to_float(prev_day.get("close"))
                if None not in (pd_high, pd_low, pd_open, pd_close):
                    self._detector.set_prev_day(pd_high, pd_low, pd_open, pd_close)

            weekly_open = self._to_float(daily_ohlc.get("weekly_open"))
            week_of_year = daily_ohlc.get("week_of_year")
            if weekly_open is not None and isinstance(week_of_year, int):
                self._detector.set_weekly_open(weekly_open, week_of_year)

            bar_time = self._coerce_datetime(daily_ohlc.get("timestamp"))
            open_ = self._to_float(daily_ohlc.get("open"))
            high = self._to_float(daily_ohlc.get("high"))
            low = self._to_float(daily_ohlc.get("low"))
            close = self._to_float(daily_ohlc.get("close"))
            if None in (bar_time, open_, high, low, close):
                return self._last_state

            result = self._detector.update_bar(bar_time, open_, high, low, close)
            direction = self._normalize_direction(getattr(result, "direction", None))
            if direction != "UNKNOWN":
                self._last_state = direction
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            logger.debug("PO3 update error: %s", exc)
        return self._last_state

    @property
    def state(self) -> str:
        return self._last_state

    def _normalize_direction(self, value: Any) -> str:
        text = str(getattr(value, "value", value) or "").upper()
        if "BULL" in text:
            return "BULLISH"
        if "BEAR" in text:
            return "BEARISH"
        if text == "NEUTRAL":
            return "NEUTRAL"
        return "UNKNOWN"

    def _coerce_datetime(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            timestamp = float(value)
            if timestamp > 1_000_000_000_000:
                timestamp /= 1000.0
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        return None

    def _to_float(self, value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None


__all__ = ["PO3Gate"]
