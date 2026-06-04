"""FlashAlpha on-demand enrichment for Claude narratives.

Used by the Claude interpreter to get richer data before generating narratives.
NOT a replacement for the polling adapter — this is supplementary on-demand data.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.flashalpha.com/v1"
_TIMEOUT = 10.0
_CACHE_TTL = 300


class FlashAlphaMCPClient:
    """On-demand FlashAlpha data enrichment for Claude narratives."""

    def __init__(self, api_key: str, symbol: str = "QQQ") -> None:
        self._api_key = api_key
        self._symbol = symbol
        self._client = httpx.AsyncClient(timeout=_TIMEOUT)
        self._cache: dict[str, tuple[float, Any]] = {}

    async def get_enrichment_context(self) -> str:
        """Fetch rich context from FlashAlpha for Claude's narrative prompt."""
        if not self._api_key:
            return ""

        sections: list[str] = []

        summary = await self._fetch_cached("exposure/summary")
        if summary:
            sections.append(self._format_exposure_summary(summary))

        levels = await self._fetch_cached("exposure/levels")
        if levels:
            sections.append(self._format_levels(levels))

        zero_dte = await self._fetch_cached("exposure/zero-dte")
        if zero_dte:
            sections.append(self._format_zero_dte(zero_dte))

        vrp = await self._fetch_cached("volatility")
        if vrp:
            formatted_vrp = self._format_vrp(vrp)
            if formatted_vrp:
                sections.append(formatted_vrp)

        narrative = await self._fetch_cached("exposure/narrative")
        if narrative and isinstance(narrative, dict):
            fa_text = narrative.get("narrative", "")
            if fa_text:
                sections.append(f"[FlashAlpha AI Narrative]: {fa_text[:200]}")

        if not sections:
            return ""

        return "<flashalpha_live_data>\n" + "\n".join(sections) + "\n</flashalpha_live_data>"

    async def _fetch_cached(self, endpoint: str) -> dict[str, Any] | None:
        """Fetch with TTL cache to avoid burning quota."""
        cache_key = f"{endpoint}:{self._symbol}"
        now = time.time()

        cached = self._cache.get(cache_key)
        if cached is not None:
            ts, data = cached
            if now - ts < _CACHE_TTL:
                return data

        url = f"{_BASE_URL}/{endpoint}/{self._symbol}"
        headers = {"X-Api-Key": self._api_key}

        try:
            response = await self._client.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict):
                    self._cache[cache_key] = (now, data)
                    return data
                logger.debug("FlashAlpha MCP %s returned non-dict payload", endpoint)
                return None
            if response.status_code == 429:
                logger.debug("FlashAlpha MCP rate limited on %s", endpoint)
            elif response.status_code == 403:
                logger.debug("FlashAlpha MCP tier restricted on %s", endpoint)
            else:
                logger.debug("FlashAlpha MCP %s returned %d", endpoint, response.status_code)
        except Exception as exc:
            logger.debug("FlashAlpha MCP fetch error on %s: %s", endpoint, exc)

        return None

    def _format_exposure_summary(self, data: dict[str, Any]) -> str:
        exposures = data.get("exposures", {}) or {}
        regime = data.get("regime", "unknown")
        hedging = data.get("hedging_estimate", {}) or {}

        lines = [
            "[FlashAlpha Exposure Summary]",
            f"  Regime: {regime}",
            f"  Net GEX: {self._fmt_num(exposures.get('net_gex'))}",
            f"  Net DEX: {self._fmt_num(exposures.get('net_dex'))}",
            f"  Net VEX: {self._fmt_num(exposures.get('net_vex'))}",
            f"  Net CHEX: {self._fmt_num(exposures.get('net_chex'))}",
        ]
        if hedging:
            lines.append(f"  Hedging +1%: {self._fmt_num(hedging.get('spot_up_1pct'))}")
            lines.append(f"  Hedging -1%: {self._fmt_num(hedging.get('spot_down_1pct'))}")
        return "\n".join(lines)

    def _format_levels(self, data: dict[str, Any]) -> str:
        levels = data.get("levels", {}) or data
        return "\n".join(
            [
                "[FlashAlpha Key Levels]",
                f"  Gamma Flip: {levels.get('gamma_flip', 'N/A')}",
                f"  Call Wall: {levels.get('call_wall', 'N/A')}",
                f"  Put Wall: {levels.get('put_wall', 'N/A')}",
                f"  Max Pain: {levels.get('max_pain', 'N/A')}",
                f"  Highest OI: {levels.get('highest_oi_strike', 'N/A')}",
                f"  0DTE Magnet: {levels.get('zero_dte_magnet', 'N/A')}",
            ]
        )

    def _format_zero_dte(self, data: dict[str, Any]) -> str:
        return "\n".join(
            [
                "[FlashAlpha 0DTE Analytics]",
                f"  Pin Risk: {data.get('pin_risk', 'N/A')}",
                f"  Expected Move: {data.get('expected_move', 'N/A')}",
                f"  Gamma Acceleration: {data.get('gamma_acceleration', 'N/A')}",
                f"  0DTE GEX %: {data.get('gex_pct_of_total', 'N/A')}",
            ]
        )

    def _format_vrp(self, data: dict[str, Any]) -> str:
        vrp = data.get("vrp")
        if vrp is None and not any(key in data for key in ("atm_iv", "realized_vol", "vrp_regime", "vrp_zscore")):
            return ""
        return "\n".join(
            [
                "[FlashAlpha Volatility Context]",
                f"  VRP: {self._fmt_num(vrp)}",
                f"  ATM IV: {data.get('atm_iv', 'N/A')}",
                f"  Realized Vol: {data.get('realized_vol', 'N/A')}",
                f"  VRP Regime: {data.get('vrp_regime', 'N/A')}",
                f"  VRP Z-Score: {data.get('vrp_zscore', 'N/A')}",
            ]
        )

    def _fmt_num(self, val: Any) -> str:
        if val is None:
            return "N/A"
        try:
            num = float(val)
        except (TypeError, ValueError):
            return str(val)
        if abs(num) >= 1e9:
            return f"{num / 1e9:+.2f}B"
        if abs(num) >= 1e6:
            return f"{num / 1e6:+.1f}M"
        return f"{num:+.0f}"

    async def close(self) -> None:
        await self._client.aclose()


__all__ = ["FlashAlphaMCPClient"]
