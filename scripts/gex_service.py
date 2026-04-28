from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import signal
import sys
import time
import http.client
import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


LOGGER = logging.getLogger("gex_service")
DEFAULT_OUTPUT = Path.home() / "Documents" / "NinjaTrader 8" / "templates" / "DEEP6" / "gex_command.json"
MASSIVE_BASE = "https://api.massive.com"
YAHOO_QUOTE = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"
CONTRACT_MULTIPLIER = 100.0
DEFAULT_ANCHOR_WINDOW_PCT = 0.07
ENV_FILE_CANDIDATES = (
    Path(".env"),
    Path(".env.local"),
    Path("scripts/.env"),
    Path("scripts/.env.local"),
)


@dataclass(slots=True)
class ExposureSnapshot:
    gex: float = 0.0
    vex: float = 0.0
    dex: float = 0.0
    chex: float = 0.0
    call_vex: float = 0.0
    put_vex: float = 0.0


@dataclass(slots=True)
class AggregateBook:
    spot: float
    by_strike: dict[float, ExposureSnapshot] = field(default_factory=dict)
    total_gex: float = 0.0
    total_vex: float = 0.0
    total_dex: float = 0.0
    total_chex: float = 0.0
    total_call_vex: float = 0.0
    total_put_vex: float = 0.0
    contract_count: int = 0
    expiry_dates: set[str] = field(default_factory=set)


@dataclass(slots=True)
class Level:
    key: str
    symbol: str
    label: str
    action: str
    price: float
    value: float
    direction: str = ""


def compute_gex(*, gamma: float, open_interest: int, spot: float) -> float:
    return gamma * open_interest * CONTRACT_MULTIPLIER * spot * spot * 0.01


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _safe_sigma(sigma: float) -> float:
    return max(abs(sigma), 1e-6)


def _safe_time(t: float) -> float:
    return max(t, 1e-6)


def _d1_d2(*, spot: float, strike: float, time_to_expiry_years: float, rate: float, dividend_yield: float, sigma: float) -> tuple[float, float]:
    sigma = _safe_sigma(sigma)
    t = _safe_time(time_to_expiry_years)
    sqrt_t = math.sqrt(t)
    d1 = (math.log(max(spot, 1e-9) / max(strike, 1e-9)) + (rate - dividend_yield + 0.5 * sigma * sigma) * t) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    return d1, d2


def compute_delta(*, option_type: str, spot: float, strike: float, time_to_expiry_years: float, rate: float, dividend_yield: float, sigma: float) -> float:
    d1, _ = _d1_d2(spot=spot, strike=strike, time_to_expiry_years=time_to_expiry_years, rate=rate, dividend_yield=dividend_yield, sigma=sigma)
    disc = math.exp(-dividend_yield * _safe_time(time_to_expiry_years))
    if option_type.lower() == "call":
        return disc * _norm_cdf(d1)
    return disc * (_norm_cdf(d1) - 1.0)


def compute_gamma(*, spot: float, strike: float, time_to_expiry_years: float, rate: float, dividend_yield: float, sigma: float) -> float:
    d1, _ = _d1_d2(spot=spot, strike=strike, time_to_expiry_years=time_to_expiry_years, rate=rate, dividend_yield=dividend_yield, sigma=sigma)
    t = _safe_time(time_to_expiry_years)
    sigma = _safe_sigma(sigma)
    return math.exp(-dividend_yield * t) * _norm_pdf(d1) / (max(spot, 1e-9) * sigma * math.sqrt(t))


def compute_vanna(*, spot: float, strike: float, time_to_expiry_years: float, rate: float, dividend_yield: float, sigma: float) -> float:
    d1, d2 = _d1_d2(spot=spot, strike=strike, time_to_expiry_years=time_to_expiry_years, rate=rate, dividend_yield=dividend_yield, sigma=sigma)
    t = _safe_time(time_to_expiry_years)
    sigma = _safe_sigma(sigma)
    return -math.exp(-dividend_yield * t) * _norm_pdf(d1) * d2 / sigma


