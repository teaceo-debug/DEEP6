"""Unusual Whales adapter — dark pool levels, options flow, and GEX for NQ proxy."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from gex_terminal.schemas import DealerPositioning, GEXLevels, SourceHealth, ZeroDTEState

logger = logging.getLogger(__name__)

UW_BASE_URL = "https://api.unusualwhales.com"
DEFAULT_NQ_QQQ_RATIO = 41.16  # Updated: NQ ~30500 / QQQ ~741 = 41.16 (June 2026)

# Prints below this dollar threshold are retail noise
_MIN_PREMIUM_DEFAULT = 1_000_000
# Cluster prints within 0.5% price distance
_CLUSTER_PCT = 0.005
# Max levels to return
_MAX_LEVELS = 10


class _TTLCache:
    """Simple TTL cache for API responses."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}

    def get(self, key: str, ttl_sec: int) -> Any | None:
        if key in self._data:
            ts, val = self._data[key]
            if time.time() - ts < ttl_sec:
                return val
        return None

    def set(self, key: str, value: Any) -> None:
        self._data[key] = (time.time(), value)


@dataclass
class DarkPoolLevel:
    """A single clustered dark pool level."""

    price_qqq: float  # Premium-weighted center in QQQ terms
    price_nq: float  # Converted to NQ-equivalent
    total_premium: float  # Sum of premiums in cluster
    print_count: int  # Number of prints in cluster


@dataclass
class DarkPoolSummary:
    """Dark pool levels and institutional bias for NQ proxy."""

    levels: list[DarkPoolLevel] = field(default_factory=list)
    net_premium: Optional[float] = None  # Net premium (positive = bullish)
    institutional_bias: str = "neutral"  # "bullish" | "bearish" | "neutral"
    source_health: SourceHealth = field(
        default_factory=lambda: SourceHealth(
            name="unusual_whales", status="pending", ttl_sec=60
        )
    )

    @property
    def levels_nq(self) -> list[float]:
        """NQ-equivalent price levels (convenience accessor)."""
        return [lvl.price_nq for lvl in self.levels]


def _cluster_prints(
    prints: list[dict],
    nq_qqq_ratio: float,
    cluster_pct: float = _CLUSTER_PCT,
) -> tuple[list[DarkPoolLevel], float]:
    """Cluster dark pool prints by price proximity, return levels + net premium."""
    if not prints:
        return [], 0.0

    # Extract valid (price, premium) pairs
    entries: list[tuple[float, float]] = []
    for p in prints:
        try:
            price = float(p.get("price", 0))
            premium = float(p.get("premium", 0))
        except (TypeError, ValueError):
            continue
        if price > 0:
            entries.append((price, premium))

    if not entries:
        return [], 0.0

    net_premium = sum(prem for _, prem in entries)
    entries.sort(key=lambda x: x[0])

    # Greedy clustering
    clusters: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = [entries[0]]

    for price, premium in entries[1:]:
        ref_price = current[0][0]
        if abs(price - ref_price) / ref_price <= cluster_pct:
            current.append((price, premium))
        else:
            clusters.append(current)
            current = [(price, premium)]
    clusters.append(current)

    # Build DarkPoolLevel per cluster
    levels: list[DarkPoolLevel] = []
    for cluster in clusters:
        prices = [p for p, _ in cluster]
        premiums = [pr for _, pr in cluster]
        total_prem = sum(abs(pr) for pr in premiums)

        # Premium-weighted center (use abs premium for weighting)
        abs_premiums = [abs(pr) for pr in premiums]
        weight_sum = sum(abs_premiums)
        if weight_sum > 0:
            center = sum(p * w for p, w in zip(prices, abs_premiums)) / weight_sum
        else:
            center = sum(prices) / len(prices)

        levels.append(
            DarkPoolLevel(
                price_qqq=round(center, 2),
                price_nq=round(center * nq_qqq_ratio, 0),
                total_premium=total_prem,
                print_count=len(cluster),
            )
        )

    # Sort by total premium descending, take top N
    levels.sort(key=lambda x: x.total_premium, reverse=True)
    return levels[:_MAX_LEVELS], net_premium


