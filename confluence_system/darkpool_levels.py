from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import numpy as np

LOG = logging.getLogger("darkpool_levels")

UW_BASE_URL = os.getenv("UW_BASE_URL", "https://api.unusualwhales.com")
UW_API_KEY = os.getenv("UW_API_KEY", "")
UW_CLIENT_API_ID = "100001"
FLASHALPHA_BASE = os.getenv("FLASHALPHA_BASE", "https://api.flashalpha.com/v1")
FLASHALPHA_API_KEY = os.getenv("FLASHALPHA_API_KEY", "")
HTTP_TIMEOUT_SEC = 15.0
MAX_PRINTS_PER_TICKER = 500
MAX_LEVELS = 15
CLUSTER_PCT = 0.005
DEFAULT_MIN_PREMIUM = 1_000_000.0
DEFAULT_MIN_SIZE = 100
MAJOR_PREMIUM_THRESHOLD = 500_000_000.0
UW_RATE_LIMIT_PER_MIN = 120
BREAKER_THRESHOLD = 5
BREAKER_RESET_SEC = 120.0
JSON_PATH = Path(r"C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\dp_levels_nt8.json")

NQ_COMPONENTS: dict[str, dict[str, float | str]] = {
    "QQQ": {"weight": 1.0, "type": "etf"},
    "AAPL": {"weight": 0.09, "type": "component"},
    "MSFT": {"weight": 0.08, "type": "component"},
    "NVDA": {"weight": 0.08, "type": "component"},
    "GOOGL": {"weight": 0.05, "type": "component"},
    "AMZN": {"weight": 0.05, "type": "component"},
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


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
        return int(value)
    except (TypeError, ValueError):
        return default


class AsyncRateLimiter:
    def __init__(self, rate_per_minute: int) -> None:
        self._interval = 60.0 / max(rate_per_minute, 1)
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = self._next_allowed - now
            if delay > 0:
                await asyncio.sleep(delay)
                now = time.monotonic()
            self._next_allowed = now + self._interval


class CircuitBreaker:
    def __init__(self, threshold: int = BREAKER_THRESHOLD, reset_seconds: float = BREAKER_RESET_SEC) -> None:
        self.threshold = threshold
        self.reset_seconds = reset_seconds
        self.consecutive_failures = 0
        self.opened_at = 0.0

    def allow_request(self) -> bool:
        if self.consecutive_failures < self.threshold:
            return True
        if (time.monotonic() - self.opened_at) >= self.reset_seconds:
            self.consecutive_failures = 0
            self.opened_at = 0.0
            return True
        return False

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.opened_at = 0.0

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.threshold and not self.opened_at:
            self.opened_at = time.monotonic()


_uw_rate_limiter = AsyncRateLimiter(UW_RATE_LIMIT_PER_MIN)
_uw_circuit_breaker = CircuitBreaker()


def compute_aggression(print_row: dict[str, Any]) -> float:
    bid = _to_float(print_row.get("nbbo_bid"))
    ask = _to_float(print_row.get("nbbo_ask"))
    price = _to_float(print_row.get("price"))
    spread = ask - bid
    if spread <= 0:
        return 0.0
    return (price - ((bid + ask) / 2.0)) / spread


def normalize_print(print_row: dict[str, Any]) -> dict[str, Any] | None:
    if print_row.get("canceled"):
        return None
    price = _to_float(print_row.get("price"))
    premium = _to_float(print_row.get("premium"))
    shares = _to_int(print_row.get("size"))
    if price <= 0 or premium <= 0 or shares <= 0:
        return None
    ts = _parse_ts(print_row.get("executed_at") or print_row.get("trf_executed_at"))
    return {
        **print_row,
        "ticker": str(print_row.get("ticker") or "").upper(),
        "price": price,
        "premium": premium,
        "size": shares,
        "aggression": compute_aggression(print_row),
        "_executed_dt": ts,
    }


def cluster_dark_pool_prints(prints: list[dict[str, Any]], cluster_pct: float = CLUSTER_PCT) -> list[dict[str, Any]]:
    """
    Cluster dark pool prints by price proximity (0.5% default).
    Returns clusters sorted by total_premium descending.
    """
    normalized = [p for raw in prints if (p := normalize_print(raw))]
    if not normalized:
        return []

    normalized.sort(key=lambda row: row["price"])
    grouped: list[list[dict[str, Any]]] = []

    for row in normalized:
        if not grouped:
            grouped.append([row])
            continue
        current = grouped[-1]
        prices = np.array([item["price"] for item in current], dtype=float)
        premiums = np.array([item["premium"] for item in current], dtype=float)
        center = float(np.average(prices, weights=premiums)) if premiums.sum() > 0 else float(prices.mean())
        if abs(row["price"] - center) / max(center, 1e-9) <= cluster_pct:
            current.append(row)
        else:
            grouped.append([row])

    clusters: list[dict[str, Any]] = []
    for cluster_rows in grouped:
        prices = np.array([item["price"] for item in cluster_rows], dtype=float)
        premiums = np.array([item["premium"] for item in cluster_rows], dtype=float)
        shares = np.array([item["size"] for item in cluster_rows], dtype=float)
        aggressions = np.array([item["aggression"] for item in cluster_rows], dtype=float)
        timestamps = [item["_executed_dt"] for item in cluster_rows if item.get("_executed_dt")]
        total_premium = float(premiums.sum())
        avg_aggression = float(aggressions.mean()) if len(aggressions) else 0.0
        clusters.append(
            {
                "ticker": cluster_rows[0]["ticker"],
                "level": float(np.average(prices, weights=premiums)) if total_premium > 0 else float(prices.mean()),
                "total_premium": total_premium,
                "total_shares": int(shares.sum()),
                "print_count": len(cluster_rows),
                "avg_aggression": avg_aggression,
                "first_seen": min(timestamps).isoformat() if timestamps else None,
                "type": "SUPPORT" if avg_aggression > 0 else "RESIST",
                "classification": "MAJOR" if total_premium > MAJOR_PREMIUM_THRESHOLD or len(cluster_rows) > 50 else "STD",
            }
        )

    clusters.sort(key=lambda item: item["total_premium"], reverse=True)
    return clusters


async def _get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    params: dict[str, Any],
    label: str,
    breaker: CircuitBreaker | None = None,
    limiter: AsyncRateLimiter | None = None,
) -> dict[str, Any] | None:
    if breaker and not breaker.allow_request():
        LOG.warning("%s skipped: circuit breaker open", label)
        return None

    last_exc: Exception | None = None
    for attempt in range(5):
        try:
            if limiter:
                await limiter.wait()
            response = await client.get(url, headers=headers, params=params)
            if response.status_code == 429:
                raise httpx.HTTPStatusError("429 rate limited", request=response.request, response=response)
            response.raise_for_status()
            payload = response.json()
            if breaker:
                breaker.record_success()
            return payload if isinstance(payload, dict) else None
        except Exception as exc:
            last_exc = exc
            if breaker:
                breaker.record_failure()
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code == 429:
                await asyncio.sleep(min(2**attempt, 16))
            else:
                await asyncio.sleep(0.5 * (attempt + 1))
    LOG.error("%s failed: %s", label, last_exc)
    return None