def compute_charm(*, spot: float, strike: float, time_to_expiry_years: float, rate: float, dividend_yield: float, sigma: float) -> float:
    d1, d2 = _d1_d2(spot=spot, strike=strike, time_to_expiry_years=time_to_expiry_years, rate=rate, dividend_yield=dividend_yield, sigma=sigma)
    t = _safe_time(time_to_expiry_years)
    sigma = _safe_sigma(sigma)
    term = rate - dividend_yield - (d2 * sigma) / (2.0 * t)
    return -math.exp(-dividend_yield * t) * (_norm_pdf(d1) * term - dividend_yield * _norm_cdf(d1))


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        if isinstance(value, str) and not value.strip():
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


def _redact_url(url: str) -> str:
    if not url:
        return url
    return re.sub(r"([?&]apiKey=)[^&]+", r"\1[REDACTED]", url, flags=re.IGNORECASE)


def _http_json(url: str, headers: dict[str, str] | None = None, *, attempts: int = 4, timeout: int = 30) -> dict[str, Any]:
    req = Request(url, headers=headers or {"User-Agent": "DEEP6-gex-service/1.0"})
    last_exc: Exception | None = None
    safe_url = _redact_url(url)
    for attempt in range(1, max(1, attempts) + 1):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (URLError, TimeoutError, socket.timeout, http.client.IncompleteRead, ConnectionResetError, ValueError) as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            sleep_s = min(8.0, 1.5 * attempt)
            LOGGER.warning("HTTP retry %s/%s for %s after %s: %s", attempt, attempts, safe_url, type(exc).__name__, exc)
            time.sleep(sleep_s)
    assert last_exc is not None
    raise last_exc


def fetch_yahoo_price(symbol: str) -> float:
    payload = _http_json(YAHOO_QUOTE.format(symbol=symbol))
    result = payload.get("chart", {}).get("result", [])
    if not result:
        raise ValueError(f"No Yahoo quote result for {symbol}")
    meta = result[0].get("meta", {})
    price = _to_float(meta.get("regularMarketPrice"))
    if price > 0:
        return price
    closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
    for value in reversed(closes):
        price = _to_float(value)
        if price > 0:
            return price
    raise ValueError(f"No valid Yahoo price for {symbol}")


def fetch_massive_spot(symbol: str, api_key: str) -> float:
    query = urlencode({"apiKey": api_key})
    url = f"{MASSIVE_BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}?{query}"
    payload = _http_json(url)
    ticker = payload.get("ticker", {})
    day = ticker.get("day", {})
    last_trade = ticker.get("lastTrade", {})
    for candidate in (day.get("c"), ticker.get("todaysChangePerc"), last_trade.get("p")):
        value = _to_float(candidate)
        if value > 0:
            return value
    raise ValueError(f"No valid Massive spot for {symbol}")


def _extract_option_row(result: dict[str, Any]) -> tuple[float, str, int, float, float, float, str] | None:
    details = result.get("details", {})
    greeks = result.get("greeks", {})
    strike = _to_float(details.get("strike_price", result.get("strike_price")))
    option_type = (details.get("contract_type") or result.get("contract_type") or "").lower()
    open_interest = _to_int(result.get("open_interest"))
    expiry = details.get("expiration_date") or result.get("expiration_date") or ""
    if strike <= 0 or option_type not in {"call", "put"} or open_interest <= 0 or not expiry:
        return None
    gamma = _to_float(greeks.get("gamma", result.get("gamma")))
    delta = _to_float(greeks.get("delta", result.get("delta")))
    sigma = _to_float(result.get("implied_volatility", greeks.get("implied_volatility", details.get("implied_volatility"))))
    return strike, option_type, open_interest, gamma, delta, sigma, expiry


