#!/usr/bin/env python3
r"""
DEEP6 Gamma Decision Surface V2

V2 sidecar for DEEP6GammaDecisionSurface.cs.  Structural detection,
behavior translation, confidence scoring, confluence zones, freshness
model, and full explainability metadata.

Outputs:
  C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\massive_gex_map_v2.json

Usage:
  python scripts/massive_gex_map_service_v2.py --once --ws-probe-seconds 0
  python scripts/massive_gex_map_service_v2.py --loop --interval 120 --ws-probe-seconds 8
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import math
import os
import random
import re
import socket
import ssl
import struct
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOG = logging.getLogger("gamma_decision_surface_v2")
MASSIVE_BASE = "https://api.massive.com"
WS_REALTIME = "wss://socket.massive.com/options"
WS_DELAYED = "wss://delayed.massive.com/options"
YAHOO_QUOTE = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"
CONTRACT_MULTIPLIER = 100.0

SCHEMA_V2 = "deep6.gamma_decision_surface.v2"
SERVICE_NAME = "gamma_decision_surface_v2"
SERVICE_VERSION = "2.0.0"

OPEN_SPACE_THRESHOLD_PTS = 80.0
CONFLUENCE_MERGE_WINDOW_PTS = 25.0

ENV_FILE_CANDIDATES = (
    Path(".env"),
    Path(".env.local"),
    Path(".env.atlas"),
    Path("scripts/.env"),
    Path("scripts/.env.local"),
)

FLASHALPHA_BASE = "https://lab.flashalpha.com"


def default_output_path() -> Path:
    wsl_docs = Path("/mnt/c/Users/Tea/Documents")
    if wsl_docs.exists():
        return wsl_docs / "NinjaTrader 8" / "templates" / "DEEP6" / "massive_gex_map_v2.json"
    return Path.home() / "Documents" / "NinjaTrader 8" / "templates" / "DEEP6" / "massive_gex_map_v2.json"


DEFAULT_OUTPUT = default_output_path()

# Module-level cache for degraded-mode re-emit
_last_good_payload: dict[str, Any] | None = None

# ---------------------------------------------------------------------------
# A1 — Base infrastructure (copied from V1, adapted names)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class StrikeExposure:
    strike: float
    call_gex: float = 0.0
    put_gex: float = 0.0
    net_gex: float = 0.0
    abs_gex: float = 0.0
    call_oi: int = 0
    put_oi: int = 0
    contract_count: int = 0
    expirations: set[str] = field(default_factory=set)


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime | None = None) -> str:
    return (dt or now_utc()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_env_files() -> None:
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
            pass


def get_api_key(cli_key: str | None = None) -> str:
    load_env_files()
    key = cli_key or os.getenv("MASSIVE_API_KEY") or ""
    if not key:
        raise SystemExit("Missing MASSIVE_API_KEY. Put it in scripts/.env.local or pass --api-key.")
    return key


def redact_url(url: str) -> str:
    return re.sub(r"([?&]apiKey=)[^&]+", r"\1[REDACTED]", url, flags=re.IGNORECASE)


def http_json(url: str, *, timeout: int = 30, attempts: int = 3) -> dict[str, Any]:
    req = Request(url, headers={"User-Agent": "DEEP6GammaDecisionSurface/2.0"})
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, socket.timeout, ConnectionError, ValueError) as exc:
            last = exc
            if attempt >= attempts:
                break
            LOG.warning("HTTP retry %s/%s for %s after %s", attempt, attempts, redact_url(url), type(exc).__name__)
            time.sleep(min(8.0, 1.5 * attempt))
    assert last is not None
    raise last


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def fetch_yahoo_price(symbol: str) -> float:
    payload = http_json(YAHOO_QUOTE.format(symbol=symbol), timeout=20, attempts=3)
    result = payload.get("chart", {}).get("result") or []
    if not result:
        raise ValueError(f"No Yahoo quote result for {symbol}")
    meta = result[0].get("meta", {})
    for key in ("regularMarketPrice", "previousClose", "chartPreviousClose"):
        px = to_float(meta.get(key))
        if px > 0:
            return px
    closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
    for value in reversed(closes):
        px = to_float(value)
        if px > 0:
            return px
    raise ValueError(f"No valid Yahoo price for {symbol}")


# ---------------------------------------------------------------------------
# FlashAlpha enrichment (optional — graceful fallback)
# ---------------------------------------------------------------------------


def get_flashalpha_api_key(cli_key: str | None = None) -> str | None:
    """Look up FlashAlpha key from CLI, env vars, or .env files.

    Returns None (not raises) if not found — FlashAlpha is optional.
    """
    load_env_files()
    return (
        cli_key
        or os.getenv("FLASHALPHA_API_KEY")
        or os.getenv("NQ_ATLAS_FLASHALPHA_API_KEY")
        or ""
    ) or None


def _http_json_with_auth(
    url: str, headers: dict[str, str], *, timeout: int = 20
) -> dict[str, Any]:
    """HTTP GET with custom headers. Thin wrapper around urllib for FlashAlpha."""
    req = Request(url, headers={"User-Agent": "DEEP6GammaDecisionSurface/2.0", **headers})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_flashalpha_summary(api_key: str, symbol: str = "QQQ") -> dict[str, Any]:
    """Fetch FlashAlpha exposure summary + levels via REST API.

    Calls two endpoints in sequence:
    - /v1/exposure/summary/{symbol}  → regime, net_gex, net_dex, net_vex, net_chex, 0DTE pct
    - /v1/exposure/levels/{symbol}   → call_wall, put_wall, gamma_flip (precise), zero_dte_magnet

    Returns a flat dict. On any failure, returns degraded dict with health='unavailable'.
    """
    auth = {"X-Api-Key": api_key}
    try:
        summary = _http_json_with_auth(f"{FLASHALPHA_BASE}/v1/exposure/summary/{symbol}", auth)
    except Exception as exc:
        LOG.warning("FlashAlpha summary fetch failed: %s", exc)
        return _flashalpha_unavailable(str(exc))

    # Levels endpoint — best-effort (non-fatal if it fails)
    try:
        lvl_raw = _http_json_with_auth(f"{FLASHALPHA_BASE}/v1/exposure/levels/{symbol}", auth)
        levels = lvl_raw.get("levels") or {}
    except Exception as exc:
        LOG.warning("FlashAlpha levels fetch failed (non-fatal): %s", exc)
        levels = {}

    return _parse_flashalpha_summary(summary, levels, symbol)


def _parse_flashalpha_summary(
    raw: dict[str, Any], levels: dict[str, Any], symbol: str
) -> dict[str, Any]:
    """Parse FlashAlpha /v1/exposure/summary + /v1/exposure/levels into a flat dict.

    Response field sources:
    - summary.exposures: net_gex, net_dex, net_vex, net_chex
    - summary.regime: regime string (e.g. "negative_gamma")
    - summary.zero_dte: zero_dte_net_gex, pct_of_total_gex
    - levels (from /v1/exposure/levels): call_wall, put_wall, gamma_flip, zero_dte_magnet
    """
    exposures = raw.get("exposures") or {}
    zero_dte = raw.get("zero_dte") or {}

    net_vex = to_float(exposures.get("net_vex", 0.0))
    net_chex = to_float(exposures.get("net_chex", 0.0))

    # VEX direction: positive VEX → when IV drops, dealers BUY → bullish tailwind
    # Negative VEX → when IV drops, dealers SELL → bearish
    vex_dir = "bullish" if net_vex > 0 else "bearish" if net_vex < 0 else "neutral"

    # CHEX direction: positive CHEX → time decay → dealers SELL → bearish drift
    # Negative CHEX → time decay → dealers BUY → bullish drift
    chex_dir = "bearish" if net_chex > 0 else "bullish" if net_chex < 0 else "neutral"

    # 0DTE pct: API returns a signed percentage (e.g. -11.6 means 0DTE is 11.6%
    # of total GEX magnitude but working against the dominant regime).
    # Store raw value; display layer uses abs().
    raw_zero_dte_pct = to_float(zero_dte.get("pct_of_total_gex", 0.0))

    # Prefer levels data for key strikes (more precise than summary.gamma_flip)
    gamma_flip_qqq = to_float(levels.get("gamma_flip")) or to_float(raw.get("gamma_flip"))
    call_wall_qqq  = to_float(levels.get("call_wall"))
    put_wall_qqq   = to_float(levels.get("put_wall"))
    zero_dte_magnet_qqq = to_float(levels.get("zero_dte_magnet"))

    return {
        "regime": raw.get("regime", "neutral"),
        "gamma_flip_qqq": gamma_flip_qqq,
        "call_wall_qqq": call_wall_qqq,
        "put_wall_qqq": put_wall_qqq,
        "net_gex": to_float(exposures.get("net_gex", 0.0)),
        "net_dex": to_float(exposures.get("net_dex", 0.0)),
        "net_vex": net_vex,
        "net_chex": net_chex,
        "vex_direction": vex_dir,
        "chex_direction": chex_dir,
        # Raw signed percentage (negative = 0DTE opposes dominant regime direction)
        "zero_dte_pct_raw": raw_zero_dte_pct,
        # Absolute fraction 0.0–1.0 for display ("what fraction of GEX is 0DTE?")
        "zero_dte_pct": round(abs(raw_zero_dte_pct) / 100.0, 4),
        "zero_dte_net_gex": to_float(zero_dte.get("net_gex", 0.0)),
        "zero_dte_magnet_qqq": zero_dte_magnet_qqq,
        "as_of_utc": iso(),
        "health": "live",
    }


def _flashalpha_unavailable(error: str = "") -> dict[str, Any]:
    """Return a degraded FlashAlpha dict when the API is unavailable."""
    return {
        "regime": "unknown",
        "gamma_flip_qqq": None,
        "call_wall_qqq": None,
        "put_wall_qqq": None,
        "net_gex": 0.0,
        "net_dex": 0.0,
        "net_vex": 0.0,
        "net_chex": 0.0,
        "vex_direction": "neutral",
        "chex_direction": "neutral",
        "zero_dte_pct_raw": 0.0,
        "zero_dte_pct": 0.0,
        "zero_dte_net_gex": 0.0,
        "zero_dte_magnet_qqq": None,
        "as_of_utc": iso(),
        "health": "unavailable",
        "error": error[:200] if error else "",
    }


def enrich_flashalpha_with_nq(fa_data: dict[str, Any], ratio: float) -> dict[str, Any]:
    """Scale QQQ-based FlashAlpha levels to NQ futures using the existing ratio."""
    enriched = dict(fa_data)

    def scale(v: float | None) -> float | None:
        if v is None or v == 0.0:
            return v
        return round(v * ratio, 2)

    enriched["gamma_flip_nq"] = scale(fa_data.get("gamma_flip_qqq"))
    enriched["call_wall_nq"] = scale(fa_data.get("call_wall_qqq"))
    enriched["put_wall_nq"] = scale(fa_data.get("put_wall_qqq"))
    enriched["zero_dte_magnet_nq"] = scale(fa_data.get("zero_dte_magnet_qqq"))
    return enriched


def fetch_option_chain(
    underlying: str, api_key: str, *, max_pages: int, max_dte: int
) -> tuple[list[dict[str, Any]], int, str]:
    query = urlencode({"limit": 250, "apiKey": api_key})
    next_url = f"{MASSIVE_BASE}/v3/snapshot/options/{underlying}?{query}"
    rows: list[dict[str, Any]] = []
    pages = 0
    cutoff = (now_utc() + timedelta(days=max_dte)).date()
    error = ""
    while next_url and pages < max_pages:
        pages += 1
        try:
            payload = http_json(next_url, timeout=35, attempts=3)
        except Exception as exc:
            error = f"chain page {pages} error: {type(exc).__name__}: {exc}"
            LOG.warning("%s", error)
            break
        for row in payload.get("results", []) or []:
            details = row.get("details", {}) or {}
            exp = str(details.get("expiration_date") or row.get("expiration_date") or "")
            if exp:
                try:
                    if datetime.fromisoformat(exp).date() > cutoff:
                        continue
                except ValueError:
                    pass
            rows.append(row)
        raw_next = payload.get("next_url") or ""
        if raw_next:
            next_url = (
                raw_next
                if "apiKey=" in raw_next
                else raw_next + ("&" if "?" in raw_next else "?") + f"apiKey={api_key}"
            )
        else:
            next_url = ""
    return rows, pages, error


def write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{random.randint(1000, 9999)}")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    os.replace(tmp, path)


def parse_optional_pct(raw: str | None) -> float | None:
    if raw is None or str(raw).strip() == "":
        return None
    return float(raw)


# ---------------------------------------------------------------------------
# WebSocket probe (copied from V1)
# ---------------------------------------------------------------------------


def _ws_recv_frame(sock: ssl.SSLSocket, timeout: float) -> str | None:
    sock.settimeout(timeout)
    try:
        hdr = sock.recv(2)
        if len(hdr) < 2:
            return None
        b1, b2 = hdr[0], hdr[1]
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack("!H", sock.recv(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", sock.recv(8))[0]
        mask = b2 & 0x80
        if mask:
            mask_key = sock.recv(4)
        data = b""
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                break
            data += chunk
        if mask:
            data = bytes(data[i] ^ mask_key[i % 4] for i in range(len(data)))
        opcode = b1 & 0x0F
        if opcode == 8:
            return None
        return data.decode("utf-8", errors="replace")
    except socket.timeout:
        return None


def _ws_send_text(sock: ssl.SSLSocket, text: str) -> None:
    payload = text.encode("utf-8")
    mask_key = os.urandom(4)
    header = bytearray([0x81])
    n = len(payload)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", n))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", n))
    masked = bytes(payload[i] ^ mask_key[i % 4] for i in range(n))
    sock.sendall(bytes(header) + mask_key + masked)


def websocket_probe(api_key: str, *, url: str, params: str, seconds: int) -> dict[str, Any]:
    status: dict[str, Any] = {
        "url_type": "realtime" if "socket.massive" in url else "delayed",
        "endpoint": url.replace("wss://", ""),
        "state": "disabled" if seconds <= 0 else "starting",
        "authenticated": False,
        "subscribed": False,
        "subscribed_contracts": 0,
        "subscription_params": params,
        "last_message_utc": "",
        "last_trade_utc": "",
        "message_count": 0,
        "trade_count": 0,
        "reconnect_count": 0,
        "last_error": "",
    }
    if seconds <= 0:
        return status
    parsed = urlparse(url)
    host = parsed.hostname or "socket.massive.com"
    path = parsed.path or "/options"
    port = parsed.port or 443
    raw: socket.socket | None = None
    try:
        raw = socket.create_connection((host, port), timeout=10)
        ctx = ssl.create_default_context()
        sock = ctx.wrap_socket(raw, server_hostname=host)
        ws_key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {ws_key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(req.encode("ascii"))
        resp = sock.recv(4096).decode("iso-8859-1", errors="replace")
        if "101" not in resp.split("\r\n", 1)[0]:
            raise RuntimeError("websocket handshake failed: " + resp.split("\r\n", 1)[0])
        _ws_recv_frame(sock, 5)
        status["state"] = "connected"
        status["last_message_utc"] = iso()
        _ws_send_text(sock, json.dumps({"action": "auth", "params": api_key}))
        auth_msg = _ws_recv_frame(sock, 8) or ""
        status["message_count"] += 1
        status["last_message_utc"] = iso()
        if "auth_success" not in auth_msg:
            raise RuntimeError("auth did not succeed: " + auth_msg[:160])
        status["authenticated"] = True
        _ws_send_text(sock, json.dumps({"action": "subscribe", "params": params}))
        sub_msg = _ws_recv_frame(sock, 8) or ""
        status["message_count"] += 1
        status["last_message_utc"] = iso()
        if "not authorized" in sub_msg.lower():
            status["state"] = "not_authorized"
            status["last_error"] = sub_msg[:220]
            return status
        status["subscribed"] = True
        status["subscribed_contracts"] = len([p for p in params.split(",") if p.strip()])
        status["state"] = "subscribed"
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            msg = _ws_recv_frame(sock, min(2.0, max(0.1, end - time.monotonic())))
            if not msg:
                continue
            status["message_count"] += 1
            status["last_message_utc"] = iso()
            if '"ev":"T"' in msg or '"ev": "T"' in msg:
                status["trade_count"] += msg.count('"ev"') or 1
                status["last_trade_utc"] = iso()
        status["state"] = "streaming" if status["message_count"] > 2 else "subscribed_no_data"
    except Exception as exc:
        status["state"] = "error"
        status["last_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            if raw:
                raw.close()
        except Exception:
            pass
    return status


# ---------------------------------------------------------------------------
# A2 — StrikeExposure + aggregate_chain (identical to V1 computation)
# ---------------------------------------------------------------------------


def compute_gex(gamma: float, open_interest: int, spot: float) -> float:
    return gamma * open_interest * CONTRACT_MULTIPLIER * spot * spot * 0.01


def aggregate_chain(rows: list[dict[str, Any]], spot: float) -> dict[float, StrikeExposure]:
    by: dict[float, StrikeExposure] = {}
    for row in rows:
        details = row.get("details", {}) or {}
        greeks = row.get("greeks", {}) or {}
        strike = to_float(details.get("strike_price", row.get("strike_price")))
        ctype = str(details.get("contract_type") or row.get("contract_type") or "").lower()
        oi = to_int(row.get("open_interest"))
        gamma = to_float(greeks.get("gamma", row.get("gamma")))
        exp = str(details.get("expiration_date") or row.get("expiration_date") or "")
        if strike <= 0 or ctype not in {"call", "put"} or oi <= 0 or gamma == 0:
            continue
        sx = by.setdefault(strike, StrikeExposure(strike=strike))
        signed = compute_gex(gamma, oi, spot)
        if ctype == "call":
            sx.call_gex += signed
            sx.call_oi += oi
            sx.net_gex += signed
        else:
            sx.put_gex += signed
            sx.put_oi += oi
            sx.net_gex -= signed
        sx.abs_gex = abs(sx.net_gex)
        sx.contract_count += 1
        if exp:
            sx.expirations.add(exp)
    return by


def spot_window(
    by: dict[float, StrikeExposure],
    spot: float,
    window_pct: float,
    max_above_pct: float | None,
    max_below_pct: float | None,
) -> list[StrikeExposure]:
    low = spot * (1.0 - window_pct)
    high = spot * (1.0 + window_pct)
    if max_below_pct is not None:
        low = max(low, spot * (1.0 - max_below_pct))
    if max_above_pct is not None:
        high = min(high, spot * (1.0 + max_above_pct))
    vals = [v for k, v in by.items() if low <= k <= high]
    if len(vals) < 6:
        low = spot * (1.0 - max(window_pct, 0.12))
        high = spot * (1.0 + max(window_pct, 0.12))
        vals = [v for k, v in by.items() if low <= k <= high]
    return sorted(vals, key=lambda x: x.strike)


def apply_near_price_cap(
    selected: list[StrikeExposure],
    futures_spot: float,
    ratio: float,
    max_futures_distance_points: float | None,
) -> list[StrikeExposure]:
    """V3 magnet rule: filter to strikes within max_futures_distance_points of futures_spot."""
    if max_futures_distance_points is None or max_futures_distance_points <= 0 or futures_spot <= 0:
        return selected
    return [
        sx
        for sx in selected
        if abs((sx.strike * ratio) - futures_spot) <= max_futures_distance_points
    ]


# ---------------------------------------------------------------------------
# A3 — Structural detection layer (NEW)
# ---------------------------------------------------------------------------


def detect_gamma_flip(strikes: list[StrikeExposure], spot: float) -> dict[str, Any] | None:
    """Linear interpolation zero-cross. Returns dict with price, confidence, meta. None if no near zero-cross."""
    if not strikes:
        return None
    best_price: float | None = None
    best_dist = float("inf")
    meta: dict[str, Any] = {"interpolated": False}
    vals = sorted(strikes, key=lambda x: x.strike)
    for left, right in zip(vals, vals[1:]):
        a, b = left.net_gex, right.net_gex
        cand: float | None = None
        if a == 0:
            cand = left.strike
        elif a * b < 0:
            cand = left.strike + (right.strike - left.strike) * abs(a) / (abs(a) + abs(b))
        if cand is not None:
            dist = abs(cand - spot)
            if dist < best_dist:
                best_price = cand
                best_dist = dist
                meta = {
                    "interpolated": cand not in (left.strike, right.strike),
                    "left_strike": left.strike,
                    "right_strike": right.strike,
                }
    if best_price is None:
        return None
    return {"price": best_price, "confidence": 1.0, "meta": meta}


def detect_call_wall(strikes: list[StrikeExposure], spot: float) -> StrikeExposure | None:
    """Max positive GEX at or above spot."""
    above_pos = [x for x in strikes if x.strike >= spot and x.net_gex > 0]
    if not above_pos:
        return None
    return max(above_pos, key=lambda x: abs(x.net_gex))


def detect_put_wall(strikes: list[StrikeExposure], spot: float) -> StrikeExposure | None:
    """Max negative GEX at or below spot."""
    below_neg = [x for x in strikes if x.strike <= spot and x.net_gex < 0]
    if not below_neg:
        return None
    return max(below_neg, key=lambda x: abs(x.net_gex))


def detect_hvl(strikes: list[StrikeExposure]) -> StrikeExposure | None:
    """Highest absolute GEX among all near candidates."""
    if not strikes:
        return None
    return max(strikes, key=lambda x: x.abs_gex)


def detect_secondary_nodes(
    strikes: list[StrikeExposure], used_strikes: set[float], max_nodes: int
) -> list[StrikeExposure]:
    """Remaining strikes sorted by abs_gex descending, excluding used_strikes."""
    remaining = [sx for sx in strikes if round(sx.strike, 6) not in used_strikes]
    remaining.sort(key=lambda x: x.abs_gex, reverse=True)
    return remaining[:max_nodes]


def detect_open_space_lanes(
    selected_levels: list[dict[str, Any]], futures_spot: float
) -> list[dict[str, Any]]:
    """Gaps > 80pts between consecutive major levels. Returns lane dicts."""
    prices = sorted({lvl["mapped_price"] for lvl in selected_levels if lvl.get("mapped_price")})
    if futures_spot not in prices:
        prices.append(futures_spot)
        prices.sort()
    lanes: list[dict[str, Any]] = []
    for i in range(len(prices) - 1):
        width = prices[i + 1] - prices[i]
        if width > OPEN_SPACE_THRESHOLD_PTS:
            lanes.append({
                "start_price": round(prices[i], 2),
                "end_price": round(prices[i + 1], 2),
                "width_pts": round(width, 2),
            })
    return lanes


# ---------------------------------------------------------------------------
# A4 — Behavior translation layer
# ---------------------------------------------------------------------------

_SELECTED_BECAUSE: dict[str, str] = {
    "put_wall": "Highest negative GEX node below current futures spot; primary dealer support zone",
    "call_wall": "Highest positive GEX node at or above current futures spot; dealer resistance ceiling",
    "hvl": "Highest absolute GEX concentration; strong price magnet / expected mean-reversion target",
    "gamma_flip": "Zero-cross of net GEX; regime transition point — positive above, negative below",
}


@dataclass
class BehaviorState:
    state: str  # DEFEND / REJECT / ATTRACT / FLIP / OPEN_SPACE
    action_hint: str  # HOLD / FADE / TARGET / WATCH_FOR_FLIP / ACCELERATION_IF_LOST


def translate_behavior(
    structural_source: str, role: str, spot: float, futures_spot: float
) -> BehaviorState:
    if structural_source == "put_wall":
        return BehaviorState("DEFEND", "HOLD")
    if structural_source == "call_wall":
        return BehaviorState("REJECT", "FADE")
    if structural_source == "hvl":
        return BehaviorState("ATTRACT", "TARGET")
    if structural_source == "gamma_flip":
        return BehaviorState("FLIP", "WATCH_FOR_FLIP")
    if structural_source == "open_space":
        return BehaviorState("OPEN_SPACE", "ACCELERATION_IF_LOST")
    # Secondary nodes: pos_gex_* above spot → REJECT/FADE, neg_gex_* below spot → DEFEND/HOLD
    if structural_source.startswith("pos_gex"):
        return BehaviorState("REJECT", "FADE")
    if structural_source.startswith("neg_gex"):
        return BehaviorState("DEFEND", "HOLD")
    # Fallback
    return BehaviorState("ATTRACT", "TARGET")


def _selected_because(structural_source: str) -> str:
    if structural_source in _SELECTED_BECAUSE:
        return _SELECTED_BECAUSE[structural_source]
    if structural_source.startswith("pos_gex"):
        return "Secondary positive GEX node above spot; secondary resistance / fade candidate"
    if structural_source.startswith("neg_gex"):
        return "Secondary negative GEX node below spot; secondary support / hold candidate"
    return "GEX node with notable exposure"


# ---------------------------------------------------------------------------
# A5 — Ranking + confidence scoring
# ---------------------------------------------------------------------------


def score_level_confidence(
    sx: StrikeExposure,
    distance_pts: float,
    futures_spot: float,
    flip_distance: float,
    *,
    max_abs_gex: float,
    max_oi: int,
    max_futures_distance_points: float,
) -> float:
    """
    Score factors:
    - abs_gex weight 40%
    - distance_proximity weight 35%
    - oi_concentration weight 15%
    - flip_proximity weight 10%
    Returns float in [0.0, 1.0]
    """
    # abs_gex normalized (40%)
    gex_norm = (sx.abs_gex / max_abs_gex) if max_abs_gex > 0 else 0.0

    # distance_proximity (35%): 1.0 when distance_pts=0, 0.0 at max_futures_distance_points
    cap = max_futures_distance_points if max_futures_distance_points > 0 else 500.0
    dist_norm = max(0.0, 1.0 - abs(distance_pts) / cap)

    # oi_concentration (15%)
    total_oi = sx.call_oi + sx.put_oi
    oi_norm = (total_oi / max_oi) if max_oi > 0 else 0.0

    # flip_proximity (10%): 1.0 when at flip, decays with distance
    flip_norm = max(0.0, 1.0 - abs(flip_distance) / cap)

    score = 0.40 * gex_norm + 0.35 * dist_norm + 0.15 * oi_norm + 0.10 * flip_norm
    return max(0.0, min(1.0, score))


def assign_tier(confidence_score: float) -> str:
    if confidence_score >= 0.75:
        return "T1"
    if confidence_score >= 0.50:
        return "T2"
    return "T3"


def rank_levels(levels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort by confidence_score descending."""
    return sorted(levels, key=lambda x: x.get("confidence_score", 0.0), reverse=True)


