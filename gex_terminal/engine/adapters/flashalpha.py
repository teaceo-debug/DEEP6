"""FlashAlpha polling adapter — wraps nq_atlas.flashalpha_client."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from gex_terminal.schemas import DealerPositioning, GEXLevels, SourceHealth, ZeroDTEState

logger = logging.getLogger(__name__)


class _MissingFlashAlphaClient:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def get_all(self) -> dict[str, Any]:
        raise self._error


@dataclass
class FlashAlphaResult:
    levels: GEXLevels
    dealer: DealerPositioning
    zero_dte: ZeroDTEState
    source_health: SourceHealth
    raw: dict[str, Any]


class FlashAlphaAdapter:
    """Thin adapter: polls FlashAlpha every cycle, normalizes to gex_terminal schemas."""

    def __init__(self, api_key: str, symbol: str = "QQQ") -> None:
        try:
            from nq_atlas.flashalpha_client import FlashAlphaClient  # IMPORT, do NOT rewrite

            self._client = FlashAlphaClient(api_key=api_key, symbol=symbol)
        except ModuleNotFoundError as exc:
            self._client = _MissingFlashAlphaClient(exc)
        self._last_result: Optional[FlashAlphaResult] = None
        self._error_count = 0

    async def poll(self) -> FlashAlphaResult:
        """Fetch all FlashAlpha endpoints and normalize to schemas."""
        try:
            raw = await self._client.get_all()
            result = self._normalize(raw)
            self._last_result = result
            self._error_count = 0
            return result
        except Exception as e:
            logger.error("FlashAlpha poll error: %s", e)
            self._error_count += 1
            return self._degraded_result(str(e))

    def _normalize(self, raw: dict[str, Any]) -> FlashAlphaResult:
        """Convert raw FlashAlpha response to gex_terminal schemas."""
        summary = raw.get("summary", {})
        levels_raw = raw.get("levels", {})
        zero_dte_raw = raw.get("zero_dte", {})
        vex_raw = raw.get("vex", {})
        chex_raw = raw.get("chex", {})

        levels_data = levels_raw.get("levels", {}) if isinstance(levels_raw, dict) else {}
        levels = GEXLevels(
            gamma_flip=summary.get("gamma_flip"),
            call_wall=levels_data.get("call_wall"),
            put_wall=levels_data.get("put_wall"),
            hvl=levels_data.get("hvl"),
            zero_dte_magnet=levels_data.get("zero_dte_magnet"),
        )

        exposures = summary.get("exposures", {}) or {}
        dealer = DealerPositioning(
            net_gex=exposures.get("net_gex"),
            net_dex=exposures.get("net_dex"),
            net_vex=vex_raw.get("net_vex") if isinstance(vex_raw, dict) else None,
            net_chex=chex_raw.get("net_chex") if isinstance(chex_raw, dict) else None,
            regime=summary.get("regime", "neutral"),
            hedge_direction=summary.get("hedge_direction", "neutral"),
        )

        zero_dte = ZeroDTEState(
            gex_pct_of_total=zero_dte_raw.get("gex_pct_of_total") if isinstance(zero_dte_raw, dict) else None,
            pin_risk=self._extract_pin_risk(zero_dte_raw.get("pin_risk", "low") if isinstance(zero_dte_raw, dict) else "low"),
            gamma_acceleration=zero_dte_raw.get("gamma_acceleration") if isinstance(zero_dte_raw, dict) else None,
        )

        source_health = SourceHealth(
            name="flashalpha",
            status="ok",
            last_update=raw.get("ts", time.time()),
            ttl_sec=60,
        )

        return FlashAlphaResult(
            levels=levels,
            dealer=dealer,
            zero_dte=zero_dte,
            source_health=source_health,
            raw=raw,
        )

    @staticmethod
    def _extract_pin_risk(value: Any) -> str:
        """Normalize pin_risk to a string — FlashAlpha may return str or dict."""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            # Extract risk level from dict, or infer from score/fields
            for key in ("risk", "risk_level", "level", "pin_risk"):
                if key in value and isinstance(value[key], str):
                    return value[key]
            # If pin_risk_score exists, map to category
            score = value.get("pin_risk_score") or value.get("score")
            if isinstance(score, (int, float)):
                if score >= 65:
                    return "high"
                if score >= 35:
                    return "medium"
                return "low"
            return "medium"  # dict present but no clear level → assume medium
        return "low"

    def _degraded_result(self, error_msg: str) -> FlashAlphaResult:
        """Return last known data with error status, or empty if no prior data."""
        health = SourceHealth(
            name="flashalpha",
            status="error",
            last_update=self._last_result.source_health.last_update if self._last_result else None,
            ttl_sec=60,
            error_msg=error_msg,
        )
        if self._last_result:
            return FlashAlphaResult(
                levels=self._last_result.levels,
                dealer=self._last_result.dealer,
                zero_dte=self._last_result.zero_dte,
                source_health=health,
                raw=self._last_result.raw,
            )
        return FlashAlphaResult(
            levels=GEXLevels(),
            dealer=DealerPositioning(),
            zero_dte=ZeroDTEState(),
            source_health=health,
            raw={},
        )


__all__ = ["FlashAlphaAdapter", "FlashAlphaResult"]
