#!/usr/bin/env python3
r"""
DEEP6 Massive GEX Map Service

Brand-new sidecar for DEEP6MassiveGexMap.cs.  The API key stays here in Python;
NinjaTrader only reads the JSON produced by this script.

Outputs:
  C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\massive_gex_map.json

Usage:
  python scripts/massive_gex_map_service.py --once --ws-probe-seconds 8
  python scripts/massive_gex_map_service.py --loop --interval 120 --ws-probe-seconds 0
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

LOG = logging.getLogger("massive_gex_map")
MASSIVE_BASE = "https://api.massive.com"
WS_REALTIME = "wss://socket.massive.com/options"
WS_DELAYED = "wss://delayed.massive.com/options"
YAHOO_QUOTE = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"
CONTRACT_MULTIPLIER = 100.0
def default_output_path() -> Path:
    # Works from WSL/Hermes and from native Windows Python.
    wsl_docs = Path("/mnt/c/Users/Tea/Documents")
    if wsl_docs.exists():
        return wsl_docs / "NinjaTrader 8" / "templates" / "DEEP6" / "massive_gex_map.json"
    return Path.home() / "Documents" / "NinjaTrader 8" / "templates" / "DEEP6" / "massive_gex_map.json"


DEFAULT_OUTPUT = default_output_path()
ENV_FILE_CANDIDATES = (Path(".env"), Path(".env.local"), Path("scripts/.env"), Path("scripts/.env.local"))


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
    req = Request(url, headers={"User-Agent": "DEEP6MassiveGexMap/1.0"})
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


def fetch_option_chain(underlying: str, api_key: str, *, max_pages: int, max_dte: int) -> tuple[list[dict[str, Any]], int, str]:
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
        except Exception as exc:  # keep last-good partial data useful
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
            next_url = raw_next if "apiKey=" in raw_next else raw_next + ("&" if "?" in raw_next else "?") + f"apiKey={api_key}"
        else:
            next_url = ""
    return rows, pages, error


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


def spot_window(by: dict[float, StrikeExposure], spot: float, window_pct: float, max_above_pct: float | None, max_below_pct: float | None) -> list[StrikeExposure]:
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


def gamma_flip(strikes: list[StrikeExposure], spot: float) -> tuple[float, dict[str, Any]]:
    if not strikes:
        return spot, {"interpolated": False}
    best = spot
    best_d = float("inf")
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
            if dist < best_d:
                best = cand
                best_d = dist
                meta = {"interpolated": cand not in (left.strike, right.strike), "left_strike": left.strike, "right_strike": right.strike}
    if best_d == float("inf"):
        nearest = min(vals, key=lambda x: abs(x.strike - spot))
        best = nearest.strike
        meta = {"interpolated": False, "fallback": "nearest_strike_no_zero_cross"}
    return best, meta


def choose_levels(by: dict[float, StrikeExposure], *, underlying: str, futures_root: str, source_spot: float, futures_spot: float, window_pct: float, max_above_pct: float | None, max_below_pct: float | None, max_levels: int, max_futures_distance_points: float | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected = spot_window(by, source_spot, window_pct, max_above_pct, max_below_pct)
    ratio = futures_spot / source_spot if source_spot > 0 else 1.0

    # V3 magnet rule: keep the original OI-gamma formula, but do not force far-away
    # pinned levels onto the chart.  The original indicator's best behavior was
    # selective: if there is no nearby wall/magnet, output no wall instead of
    # pretending that a 1,000+ point level is actionable.
    near_selected = selected
    if max_futures_distance_points is not None and max_futures_distance_points > 0 and futures_spot > 0:
        near_selected = [
            sx for sx in selected
            if abs((sx.strike * ratio) - futures_spot) <= max_futures_distance_points
        ]

    levels: list[dict[str, Any]] = []
    used: set[tuple[str, float]] = set()
    used_strikes: set[float] = set()

    def add(role: str, label: str, action: str, side: str, strike: float, value: float, rank: int, pinned: bool, meta: dict[str, Any] | None = None) -> None:
        if strike <= 0:
            return
        rounded_strike = round(strike, 6)
        # Original indicator behavior: once a structural role pins a strike,
        # do not add a second label at the same price under another role.
        if rounded_strike in used_strikes:
            return
        key = (role, rounded_strike)
        if key in used:
            return
        used.add(key)
        used_strikes.add(rounded_strike)
        mapped = strike * ratio
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
            "gex": round(value, 2),
            "value": round(value, 2),
            "abs_gex_rank": rank,
            "distance_from_spot_source": round(strike - source_spot, 4),
            "distance_from_futures_spot": round(mapped - futures_spot, 2),
            "is_pinned": pinned,
            "confidence": 1.0 if pinned else 0.75,
            "metadata": meta or {},
        })

    if not near_selected:
        selection = {
            "spot_centered": True,
            "center_source": "underlying_spot",
            "window_pct": window_pct,
            "max_above_pct": -1.0 if max_above_pct is None else max_above_pct,
            "max_below_pct": -1.0 if max_below_pct is None else max_below_pct,
            "max_futures_distance_points": -1.0 if max_futures_distance_points is None else max_futures_distance_points,
            "candidate_strikes": len(selected),
            "near_candidate_strikes": 0,
            "max_levels": max_levels,
            "algorithm": "original_v1_oi_gex_selective_near_price",
        }
        return levels, selection

    flip, flip_meta = gamma_flip(near_selected, source_spot)
    if "fallback" not in flip_meta and (max_futures_distance_points is None or abs((flip * ratio) - futures_spot) <= max_futures_distance_points):
        add("gamma_flip", "GAMMA FLIP", "REGIME PIVOT", "neutral", flip, 0.0, 0, True, flip_meta)

    above_pos = [x for x in near_selected if x.strike >= source_spot and x.net_gex > 0]
    below_neg = [x for x in near_selected if x.strike <= source_spot and x.net_gex < 0]
    if above_pos:
        cw = max(above_pos, key=lambda x: abs(x.net_gex))
        add("call_wall", "CALL WALL", "RESISTANCE / FADE", "resistance", cw.strike, cw.net_gex, 1, True)
    if below_neg:
        pw = max(below_neg, key=lambda x: abs(x.net_gex))
        add("put_wall", "PUT WALL", "SUPPORT / BOUNCE", "support", pw.strike, pw.net_gex, 2, True)

    hvl_candidates = sorted(near_selected, key=lambda x: abs(x.net_gex), reverse=True)
    if hvl_candidates:
        hvl = hvl_candidates[0]
        add("hvl", "HVL", "HIGH GAMMA MAGNET", "magnet", hvl.strike, hvl.net_gex, 3, True)

    rank = 4
    for sx in hvl_candidates:
        if len(levels) >= max_levels:
            break
        if any(abs(l["source_strike"] - sx.strike) < 1e-6 for l in levels):
            continue
        role = "pos_gex" if sx.net_gex >= 0 else "neg_gex"
        side = "resistance" if sx.net_gex >= 0 and sx.strike >= source_spot else "support" if sx.net_gex < 0 and sx.strike <= source_spot else "magnet"
        label = "+GEX NODE" if sx.net_gex >= 0 else "-GEX NODE"
        action = "PIN / RESIST" if sx.net_gex >= 0 else "VOL / SUPPORT"
        add(f"{role}_{rank}", label, action, side, sx.strike, sx.net_gex, rank, False)
        rank += 1

    selection = {
        "spot_centered": True,
        "center_source": "underlying_spot",
        "window_pct": window_pct,
        "max_above_pct": -1.0 if max_above_pct is None else max_above_pct,
        "max_below_pct": -1.0 if max_below_pct is None else max_below_pct,
        "max_futures_distance_points": -1.0 if max_futures_distance_points is None else max_futures_distance_points,
        "candidate_strikes": len(selected),
        "near_candidate_strikes": len(near_selected),
        "max_levels": max_levels,
        "algorithm": "original_v1_oi_gex_selective_near_price",
    }
    return levels, selection


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
            key = sock.recv(4)
        data = b""
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                break
            data += chunk
        if mask:
            data = bytes(data[i] ^ key[i % 4] for i in range(len(data)))
        opcode = b1 & 0x0F
        if opcode == 8:
            return None
        return data.decode("utf-8", errors="replace")
    except socket.timeout:
        return None


def _ws_send_text(sock: ssl.SSLSocket, text: str) -> None:
    payload = text.encode("utf-8")
    key = os.urandom(4)
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
    masked = bytes(payload[i] ^ key[i % 4] for i in range(n))
    sock.sendall(bytes(header) + key + masked)


def websocket_probe(api_key: str, *, url: str, params: str, seconds: int) -> dict[str, Any]:
    status = {
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
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(req.encode("ascii"))
        resp = sock.recv(4096).decode("iso-8859-1", errors="replace")
        if "101" not in resp.split("\r\n", 1)[0]:
            raise RuntimeError("websocket handshake failed: " + resp.split("\r\n", 1)[0])
        first = _ws_recv_frame(sock, 5) or ""
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


def build_payload(args: argparse.Namespace, api_key: str, sequence: int) -> dict[str, Any]:
    generated = now_utc()
    underlying = args.underlying.upper()
    futures_root = args.futures_root.upper()
    chain_started = now_utc()
    source_spot = fetch_yahoo_price(args.source_spot_symbol)
    futures_spot = fetch_yahoo_price(args.futures_spot_symbol)
    rows, pages, chain_error = fetch_option_chain(underlying, api_key, max_pages=args.max_pages, max_dte=args.max_dte)
    by = aggregate_chain(rows, source_spot)
    levels, selection = choose_levels(
        by,
        underlying=underlying,
        futures_root=futures_root,
        source_spot=source_spot,
        futures_spot=futures_spot,
        window_pct=args.anchor_window_pct,
        max_above_pct=args.max_above_pct,
        max_below_pct=args.max_below_pct,
        max_levels=args.max_levels,
        max_futures_distance_points=args.max_futures_distance_points,
    )
    # Subscribe to wildcard channels for a dashboard-visible probe.  Standard GEX still comes from REST greeks/OI.
    ws_params = args.ws_params or f"T.O:{underlying}*,Q.O:{underlying}*,AM.O:{underlying}*"
    ws = websocket_probe(api_key, url=WS_DELAYED if args.delayed_ws else WS_REALTIME, params=ws_params, seconds=args.ws_probe_seconds)
    chain_age = int((now_utc() - chain_started).total_seconds())
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
            "ratio": round(futures_spot / source_spot, 8) if source_spot else 0.0,
            "source": f"{underlying}_to_{futures_root}",
            "source_spot": round(source_spot, 4),
            "target_spot": round(futures_spot, 4),
            "computed_at_utc": iso(generated),
        },
        "freshness": {
            "generated_age_s": 0,
            "chain_snapshot_age_s": chain_age,
            "spot_age_s": chain_age,
            "futures_spot_age_s": chain_age,
            "trade_stream_age_s": -1 if not ws.get("last_trade_utc") else 0,
            "stale": False,
            "very_stale": False,
        },
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
        "net_exposures": {"gex": round(sum(x.net_gex for x in by.values()), 2)},
        "chain_error": chain_error,
        "stale": False,
        "age_seconds": chain_age,
        "as_of_utc": iso(generated),
    }
    return {
        "schema": "deep6.massive_gex_map.v1",
        "service": "massive_gex_map_service",
        "service_version": "1.0.0",
        "generated_at_utc": iso(generated),
        "sequence": sequence,
        "assets": [asset],
        "errors": [chain_error] if chain_error else [],
    }


def write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{random.randint(1000,9999)}")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    os.replace(tmp, path)


def parse_optional_pct(raw: str | None) -> float | None:
    if raw is None or str(raw).strip() == "":
        return None
    return float(raw)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DEEP6 Massive GEX Map sidecar")
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--underlying", default="QQQ")
    ap.add_argument("--futures-root", default="NQ")
    ap.add_argument("--source-spot-symbol", default="QQQ")
    ap.add_argument("--futures-spot-symbol", default="NQ=F")
    ap.add_argument("--max-pages", type=int, default=80)
    ap.add_argument("--max-dte", type=int, default=45)
    ap.add_argument("--anchor-window-pct", type=float, default=float(os.getenv("GEX_ANCHOR_WINDOW_PCT", "0.07")))
    ap.add_argument("--max-above-pct", type=parse_optional_pct, default=os.getenv("GEX_MAX_ABOVE_PCT", ""))
    ap.add_argument("--max-below-pct", type=parse_optional_pct, default=os.getenv("GEX_MAX_BELOW_PCT", ""))
    ap.add_argument("--max-levels", type=int, default=9)
    ap.add_argument("--max-futures-distance-points", type=float, default=float(os.getenv("GEX_MAX_FUTURES_DISTANCE_POINTS", "350")), help="V3 magnet cap: only output levels within this many futures points of current futures spot; <=0 disables.")
    ap.add_argument("--ws-probe-seconds", type=int, default=8, help="Open/auth/subscribe Massive options websocket for N seconds. 0 disables.")
    ap.add_argument("--ws-params", default="", help="Override subscription params, e.g. T.O:QQQ*,Q.O:QQQ*.")
    ap.add_argument("--delayed-ws", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=120)
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
    api_key = get_api_key(args.api_key)
    seq = 1
    while True:
        try:
            payload = build_payload(args, api_key, seq)
            write_atomic(args.output, payload)
            asset = payload["assets"][0]
            LOG.info("wrote %s levels=%s ws=%s contracts=%s strikes=%s", args.output, len(asset.get("levels", [])), asset.get("websocket", {}).get("state"), asset.get("chain", {}).get("snapshot_contracts"), asset.get("chain", {}).get("strike_count"))
        except Exception as exc:
            LOG.exception("refresh failed: %s", exc)
            if args.once or not args.loop:
                return 2
        if args.once or not args.loop:
            return 0
        seq += 1
        time.sleep(max(10, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