def _time_to_expiry_years(expiry_date: str) -> float:
    expiry = datetime.fromisoformat(expiry_date).replace(tzinfo=UTC) + timedelta(hours=20)
    seconds = max((expiry - datetime.now(UTC)).total_seconds(), 3600.0)
    return seconds / (365.0 * 24.0 * 3600.0)


def fetch_full_chain(underlying: str, api_key: str, *, max_pages: int = 120) -> list[dict[str, Any]]:
    query = urlencode({"limit": 250, "apiKey": api_key})
    next_url = f"{MASSIVE_BASE}/v3/snapshot/options/{underlying}?{query}"
    rows: list[dict[str, Any]] = []
    pages = 0
    while next_url and pages < max_pages:
        pages += 1
        payload = _http_json(next_url)
        rows.extend(payload.get("results", []))
        raw_next = payload.get("next_url")
        if not raw_next:
            break
        next_url = raw_next if "apiKey=" in raw_next else f"{raw_next}&apiKey={api_key}"
    return rows


def build_aggregate_book(*, rows: list[dict[str, Any]], spot: float, rate: float, dividend_yield: float) -> AggregateBook:
    book = AggregateBook(spot=spot)
    for result in rows:
        parsed = _extract_option_row(result)
        if parsed is None:
            continue
        strike, option_type, open_interest, gamma, delta, sigma, expiry = parsed
        t = _time_to_expiry_years(expiry)
        sigma = max(_to_float(sigma, 0.0), 0.05)
        if gamma == 0.0:
            gamma = compute_gamma(spot=spot, strike=strike, time_to_expiry_years=t, rate=rate, dividend_yield=dividend_yield, sigma=sigma)
        if delta == 0.0:
            delta = compute_delta(option_type=option_type, spot=spot, strike=strike, time_to_expiry_years=t, rate=rate, dividend_yield=dividend_yield, sigma=sigma)
        vanna = compute_vanna(spot=spot, strike=strike, time_to_expiry_years=t, rate=rate, dividend_yield=dividend_yield, sigma=sigma)
        charm = compute_charm(spot=spot, strike=strike, time_to_expiry_years=t, rate=rate, dividend_yield=dividend_yield, sigma=sigma)

        snap = book.by_strike.setdefault(strike, ExposureSnapshot())
        gex = compute_gex(gamma=gamma, open_interest=open_interest, spot=spot)
        signed_gex = gex if option_type == "call" else -gex
        vex = vanna * open_interest * CONTRACT_MULTIPLIER * spot
        dex = delta * open_interest * CONTRACT_MULTIPLIER * spot
        chex = charm * open_interest * CONTRACT_MULTIPLIER * spot

        snap.gex += signed_gex
        snap.vex += vex
        snap.dex += dex
        snap.chex += chex
        if option_type == "call":
            snap.call_vex += vex
        else:
            snap.put_vex += vex

        book.total_gex += signed_gex
        book.total_vex += vex
        book.total_dex += dex
        book.total_chex += chex
        book.total_call_vex += vex if option_type == "call" else 0.0
        book.total_put_vex += vex if option_type == "put" else 0.0
        book.contract_count += 1
        book.expiry_dates.add(expiry)
    return book


def _pick_max(strikes: dict[float, float]) -> tuple[float, float]:
    strike = max(strikes, key=lambda k: strikes[k])
    return strike, strikes[strike]


def _pick_min(strikes: dict[float, float]) -> tuple[float, float]:
    strike = min(strikes, key=lambda k: strikes[k])
    return strike, strikes[strike]


def _pick_abs(strikes: dict[float, float]) -> tuple[float, float]:
    strike = max(strikes, key=lambda k: abs(strikes[k]))
    return strike, strikes[strike]