async def fetch_uw_darkpool(
    client: httpx.AsyncClient,
    ticker: str,
    *,
    query_date: str,
    min_premium: float = DEFAULT_MIN_PREMIUM,
    min_size: int = DEFAULT_MIN_SIZE,
    limit: int = MAX_PRINTS_PER_TICKER,
) -> list[dict[str, Any]]:
    if not UW_API_KEY:
        LOG.warning("UW_API_KEY missing; dark pool fetch skipped for %s", ticker)
        return []

    url = f"{UW_BASE_URL.rstrip('/')}/api/darkpool/{ticker}"
    headers = {
        "Authorization": f"Bearer {UW_API_KEY}",
        "UW-CLIENT-API-ID": UW_CLIENT_API_ID,
    }
    params = {
        "date": query_date,
        "min_premium": min_premium,
        "min_size": min_size,
        "limit": min(limit, MAX_PRINTS_PER_TICKER),
    }
    payload = await _get_json(
        client,
        url,
        headers=headers,
        params=params,
        label=f"uw-darkpool-{ticker}",
        breaker=_uw_circuit_breaker,
        limiter=_uw_rate_limiter,
    )
    rows = payload.get("data") if payload else []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def estimate_spot_from_prints(prints: list[dict[str, Any]]) -> float | None:
    normalized = [p for raw in prints if (p := normalize_print(raw))]
    if not normalized:
        return None
    normalized.sort(key=lambda row: row.get("_executed_dt") or datetime.min.replace(tzinfo=UTC), reverse=True)
    latest = normalized[0]["price"]
    return latest if latest > 0 else None


