"""Massive.com (Polygon.io) data client for QQQ options chain + NQ futures price."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import date, datetime, timezone
from typing import Any, Optional

import httpx
from scipy.stats import norm

from nq_atlas.state import AtlasState
from nq_atlas.types import ChainSnapshot, OptionsContract

logger = logging.getLogger(__name__)

_POLYGON_BASE = "https://api.polygon.io"
_BACKOFF_INIT = 5.0
_BACKOFF_MAX = 120.0
_MAX_RETRIES = 3


def _bs_gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes gamma (identical for calls and puts)."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    return float(norm.pdf(d1) / (S * sigma * math.sqrt(T)))


class MassiveClient:
    """Async client for Polygon.io options snapshots and NQ futures quotes."""

    def __init__(self, api_key: str, min_oi: int = 100) -> None:
        self._api_key = api_key
        self._min_oi = min_oi
        self._http: Optional[httpx.AsyncClient] = None

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=_POLYGON_BASE,
                timeout=httpx.Timeout(30.0),
            )
        return self._http

    async def _request(self, path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Make a GET request with retry/backoff logic."""
        merged = {"apiKey": self._api_key}
        if params:
            merged.update(params)

        backoff = _BACKOFF_INIT
        last_exc: Optional[Exception] = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                client = await self._client()
                resp = await client.get(path, params=merged)

                if resp.status_code in (401, 403):
                    raise PermissionError(
                        f"Polygon API auth error {resp.status_code}: {resp.text[:200]}"
                    )

                if resp.status_code == 429:
                    logger.warning("rate-limited (429), backoff %.1fs", backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, _BACKOFF_MAX)
                    continue

                if resp.status_code >= 500:
                    logger.warning(
                        "server error %d (attempt %d/%d)", resp.status_code, attempt, _MAX_RETRIES
                    )
                    if attempt < _MAX_RETRIES:
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, _BACKOFF_MAX)
                        continue
                    resp.raise_for_status()

                resp.raise_for_status()
                return resp.json()

            except (PermissionError, httpx.HTTPStatusError):
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    logger.warning("request error (attempt %d/%d): %s", attempt, _MAX_RETRIES, exc)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, _BACKOFF_MAX)

        raise RuntimeError(f"request failed after {_MAX_RETRIES} attempts") from last_exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def validate_connection(self) -> dict[str, bool]:
        """Test API access. Returns ``{"connected": bool, "has_greeks": bool}``."""
        try:
            data = await self._request(
                "/v3/snapshot/options/QQQ", {"limit": "1"}
            )
            results = data.get("results", [])
            has_greeks = False
            if results:
                greeks = results[0].get("greeks") or {}
                has_greeks = greeks.get("delta") is not None
            return {"connected": True, "has_greeks": has_greeks}
        except PermissionError:
            return {"connected": False, "has_greeks": False}
        except Exception as exc:
            logger.error("validate_connection failed: %s", exc)
            return {"connected": False, "has_greeks": False}

    async def get_options_chain(self, underlying: str = "QQQ") -> ChainSnapshot:
        """Fetch full options chain via Polygon snapshot endpoint with pagination."""
        contracts: list[OptionsContract] = []
        spot_price = 0.0
        path = f"/v3/snapshot/options/{underlying}"
        params: dict[str, Any] = {"limit": "250"}
        max_pages = 20
        page_num = 0
        contracts_before = 0

        while page_num < max_pages:
            data = await self._request(path, params)
            page_num += 1

            # Extract spot from underlying_asset on first page
            if page_num == 1:
                results_list = data.get("results", [])
                if results_list:
                    ua = results_list[0].get("underlying_asset", {})
                    if ua and spot_price == 0.0:
                        spot_price = float(ua.get("price", 0) or ua.get("last_updated_price", 0) or 0)

            for raw in data.get("results", []):
                contract = self._parse_contract(raw, spot_price)
                if contract is not None:
                    contracts.append(contract)

            next_url = data.get("next_url")
            if not next_url:
                break

            if page_num > 1 and len(contracts) == contracts_before:
                logger.debug("No new valid contracts on page %d — stopping pagination early", page_num)
                break

            contracts_before = len(contracts)
            # next_url is absolute; switch to it directly
            path = next_url.replace(_POLYGON_BASE, "")
            params = {}  # next_url already includes query params except apiKey

        return ChainSnapshot(
            underlying=underlying,
            spot_price=spot_price,
            timestamp=datetime.now(tz=timezone.utc),
            contracts=contracts,
        )

    async def get_nq_quote(self) -> float:
        """Get live NQ futures price. Falls back through multiple tickers."""
        tickers = [
            ("/v2/last/trade/NQ%3ACME", lambda d: d.get("results", {}).get("p")),
            ("/v2/aggs/ticker/NQ%3ACME/prev", lambda d: _agg_close(d)),
            ("/v2/last/trade/I%3ANDX", lambda d: d.get("results", {}).get("p")),
            ("/v2/aggs/ticker/I%3ANDX/prev", lambda d: _agg_close(d)),
        ]

        for path, extractor in tickers:
            try:
                data = await self._request(path)
                price = extractor(data)
                if price is not None and float(price) > 0:
                    return float(price)
            except Exception as exc:
                logger.debug("NQ quote attempt %s failed: %s", path, exc)

        raise RuntimeError("Cannot get NQ price from any source")

    async def poll_loop(self, state: AtlasState, interval: int) -> None:
        """Fetch chain every *interval* seconds and update shared state."""
        while True:
            try:
                underlying = state.spots.get("underlying_sym", "QQQ")
                chain = await self.get_options_chain(underlying)
                nq_price = await self.get_nq_quote()
                state.chain = chain
                state.spots["QQQ"] = chain.spot_price
                state.spots["NQ"] = nq_price
                state.last_chain_ts = time.time()
                logger.info(
                    "chain updated: %d contracts, QQQ=%.2f, NQ=%.2f",
                    len(chain.contracts),
                    chain.spot_price,
                    nq_price,
                )
            except Exception as exc:
                logger.error("poll_loop error: %s", exc)
                state.log_error("massive_client", str(exc))
            await asyncio.sleep(interval)

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_contract(self, raw: dict[str, Any], spot: float) -> Optional[OptionsContract]:
        """Parse a single Polygon snapshot result into an OptionsContract.

        Returns ``None`` if the contract fails OI or Greeks filters.
        """
        details = raw.get("details", {})
        greeks_raw = raw.get("greeks") or {}
        quote = raw.get("last_quote") or {}
        trade = raw.get("last_trade") or {}
        day = raw.get("day") or {}

        oi = int(raw.get("open_interest", 0) or 0)
        if oi < self._min_oi:
            return None

        delta = _to_float(greeks_raw.get("delta"))
        gamma = _to_float(greeks_raw.get("gamma"))
        theta = _to_float(greeks_raw.get("theta"))
        vega = _to_float(greeks_raw.get("vega"))
        iv = _to_float(greeks_raw.get("implied_volatility"))

        # Skip if ALL Greeks and IV are missing
        if delta is None and gamma is None and iv is None:
            return None

        strike = float(details.get("strike_price", 0))
        expiry_str = details.get("expiration_date", "")

        # 0DTE T clamping
        T = 1.0 / 365.0  # default minimum
        if expiry_str:
            try:
                days_to_expiry = (date.fromisoformat(expiry_str) - date.today()).days
                T = max(days_to_expiry / 365.0, 1.0 / 365.0)
            except ValueError:
                pass

        # Gamma fallback via Black-Scholes when API gamma missing but IV present
        if gamma is None and iv is not None and spot > 0 and strike > 0:
            gamma = _bs_gamma(spot, strike, T, 0.05, iv)

        return OptionsContract(
            symbol=details.get("ticker", raw.get("ticker", "")),
            strike=strike,
            expiry=expiry_str,
            call_put=details.get("contract_type", "").lower(),
            bid=_to_float(quote.get("bid")),
            ask=_to_float(quote.get("ask")),
            last=_to_float(trade.get("price")),
            volume=int(day.get("volume", 0) or 0) or None,
            oi=oi,
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            iv=iv,
        )


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _to_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _agg_close(data: dict[str, Any]) -> Optional[float]:
    results = data.get("results", [])
    if results and isinstance(results, list):
        return _to_float(results[0].get("c"))
    return None


__all__ = ["MassiveClient"]