def _nearest_gamma_flip(strikes: list[float], gex_map: dict[float, float], spot: float) -> float:
    nearest_flip = spot
    nearest_distance = float("inf")
    for left, right in zip(strikes, strikes[1:]):
        lval = gex_map.get(left, 0.0)
        rval = gex_map.get(right, 0.0)
        candidate = None
        if lval == 0.0:
            candidate = left
        elif lval * rval < 0:
            candidate = left + (right - left) * abs(lval) / (abs(lval) + abs(rval))
        if candidate is None:
            continue
        distance = abs(candidate - spot)
        if distance < nearest_distance:
            nearest_distance = distance
            nearest_flip = candidate
    return nearest_flip


def _windowed_map(source: dict[float, float], low: float, high: float) -> dict[str, float]:
    return {strike: value for strike, value in source.items() if low <= strike <= high}


def _apply_distance_cap(source: dict[float, float], spot: float, *, max_above_pct: float | None = None, max_below_pct: float | None = None) -> dict[float, float]:
    filtered: dict[float, float] = {}
    for strike, value in source.items():
        if strike >= spot and max_above_pct is not None:
            if strike > spot * (1.0 + max(0.0, max_above_pct)):
                continue
        if strike <= spot and max_below_pct is not None:
            if strike < spot * (1.0 - max(0.0, max_below_pct)):
                continue
        filtered[strike] = value
    return filtered


def choose_anchor_levels(
    book: AggregateBook,
    *,
    anchor_window_pct: float = DEFAULT_ANCHOR_WINDOW_PCT,
    max_above_pct: float | None = None,
    max_below_pct: float | None = None,
) -> dict[str, Level]:
    strikes = sorted(book.by_strike)
    if not strikes:
        return {}

    gex_map = {strike: snap.gex for strike, snap in book.by_strike.items()}
    call_vex_map = {strike: snap.call_vex for strike, snap in book.by_strike.items() if snap.call_vex != 0.0}
    put_vex_map = {strike: snap.put_vex for strike, snap in book.by_strike.items() if snap.put_vex != 0.0}
    dex_map = {strike: snap.dex for strike, snap in book.by_strike.items()}
    chex_map = {strike: snap.chex for strike, snap in book.by_strike.items()}

    window_pct = max(0.01, anchor_window_pct)
    low = book.spot * (1.0 - window_pct)
    high = book.spot * (1.0 + window_pct)
    window_strikes = [strike for strike in strikes if low <= strike <= high]
    if len(window_strikes) < 8:
        low = book.spot * (1.0 - max(window_pct, 0.12))
        high = book.spot * (1.0 + max(window_pct, 0.12))
        window_strikes = [strike for strike in strikes if low <= strike <= high]
    if not window_strikes:
        window_strikes = strikes
        low = strikes[0]
        high = strikes[-1]

    gex_window = _windowed_map(gex_map, low, high) or gex_map
    call_vex_window = _windowed_map(call_vex_map, low, high) or call_vex_map or gex_window
    put_vex_window = _windowed_map(put_vex_map, low, high) or put_vex_map or gex_window
    dex_window = _windowed_map(dex_map, low, high) or dex_map
    chex_window = _windowed_map(chex_map, low, high) or chex_map

    gamma_flip = _nearest_gamma_flip(window_strikes, gex_map, book.spot)

    gex_capped = _apply_distance_cap(gex_window, book.spot, max_above_pct=max_above_pct, max_below_pct=max_below_pct) or gex_window
    call_vex_capped = _apply_distance_cap(call_vex_window, book.spot, max_above_pct=max_above_pct) or call_vex_window
    put_vex_capped = _apply_distance_cap(put_vex_window, book.spot, max_below_pct=max_below_pct) or put_vex_window
    dex_capped = _apply_distance_cap(dex_window, book.spot, max_above_pct=max_above_pct, max_below_pct=max_below_pct) or dex_window
    chex_capped = _apply_distance_cap(chex_window, book.spot, max_above_pct=max_above_pct, max_below_pct=max_below_pct) or chex_window

    above_spot = {k: v for k, v in gex_capped.items() if k >= book.spot}
    below_spot = {k: v for k, v in gex_capped.items() if k <= book.spot}
    call_wall_strike, call_wall_value = _pick_max(above_spot or gex_capped)
    put_wall_strike, put_wall_value = _pick_min(below_spot or gex_capped)
    hvl_strike, hvl_value = _pick_abs(gex_capped)
    vanna_call_strike, vanna_call_value = _pick_max(call_vex_capped)

    negative_puts = {k: v for k, v in put_vex_capped.items() if v < 0}
    if negative_puts:
        vanna_put_strike, vanna_put_value = _pick_min(negative_puts)
    else:
        vanna_put_strike, vanna_put_value = _pick_abs(put_vex_capped)

    dex_peak_strike, dex_peak_value = _pick_abs(dex_capped)
    charm_strike, charm_value = _pick_abs(chex_capped)
    charm_direction = "▲" if charm_value >= 0 else "▼"

    return {
        "gamma_flip": Level("gamma_flip", "⚡", "GAMMA FLIP", "REGIME PIVOT", gamma_flip, 0.0),
        "call_wall": Level("call_wall", "▲", "CALL WALL", "RESISTANCE — FADE", call_wall_strike, call_wall_value),
        "put_wall": Level("put_wall", "▼", "PUT WALL", "SUPPORT — BOUNCE", put_wall_strike, put_wall_value),
        "hvl": Level("hvl", "◆", "HVL", "PIN LEVEL", hvl_strike, hvl_value),
        "vanna_call": Level("vanna_call", "⟐", "VANNA CALL", "VOL↓ = BUY FUEL", vanna_call_strike, vanna_call_value),
        "vanna_put": Level("vanna_put", "⟐", "VANNA PUT", "VOL↑ = SELL FUEL", vanna_put_strike, vanna_put_value),
        "dex_peak": Level("dex_peak", "◎", "DEX PEAK", "PRICE MAGNET", dex_peak_strike, dex_peak_value),
        "charm_drift": Level("charm_drift", "⏱", f"CHARM DRIFT {charm_direction}", f"PM DRIFT {charm_direction}", charm_strike, charm_value, direction=charm_direction),
    }