def convert_cluster_to_nq(
    cluster: dict[str, Any],
    *,
    ticker_spot: float,
    qqq_price: float,
    nq_price: float,
) -> float:
    ticker = cluster["ticker"]
    component = NQ_COMPONENTS.get(ticker, {"weight": 0.0, "type": "component"})
    weight = float(component["weight"])
    ticker_type = str(component["type"])

    if ticker_type == "etf":
        ratio = nq_price / qqq_price if qqq_price > 0 else 1.0
        return cluster["level"] * ratio

    price_delta = cluster["level"] - ticker_spot
    return nq_price + ((price_delta / max(qqq_price, 1e-9)) * nq_price * weight)


def merge_component_levels(levels: list[dict[str, Any]], cluster_pct: float = CLUSTER_PCT) -> list[dict[str, Any]]:
    if not levels:
        return []
    levels = sorted(levels, key=lambda item: item["price"])
    merged: list[dict[str, Any]] = []

    for level in levels:
        if not merged:
            merged.append(dict(level))
            continue
        last = merged[-1]
        if abs(level["price"] - last["price"]) / max(last["price"], 1e-9) <= cluster_pct:
            combined_premium = last["premium"] + level["premium"]
            last["price"] = (
                ((last["price"] * last["premium"]) + (level["price"] * level["premium"])) / combined_premium
                if combined_premium > 0
                else last["price"]
            )
            last["premium"] = combined_premium
            last["count"] += level["count"]
            last["shares"] += level["shares"]
            last["avg_aggression"] = (
                (last["avg_aggression"] + level["avg_aggression"]) / 2.0
            )
            last["age_hours"] = min(last["age_hours"], level["age_hours"])
            last["classification"] = "MAJOR" if "MAJOR" in {last["classification"], level["classification"]} else "STD"
            last["type"] = "SUPPORT" if last["avg_aggression"] > 0 else "RESIST"
        else:
            merged.append(dict(level))

    merged.sort(key=lambda item: item["premium"], reverse=True)
    return merged[:MAX_LEVELS]