# ---------------------------------------------------------------------------
# A6 — Confluence zone detection
# ---------------------------------------------------------------------------


@dataclass
class ConfluenceZone:
    zone_id: str
    zone_high: float
    zone_low: float
    dominant_behavior: str
    dominant_source: str
    confidence_score: float
    tier: str
    member_level_ids: list[str]
    action_hint: str
    label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "zone_high": self.zone_high,
            "zone_low": self.zone_low,
            "dominant_behavior": self.dominant_behavior,
            "dominant_source": self.dominant_source,
            "confidence_score": round(self.confidence_score, 4),
            "tier": self.tier,
            "member_level_ids": self.member_level_ids,
            "action_hint": self.action_hint,
            "label": self.label,
        }


_CONFLUENCE_LABELS: dict[str, str] = {
    "DEFEND": "DEFEND CLUSTER",
    "REJECT": "REJECT CLUSTER",
    "FLIP": "CONFLUENCE FLIP",
    "ATTRACT": "ATTRACT ZONE",
    "OPEN_SPACE": "OPEN SPACE",
}


def detect_confluence_zones(
    levels: list[dict[str, Any]],
    futures_spot: float,
    merge_window_pts: float = CONFLUENCE_MERGE_WINDOW_PTS,
) -> list[ConfluenceZone]:
    """Group levels within merge_window_pts of each other."""
    if not levels:
        return []

    sorted_levels = sorted(levels, key=lambda x: x.get("mapped_price", 0.0))
    groups: list[list[dict[str, Any]]] = []
    current_group: list[dict[str, Any]] = [sorted_levels[0]]

    for lvl in sorted_levels[1:]:
        prev_price = current_group[-1].get("mapped_price", 0.0)
        curr_price = lvl.get("mapped_price", 0.0)
        if abs(curr_price - prev_price) <= merge_window_pts:
            current_group.append(lvl)
        else:
            groups.append(current_group)
            current_group = [lvl]
    groups.append(current_group)

    # Only form zones from groups with 2+ members
    zones: list[ConfluenceZone] = []
    for idx, group in enumerate(groups):
        if len(group) < 2:
            continue
        prices = [g["mapped_price"] for g in group]
        confidences = [g.get("confidence_score", 0.5) for g in group]
        behaviors = [g.get("behavior_state", "ATTRACT") for g in group]
        sources = [g.get("structural_source", "unknown") for g in group]
        ids = [g.get("id", "") for g in group]

        zone_confidence = sum(confidences) / len(confidences)
        # Dominant behavior = most common
        behavior_counts: dict[str, int] = {}
        for b in behaviors:
            behavior_counts[b] = behavior_counts.get(b, 0) + 1
        dominant_behavior = max(behavior_counts, key=behavior_counts.get)  # type: ignore[arg-type]
        dominant_source = sources[confidences.index(max(confidences))]
        label = _CONFLUENCE_LABELS.get(dominant_behavior, "CONFLUENCE")

        zones.append(ConfluenceZone(
            zone_id=f"cz_{idx + 1}",
            zone_high=round(max(prices), 2),
            zone_low=round(min(prices), 2),
            dominant_behavior=dominant_behavior,
            dominant_source=dominant_source,
            confidence_score=zone_confidence,
            tier=assign_tier(zone_confidence),
            member_level_ids=ids,
            action_hint=translate_behavior(dominant_source, "", 0, futures_spot).action_hint,
            label=label,
        ))
    return zones


