#!/usr/bin/env python3
"""Rithmic → NDJSON feed adapter for the NinjaScript Simulator.

Connects to Rithmic via async-rithmic, subscribes to NQ tick + DOM data,
and outputs NDJSON lines that the simulator consumes directly.

Environments:
  test  — Rithmic Test (wss://rituz00100.rithmic.com:443) — free, no broker needed
  paper — Rithmic Paper Trading
  live  — Production (requires broker API mode enabled)

Usage:
  # Test server (works immediately, free):
  python rithmic_feed.py --env test --user YOUR_USER --pass YOUR_PASS

  # Record to file for later replay:
  python rithmic_feed.py --env test --user U --pass P --output session.ndjson

  # Pipe directly to simulator:
  python rithmic_feed.py --env test --user U --pass P | \
    dotnet run --project ninjatrader/simulator -- replay /dev/stdin

  # Live (when broker enables API mode):
  python rithmic_feed.py --env live --user U --pass P --gateway chicago

Output format (one JSON per line):
  {"type":"trade","ts_ms":N,"price":P,"size":S,"aggressor":A}
  {"type":"depth","ts_ms":N,"side":0|1,"levelIdx":L,"price":P,"size":S}
  {"type":"bar","ts_ms":N,"open":O,"high":H,"low":Lo,"close":C,"barDelta":D,"totalVol":V,"cvd":CV}
  {"type":"session_reset","ts_ms":N}
"""

import argparse
import asyncio
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from async_rithmic import RithmicClient, DataType, ReconnectionSettings

# ── Rithmic environments ─────────────────────────────────────────────────────

ENVIRONMENTS = {
    "test":  {"uri": "wss://rituz00100.rithmic.com:443",    "system": "Rithmic Test"},
    "paper": {"uri": "wss://rituz00100.rithmic.com:443",    "system": "Rithmic Paper Trading"},
    "live":  {"uri": "wss://rprotocol.rithmic.com:443",     "system": "Rithmic 01"},
}

LIVE_GATEWAYS = {
    "chicago":   "wss://rprotocol.rithmic.com:443",
    "newyork":   "wss://rprotocol-nyc.rithmic.com:443",
    "colo75":    "wss://rprotocol-colo75.rithmic.com:443",
    "frankfurt":  "wss://rprotocol-de.rithmic.com:443",
    "tokyo":     "wss://rprotocol-jp.rithmic.com:443",
    "singapore": "wss://rprotocol-sg.rithmic.com:443",
    "sydney":    "wss://rprotocol-au.rithmic.com:443",
    "hongkong":  "wss://rprotocol-hk.rithmic.com:443",
    "mumbai":    "wss://rprotocol-in.rithmic.com:443",
    "seoul":     "wss://rprotocol-kr.rithmic.com:443",
    "capetown":  "wss://rprotocol-za.rithmic.com:443",
    "saopaolo":  "wss://rprotocol-br.rithmic.com:443",
    "ireland":   "wss://rprotocol-ie.rithmic.com:443",
}

# ── Bar accumulator ──────────────────────────────────────────────────────────