def summarize_print_flow(prints: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = [p for raw in prints if (p := normalize_print(raw))]
    buy_volume = sum(p["size"] for p in normalized if p["aggression"] > 0)
    sell_volume = sum(p["size"] for p in normalized if p["aggression"] <= 0)
    total = buy_volume + sell_volume
    net_pct = (((buy_volume - sell_volume) / total) * 100.0) if total > 0 else 0.0
    return {
        "dp_buy_volume": int(buy_volume),
        "dp_sell_volume": int(sell_volume),
        "dp_net_pct": round(net_pct, 2),
        "dp_flow_type": "ACCUMULATION" if net_pct > 0 else "DISTRIBUTION" if net_pct < 0 else "NEUTRAL",
        "dp_total_prints": len(normalized),
        "dp_bias_score": round(abs(net_pct), 2),
        "dp_bias": "BULLISH" if net_pct > 10 else "BEARISH" if net_pct < -10 else "NEUTRAL",
    }


def load_existing_json(json_path: Path = JSON_PATH) -> dict[str, Any]:
    if not json_path.exists():
        return {}
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        LOG.warning("Failed reading existing JSON %s: %s", json_path, exc)
        return {}


def extract_stale_darkpool_payload(existing: dict[str, Any]) -> dict[str, Any]:
    darkpool_keys = {
        "dp_levels",
        "dp_levels_count",
        "dp_buy_volume",
        "dp_sell_volume",
        "dp_net_pct",
        "dp_flow_type",
        "dp_total_prints",
        "dp_bias_score",
        "dp_bias",
        "swing_equilibrium",
        "dark_pool_levels_nq",
        "dark_pool_status",
        "dp_stale",
        "dp_last_update",
    }
    stale = {key: existing[key] for key in darkpool_keys if key in existing}
    stale.setdefault("dp_levels", [])
    stale.setdefault("dp_levels_count", len(stale["dp_levels"]))
    stale["dark_pool_status"] = "stale"
    stale["dp_stale"] = True
    stale["dp_last_update"] = existing.get("dp_last_update") or _utc_now().isoformat()
    return stale


def write_merged_json(darkpool_payload: dict[str, Any], json_path: Path = JSON_PATH) -> dict[str, Any]:
    merged = load_existing_json(json_path)
    merged.update(darkpool_payload)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged


async def fetch_flashalpha_price(client: httpx.AsyncClient, symbol: str) -> float | None:
    if not FLASHALPHA_API_KEY:
        return None

    headers = {"x-api-key": FLASHALPHA_API_KEY, "Authorization": f"Bearer {FLASHALPHA_API_KEY}"}
    candidate_urls = [
        f"{FLASHALPHA_BASE.rstrip('/')}/stock/quote/{symbol}",
        f"{FLASHALPHA_BASE.rstrip('/')}/stocks/quote/{symbol}",
        f"{FLASHALPHA_BASE.rstrip('/')}/quote/stock/{symbol}",
    ]
    for url in candidate_urls:
        payload = await _get_json(client, url, headers=headers, params={}, label=f"flashalpha-{symbol}")
        if not payload:
            continue
        candidates = [
            payload.get("last"),
            payload.get("price"),
            payload.get("mid"),
            (payload.get("data") or {}).get("last") if isinstance(payload.get("data"), dict) else None,
            (payload.get("data") or {}).get("price") if isinstance(payload.get("data"), dict) else None,
            (payload.get("quote") or {}).get("last") if isinstance(payload.get("quote"), dict) else None,
        ]
        for candidate in candidates:
            value = _to_float(candidate, default=0.0)
            if value > 0:
                return value
    return None


async def resolve_reference_prices(
    client: httpx.AsyncClient,
    *,
    nq_price: float | None,
    qqq_price: float | None,
    qqq_prints: list[dict[str, Any]],
) -> tuple[float, float]:
    resolved_qqq = qqq_price or estimate_spot_from_prints(qqq_prints) or await fetch_flashalpha_price(client, "QQQ")
    resolved_nq = nq_price or await fetch_flashalpha_price(client, "NQ")
    if not resolved_qqq or not resolved_nq:
        raise ValueError("Unable to resolve nq_price/qqq_price; pass them explicitly or provide FLASHALPHA_API_KEY")
    return float(resolved_nq), float(resolved_qqq)


async def build_darkpool_payload(
    nq_price: float | None,
    qqq_price: float | None,
    *,
    query_date: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    existing = load_existing_json(JSON_PATH)
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC)

    query_date = query_date or date.today().isoformat()
    try:
        tasks = [
            fetch_uw_darkpool(
                client,
                ticker,
                query_date=query_date,
                min_premium=DEFAULT_MIN_PREMIUM if ticker == "QQQ" else max(DEFAULT_MIN_PREMIUM * 0.5, 500_000.0),
                min_size=DEFAULT_MIN_SIZE,
            )
            for ticker in NQ_COMPONENTS
        ]
        fetched = await asyncio.gather(*tasks, return_exceptions=True)
        ticker_prints: dict[str, list[dict[str, Any]]] = {}
        for ticker, result in zip(NQ_COMPONENTS, fetched, strict=True):
            if isinstance(result, Exception):
                LOG.error("Fetch failed for %s: %s", ticker, result)
                ticker_prints[ticker] = []
            else:
                ticker_prints[ticker] = result

        nq_price, qqq_price = await resolve_reference_prices(
            client,
            nq_price=nq_price,
            qqq_price=qqq_price,
            qqq_prints=ticker_prints.get("QQQ", []),
        )

        all_prints = [row for rows in ticker_prints.values() for row in rows]
        if not any(ticker_prints.values()):
            raise RuntimeError("No dark pool data returned from Unusual Whales")

        nq_levels: list[dict[str, Any]] = []
        now = _utc_now()
        for ticker, rows in ticker_prints.items():
            clusters = cluster_dark_pool_prints(rows, cluster_pct=CLUSTER_PCT)
            if not clusters:
                continue
            ticker_spot = qqq_price if ticker == "QQQ" else estimate_spot_from_prints(rows)
            if not ticker_spot or ticker_spot <= 0:
                LOG.warning("Skipping %s dark pool conversion; no spot price", ticker)
                continue

            for cluster in clusters:
                first_seen = _parse_ts(cluster.get("first_seen"))
                age_hours = round(max((now - first_seen).total_seconds(), 0.0) / 3600.0, 2) if first_seen else 0.0
                nq_levels.append(
                    {
                        "price": round(convert_cluster_to_nq(cluster, ticker_spot=ticker_spot, qqq_price=qqq_price, nq_price=nq_price), 2),
                        "type": cluster["type"],
                        "premium": round(cluster["total_premium"], 2),
                        "count": cluster["print_count"],
                        "shares": cluster["total_shares"],
                        "classification": cluster["classification"],
                        "age_hours": age_hours,
                        "avg_aggression": round(cluster["avg_aggression"], 4),
                    }
                )

        merged_levels = merge_component_levels(nq_levels, cluster_pct=CLUSTER_PCT)[:MAX_LEVELS]
        level_prices = [level["price"] for level in merged_levels]
        swing_equilibrium = round(
            float(np.average([lvl["price"] for lvl in merged_levels], weights=[lvl["premium"] for lvl in merged_levels]))
            if merged_levels
            else 0.0,
            2,
        )

        payload = {
            **summarize_print_flow(all_prints),
            "dp_levels": merged_levels,
            "dp_levels_count": len(merged_levels),
            "dark_pool_levels_nq": level_prices,
            "swing_equilibrium": swing_equilibrium,
            "dark_pool_status": "ok",
            "dp_stale": False,
            "dp_last_update": now.isoformat(),
            "dp_proxy_ticker": "QQQ",
            "dp_reference_prices": {"nq": round(nq_price, 2), "qqq": round(qqq_price, 2)},
        }
        return payload
    except Exception as exc:
        LOG.error("build_darkpool_payload failed: %s", exc)
        stale = extract_stale_darkpool_payload(existing)
        stale.setdefault("dp_proxy_ticker", "QQQ")
        return stale
    finally:
        if owns_client:
            await client.aclose()


async def update_darkpool_levels(nq_price: float, qqq_price: float) -> dict[str, Any]:
    """Fetch, cluster, convert dark pool levels. Returns dict to merge into JSON payload."""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC) as client:
        payload = await build_darkpool_payload(nq_price=nq_price, qqq_price=qqq_price, client=client)
    write_merged_json(payload, JSON_PATH)
    return payload


async def _run_cli(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC) as client:
        payload = await build_darkpool_payload(
            nq_price=args.nq_price,
            qqq_price=args.qqq_price,
            query_date=args.date,
            client=client,
        )
    merged = write_merged_json(payload, JSON_PATH)
    print(
        json.dumps(
            {
                "status": payload.get("dark_pool_status", "unknown"),
                "levels": payload.get("dp_levels_count", 0),
                "bias": payload.get("dp_bias", "NEUTRAL"),
                "flow_type": payload.get("dp_flow_type", "NEUTRAL"),
                "swing_equilibrium": payload.get("swing_equilibrium"),
                "output_path": str(JSON_PATH),
                "merged_keys": len(merged),
            },
            indent=2,
        )
    )
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build DEEP6 dark pool levels payload")
    parser.add_argument("--nq-price", type=float, default=None, help="Current NQ price")
    parser.add_argument("--qqq-price", type=float, default=None, help="Current QQQ price")
    parser.add_argument("--date", type=str, default=None, help="Query date in YYYY-MM-DD")
    return parser


def main() -> int:
    args = _build_arg_parser().parse_args()
    return asyncio.run(_run_cli(args))


if __name__ == "__main__":
    raise SystemExit(main())