# ---------------------------------------------------------------------------
# A7 — Freshness model
# ---------------------------------------------------------------------------


@dataclass
class FreshnessModel:
    payload_age_seconds: int = 0
    chain_snapshot_age_seconds: int = 0
    spot_age_seconds: int = 0
    futures_spot_age_seconds: int = 0
    websocket_age_seconds: int = 0
    compute_duration_ms: int = 0
    last_successful_refresh_utc: str = ""
    health_state: str = "healthy"

    def to_dict(self) -> dict[str, Any]:
        return {
            "payload_age_seconds": self.payload_age_seconds,
            "chain_snapshot_age_seconds": self.chain_snapshot_age_seconds,
            "spot_age_seconds": self.spot_age_seconds,
            "futures_spot_age_seconds": self.futures_spot_age_seconds,
            "websocket_age_seconds": self.websocket_age_seconds,
            "compute_duration_ms": self.compute_duration_ms,
            "last_successful_refresh_utc": self.last_successful_refresh_utc,
            "health_state": self.health_state,
        }


def compute_health_state(
    payload_age_seconds: int, stale_seconds: int = 180, very_stale_seconds: int = 600
) -> str:
    if payload_age_seconds >= very_stale_seconds:
        return "very_stale"
    if payload_age_seconds >= stale_seconds:
        return "stale"
    return "healthy"