class BarAccumulator:
    """Accumulates trades into 1-minute bars, emits bar events."""

    def __init__(self, bar_seconds: int = 60):
        self.bar_seconds = bar_seconds
        self.reset()
        self._boundary = 0
        self._cvd = 0

    def reset(self):
        self.open = 0.0
        self.high = -float("inf")
        self.low = float("inf")
        self.close = 0.0
        self.total_vol = 0
        self.buy_vol = 0
        self.sell_vol = 0
        self.trade_count = 0

    def add_trade(self, price: float, size: int, aggressor: int, ts_ms: int) -> dict | None:
        """Add a trade. Returns a bar dict if the bar period elapsed, else None."""
        # Initialize boundary on first trade
        if self._boundary == 0:
            self._boundary = (ts_ms // (self.bar_seconds * 1000) + 1) * (self.bar_seconds * 1000)

        # Check if we crossed a bar boundary
        bar_event = None
        if ts_ms >= self._boundary and self.trade_count > 0:
            bar_event = self._emit()
            self.reset()
            self._boundary += self.bar_seconds * 1000

        # Accumulate
        if self.trade_count == 0:
            self.open = price
        self.close = price
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price
        self.total_vol += size
        if aggressor == 1:
            self.buy_vol += size
        elif aggressor == 2:
            self.sell_vol += size
        self.trade_count += 1

        return bar_event

    def flush(self) -> dict | None:
        """Emit the current partial bar (call at session end)."""
        if self.trade_count > 0:
            return self._emit()
        return None

    def _emit(self) -> dict:
        delta = self.buy_vol - self.sell_vol
        self._cvd += delta
        return {
            "type": "bar",
            "ts_ms": self._boundary,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "barDelta": delta,
            "totalVol": self.total_vol,
            "cvd": self._cvd,
        }


# ── NDJSON writer ────────────────────────────────────────────────────────────

class NdjsonWriter:
    """Writes NDJSON lines to stdout and/or a file."""

    def __init__(self, output_path: str | None = None):
        self._file = open(output_path, "w") if output_path else None
        self.lines_written = 0

    def write(self, obj: dict):
        line = json.dumps(obj, separators=(",", ":"))
        print(line, flush=True)  # always to stdout
        if self._file:
            self._file.write(line + "\n")
            self._file.flush()
        self.lines_written += 1

    def close(self):
        if self._file:
            self._file.close()


# ── Main feed loop ───────────────────────────────────────────────────────────

async def run_feed(args):
    env = ENVIRONMENTS.get(args.env, ENVIRONMENTS["test"])
    uri = env["uri"]
    system = env["system"]

    # Override gateway for live
    if args.env == "live" and args.gateway:
        uri = LIVE_GATEWAYS.get(args.gateway, uri)

    writer = NdjsonWriter(args.output)
    bar_acc = BarAccumulator(args.bar_seconds)

    # Stats
    stats = {"trades": 0, "depth": 0, "bars": 0, "start": time.time()}

    print(f"[rithmic_feed] Connecting to {system} ({uri})...", file=sys.stderr)
    print(f"[rithmic_feed] Instrument: {args.instrument} / {args.exchange}", file=sys.stderr)
    print(f"[rithmic_feed] App: migo:DEEP6-sim", file=sys.stderr)

    client = RithmicClient(
        user=args.user,
        password=args.password,
        system_name=system,
        app_name="migo:DEEP6-sim",
        app_version="2.0.0",
        url=uri,
        reconnection_settings=ReconnectionSettings(
            max_retries=10,
            backoff_type="exponential",
            interval=1.0,
            max_delay=60.0,
            jitter_range=(0.5, 1.5),
        ),
    )

    # Session reset
    ts_ms = int(time.time() * 1000)
    writer.write({"type": "session_reset", "ts_ms": ts_ms})

    # Tick callback
    async def on_tick(tick):
        if not hasattr(tick, "data_type"):
            return
        if tick.data_type != DataType.LAST_TRADE:
            return
        lt = getattr(tick, "last_trade", None)
        if lt is None:
            return

        price = getattr(lt, "price", None)
        size = getattr(lt, "size", None)
        aggressor = getattr(lt, "aggressor", 0)
        if price is None or size is None:
            return

        ts_ms = int(time.time() * 1000)
        stats["trades"] += 1

        # Write trade event
        writer.write({
            "type": "trade",
            "ts_ms": ts_ms,
            "price": float(price),
            "size": int(size),
            "aggressor": int(aggressor),
        })

        # Bar accumulation
        bar_event = bar_acc.add_trade(float(price), int(size), int(aggressor), ts_ms)
        if bar_event:
            writer.write(bar_event)
            stats["bars"] += 1

    # DOM callback
    async def on_order_book(update):
        update_type = getattr(update, "update_type", None)
        if update_type not in ("SOLO", "END"):
            return

        ts_ms = int(time.time() * 1000)
        bids = getattr(update, "bids", None) or []
        asks = getattr(update, "asks", None) or []

        for idx, lv in enumerate(bids[:10]):
            writer.write({
                "type": "depth",
                "ts_ms": ts_ms,
                "side": 0,
                "levelIdx": idx,
                "price": float(lv.price),
                "size": int(lv.size),
            })
            stats["depth"] += 1

        for idx, lv in enumerate(asks[:10]):
            writer.write({
                "type": "depth",
                "ts_ms": ts_ms,
                "side": 1,
                "levelIdx": idx,
                "price": float(lv.price),
                "size": int(lv.size),
            })
            stats["depth"] += 1

    # Connect
    try:
        await client.connect()
        await asyncio.sleep(0.5)  # Issue #49 workaround
        print(f"[rithmic_feed] Connected! Subscribing to {args.instrument}...", file=sys.stderr)
    except Exception as e:
        print(f"[rithmic_feed] Connection failed: {e}", file=sys.stderr)
        if "rpCode=13" in str(e) or "rpcode=13" in str(e).lower():
            print("[rithmic_feed] rpCode=13 = API/plugin mode not enabled by broker.", file=sys.stderr)
            print("[rithmic_feed] Contact your broker to enable API mode, or use --env test", file=sys.stderr)
        writer.close()
        return

    # Register callbacks
    client.on_tick += on_tick
    client.on_order_book += on_order_book

    # Subscribe
    await client.subscribe_to_market_data(args.instrument, args.exchange)
    print(f"[rithmic_feed] Streaming... Press Ctrl+C to stop.", file=sys.stderr)

    # Status ticker
    async def status_loop():
        while True:
            await asyncio.sleep(5)
            elapsed = time.time() - stats["start"]
            rate = stats["trades"] / max(elapsed, 1)
            print(
                f"\r[rithmic_feed] {stats['trades']} trades | {stats['depth']} depth | "
                f"{stats['bars']} bars | {rate:.0f} ticks/sec | {writer.lines_written} lines",
                end="", file=sys.stderr,
            )

    status_task = asyncio.create_task(status_loop())

    # Wait for Ctrl+C
    stop = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    print(file=sys.stderr)
    print(f"[rithmic_feed] Stopping...", file=sys.stderr)

    status_task.cancel()

    # Flush final bar
    final_bar = bar_acc.flush()
    if final_bar:
        writer.write(final_bar)

    # Disconnect
    try:
        await client.disconnect()
    except Exception:
        pass

    writer.close()

    elapsed = time.time() - stats["start"]
    print(f"[rithmic_feed] Done. {stats['trades']} trades, {stats['depth']} depth, "
          f"{stats['bars']} bars in {elapsed:.1f}s", file=sys.stderr)
    if args.output:
        print(f"[rithmic_feed] Saved to: {args.output}", file=sys.stderr)
        print(f"[rithmic_feed] Replay:   dotnet run --project ninjatrader/simulator -- replay {args.output}",
              file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Rithmic → NDJSON feed for NinjaScript Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
environments:
  test   Rithmic Test server (free, no broker approval needed)
  paper  Rithmic Paper Trading
  live   Production (requires broker to enable API/plugin mode)

examples:
  # Test server (free):
  python rithmic_feed.py --env test --user demo --pass demo

  # Record session:
  python rithmic_feed.py --env test --user U --pass P --output nq-session.ndjson

  # Live with specific gateway:
  python rithmic_feed.py --env live --user U --pass P --gateway chicago
        """,
    )
    parser.add_argument("--env", default="test", choices=["test", "paper", "live"],
                        help="Rithmic environment (default: test)")
    parser.add_argument("--user", required=True, help="Rithmic username")
    parser.add_argument("--pass", dest="password", required=True, help="Rithmic password")
    parser.add_argument("--instrument", default="NQM6", help="Symbol (default: NQM6)")
    parser.add_argument("--exchange", default="CME", help="Exchange (default: CME)")
    parser.add_argument("--gateway", default=None, help="Live gateway (chicago, newyork, etc.)")
    parser.add_argument("--output", "-o", default=None, help="Save NDJSON to file")
    parser.add_argument("--bar-seconds", type=int, default=60, help="Bar period in seconds (default: 60)")

    args = parser.parse_args()
    asyncio.run(run_feed(args))


if __name__ == "__main__":
    main()
