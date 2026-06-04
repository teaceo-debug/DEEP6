"""Unusual Whales on-demand enrichment — dark pool + flow + market tide for Claude narratives."""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.unusualwhales.com"
_TIMEOUT = 10.0
_CACHE_TTL = 300


class UWMCPClient:
    """On-demand Unusual Whales data enrichment for Claude narratives."""

    def __init__(self, api_key: str, symbol: str = "QQQ") -> None:
        self._api_key = api_key
        self._symbol = symbol
        self._client = httpx.AsyncClient(timeout=_TIMEOUT)
        self._cache: dict[str, tuple[float, Any]] = {}

    async def get_enrichment_context(self) -> str:
        """Fetch rich UW context for Claude narrative."""
        if not self._api_key:
            return ""

        sections: list[str] = []

        dark_pool = await self._fetch_cached(f"/api/darkpool/{self._symbol}", {})
        if dark_pool:
            formatted = self._format_dark_pool(dark_pool)
            if formatted:
                sections.append(formatted)

        market_tide = await self._fetch_cached("/api/market/market-tide", {"interval_5m": "false"})
        if market_tide:
            formatted = self._format_market_tide(market_tide)
            if formatted:
                sections.append(formatted)

        flow_alerts = await self._fetch_cached(
            "/api/option-trades/flow-alerts",
            {"ticker_symbol": self._symbol, "min_premium": "500000", "limit": "10"},
        )
        if flow_alerts:
            formatted = self._format_flow_alerts(flow_alerts)
            if formatted:
                sections.append(formatted)

        spot_gex = await self._fetch_cached(f"/api/stock/{self._symbol}/spot-exposures/strike", {})
        if spot_gex:
            formatted = self._format_spot_gex(spot_gex)
            if formatted:
                sections.append(formatted)

        if not sections:
            return ""
        return "<unusual_whales_live_data>\n" + "\n".join(sections) + "\n</unusual_whales_live_data>"

    async def _fetch_cached(self, endpoint: str, params: dict[str, Any]) -> Optional[dict[str, Any]]:
        cache_key = f"{endpoint}:{str(params)}"
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached is not None:
            ts, data = cached
            if now - ts < _CACHE_TTL and isinstance(data, dict):
                return data

        try:
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "UW-CLIENT-API-ID": "100001",
            }
            response = await self._client.get(f"{_BASE_URL}{endpoint}", headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict):
                    self._cache[cache_key] = (now, data)
                    return data
            else:
                logger.debug("UW MCP %s returned %d", endpoint, response.status_code)
        except Exception as exc:
            logger.debug("UW MCP fetch error on %s: %s", endpoint, exc)
        return None

    def _format_dark_pool(self, data: dict[str, Any]) -> str:
        prints = data.get("data", [])[:10]
        if not prints:
            return ""

        total_premium = 0.0
        buy_count = 0
        sell_count = 0
        for print_row in prints:
            price = self._safe_float(print_row.get("price"))
            premium = abs(self._safe_float(print_row.get("premium")))
            total_premium += premium
            bid = self._safe_float(print_row.get("nbbo_bid"))
            ask = self._safe_float(print_row.get("nbbo_ask"))
            nbbo_mid = (bid + ask) / 2 if bid > 0 and ask > 0 else 0.0
            if nbbo_mid > 0:
                if price >= nbbo_mid:
                    buy_count += 1
                else:
                    sell_count += 1

        bias = "BUY" if buy_count > sell_count else "SELL" if sell_count > buy_count else "MIXED"
        return "\n".join(
            [
                "[UW Dark Pool Recent Prints]",
                f"  Prints: {len(prints)} | Premium: ${total_premium / 1e6:.1f}M | Bias: {bias}",
                f"  Buy-side: {buy_count} | Sell-side: {sell_count}",
            ]
        )

    def _format_market_tide(self, data: dict[str, Any]) -> str:
        payload = data.get("data", [])
        if not payload:
            return ""
        latest = payload[-1] if isinstance(payload, list) else payload
        if not isinstance(latest, dict):
            return ""

        call_prem = self._safe_float(latest.get("net_call_premium", latest.get("call_premium")))
        put_prem = self._safe_float(latest.get("net_put_premium", latest.get("put_premium")))
        direction = "BULLISH" if call_prem > put_prem * 1.2 else "BEARISH" if put_prem > call_prem * 1.2 else "MIXED"
        return (
            "[UW Market Tide]\n"
            f"  Call Premium: ${call_prem / 1e6:.1f}M | Put Premium: ${put_prem / 1e6:.1f}M | Direction: {direction}"
        )

    def _format_flow_alerts(self, data: dict[str, Any]) -> str:
        alerts = data.get("data", [])[:5]
        if not alerts:
            return ""

        lines = ["[UW Flow Alerts (Top 5)]"]
        for alert in alerts:
            option_type = str(alert.get("type") or alert.get("call_put") or "?")
            premium = self._safe_float(alert.get("total_premium", alert.get("premium")))
            score = alert.get("score", "?")
            lines.append(f"  {option_type} ${premium / 1e6:.1f}M score:{score}")
        return "\n".join(lines)

    def _format_spot_gex(self, data: dict[str, Any]) -> str:
        strikes = data.get("data", [])
        if not strikes:
            return ""

        max_call = max(
            strikes,
            key=lambda strike: self._safe_float(strike.get("call_gamma_oi", strike.get("call_gex"))),
            default=None,
        )
        max_put = max(
            strikes,
            key=lambda strike: self._safe_float(strike.get("put_gamma_oi", strike.get("put_gex"))),
            default=None,
        )
        lines = ["[UW Spot GEX by Strike]"]
        if isinstance(max_call, dict):
            lines.append(f"  Call Wall: {max_call.get('strike', 'N/A')}")
        if isinstance(max_put, dict):
            lines.append(f"  Put Wall: {max_put.get('strike', 'N/A')}")
        return "\n".join(lines)

    def _safe_float(self, value: Any) -> float:
        try:
            if value is None:
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    async def close(self) -> None:
        await self._client.aclose()


__all__ = ["UWMCPClient"]