@dataclass
class UWGEXResult:
    """GEX/Greeks data from Unusual Whales — replaces FlashAlpha."""

    levels: GEXLevels
    dealer: DealerPositioning
    zero_dte: ZeroDTEState
    source_health: SourceHealth


class UnusualWhalesAdapter:
    """Async httpx client for Unusual Whales dark pool data.

    Fetches dark pool prints for QQQ (or configurable symbol),
    clusters them into S/R levels, and converts to NQ-equivalent prices.
    """

    def __init__(
        self,
        api_key: str,
        symbol: str = "QQQ",
        nq_qqq_ratio: float = DEFAULT_NQ_QQQ_RATIO,
        min_premium: float = _MIN_PREMIUM_DEFAULT,
    ) -> None:
        self._api_key = api_key
        self._symbol = symbol
        self._nq_qqq_ratio = nq_qqq_ratio
        self._min_premium = min_premium
        self._client = httpx.AsyncClient(
            base_url=UW_BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            timeout=10.0,
        )
        self._cache = _TTLCache()
        self._last_result: Optional[DarkPoolSummary] = None
        self._error_count = 0

    async def poll(self) -> DarkPoolSummary:
        """Fetch dark pool prints and cluster into NQ levels."""
        if not self._api_key:
            return self._no_key_result()

        try:
            resp = await self._client.get(
                f"/api/darkpool/{self._symbol}",
                params={"limit": 200, "min_premium": int(self._min_premium)},
            )
            resp.raise_for_status()
            data = resp.json()

            result = self._normalize(data)
            self._last_result = result
            self._error_count = 0
            return result

        except httpx.HTTPStatusError as e:
            self._error_count += 1
            code = e.response.status_code
            if code in (401, 403):
                return self._degraded_result("AUTH_FAILED")
            if code == 429:
                return self._degraded_result("RATE_LIMITED")
            return self._degraded_result(f"HTTP_{code}")

        except Exception as e:
            self._error_count += 1
            logger.error("UW poll error: %s", e)
            return self._degraded_result(str(e))

    def _normalize(self, data: dict) -> DarkPoolSummary:
        """Convert UW API response to DarkPoolSummary with clustered levels."""
        prints = data.get("data", []) if isinstance(data, dict) else []

        levels, net_premium = _cluster_prints(
            prints, self._nq_qqq_ratio, _CLUSTER_PCT
        )

        # Bias from net premium direction
        if net_premium > _MIN_PREMIUM_DEFAULT:
            bias = "bullish"
        elif net_premium < -_MIN_PREMIUM_DEFAULT:
            bias = "bearish"
        else:
            bias = "neutral"

        return DarkPoolSummary(
            levels=levels,
            net_premium=net_premium if net_premium != 0 else None,
            institutional_bias=bias,
            source_health=SourceHealth(
                name="unusual_whales",
                status="ok",
                last_update=time.time(),
                ttl_sec=60,
            ),
        )

    def _no_key_result(self) -> DarkPoolSummary:
        return DarkPoolSummary(
            source_health=SourceHealth(
                name="unusual_whales",
                status="pending",
                ttl_sec=60,
                error_msg="API key not configured",
            ),
        )

    def _degraded_result(self, error_msg: str) -> DarkPoolSummary:
        """Return last known data with error status, or empty."""
        health = SourceHealth(
            name="unusual_whales",
            status="error",
            last_update=(
                self._last_result.source_health.last_update
                if self._last_result
                else None
            ),
            ttl_sec=60,
            error_msg=error_msg,
        )
        if self._last_result:
            return DarkPoolSummary(
                levels=self._last_result.levels,
                net_premium=self._last_result.net_premium,
                institutional_bias=self._last_result.institutional_bias,
                source_health=health,
            )
        return DarkPoolSummary(source_health=health)

    # ── GEX / Greeks (replaces FlashAlpha) ─────────────────────────

    async def poll_gex(self) -> UWGEXResult:
        """Fetch GEX, greek exposure, and greek flow; return dealer + levels + 0DTE."""
        if not self._api_key:
            return self._no_key_gex_result()

        try:
            spot_gex, greek_exp, greek_flow, gex_expiry = await asyncio.gather(
                self._fetch_spot_gex(),
                self._fetch_greek_exposure(),
                self._fetch_greek_flow(),
                self._fetch_gex_by_expiry(),
                return_exceptions=True,
            )

            levels = self._parse_spot_gex_levels(
                spot_gex if not isinstance(spot_gex, Exception) else None,
            )
            dealer = self._parse_dealer_positioning(
                greek_exp if not isinstance(greek_exp, Exception) else None,
                greek_flow if not isinstance(greek_flow, Exception) else None,
                spot_gex if not isinstance(spot_gex, Exception) else None,
            )
            zero_dte = self._parse_zero_dte(
                gex_expiry if not isinstance(gex_expiry, Exception) else None,
            )

            return UWGEXResult(
                levels=levels,
                dealer=dealer,
                zero_dte=zero_dte,
                source_health=SourceHealth(
                    name="unusual_whales_gex",
                    status="ok",
                    last_update=time.time(),
                    ttl_sec=60,
                ),
            )
        except Exception as exc:
            logger.error("UW poll_gex error: %s", exc)
            return UWGEXResult(
                levels=GEXLevels(),
                dealer=DealerPositioning(),
                zero_dte=ZeroDTEState(),
                source_health=SourceHealth(
                    name="unusual_whales_gex",
                    status="error",
                    ttl_sec=60,
                    error_msg=str(exc),
                ),
            )

    async def _fetch_spot_gex(self) -> dict | None:
        """GET /api/stock/{ticker}/spot-exposures/strike — real-time GEX by strike."""
        cache_key = f"spot_gex_{self._symbol}"
        cached = self._cache.get(cache_key, 60)
        if cached is not None:
            return cached
        resp = await self._client.get(
            f"/api/stock/{self._symbol}/spot-exposures/strike",
        )
        resp.raise_for_status()
        data = resp.json()
        self._cache.set(cache_key, data)
        return data

    async def _fetch_greek_exposure(self) -> dict | None:
        """GET /api/stock/{ticker}/greek-exposure — aggregate greek exposure."""
        cache_key = f"greek_exp_{self._symbol}"
        cached = self._cache.get(cache_key, 60)
        if cached is not None:
            return cached
        resp = await self._client.get(
            f"/api/stock/{self._symbol}/greek-exposure",
        )
        resp.raise_for_status()
        data = resp.json()
        self._cache.set(cache_key, data)
        return data

    async def _fetch_greek_flow(self) -> dict | None:
        """GET /api/stock/{ticker}/greek-flow — directional delta/vega/charm flow."""
        cache_key = f"greek_flow_{self._symbol}"
        cached = self._cache.get(cache_key, 60)
        if cached is not None:
            return cached
        resp = await self._client.get(
            f"/api/stock/{self._symbol}/greek-flow",
        )
        resp.raise_for_status()
        data = resp.json()
        self._cache.set(cache_key, data)
        return data

    async def _fetch_gex_by_expiry(self) -> dict | None:
        """GET /api/stock/{ticker}/greek-exposure/expiry — GEX by expiry for 0DTE pct."""
        cache_key = f"gex_expiry_{self._symbol}"
        cached = self._cache.get(cache_key, 120)
        if cached is not None:
            return cached
        resp = await self._client.get(
            f"/api/stock/{self._symbol}/greek-exposure/expiry",
        )
        resp.raise_for_status()
        data = resp.json()
        self._cache.set(cache_key, data)
        return data

    def _parse_spot_gex_levels(self, data: dict | None) -> GEXLevels:
        """Extract gamma_flip, call_wall, put_wall from spot GEX by strike."""
        if not data:
            return GEXLevels()

        strikes_raw = data.get("data", [])
        if not isinstance(strikes_raw, list) or not strikes_raw:
            return GEXLevels()

        strikes: list[dict] = []
        for row in strikes_raw:
            if not isinstance(row, dict):
                continue
            strike = self._safe_float(row.get("strike"))
            if strike <= 0:
                continue
            net_gamma = self._compute_net_gamma(row)
            strikes.append({"strike": strike, "net_gamma": net_gamma})

        if not strikes:
            return GEXLevels()

        strikes.sort(key=lambda x: x["strike"])

        # Gamma flip: strike where net gamma crosses from negative to positive
        gamma_flip = None
        for i in range(len(strikes) - 1):
            if strikes[i]["net_gamma"] <= 0 < strikes[i + 1]["net_gamma"]:
                gamma_flip = (strikes[i]["strike"] + strikes[i + 1]["strike"]) / 2
                break

        # Call wall: highest positive gamma strike above flip
        above_flip = [s for s in strikes if gamma_flip is not None and s["strike"] > gamma_flip]
        call_wall = max(above_flip, key=lambda x: x["net_gamma"], default=None)

        # Put wall: largest negative gamma strike below flip
        below_flip = [s for s in strikes if gamma_flip is not None and s["strike"] < gamma_flip]
        put_wall = min(below_flip, key=lambda x: x["net_gamma"], default=None)

        return GEXLevels(
            gamma_flip=round(gamma_flip, 2) if gamma_flip else None,
            call_wall=round(call_wall["strike"], 2) if call_wall else None,
            put_wall=round(put_wall["strike"], 2) if put_wall else None,
        )

    def _parse_dealer_positioning(
        self,
        greek_exp: dict | None,
        greek_flow: dict | None,
        spot_gex: dict | None,
    ) -> DealerPositioning:
        """Build DealerPositioning from UW greek exposure + flow."""
        net_gex: float | None = None
        net_dex: float | None = None
        net_vex: float | None = None
        net_chex: float | None = None
        regime = "neutral"
        hedge_direction = "neutral"

        # From greek-exposure: aggregate greeks
        if isinstance(greek_exp, dict):
            payload = greek_exp.get("data", greek_exp)
            if isinstance(payload, list) and payload:
                payload = payload[0]  # latest snapshot
            if isinstance(payload, dict):
                net_gex = self._safe_float(payload.get("gamma"))
                net_dex = self._safe_float(payload.get("delta"))
                net_vex = self._safe_float(payload.get("vega"))
                net_chex = self._safe_float(payload.get("charm"))

        # From greek-flow: directional flow, may have better charm
        if isinstance(greek_flow, dict):
            flow_data = greek_flow.get("data", greek_flow)
            if isinstance(flow_data, list) and flow_data:
                flow_data = flow_data[-1]  # latest
            if isinstance(flow_data, dict):
                charm_val = self._safe_float(flow_data.get("charm"))
                if charm_val != 0.0:
                    net_chex = charm_val
                # Override vex with dir_vega_flow if available
                vega_flow = self._safe_float(flow_data.get("dir_vega_flow"))
                if vega_flow != 0.0:
                    net_vex = vega_flow

        # Regime from spot GEX net total
        if isinstance(spot_gex, dict):
            strikes_raw = spot_gex.get("data", [])
            if isinstance(strikes_raw, list):
                total_gamma = sum(
                    self._compute_net_gamma(row)
                    for row in strikes_raw
                    if isinstance(row, dict)
                )
                if total_gamma > 0:
                    regime = "positive"
                    hedge_direction = "buying"
                elif total_gamma < 0:
                    regime = "negative"
                    hedge_direction = "selling"
        elif net_gex is not None:
            if net_gex > 0:
                regime = "positive"
                hedge_direction = "buying"
            elif net_gex < 0:
                regime = "negative"
                hedge_direction = "selling"

        return DealerPositioning(
            net_gex=net_gex if net_gex != 0.0 else None,
            net_dex=net_dex if net_dex != 0.0 else None,
            net_vex=net_vex if net_vex != 0.0 else None,
            net_chex=net_chex if net_chex != 0.0 else None,
            regime=regime,
            hedge_direction=hedge_direction,
        )

    def _parse_zero_dte(self, data: dict | None) -> ZeroDTEState:
        """Extract 0DTE share from greek-exposure/expiry data."""
        if not data:
            return ZeroDTEState()

        expiries = data.get("data", [])
        if not isinstance(expiries, list) or not expiries:
            return ZeroDTEState()

        from datetime import date

        today_str = date.today().isoformat()
        total_gamma = 0.0
        zero_dte_gamma = 0.0

        for row in expiries:
            if not isinstance(row, dict):
                continue
            gamma = abs(self._safe_float(row.get("gamma", row.get("net_gamma"))))
            total_gamma += gamma
            expiry_date = str(row.get("expiry", row.get("expiration_date", "")))
            if expiry_date.startswith(today_str):
                zero_dte_gamma = gamma

        gex_pct = zero_dte_gamma / total_gamma if total_gamma > 0 else None
        pin_risk = "low"
        if gex_pct is not None:
            if gex_pct > 0.5:
                pin_risk = "high"
            elif gex_pct > 0.25:
                pin_risk = "medium"

        return ZeroDTEState(
            gex_pct_of_total=round(gex_pct, 4) if gex_pct is not None else None,
            pin_risk=pin_risk,
        )

    @staticmethod
    def _compute_net_gamma(row: dict) -> float:
        """Net dealer gamma at a strike from UW spot GEX data."""
        call_net = (
            float(row.get("call_gamma_oi", 0) or 0)
            + float(row.get("call_gamma_ask", 0) or 0)
            - float(row.get("call_gamma_bid", 0) or 0)
        )
        put_net = (
            float(row.get("put_gamma_oi", 0) or 0)
            + float(row.get("put_gamma_ask", 0) or 0)
            - float(row.get("put_gamma_bid", 0) or 0)
        )
        return call_net - put_net

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            if value is None:
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _no_key_gex_result(self) -> UWGEXResult:
        return UWGEXResult(
            levels=GEXLevels(),
            dealer=DealerPositioning(),
            zero_dte=ZeroDTEState(),
            source_health=SourceHealth(
                name="unusual_whales_gex",
                status="pending",
                ttl_sec=60,
                error_msg="API key not configured",
            ),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_institutional_flow(self, ticker: str = "QQQ") -> dict | None:
        """GET /api/option-trades/flow-alerts — institutional flow direction."""
        cache_key = f"inst_flow_{ticker}"
        cached = self._cache.get(cache_key, 300)
        if cached is not None:
            return cached

        try:
            response = await self._client.get(
                "/api/option-trades/flow-alerts",
                params={"ticker_symbol": ticker, "min_premium": 500000, "limit": 100},
            )
            response.raise_for_status()
            data = response.json()
            self._cache.set(cache_key, data)
            return data
        except Exception as exc:
            logger.debug("UW fetch_institutional_flow failed for %s: %s", ticker, exc)
            return None

    async def fetch_13f_ownership(self, ticker: str = "QQQ") -> dict | None:
        """GET /api/stock/{ticker}/ownership — top institutional holders."""
        cache_key = f"ownership_{ticker}"
        cached = self._cache.get(cache_key, 3600)
        if cached is not None:
            return cached

        try:
            response = await self._client.get(
                f"/api/stock/{ticker}/ownership",
                params={"limit": 10},
            )
            response.raise_for_status()
            data = response.json()
            self._cache.set(cache_key, data)
            return data
        except Exception as exc:
            logger.debug("UW fetch_13f_ownership failed for %s: %s", ticker, exc)
            return None

    async def fetch_latest_filings(self) -> dict | None:
        """GET /api/institutions/latest_filings — recent 13F filings."""
        cache_key = "latest_filings"
        cached = self._cache.get(cache_key, 3600)
        if cached is not None:
            return cached

        try:
            response = await self._client.get(
                "/api/institutions/latest_filings",
                params={"limit": 10, "order": "date", "order_direction": "desc"},
            )
            response.raise_for_status()
            data = response.json()
            self._cache.set(cache_key, data)
            return data
        except Exception as exc:
            logger.debug("UW fetch_latest_filings failed: %s", exc)
            return None

    async def fetch_market_tide(self) -> dict | None:
        """GET /api/market/market-tide — bull/bear premium balance."""
        cache_key = "market_tide"
        cached = self._cache.get(cache_key, 60)
        if cached is not None:
            return cached

        try:
            response = await self._client.get("/api/market/market-tide")
            response.raise_for_status()
            data = response.json()
            self._cache.set(cache_key, data)
            return data
        except Exception as exc:
            logger.debug("UW fetch_market_tide failed: %s", exc)
            return None

    async def fetch_dark_pool_detailed(self, ticker: str = "QQQ") -> dict | None:
        """GET /api/darkpool/{ticker} — detailed dark pool prints."""
        cache_key = f"dp_detailed_{ticker}"
        cached = self._cache.get(cache_key, 900)
        if cached is not None:
            return cached

        try:
            response = await self._client.get(
                f"/api/darkpool/{ticker}",
                params={"limit": 500},
            )
            response.raise_for_status()
            data = response.json()
            self._cache.set(cache_key, data)
            return data
        except Exception as exc:
            logger.debug("UW fetch_dark_pool_detailed failed for %s: %s", ticker, exc)
            return None

    async def fetch_oi_change(self, ticker: str = "QQQ") -> dict | None:
        """GET /api/stock/{ticker}/oi-change — OI change data."""
        cache_key = f"oi_change_{ticker}"
        cached = self._cache.get(cache_key, 300)
        if cached is not None:
            return cached

        try:
            response = await self._client.get(f"/api/stock/{ticker}/oi-change")
            response.raise_for_status()
            data = response.json()
            self._cache.set(cache_key, data)
            return data
        except Exception as exc:
            logger.debug("UW fetch_oi_change failed for %s: %s", ticker, exc)
            return None

    async def fetch_flow_alerts(self, ticker: str = "QQQ") -> dict | None:
        """GET /api/option-trades/flow-alerts — sweep/block alerts."""
        cache_key = f"flow_alerts_{ticker}"
        cached = self._cache.get(cache_key, 300)
        if cached is not None:
            return cached

        try:
            response = await self._client.get(
                "/api/option-trades/flow-alerts",
                params={"ticker_symbol": ticker, "limit": 50},
            )
            response.raise_for_status()
            data = response.json()
            self._cache.set(cache_key, data)
            return data
        except Exception as exc:
            logger.debug("UW fetch_flow_alerts failed for %s: %s", ticker, exc)
            return None

    async def poll_institutional(self) -> dict[str, dict | None]:
        """Fetch all institutional data in one call."""
        results: dict[str, dict | None] = {}
        for name, coro in [
            ("inst_flow", self.fetch_institutional_flow()),
            ("ownership", self.fetch_13f_ownership()),
            ("filings", self.fetch_latest_filings()),
            ("market_tide", self.fetch_market_tide()),
            ("dp_detailed", self.fetch_dark_pool_detailed()),
            ("oi_change", self.fetch_oi_change()),
            ("flow_alerts", self.fetch_flow_alerts()),
        ]:
            try:
                results[name] = await coro
            except Exception as exc:
                logger.debug("UW %s fetch failed: %s", name, exc)
                results[name] = None
        return results


__all__ = ["UnusualWhalesAdapter", "DarkPoolSummary", "DarkPoolLevel", "UWGEXResult"]