def map_levels_to_futures(levels: dict[str, Level], ratio: float) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for key, level in levels.items():
        mapped[key] = {
            "symbol": level.symbol,
            "label": level.label,
            "action": level.action,
            "price": level.price * ratio,
            "source_price": level.price,
            "value": level.value,
            "direction": level.direction,
        }
    return mapped


def build_payload(*, generated_at_utc: str, assets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "service": "gex_service",
        "service_version": "1.0.0",
        "generated_at_utc": generated_at_utc,
        "assets": assets,
    }


def _is_zero_dte(expiry_dates: set[str]) -> bool:
    today = datetime.now(UTC).date().isoformat()
    return today in expiry_dates


def write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    tmp.replace(path)


class GexService:
    def __init__(
        self,
        *,
        api_key: str,
        output_path: Path,
        chain_refresh_seconds: int,
        spot_refresh_seconds: int,
        rate: float,
        dividend_yield: float,
        qqq_underlying: str,
        spx_underlying: str,
        anchor_window_pct: float,
        max_above_pct: float | None,
        max_below_pct: float | None,
    ) -> None:
        self.api_key = api_key
        self.output_path = output_path
        self.chain_refresh_seconds = chain_refresh_seconds
        self.spot_refresh_seconds = spot_refresh_seconds
        self.rate = rate
        self.dividend_yield = dividend_yield
        self.qqq_underlying = qqq_underlying
        self.spx_underlying = spx_underlying
        self.anchor_window_pct = anchor_window_pct
        self.max_above_pct = max_above_pct
        self.max_below_pct = max_below_pct
        self._running = True
        self._state: dict[str, dict[str, Any]] = {}

    def stop(self, *_: Any) -> None:
        LOGGER.info("Stop signal received")
        self._running = False

    def _fetch_asset_chain(self, underlying: str) -> AggregateBook:
        spot = fetch_yahoo_price("QQQ" if underlying == self.qqq_underlying else "^SPX")
        rows = fetch_full_chain(underlying, self.api_key)
        return build_aggregate_book(rows=rows, spot=spot, rate=self.rate, dividend_yield=self.dividend_yield)

    def _refresh_chains(self) -> None:
        assets = [
            (self.qqq_underlying, "QQQ", "NQ", "NQ=F"),
            (self.spx_underlying, "SPX", "ES", "ES=F"),
        ]
        for vendor_symbol, label, futures_root, yahoo_futures in assets:
            try:
                book = self._fetch_asset_chain(vendor_symbol)
                levels = choose_anchor_levels(
                    book,
                    anchor_window_pct=self.anchor_window_pct,
                    max_above_pct=self.max_above_pct,
                    max_below_pct=self.max_below_pct,
                )
                self._state[label] = {
                    "label": label,
                    "futures_root": futures_root,
                    "book": book,
                    "levels": levels,
                    "futures_symbol": yahoo_futures,
                    "as_of_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "last_chain_success": time.time(),
                    "chain_error": "",
                }
                LOGGER.info("Chain refresh ok: %s (%s contracts, %s strikes)", label, book.contract_count, len(book.by_strike))
            except Exception as exc:
                LOGGER.exception("Chain refresh failed for %s", label)
                state = self._state.setdefault(label, {
                    "label": label,
                    "futures_root": futures_root,
                    "futures_symbol": yahoo_futures,
                    "book": AggregateBook(spot=0.0),
                    "levels": {},
                    "as_of_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "last_chain_success": 0.0,
                    "chain_error": str(exc),
                })
                state["chain_error"] = str(exc)

    def _build_asset_payload(self, label: str, state: dict[str, Any]) -> dict[str, Any]:
        futures_spot = fetch_yahoo_price(state["futures_symbol"])
        book: AggregateBook = state["book"]
        spot = max(book.spot, 0.0)
        ratio = futures_spot / spot if spot > 0 else 0.0
        levels = map_levels_to_futures(state.get("levels", {}), ratio) if ratio > 0 else {}
        levels_list = [dict({"key": key}, **value) for key, value in levels.items()]
        now = time.time()
        age_seconds = None if not state.get("last_chain_success") else max(0, int(now - state["last_chain_success"]))
        stale = state.get("last_chain_success", 0.0) <= 0 or now - state["last_chain_success"] > self.chain_refresh_seconds * 2
        vex_regime = "VOL↓=BUY" if book.total_vex >= 0 else "VOL↑=SELL"
        charm_direction = "▲" if book.total_chex >= 0 else "▼"
        return {
            "underlying": label,
            "vendor_symbol": self.qqq_underlying if label == "QQQ" else self.spx_underlying,
            "futures_root": state["futures_root"],
            "underlying_spot": spot,
            "futures_spot": futures_spot,
            "mapped_spot": futures_spot,
            "ratio": ratio,
            "as_of_utc": state.get("as_of_utc"),
            "stale": stale,
            "age_seconds": age_seconds,
            "is_0dte": _is_zero_dte(book.expiry_dates),
            "regime": vex_regime,
            "charm_direction": charm_direction,
            "chain_error": state.get("chain_error", ""),
            "contract_count": book.contract_count,
            "strike_count": len(book.by_strike),
            "net_exposures": {
                "gex": book.total_gex,
                "vex": book.total_vex,
                "dex": book.total_dex,
                "chex": book.total_chex,
            },
            "levels": levels,
            "levels_list": levels_list,
        }

    def write_snapshot(self) -> None:
        asset_payloads = []
        for label in ("QQQ", "SPX"):
            if label in self._state:
                try:
                    asset_payloads.append(self._build_asset_payload(label, self._state[label]))
                except Exception as exc:
                    LOGGER.exception("Spot refresh failed for %s", label)
                    asset_payloads.append({
                        "underlying": label,
                        "futures_root": self._state[label].get("futures_root", ""),
                        "stale": True,
                        "chain_error": f"spot refresh failed: {exc}",
                        "levels": {},
                    })
        payload = build_payload(
            generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            assets=asset_payloads,
        )
        write_payload(self.output_path, payload)
        LOGGER.info("Wrote snapshot: %s", self.output_path)

    def run(self) -> int:
        next_chain = 0.0
        next_spot = 0.0
        while self._running:
            now = time.monotonic()
            if now >= next_chain:
                self._refresh_chains()
                next_chain = now + self.chain_refresh_seconds
            if now >= next_spot:
                self.write_snapshot()
                next_spot = now + self.spot_refresh_seconds
            time.sleep(0.25)
        return 0