# ---------------------------------------------------------------------------
# A8 + A9 — Enriched level builder + build_payload_v2 + main
# ---------------------------------------------------------------------------


def _build_enriched_levels(
    near_selected: list[StrikeExposure],
    source_spot: float,
    futures_spot: float,
    ratio: float,
    max_levels: int,
    max_futures_distance_points: float,
    underlying: str,
    futures_root: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build enriched levels with all V2 explainability metadata. Returns (levels, regime_summary)."""
    levels: list[dict[str, Any]] = []
    used_strikes: set[float] = set()

    if not near_selected:
        regime_summary = {
            "net_gex": 0.0,
            "dominant_regime": "NEUTRAL",
            "flip_price": None,
            "magnet_price": None,
        }
        return levels, regime_summary

    # Compute context for scoring
    max_abs_gex = max((sx.abs_gex for sx in near_selected), default=1.0)
    max_oi = max(((sx.call_oi + sx.put_oi) for sx in near_selected), default=1)

    # Structural detection
    flip_result = detect_gamma_flip(near_selected, source_spot)
    call_wall = detect_call_wall(near_selected, source_spot)
    put_wall = detect_put_wall(near_selected, source_spot)
    hvl = detect_hvl(near_selected)

    flip_price = flip_result["price"] if flip_result else source_spot
    flip_mapped = flip_price * ratio

    # Net GEX for regime
    total_net_gex = sum(sx.net_gex for sx in near_selected)
    if total_net_gex > 0:
        dominant_regime = "POS_GEX"
    elif total_net_gex < 0:
        dominant_regime = "NEG_GEX"
    else:
        dominant_regime = "NEUTRAL"

    magnet_price = (hvl.strike * ratio) if hvl else None

    regime_summary = {
        "net_gex": round(total_net_gex, 2),
        "dominant_regime": dominant_regime,
        "flip_price": round(flip_mapped, 2) if flip_result else None,
        "magnet_price": round(magnet_price, 2) if magnet_price else None,
    }

    def _add_level(
        role: str,
        structural_source: str,
        sx: StrikeExposure | None,
        strike: float,
        gex_value: float,
        rank: int,
        meta: dict[str, Any] | None = None,
    ) -> None:
        if strike <= 0:
            return
        rounded = round(strike, 6)
        if rounded in used_strikes:
            return
        used_strikes.add(rounded)

        mapped = strike * ratio
        distance_pts = mapped - futures_spot
        flip_dist = mapped - flip_mapped

        behavior = translate_behavior(structural_source, role, source_spot, futures_spot)

        if sx is not None:
            confidence = score_level_confidence(
                sx,
                distance_pts,
                futures_spot,
                flip_dist,
                max_abs_gex=max_abs_gex,
                max_oi=max_oi,
                max_futures_distance_points=max_futures_distance_points if max_futures_distance_points > 0 else 500.0,
            )
        else:
            confidence = 0.85  # gamma_flip has no StrikeExposure

        tier = assign_tier(confidence)
        side = "neutral"
        if structural_source in ("put_wall",) or structural_source.startswith("neg_gex"):
            side = "support"
        elif structural_source in ("call_wall",) or structural_source.startswith("pos_gex"):
            side = "resistance"
        elif structural_source == "hvl":
            side = "magnet"

        label_map: dict[str, str] = {
            "gamma_flip": "GAMMA FLIP",
            "call_wall": "CALL WALL",
            "put_wall": "PUT WALL",
            "hvl": "HVL",
        }
        action_map: dict[str, str] = {
            "gamma_flip": "REGIME PIVOT",
            "call_wall": "RESISTANCE / FADE",
            "put_wall": "SUPPORT / BOUNCE",
            "hvl": "HIGH GAMMA MAGNET",
        }
        if structural_source.startswith("pos_gex"):
            label = "+GEX NODE"
            action = "PIN / RESIST"
        elif structural_source.startswith("neg_gex"):
            label = "-GEX NODE"
            action = "VOL / SUPPORT"
        else:
            label = label_map.get(structural_source, structural_source.upper())
            action = action_map.get(structural_source, "OBSERVE")

        levels.append({
            "id": role,
            "key": role,
            "role": role,
            "symbol": futures_root,
            "label": label,
            "action": action,
            "side": side,
            "source_underlying": underlying,
            "source_strike": round(strike, 4),
            "source_price": round(strike, 4),
            "mapped_price": round(mapped, 2),
            "price": round(mapped, 2),
            "gex": round(gex_value, 2),
            "value": round(gex_value, 2),
            "abs_gex_rank": rank,
            "distance_from_spot_source": round(strike - source_spot, 4),
            "distance_from_futures_spot": round(mapped - futures_spot, 2),
            "is_pinned": structural_source in ("gamma_flip", "call_wall", "put_wall", "hvl"),
            # V2 explainability metadata (A8)
            "behavior_state": behavior.state,
            "structural_source": structural_source,
            "confidence_score": round(confidence, 4),
            "selected_because": _selected_because(structural_source),
            "distance_points": round(distance_pts, 2),
            "tier": tier,
            "lifecycle_state": "active",
            "action_hint": behavior.action_hint,
            "confluence_group": None,
            "acceleration_context": None,
            "metadata": meta or {},
        })

    # Pinned levels first
    if flip_result and (max_futures_distance_points <= 0 or abs(flip_mapped - futures_spot) <= max_futures_distance_points):
        _add_level("gamma_flip", "gamma_flip", None, flip_result["price"], 0.0, 0, flip_result.get("meta"))

    if call_wall:
        _add_level("call_wall", "call_wall", call_wall, call_wall.strike, call_wall.net_gex, 1)

    if put_wall:
        _add_level("put_wall", "put_wall", put_wall, put_wall.strike, put_wall.net_gex, 2)

    if hvl:
        _add_level("hvl", "hvl", hvl, hvl.strike, hvl.net_gex, 3)

    # Secondary nodes
    secondary = detect_secondary_nodes(near_selected, used_strikes, max_levels - len(levels))
    rank = 4
    for sx in secondary:
        if len(levels) >= max_levels:
            break
        role_prefix = "pos_gex" if sx.net_gex >= 0 else "neg_gex"
        role = f"{role_prefix}_{rank}"
        _add_level(role, role, sx, sx.strike, sx.net_gex, rank)
        rank += 1

    # Score and rank
    levels = rank_levels(levels)

    return levels, regime_summary


def build_payload_v2(
    args: argparse.Namespace,
    api_key: str,
    sequence: int,
    last_good_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Assembles V2 payload with full structural + behavioral + confluence data."""
    generated = now_utc()
    compute_start = time.monotonic()
    underlying = args.underlying.upper()
    futures_root = args.futures_root.upper()

    chain_started = now_utc()
    source_spot = fetch_yahoo_price(args.source_spot_symbol)
    futures_spot = fetch_yahoo_price(args.futures_spot_symbol)

    rows, pages, chain_error = fetch_option_chain(
        underlying, api_key, max_pages=args.max_pages, max_dte=args.max_dte
    )

    by = aggregate_chain(rows, source_spot)
    ratio = futures_spot / source_spot if source_spot > 0 else 1.0

    # FlashAlpha enrichment (optional — graceful fallback)
    fa_api_key = get_flashalpha_api_key(getattr(args, "flashalpha_api_key", None))
    if fa_api_key:
        fa_data = fetch_flashalpha_summary(fa_api_key, args.underlying)
        fa_data = enrich_flashalpha_with_nq(fa_data, ratio)
    else:
        fa_data = _flashalpha_unavailable("No API key configured")

    selected = spot_window(by, source_spot, args.anchor_window_pct, args.max_above_pct, args.max_below_pct)
    near_selected = apply_near_price_cap(
        selected, futures_spot, ratio, args.max_futures_distance_points
    )

    levels, regime_summary = _build_enriched_levels(
        near_selected,
        source_spot=source_spot,
        futures_spot=futures_spot,
        ratio=ratio,
        max_levels=args.max_levels,
        max_futures_distance_points=args.max_futures_distance_points,
        underlying=underlying,
        futures_root=futures_root,
    )

    # Confluence zones (A6)
    confluence_zones = detect_confluence_zones(levels, futures_spot)

    # Tag confluence group back onto levels
    for zone in confluence_zones:
        for lvl in levels:
            if lvl["id"] in zone.member_level_ids:
                lvl["confluence_group"] = zone.zone_id

    # 0DTE enrichment on levels (aggregate proxy from FlashAlpha)
    zero_dte_pct = fa_data.get("zero_dte_pct", 0.0)
    for lvl in levels:
        lvl["zero_dte_gex_pct"] = round(zero_dte_pct, 4)
        lvl["is_zero_dte_dominant"] = zero_dte_pct >= 0.50

    # Open-space lanes (A3)
    lanes = detect_open_space_lanes(levels, futures_spot)

    # WebSocket probe
    ws_params = args.ws_params or f"T.O:{underlying}*,Q.O:{underlying}*,AM.O:{underlying}*"
    ws = websocket_probe(
        api_key,
        url=WS_DELAYED if args.delayed_ws else WS_REALTIME,
        params=ws_params,
        seconds=args.ws_probe_seconds,
    )

    chain_age = int((now_utc() - chain_started).total_seconds())
    compute_duration_ms = int((time.monotonic() - compute_start) * 1000)

    # Freshness model (A7)
    freshness = FreshnessModel(
        payload_age_seconds=0,
        chain_snapshot_age_seconds=chain_age,
        spot_age_seconds=chain_age,
        futures_spot_age_seconds=chain_age,
        websocket_age_seconds=-1 if not ws.get("last_trade_utc") else 0,
        compute_duration_ms=compute_duration_ms,
        last_successful_refresh_utc=iso(generated),
        health_state=compute_health_state(0),
    )

    selection = {
        "spot_centered": True,
        "center_source": "underlying_spot",
        "window_pct": args.anchor_window_pct,
        "max_above_pct": -1.0 if args.max_above_pct is None else args.max_above_pct,
        "max_below_pct": -1.0 if args.max_below_pct is None else args.max_below_pct,
        "max_futures_distance_points": (
            -1.0 if args.max_futures_distance_points is None else args.max_futures_distance_points
        ),
        "candidate_strikes": len(selected),
        "near_candidate_strikes": len(near_selected),
        "max_levels": args.max_levels,
        "algorithm": "gamma_decision_surface_v2_structural_behavioral",
    }

    asset = {
        "asset_id": f"{futures_root}_{underlying}",
        "futures_root": futures_root,
        "chart_symbol_hint": futures_root,
        "underlying": underlying,
        "underlying_spot": round(source_spot, 4),
        "futures_symbol": args.futures_spot_symbol,
        "futures_spot": round(futures_spot, 4),
        "mapping": {
            "method": "spot_ratio",
            "ratio": round(ratio, 8),
            "source": f"{underlying}_to_{futures_root}",
            "source_spot": round(source_spot, 4),
            "target_spot": round(futures_spot, 4),
            "computed_at_utc": iso(generated),
        },
        "freshness": freshness.to_dict(),
        "websocket": ws,
        "chain": {
            "snapshot_contracts": len(rows),
            "used_contracts": sum(x.contract_count for x in by.values()),
            "strike_count": len(by),
            "pages": pages,
            "max_dte": args.max_dte,
            "snapshot_source": "massive_rest_snapshot_options_chain",
            "chain_error": chain_error,
        },
        "selection": selection,
        "levels": levels,
        "levels_list": levels,
        "confluence_zones": [z.to_dict() for z in confluence_zones],
        "lanes": lanes,
        "regime_summary": regime_summary,
        "flashalpha": fa_data,
        "net_exposures": {"gex": round(sum(x.net_gex for x in by.values()), 2)},
        "chain_error": chain_error,
        "stale": False,
        "age_seconds": chain_age,
        "as_of_utc": iso(generated),
    }

    return {
        "schema": SCHEMA_V2,
        "service": SERVICE_NAME,
        "service_version": SERVICE_VERSION,
        "generated_at_utc": iso(generated),
        "sequence": sequence,
        "assets": [asset],
        "errors": [chain_error] if chain_error else [],
    }


def main(argv: list[str] | None = None) -> int:
    global _last_good_payload

    ap = argparse.ArgumentParser(description="DEEP6 Gamma Decision Surface V2 sidecar")
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--underlying", default="QQQ")
    ap.add_argument("--futures-root", default="NQ")
    ap.add_argument("--source-spot-symbol", default="QQQ")
    ap.add_argument("--futures-spot-symbol", default="NQ=F")
    ap.add_argument("--max-pages", type=int, default=80)
    ap.add_argument("--max-dte", type=int, default=45)
    ap.add_argument(
        "--anchor-window-pct",
        type=float,
        default=float(os.getenv("GEX_ANCHOR_WINDOW_PCT", "0.07")),
    )
    ap.add_argument(
        "--max-above-pct",
        type=parse_optional_pct,
        default=os.getenv("GEX_MAX_ABOVE_PCT", ""),
    )
    ap.add_argument(
        "--max-below-pct",
        type=parse_optional_pct,
        default=os.getenv("GEX_MAX_BELOW_PCT", ""),
    )
    ap.add_argument("--max-levels", type=int, default=9)
    ap.add_argument(
        "--max-futures-distance-points",
        type=float,
        default=float(os.getenv("GEX_MAX_FUTURES_DISTANCE_POINTS", "350")),
        help="Only output levels within this many futures points of current futures spot; <=0 disables.",
    )
    ap.add_argument(
        "--ws-probe-seconds",
        type=int,
        default=8,
        help="Open/auth/subscribe Massive options websocket for N seconds. 0 disables.",
    )
    ap.add_argument("--ws-params", default="", help="Override subscription params.")
    ap.add_argument("--delayed-ws", action="store_true")
    ap.add_argument(
        "--flashalpha-api-key",
        default=None,
        help="FlashAlpha API key (optional; also reads FLASHALPHA_API_KEY / NQ_ATLAS_FLASHALPHA_API_KEY env vars)",
    )
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=120)
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    api_key = get_api_key(args.api_key)
    seq = 1

    while True:
        try:
            payload = build_payload_v2(args, api_key, seq, _last_good_payload)
            write_atomic(args.output, payload)
            _last_good_payload = payload
            asset = payload["assets"][0]
            LOG.info(
                "wrote %s levels=%s zones=%s lanes=%s ws=%s contracts=%s strikes=%s regime=%s",
                args.output,
                len(asset.get("levels", [])),
                len(asset.get("confluence_zones", [])),
                len(asset.get("lanes", [])),
                asset.get("websocket", {}).get("state"),
                asset.get("chain", {}).get("snapshot_contracts"),
                asset.get("chain", {}).get("strike_count"),
                asset.get("regime_summary", {}).get("dominant_regime"),
            )
        except SystemExit:
            raise
        except Exception as exc:
            LOG.exception("refresh failed: %s", exc)
            # Degraded mode: re-emit last good payload with updated health_state
            if _last_good_payload is not None:
                degraded = json.loads(json.dumps(_last_good_payload))
                for a in degraded.get("assets", []):
                    f = a.get("freshness", {})
                    f["health_state"] = "degraded"
                degraded["errors"] = degraded.get("errors", []) + [f"{type(exc).__name__}: {exc}"]
                write_atomic(args.output, degraded)
                LOG.warning("emitted degraded payload from last-good cache")
            elif args.once or not args.loop:
                return 2
        if args.once or not args.loop:
            return 0
        seq += 1
        time.sleep(max(10, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
