from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx

from .convert import compute_nq_qqq_factor
from .schemas import NQQuote

log = logging.getLogger(__name__)
__all__ = ["NQPriceService"]

POLYGON_BASE = "https://api.polygon.io"
NQ_SYMBOL = "NQ%3ACME"  # NQ futures continuous front-month
MIN_REFRESH_SEC = 5
STALE_AFTER_SEC = 30


class NQPriceService:
    """Async NQ spot price service with multi-source fallback.

    Priority:
    1. Polygon.io /v2/last/trade/NQ (real-time NQ futures last trade)
    2. FlashAlpha snapshot underlying_price (QQQ) + ratio conversion

    Caches last known price. Returns stale=True if cache > STALE_AFTER_SEC.
    """

    def __init__(
        self,
        polygon_api_key: str = "",
        flash_api_key: str = "",
        stale_threshold_sec: int = STALE_AFTER_SEC,
    ) -> None:
        self._polygon_key = polygon_api_key
        self._flash_key = flash_api_key
        self._stale_threshold = stale_threshold_sec
        self._cache: NQQuote | None = None
        self._last_fetch: float = 0.0

    async def get_nq_quote(self) -> NQQuote:
        """Return current NQ quote. Uses cache if fresh."""
        now = time.monotonic()
        if self._cache and (now - self._last_fetch) < MIN_REFRESH_SEC:
            return self._cache

        quote = await self._fetch_polygon_nq()
        if quote is None:
            quote = await self._fetch_flashalpha_qqq()
        if quote is None and self._cache is not None:
            log.warning("all price sources failed, returning stale cache")
            return NQQuote(
                nq_price=self._cache.nq_price,
                qqq_price=self._cache.qqq_price,
                nq_qqq_factor=self._cache.nq_qqq_factor,
                source="stale_cache",
                timestamp=datetime.now(timezone.utc).isoformat(),
                stale=True,
            )
        if quote is None:
            raise RuntimeError("No NQ price available from any source")

        self._cache = quote
        self._last_fetch = now
        return quote

    async def get_conversion_factors(self) -> dict[str, float | None]:
        """Return current NQ/QQQ factor and NQ-NDX basis for adapter use."""
        quote = await self.get_nq_quote()
        return {
            "nq_qqq_factor": quote.nq_qqq_factor,
            "nq_ndx_basis": quote.nq_ndx_basis,
            "nq_price": quote.nq_price,
            "qqq_price": quote.qqq_price,
        }

    async def _fetch_polygon_nq(self) -> NQQuote | None:
        """Fetch NQ last trade from Polygon.io."""
        if not self._polygon_key:
            return None
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{POLYGON_BASE}/v2/last/trade/{NQ_SYMBOL}",
                    params={"apiKey": self._polygon_key},
                )
                if resp.status_code != 200:
                    log.debug("polygon NQ returned %d", resp.status_code)
                    return None
                data = resp.json()
                results = data.get("results", {})
                nq_price = results.get("p") or results.get("price")
                if not nq_price:
                    return None
                return NQQuote(
                    nq_price=float(nq_price),
                    qqq_price=None,
                    nq_qqq_factor=None,
                    source="polygon",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    stale=False,
                )
        except Exception as exc:
            log.debug("polygon NQ fetch failed: %s", exc)
            return None

    async def _fetch_flashalpha_qqq(self) -> NQQuote | None:
        """Fetch QQQ spot from FlashAlpha and estimate NQ via ratio."""
        if not self._flash_key:
            return None
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    "https://lab.flashalpha.com/v1/exposure/summary/QQQ",
                    headers={"X-Api-Key": self._flash_key},
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
                qqq_price = data.get("spot") or data.get("underlying_price")
                if not qqq_price:
                    return None

                # Use cached NQ if available for ratio, else use default
                if self._cache and self._cache.nq_price:
                    nq_estimated = self._cache.nq_price
                    factor = compute_nq_qqq_factor(nq_estimated, float(qqq_price))
                else:
                    # Bootstrap with approximate ratio — refined on next Polygon call
                    factor = 45.0
                    nq_estimated = float(qqq_price) * factor

                return NQQuote(
                    nq_price=nq_estimated,
                    qqq_price=float(qqq_price),
                    nq_qqq_factor=factor,
                    source="flashalpha_qqq",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    stale=False,
                )
        except Exception as exc:
            log.debug("flashalpha QQQ fetch failed: %s", exc)
            return None