def _load_env_files() -> None:
    for candidate in ENV_FILE_CANDIDATES:
        try:
            if not candidate.exists():
                continue
            for raw_line in candidate.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
        except Exception:
            LOGGER.exception("Failed reading env file: %s", candidate)



def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_optional_float(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return None if value < 0 else value


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute GEX/VEX/DEX/CHEX levels from Massive.com options chains and export them for NinjaTrader.")
    parser.add_argument("--api-key", default="", help="Massive.com API key (defaults to MASSIVE_API_KEY env var)")
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT), help="JSON output path readable by NinjaTrader")
    parser.add_argument("--chain-refresh-seconds", type=int,
        default=int(os.environ.get("GEX_CHAIN_REFRESH_SECONDS", "60")))
    parser.add_argument("--spot-refresh-seconds", type=int,
        default=int(os.environ.get("GEX_SPOT_REFRESH_SECONDS", "5")))
    parser.add_argument("--rate", type=float, default=0.05)
    parser.add_argument("--dividend-yield", type=float, default=0.0)
    parser.add_argument("--qqq-underlying", default="QQQ")
    parser.add_argument("--spx-underlying", default="SPX")
    parser.add_argument("--anchor-window-pct", type=float, default=_env_float("GEX_ANCHOR_WINDOW_PCT", DEFAULT_ANCHOR_WINDOW_PCT), help="Spot-centered strike window percentage used for anchor selection, e.g. 0.07 = 7%%")
    parser.add_argument("--max-above-pct", type=float, default=_env_optional_float("GEX_MAX_ABOVE_PCT"), help="Optional cap for above-spot levels as a percentage of spot, e.g. 0.03 = 3%% above current price")
    parser.add_argument("--max-below-pct", type=float, default=_env_optional_float("GEX_MAX_BELOW_PCT"), help="Optional cap for below-spot levels as a percentage of spot, e.g. 0.03 = 3%% below current price")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _load_env_files()
    args = parse_args(argv or sys.argv[1:])
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
    api_key = (args.api_key or os.environ.get("MASSIVE_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("Missing Massive.com API key. Use --api-key or set MASSIVE_API_KEY in .env / environment.")
    service = GexService(
        api_key=api_key,
        output_path=Path(args.output_path),
        chain_refresh_seconds=max(15, args.chain_refresh_seconds),
        spot_refresh_seconds=max(1, args.spot_refresh_seconds),
        rate=args.rate,
        dividend_yield=args.dividend_yield,
        qqq_underlying=args.qqq_underlying,
        spx_underlying=args.spx_underlying,
        anchor_window_pct=max(0.01, args.anchor_window_pct),
        max_above_pct=args.max_above_pct,
        max_below_pct=args.max_below_pct,
    )
    signal.signal(signal.SIGINT, service.stop)
    signal.signal(signal.SIGTERM, service.stop)
    return service.run()


if __name__ == "__main__":
    raise SystemExit(main())
