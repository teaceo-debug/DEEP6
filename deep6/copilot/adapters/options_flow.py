"""Massive.com options flow adapter for DEEP6 copilot."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

try:
    import httpx  # type: ignore
except Exception:  # pragma: no cover - optional dependency at import time
    httpx = None  # type: ignore

from deep6.copilot.types import OptionsFlowSnapshot, UnusualTrade

logger = logging.getLogger(__name__)

MASSIVE_BASE = "https://api.massive.com"
POLL_INTERVAL_SECONDS = 180
MIN_PREMIUM_USD = 100_000.0
MIN_VOLUME_TO_OI = 2.0
ENV_FILE_CANDIDATES = (
    Path(".env"),
    Path(".env.local"),
    Path("scripts/.env"),
    Path("scripts/.env.local"),
)


def _load_env_files() -> None:
    for env_path in ENV_FILE_CANDIDATES:
        if not env_path.exists():
            continue
        try:
            for raw in env_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
        except OSError:
            continue


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _utc_timestamp() -> float:
    return time.time()


def _normalize_trade_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"call", "c"} or "call" in text:
        return "call"
    if text in {"put", "p"} or "put" in text:
        return "put"
    return ""


class OptionsFlowAdapter:
    """Fetch and cache unusual options flow from Massive.com."""

    POLL_INTERVAL_SECONDS = POLL_INTERVAL_SECONDS

    # TODO: confirm the exact Massive.com options-flow endpoint names.
    # The adapter tries multiple reasonable candidates and falls back to an empty
    # snapshot if the API shape differs or the request fails.
    _ENDPOINT_CANDIDATES = (
        "/v3/options/flow/{symbol}",
        "/v3/flow/options/{symbol}",
        "/v3/snapshot/options/{symbol}",
    )

    def __init__(self, api_key: str | None = None, *, timeout: float = 12.0) -> None:
        _load_env_files()
        self._api_key = (api_key or os.getenv("MASSIVE_API_KEY") or os.getenv("FLASHALPHA_API_KEY") or "").strip()
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._cached_snapshot = OptionsFlowSnapshot(timestamp=_utc_timestamp())
        self._last_fetch_monotonic: float = 0.0

    async def __aenter__(self) -> "OptionsFlowAdapter":
        if httpx is None:
            return self
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(self._timeout), follow_redirects=True)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_flow(self, symbol: str = "NQ") -> OptionsFlowSnapshot:
        """Fetch options flow for a symbol and return a cached snapshot on failure."""

        if self._is_cache_fresh():
            return self._cached_snapshot

        if httpx is None:
            logger.warning("httpx is unavailable; returning cached options flow snapshot")
            return self._cached_snapshot

        if not self._api_key:
            logger.warning("Missing Massive.com API key; returning cached options flow snapshot")
            return self._cached_snapshot

        try:
            payload = await self._fetch_payload(symbol)
            snapshot = self._build_snapshot(payload)
        except Exception as exc:
            logger.warning("options flow fetch failed for %s: %s", symbol, exc)
            return self._cached_snapshot

        self._cached_snapshot = snapshot
        self._last_fetch_monotonic = time.monotonic()
        return snapshot

    async def _fetch_payload(self, symbol: str) -> dict[str, Any] | list[Any]:
        client = self._client
        owns_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=httpx.Timeout(self._timeout), follow_redirects=True)
            owns_client = True

        try:
            last_exc: Exception | None = None
            for endpoint in self._ENDPOINT_CANDIDATES:
                url = f"{MASSIVE_BASE}{endpoint.format(symbol=symbol)}?{urlencode({'limit': 250, 'apiKey': self._api_key})}"
                try:
                    response = await client.get(url)
                    if response.status_code >= 400:
                        logger.warning("options flow endpoint returned HTTP %s for %s", response.status_code, symbol)
                        continue
                    return response.json()
                except Exception as exc:
                    last_exc = exc
                    logger.warning("options flow request failed for %s via %s: %s", symbol, endpoint, exc)
            if last_exc is not None:
                raise last_exc
            raise RuntimeError("No Massive.com options-flow endpoint responded successfully")
        finally:
            if owns_client:
                await client.aclose()

    def _build_snapshot(self, payload: dict[str, Any] | list[Any]) -> OptionsFlowSnapshot:
        rows = self._extract_rows(payload)
        if not rows:
            return OptionsFlowSnapshot(timestamp=_utc_timestamp())

        unusual: list[UnusualTrade] = []
        call_premium = 0.0
        put_premium = 0.0
        largest: UnusualTrade | None = None
        largest_premium = -1.0

        for row in rows:
            trade = self._parse_trade(row)
            if trade is None:
                continue

            if trade.trade_type == "call":
                call_premium += trade.premium
            elif trade.trade_type == "put":
                put_premium += trade.premium

            if trade.premium > largest_premium:
                largest = trade
                largest_premium = trade.premium

            if self._is_unusual(trade, row):
                unusual.append(trade)

        put_call_ratio = (put_premium / call_premium) if call_premium > 0 else (float("inf") if put_premium > 0 else 0.0)
        return OptionsFlowSnapshot(
            unusual_trades=unusual,
            net_premium=call_premium - put_premium,
            put_call_ratio=put_call_ratio,
            largest_trade=largest,
            timestamp=_utc_timestamp(),
        )

    def _extract_rows(self, payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if not isinstance(payload, dict):
            return []

        for key in ("results", "data", "items", "rows", "trades", "flow", "options_flow"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]

        if any(key in payload for key in ("premium", "strike_price", "volume", "open_interest")):
            return [payload]
        return []

    def _parse_trade(self, row: dict[str, Any]) -> UnusualTrade | None:
        details = row.get("details", {}) if isinstance(row.get("details"), dict) else {}
        strike = _to_float(details.get("strike_price", row.get("strike")))
        expiry = str(details.get("expiration_date") or row.get("expiry") or row.get("expiration") or "").strip()
        trade_type = _normalize_trade_type(details.get("contract_type") or row.get("trade_type") or row.get("type"))
        premium = _to_float(
            row.get("premium")
            or row.get("notional")
            or row.get("value")
            or row.get("trade_premium")
            or row.get("amount")
        )
        volume = _to_int(row.get("volume") or row.get("size") or row.get("contracts") or row.get("qty"))
        open_interest = _to_int(row.get("open_interest") or row.get("oi") or row.get("openInterest"))
        oi_ratio = _to_float(row.get("oi_ratio") or row.get("oiRatio"))
        if oi_ratio <= 0.0:
            if open_interest > 0:
                oi_ratio = volume / float(open_interest)
            elif volume > 0:
                oi_ratio = float(volume)

        if strike <= 0.0 or not expiry or trade_type not in {"call", "put"} or premium <= 0.0 or volume <= 0:
            return None

        sentiment = str(row.get("sentiment") or row.get("side") or row.get("direction") or "").strip().lower()
        if not sentiment:
            sentiment = "bullish" if trade_type == "call" else "bearish"

        return UnusualTrade(
            strike=strike,
            expiry=expiry,
            trade_type=trade_type,
            premium=premium,
            volume=volume,
            oi_ratio=oi_ratio,
            sentiment=sentiment,
        )

    def _is_unusual(self, trade: UnusualTrade, row: dict[str, Any]) -> bool:
        open_interest = _to_int(row.get("open_interest") or row.get("oi") or row.get("openInterest"))
        volume = trade.volume
        if trade.oi_ratio >= MIN_VOLUME_TO_OI:
            return trade.premium >= MIN_PREMIUM_USD
        return trade.premium >= MIN_PREMIUM_USD and open_interest > 0 and volume > (MIN_VOLUME_TO_OI * open_interest)

    def _is_cache_fresh(self) -> bool:
        return self._last_fetch_monotonic > 0.0 and (time.monotonic() - self._last_fetch_monotonic) < self.POLL_INTERVAL_SECONDS


__all__ = ["OptionsFlowAdapter"]
