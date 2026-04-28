#!/usr/bin/env python3
"""
gex_service_v2.py — DEEP6 GEX Service v2 (Massive.com WebSocket streaming)

Hybrid approach:
  REST snapshot every 120s  → gamma per contract (near-term only, ≤45 DTE)
  WebSocket T.O:QQQ*        → volume per trade (seconds latency)
  Output every 3s           → flow GEX levels → gex_command.json

Flow GEX = gamma × today_volume × 100 × spot² × 0.01
Same JSON output format as gex_service.py — NT8 LocalFile mode works unchanged.

Requirements:
    pip install websockets

Run:
    python scripts/gex_service_v2.py
    (reads MASSIVE_API_KEY from .env automatically)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

try:
    import websockets
except ImportError:
    raise SystemExit("Missing dependency: pip install websockets")

# ── constants ──────────────────────────────────────────────────────────────────
LOGGER = logging.getLogger("gex_v2")

DEFAULT_OUTPUT    = Path.home() / "Documents" / "NinjaTrader 8" / "templates" / "DEEP6" / "gex_command.json"
MASSIVE_BASE      = "https://api.massive.com"
WS_RT             = "wss://socket.massive.com/options"
WS_DLY            = "wss://delayed.massive.com/options"
YAHOO             = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1m&range=1d"
MULT              = 100.0    # shares per options contract

MAX_DTE           = 45       # only subscribe to contracts expiring within this many days
MAX_CONTRACTS     = 950      # stay under Massive's 1,000-per-connection limit
SNAPSHOT_INTERVAL = 120      # seconds between REST gamma refreshes
OUTPUT_INTERVAL   = 3        # seconds between JSON writes
RECONNECT_DELAY   = 5        # seconds before WebSocket reconnect

ENV_FILES = (Path(".env"), Path(".env.local"), Path("scripts/.env"))

# ── OCC symbol helpers ─────────────────────────────────────────────────────────

def parse_occ_strike(sym: str) -> tuple[str, float] | None:
    """'O:QQQ241220C00480000' → ('C', 480.0)"""
    s = sym[2:] if sym.startswith("O:") else sym
    m = re.match(r"[A-Z]+\d{6}([CP])(\d{8})", s)
    if not m:
        return None
    return m.group(1), int(m.group(2)) / 1000.0

# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _http_json(url: str, attempts: int = 3, timeout: int = 30) -> dict:
    req = Request(url, headers={"User-Agent": "DEEP6-gex-v2/2.0"})
    last: Exception | None = None
    for i in range(attempts):
        try:
            with urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as exc:
            last = exc
            if i < attempts - 1:
                time.sleep(min(4.0, 1.5 * (i + 1)))
    raise last  # type: ignore[misc]


_spot_cache: dict[str, tuple[float, float]] = {}

def yahoo_spot(symbol: str, cache_ttl: float = 5.0) -> float:
    now = time.monotonic()
    if symbol in _spot_cache:
        price, ts = _spot_cache[symbol]
        if now - ts < cache_ttl:
            return price
    d = _http_json(YAHOO.format(sym=symbol))
    result = d.get("chart", {}).get("result", [])
    if not result:
        raise ValueError(f"No Yahoo result for {symbol}")
    meta = result[0].get("meta", {})
    p = float(meta.get("regularMarketPrice") or 0)
    if not p:
        closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
        for v in reversed(closes):
            if v:
                p = float(v)
                break
    if not p:
        raise ValueError(f"No price for {symbol}")
    _spot_cache[symbol] = (p, now)
    return p

# ── REST: gamma snapshot ───────────────────────────────────────────────────────

def fetch_gamma_snapshot(underlying: str, api_key: str) -> dict[str, dict]:
    """
    Fetch near-term chain snapshot via REST.
    Returns {occ_ticker_no_prefix: {strike, type, gamma, expiry}}.
    Filters to contracts expiring within MAX_DTE days.
    """
    cutoff = (datetime.now(UTC) + timedelta(days=MAX_DTE)).strftime("%Y-%m-%d")
    url = f"{MASSIVE_BASE}/v3/snapshot/options/{underlying}?limit=250&apiKey={api_key}"
    out: dict[str, dict] = {}
    pages = 0

    while url and pages < 60 and len(out) < MAX_CONTRACTS:
        pages += 1
        try:
            data = _http_json(url)
        except Exception as exc:
            LOGGER.warning("[%s] Snapshot page %d error: %s", underlying, pages, exc)
            break

        for row in data.get("results", []):
            det = row.get("details", {})
            ticker = det.get("ticker", "")
            if not ticker:
                continue
            expiry = det.get("expiration_date", "")
            if expiry and expiry > cutoff:
                continue
            ctype  = (det.get("contract_type") or "").lower()
            strike = float(det.get("strike_price") or 0)
            if not strike or ctype not in ("call", "put"):
                continue
            gamma = float((row.get("greeks") or {}).get("gamma") or 0)
            key = ticker[2:] if ticker.startswith("O:") else ticker
            out[key] = {
                "strike": strike,
                "type":   "C" if ctype == "call" else "P",
                "gamma":  gamma,
                "expiry": expiry,
            }

        url = data.get("next_url", "")
        if url and "apiKey=" not in url:
            url += f"&apiKey={api_key}"

    LOGGER.info("[%s] Snapshot: %d contracts (%d pages)", underlying, len(out), pages)
    return out

# ── Flow book ──────────────────────────────────────────────────────────────────

class FlowBook:
    """Per-underlying state: gamma snapshot + intraday volume accumulator."""

    def __init__(self, underlying: str, futures_root: str,
                 yahoo_futures_sym: str, yahoo_spot_sym: str):
        self.underlying       = underlying
        self.futures_root     = futures_root
        self.yahoo_futures    = yahoo_futures_sym
        self.yahoo_spot_sym   = yahoo_spot_sym
        self._lock            = asyncio.Lock()
        self.snapshot:        dict[str, dict]              = {}
        self.volume:          dict[float, dict[str, int]]  = defaultdict(lambda: {"C": 0, "P": 0})
        self.spot:            float         = 0.0
        self.snap_at:         datetime | None = None
        self.trades_today:    int           = 0
        self.n_subscribed:    int           = 0
        self.error:           str           = ""

    async def update_snapshot(self, snap: dict, spot: float) -> None:
        async with self._lock:
            self.snapshot = snap
            self.spot     = spot
            self.snap_at  = datetime.now(UTC)
            self.error    = ""

    async def on_trade(self, sym: str, size: int) -> None:
        if size <= 0:
            return
        parsed = parse_occ_strike(sym)
        if parsed is None:
            return
        opt_type, strike = parsed
        async with self._lock:
            self.volume[strike][opt_type] += size
            self.trades_today += 1

    async def build_gex_map(self) -> tuple[float, dict[float, float]]:
        """Return (spot, {strike: net_flow_gex})."""
        async with self._lock:
            spot = self.spot
            if spot <= 0:
                return 0.0, {}

            # Best gamma per strike from snapshot
            g: dict[float, dict[str, float]] = defaultdict(lambda: {"C": 0.0, "P": 0.0})
            for info in self.snapshot.values():
                s, t, gv = info["strike"], info["type"], info["gamma"]
                if gv > g[s][t]:
                    g[s][t] = gv

            result: dict[float, float] = {}
            for strike, vols in self.volume.items():
                net = (g[strike]["C"] * vols["C"] - g[strike]["P"] * vols["P"]) * MULT * spot * spot * 0.01
                if abs(net) > 0:
                    result[strike] = net
            return spot, result

    async def stats(self) -> dict:
        async with self._lock:
            age = int((datetime.now(UTC) - self.snap_at).total_seconds()) if self.snap_at else None
            return {
                "trades_today":          self.trades_today,
                "contracts_subscribed":  self.n_subscribed,
                "snapshot_contracts":    len(self.snapshot),
                "snapshot_age_s":        age,
                "error":                 self.error,
            }

# ── GEX level selection ────────────────────────────────────────────────────────

def _gamma_flip(strikes: list[float], gex: dict[float, float], spot: float) -> float:
    best, best_d = spot, float("inf")
    for a, b in zip(strikes, strikes[1:]):
        la, lb = gex.get(a, 0.0), gex.get(b, 0.0)
        if la == 0.0:
            cand: float | None = a
        elif la * lb < 0:
            cand = a + (b - a) * abs(la) / (abs(la) + abs(lb))
        else:
            cand = None
        if cand is not None:
            d = abs(cand - spot)
            if d < best_d:
                best, best_d = cand, d
    return best


def build_levels(by_strike: dict[float, float], spot: float, futures_spot: float) -> list[dict]:
    if not by_strike or spot <= 0 or futures_spot <= 0:
        return []

    ratio  = futures_spot / spot
    sk     = sorted(by_strike)
    flip   = _gamma_flip(sk, by_strike, spot)
    above  = {k: v for k, v in by_strike.items() if k >= spot}
    below  = {k: v for k, v in by_strike.items() if k <= spot}

    def _lv(key: str, sym: str, label: str, action: str, price_u: float, val: float) -> dict:
        return {"key": key, "symbol": sym, "label": label, "action": action,
                "price": round(price_u * ratio, 2), "source_price": price_u, "value": val,
                "direction": ""}

    levels = [_lv("gamma_flip", "⚡", "GAMMA FLIP (FLOW)", "REGIME PIVOT", flip, 0.0)]

    if above:
        cw = max(above, key=lambda k: above[k])
        if abs(cw - flip) > 0.5:
            levels.append(_lv("call_wall", "▲", "CALL WALL (FLOW)", "RESISTANCE — FADE", cw, above[cw]))
    if below:
        pw = min(below, key=lambda k: below[k])
        if abs(pw - flip) > 0.5:
            levels.append(_lv("put_wall", "▼", "PUT WALL (FLOW)", "SUPPORT — BOUNCE", pw, below[pw]))

    hvl = max(by_strike, key=lambda k: abs(by_strike[k]))
    if not any(abs(lv["source_price"] - hvl) < 0.5 for lv in levels):
        levels.append(_lv("hvl", "◆", "HVL (FLOW)", "PIN LEVEL", hvl, by_strike[hvl]))

    return levels

# ── Async tasks ────────────────────────────────────────────────────────────────

async def snapshot_loop(book: FlowBook, api_key: str, stop: asyncio.Event) -> None:
    loop = asyncio.get_event_loop()
    while not stop.is_set():
        try:
            snap, spot = await asyncio.gather(
                loop.run_in_executor(None, fetch_gamma_snapshot, book.underlying, api_key),
                loop.run_in_executor(None, yahoo_spot, book.yahoo_spot_sym),
            )
            await book.update_snapshot(snap, spot)
        except Exception as exc:
            LOGGER.warning("[%s] Snapshot error: %s", book.underlying, exc)
            async with book._lock:
                book.error = str(exc)
        await asyncio.sleep(SNAPSHOT_INTERVAL)


async def ws_loop(book: FlowBook, api_key: str,
                  contracts: list[str], ws_url: str, stop: asyncio.Event) -> None:
    # Subscription strings: "T.O:QQQ241220C00480000,..."
    subs = [f"T.O:{c}" if not c.startswith("O:") else f"T.{c}" for c in contracts]
    async with book._lock:
        book.n_subscribed = len(subs)

    while not stop.is_set():
        try:
            LOGGER.info("[%s WS] Connecting to %s (%d contracts)…",
                        book.underlying, ws_url, len(subs))
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=30) as ws:

                # 1. Wait for "connected" status
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                msgs = json.loads(raw)
                ev = next((m for m in msgs if m.get("ev") == "status"), {})
                if ev.get("status") != "connected":
                    raise ConnectionError(f"Unexpected connect message: {msgs}")

                # 2. Authenticate
                await ws.send(json.dumps({"action": "auth", "params": api_key}))
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                msgs = json.loads(raw)
                ev = next((m for m in msgs if m.get("ev") == "status"), {})
                if ev.get("status") != "auth_success":
                    raise PermissionError(f"Auth failed: {msgs}")
                LOGGER.info("[%s WS] Authenticated", book.underlying)

                # 3. Subscribe in batches of 200 to avoid oversized messages
                for i in range(0, len(subs), 200):
                    batch = ",".join(subs[i : i + 200])
                    await ws.send(json.dumps({"action": "subscribe", "params": batch}))
                    await asyncio.sleep(0.05)
                LOGGER.info("[%s WS] Subscribed. Streaming…", book.underlying)

                # 4. Consume trade stream
                async for raw_msg in ws:
                    if stop.is_set():
                        break
                    try:
                        for ev in json.loads(raw_msg):
                            if ev.get("ev") == "T":
                                await book.on_trade(ev.get("sym", ""), int(ev.get("s", 0)))
                    except Exception:
                        pass

        except asyncio.CancelledError:
            break
        except Exception as exc:
            if not stop.is_set():
                LOGGER.warning("[%s WS] %s — reconnect in %ds",
                               book.underlying, exc, RECONNECT_DELAY)
                await asyncio.sleep(RECONNECT_DELAY)


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


async def output_loop(books: list[FlowBook], out_path: Path, stop: asyncio.Event) -> None:
    loop = asyncio.get_event_loop()
    while not stop.is_set():
        try:
            now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            assets: list[dict] = []

            for book in books:
                try:
                    futures_spot = await loop.run_in_executor(None, yahoo_spot, book.yahoo_futures)
                except Exception:
                    futures_spot = 0.0

                spot, by_strike = await book.build_gex_map()
                levels_list = build_levels(by_strike, spot, futures_spot)
                st = await book.stats()
                stale = st["snapshot_age_s"] is None or st["snapshot_age_s"] > SNAPSHOT_INTERVAL * 2

                assets.append({
                    "underlying":      book.underlying,
                    "futures_root":    book.futures_root,
                    "underlying_spot": spot,
                    "futures_spot":    futures_spot,
                    "mapped_spot":     futures_spot,
                    "ratio":           round(futures_spot / spot, 6) if spot > 0 else 0,
                    "as_of_utc":       now,
                    "stale":           stale,
                    "chain_error":     st["error"],
                    "contract_count":  st["snapshot_contracts"],
                    "strike_count":    len(by_strike),
                    "stream_stats":    st,
                    "levels":          {lv["key"]: lv for lv in levels_list},
                    "levels_list":     levels_list,
                })

            await loop.run_in_executor(None, _atomic_write, out_path, {
                "service":          "gex_service_v2",
                "service_version":  "2.0.0",
                "generated_at_utc": now,
                "assets":           assets,
            })

        except Exception as exc:
            LOGGER.warning("Output error: %s", exc)

        await asyncio.sleep(OUTPUT_INTERVAL)

# ── Bootstrap + orchestration ──────────────────────────────────────────────────

async def run(api_key: str, out_path: Path, ws_url: str) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, AttributeError):
            pass  # Windows — Ctrl+C still works via default handler

    assets_cfg = [
        # (underlying, futures_root, yahoo_futures, yahoo_spot_sym)
        ("QQQ", "NQ", "NQ=F",  "QQQ"),
        ("SPX", "ES", "ES=F",  "^SPX"),
    ]

    books: list[FlowBook] = []
    tasks: list[asyncio.Task] = []

    for underlying, futures_root, yahoo_fut, yahoo_spot_sym in assets_cfg:
        book = FlowBook(underlying, futures_root, yahoo_fut, yahoo_spot_sym)
        books.append(book)

        LOGGER.info("[%s] Bootstrapping snapshot + spot…", underlying)
        try:
            snap, spot = await asyncio.gather(
                loop.run_in_executor(None, fetch_gamma_snapshot, underlying, api_key),
                loop.run_in_executor(None, yahoo_spot, yahoo_spot_sym),
            )
            await book.update_snapshot(snap, spot)
            contracts = list(snap.keys())[:MAX_CONTRACTS]
            LOGGER.info("[%s] Bootstrap OK — %d contracts, spot=%.2f",
                        underlying, len(contracts), spot)
        except Exception as exc:
            LOGGER.error("[%s] Bootstrap failed: %s", underlying, exc)
            contracts = []
            book.error = str(exc)

        tasks.append(asyncio.create_task(
            snapshot_loop(book, api_key, stop), name=f"snap_{underlying}"))

        if contracts:
            tasks.append(asyncio.create_task(
                ws_loop(book, api_key, contracts, ws_url, stop), name=f"ws_{underlying}"))
        else:
            LOGGER.warning("[%s] No contracts fetched — WebSocket stream disabled", underlying)

    tasks.append(asyncio.create_task(
        output_loop(books, out_path, stop), name="output"))

    LOGGER.info("Streaming → %s  (output every %ds)", out_path, OUTPUT_INTERVAL)
    await stop.wait()

    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    LOGGER.info("Stopped.")

# ── Entry point ────────────────────────────────────────────────────────────────

def _load_env() -> None:
    for p in ENV_FILES:
        try:
            if not p.exists():
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
        except Exception:
            pass


def main() -> None:
    _load_env()

    import argparse
    ap = argparse.ArgumentParser(description="DEEP6 GEX Service v2 — WebSocket streaming")
    ap.add_argument("--api-key",   default="",
                    help="Massive.com API key (default: MASSIVE_API_KEY env var)")
    ap.add_argument("--output",    default=str(DEFAULT_OUTPUT),
                    help="Output JSON path (read by NT8 LocalFile mode)")
    ap.add_argument("--delayed",   action="store_true",
                    help="Use delayed feed (wss://delayed.massive.com) — for testing")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s")

    api_key = (args.api_key or os.environ.get("MASSIVE_API_KEY", "")).strip()
    if not api_key:
        raise SystemExit("MASSIVE_API_KEY not set. Add to .env or pass --api-key.")

    ws_url = WS_DLY if args.delayed else WS_RT
    mode   = "DELAYED (15 min)" if args.delayed else "REAL-TIME"

    LOGGER.info("DEEP6 GEX Service v2  |  %s  |  out: %s", mode, args.output)
    asyncio.run(run(api_key, Path(args.output), ws_url))


if __name__ == "__main__":
    main()
