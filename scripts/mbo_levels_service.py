"""MBO Levels Service — L2 DOM heat map level detection for NinjaTrader.

Connects to Rithmic via async-rithmic, tracks order book state over time,
identifies significant price levels (walls, persistent liquidity), and
writes mbo_levels.json for consumption by DEEP6MBOHeatMap indicator.

Architecture:
    async-rithmic (L2 DOM) → DOMAccumulator → LevelTracker → JSON output

Usage:
    python scripts/mbo_levels_service.py \\
        --user YOUR_USER --password YOUR_PASS \\
        --system "Rithmic Paper Trading" \\
        --url rituz00100.rithmic.com:443 \\
        --symbol NQ --exchange CME

    Environment variables (via .env or shell):
        RITHMIC_USER, RITHMIC_PASSWORD, RITHMIC_SYSTEM_NAME, RITHMIC_URI

NOTE: If NinjaTrader is already connected to Rithmic with the same credentials,
      you may get a ForcedLogout. Use a different broker account (e.g., Apex for
      NT8, Edge Pro for this service) or run this while NT8 is disconnected.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("mbo_levels_service")
DEFAULT_OUTPUT = (
    Path.home() / "Documents" / "NinjaTrader 8" / "templates" / "DEEP6" / "mbo_levels.json"
)
ENV_FILE_CANDIDATES = (
    Path(".env"),
    Path(".env.local"),
    Path("scripts/.env"),
    Path("scripts/.env.local"),
)


@dataclass(slots=True)
class LevelTracker:
    """Track a single price level's volume history over time."""

    price: float
    side: str  # "bid" or "ask"
    current_size: int = 0
    peak_size: int = 0
    first_seen: float = 0.0  # monotonic time
    last_seen: float = 0.0
    last_size: int = 0
    refill_count: int = 0
    snapshots: int = 0  # number of times seen in a snapshot
    cumulative_size: float = 0.0  # decay-weighted cumulative volume

    @property
    def persistence_sec(self) -> float:
        if self.first_seen <= 0 or self.last_seen <= 0:
            return 0.0
        return self.last_seen - self.first_seen

    @property
    def heat(self) -> float:
        """Normalized heat intensity (0.0–1.0). Set externally after normalization."""
        return self._heat

    @heat.setter
    def heat(self, value: float) -> None:
        self._heat = max(0.0, min(1.0, value))

    def __post_init__(self) -> None:
        self._heat: float = 0.0


class DOMAccumulator:
    """Accumulate L2 DOM snapshots and identify significant price levels."""

    def __init__(
        self,
        *,
        wall_min_size: int = 100,
        wall_stale_sec: float = 90.0,
        max_levels_per_side: int = 4,
        decay_half_life_sec: float = 120.0,
    ) -> None:
        self.wall_min_size = wall_min_size
        self.wall_stale_sec = wall_stale_sec
        self.max_levels_per_side = max_levels_per_side
        self.decay_half_life_sec = decay_half_life_sec
        self._bid_levels: dict[float, LevelTracker] = {}
        self._ask_levels: dict[float, LevelTracker] = {}
        self._mid_price: float = 0.0
        self._spread: float = 0.0
        self._total_bid_depth: int = 0
        self._total_ask_depth: int = 0
        self._snapshot_count: int = 0

    def on_order_book(self, bids: list[tuple[float, int]], asks: list[tuple[float, int]]) -> None:
        """Process a complete L2 order book snapshot.

        Args:
            bids: list of (price, size) tuples, best bid first
            asks: list of (price, size) tuples, best ask first
        """
        now = time.monotonic()
        self._snapshot_count += 1

        # Update mid price and spread
        if bids and asks:
            self._mid_price = (bids[0][0] + asks[0][0]) / 2.0
            self._spread = asks[0][0] - bids[0][0]

        # Track totals
        self._total_bid_depth = sum(s for _, s in bids)
        self._total_ask_depth = sum(s for _, s in asks)

        # Update bid levels
        seen_bid_prices: set[float] = set()
        for price, size in bids:
            seen_bid_prices.add(price)
            self._update_level(self._bid_levels, price, "bid", size, now)

        # Update ask levels
        seen_ask_prices: set[float] = set()
        for price, size in asks:
            seen_ask_prices.add(price)
            self._update_level(self._ask_levels, price, "ask", size, now)

        # Prune stale levels not in current snapshot
        self._prune_stale(self._bid_levels, seen_bid_prices, now)
        self._prune_stale(self._ask_levels, seen_ask_prices, now)

    def _update_level(
        self,
        levels: dict[float, LevelTracker],
        price: float,
        side: str,
        size: int,
        now: float,
    ) -> None:
        tracker = levels.get(price)
        if tracker is None:
            tracker = LevelTracker(price=price, side=side, first_seen=now)
            levels[price] = tracker

        prev_size = tracker.current_size

        # Detect refill: size dropped significantly then recovered
        if prev_size > 0 and tracker.last_size < prev_size * 0.3 and size >= prev_size * 0.7:
            tracker.refill_count += 1

        tracker.last_size = tracker.current_size
        tracker.current_size = size
        tracker.peak_size = max(tracker.peak_size, size)
        tracker.last_seen = now
        tracker.snapshots += 1

        # Decay-weighted cumulative: exponential moving sum
        dt = now - tracker.last_seen if tracker.last_seen > 0 else 0
        decay = 0.5 ** (dt / max(self.decay_half_life_sec, 1.0)) if dt > 0 else 1.0
        tracker.cumulative_size = tracker.cumulative_size * decay + size

    def _prune_stale(
        self, levels: dict[float, LevelTracker], seen: set[float], now: float
    ) -> None:
        stale_prices = [
            p
            for p, t in levels.items()
            if p not in seen and (now - t.last_seen) > self.wall_stale_sec
        ]
        for p in stale_prices:
            del levels[p]

    def get_significant_levels(self) -> list[dict[str, Any]]:
        """Return top levels per side, sorted by heat intensity."""
        all_levels: list[LevelTracker] = []

        for tracker in self._bid_levels.values():
            if tracker.current_size >= self.wall_min_size:
                all_levels.append(tracker)

        for tracker in self._ask_levels.values():
            if tracker.current_size >= self.wall_min_size:
                all_levels.append(tracker)

        if not all_levels:
            return []

        # Compute heat: normalize cumulative_size across all levels
        max_cumulative = max(t.cumulative_size for t in all_levels) or 1.0
        for t in all_levels:
            raw_heat = t.cumulative_size / max_cumulative
            # Boost for persistence and refills
            persistence_boost = min(t.persistence_sec / 300.0, 0.3)
            refill_boost = min(t.refill_count * 0.1, 0.2)
            t.heat = raw_heat + persistence_boost + refill_boost

        # Split by side and take top N per side
        bid_levels = sorted(
            [t for t in all_levels if t.side == "bid"],
            key=lambda t: t.heat,
            reverse=True,
        )[: self.max_levels_per_side]

        ask_levels = sorted(
            [t for t in all_levels if t.side == "ask"],
            key=lambda t: t.heat,
            reverse=True,
        )[: self.max_levels_per_side]

        combined = bid_levels + ask_levels
        now_utc = datetime.now(UTC)
        result = []
        for t in combined:
            first_utc = now_utc.timestamp() - (time.monotonic() - t.first_seen) if t.first_seen > 0 else 0
            last_utc = now_utc.timestamp() - (time.monotonic() - t.last_seen) if t.last_seen > 0 else 0
            result.append(
                {
                    "price": t.price,
                    "side": t.side,
                    "current_size": t.current_size,
                    "peak_size": t.peak_size,
                    "heat": round(t.heat, 4),
                    "persistence_sec": round(t.persistence_sec, 1),
                    "first_seen_utc": datetime.fromtimestamp(first_utc, tz=UTC).isoformat().replace("+00:00", "Z") if first_utc > 0 else "",
                    "last_seen_utc": datetime.fromtimestamp(last_utc, tz=UTC).isoformat().replace("+00:00", "Z") if last_utc > 0 else "",
                    "refill_count": t.refill_count,
                    "is_wall": t.current_size >= self.wall_min_size,
                    "distance": round(t.price - self._mid_price, 2) if self._mid_price > 0 else 0.0,
                }
            )

        return sorted(result, key=lambda l: l["heat"], reverse=True)

    def build_payload(self, *, symbol: str, exchange: str, connection_status: str) -> dict[str, Any]:
        return {
            "service": "mbo_levels_service",
            "service_version": "1.0.0",
            "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "sequence": self._snapshot_count,
            "symbol": symbol,
            "exchange": exchange,
            "connection_status": connection_status,
            "mid_price": round(self._mid_price, 2),
            "spread": round(self._spread, 4),
            "total_bid_depth": self._total_bid_depth,
            "total_ask_depth": self._total_ask_depth,
            "levels": self.get_significant_levels(),
            "config": {
                "wall_min_size": self.wall_min_size,
                "wall_stale_sec": self.wall_stale_sec,
                "max_levels_per_side": self.max_levels_per_side,
                "decay_half_life_sec": self.decay_half_life_sec,
            },
        }


def write_payload(path: Path, payload: dict[str, Any]) -> None:
    """Atomic JSON write via tmp + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    tmp.replace(path)


class MBOLevelsService:
    """Orchestrate Rithmic connection, DOM accumulation, and JSON output."""

    def __init__(
        self,
        *,
        user: str,
        password: str,
        system_name: str,
        url: str,
        app_name: str,
        symbol: str,
        exchange: str,
        output_path: Path,
        write_interval_sec: float,
        wall_min_size: int,
        wall_stale_sec: float,
        max_levels_per_side: int,
        decay_half_life_sec: float,
    ) -> None:
        self.user = user
        self.password = password
        self.system_name = system_name
        self.url = url
        self.app_name = app_name
        self.symbol = symbol
        self.exchange = exchange
        self.output_path = output_path
        self.write_interval_sec = write_interval_sec
        self._running = True
        self._connection_status = "disconnected"
        self._accumulator = DOMAccumulator(
            wall_min_size=wall_min_size,
            wall_stale_sec=wall_stale_sec,
            max_levels_per_side=max_levels_per_side,
            decay_half_life_sec=decay_half_life_sec,
        )

    def stop(self, *_: Any) -> None:
        LOGGER.info("Stop signal received")
        self._running = False

    async def _on_order_book(self, update: Any) -> None:
        """Handle L2 order book snapshot from async-rithmic.

        The raw protobuf (template 156) has separate repeated fields:
            bid_price[], bid_size[], ask_price[], ask_size[]
        Not nested objects with .price/.size attributes.
        """
        # Skip partial multi-part updates (BEGIN=4, MIDDLE=5).
        # Accept SOLO=7, END=6, SNAPSHOT_IMAGE=3, and UNSPECIFIED=0.
        update_type = getattr(update, "update_type", 0)
        if update_type in (4, 5):
            return

        bid_prices = list(getattr(update, "bid_price", []))
        bid_sizes = list(getattr(update, "bid_size", []))
        ask_prices = list(getattr(update, "ask_price", []))
        ask_sizes = list(getattr(update, "ask_size", []))

        bids = list(zip(bid_prices, bid_sizes))
        asks = list(zip(ask_prices, ask_sizes))

        self._accumulator.on_order_book(bids, asks)

    async def _write_loop(self) -> None:
        """Periodically write JSON snapshot."""
        while self._running:
            try:
                payload = self._accumulator.build_payload(
                    symbol=self.symbol,
                    exchange=self.exchange,
                    connection_status=self._connection_status,
                )
                write_payload(self.output_path, payload)
                level_count = len(payload.get("levels", []))
                LOGGER.debug(
                    "Wrote snapshot: %s (%d levels, mid=%.2f)",
                    self.output_path,
                    level_count,
                    payload.get("mid_price", 0),
                )
            except Exception:
                LOGGER.exception("Failed to write snapshot")
            await asyncio.sleep(self.write_interval_sec)

    async def run(self) -> int:
        """Main async entry point."""
        from async_rithmic import RithmicClient, ReconnectionSettings

        client = RithmicClient(
            user=self.user,
            password=self.password,
            system_name=self.system_name,
            app_name=self.app_name,
            app_version="1.0.0",
            url=self.url,
            reconnection_settings=ReconnectionSettings(
                max_retries=20,
                backoff_type="exponential",
                interval=1.0,
                max_delay=60.0,
                jitter_range=(0.5, 1.5),
            ),
        )

        client.on_order_book += self._on_order_book
        client.on_connected += lambda _plant_type: self._on_connected()
        client.on_disconnected += lambda _plant_type: self._on_disconnected()

        try:
            LOGGER.info(
                "Connecting to Rithmic: system=%s, url=%s, symbol=%s/%s",
                self.system_name,
                self.url,
                self.symbol,
                self.exchange,
            )
            await client.connect()
            await asyncio.sleep(0.5)  # Issue #49 workaround

            self._connection_status = "streaming"
            LOGGER.info("Connected. Subscribing to %s/%s order book...", self.symbol, self.exchange)

            # Subscribe to L2 order book
            from async_rithmic import DataType

            await client.subscribe_to_market_data(self.symbol, self.exchange, DataType.ORDER_BOOK)
            LOGGER.info("Subscribed. Writing to %s every %.1fs", self.output_path, self.write_interval_sec)

            # Start write loop
            write_task = asyncio.create_task(self._write_loop())

            # Keep running until stopped
            while self._running:
                await asyncio.sleep(0.25)

            write_task.cancel()
            try:
                await write_task
            except asyncio.CancelledError:
                pass

        except KeyboardInterrupt:
            LOGGER.info("Keyboard interrupt")
        except Exception:
            LOGGER.exception("Fatal error in MBO levels service")
            return 1
        finally:
            self._connection_status = "disconnected"
            try:
                await client.disconnect()
            except Exception:
                LOGGER.exception("Error during disconnect")

        return 0

    def _on_connected(self) -> None:
        self._connection_status = "streaming"
        LOGGER.info("Rithmic connected")

    def _on_disconnected(self) -> None:
        self._connection_status = "reconnecting"
        LOGGER.warning("Rithmic disconnected — waiting for reconnection")


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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream Rithmic L2 DOM data and export significant price levels as JSON for NinjaTrader."
    )
    parser.add_argument("--user", default="", help="Rithmic username (or RITHMIC_USER env)")
    parser.add_argument("--password", default="", help="Rithmic password (or RITHMIC_PASSWORD env)")
    parser.add_argument(
        "--system",
        default="",
        help='Rithmic system name, e.g. "Rithmic Paper Trading" (or RITHMIC_SYSTEM_NAME env)',
    )
    parser.add_argument(
        "--url",
        default="",
        help="Rithmic gateway URL (or RITHMIC_URI env). Default: rituz00100.rithmic.com:443 (test)",
    )
    parser.add_argument("--symbol", default="NQ", help="Futures symbol (default: NQ)")
    parser.add_argument("--exchange", default="CME", help="Exchange (default: CME)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="JSON output path")
    parser.add_argument("--write-interval", type=float, default=2.0, help="Seconds between JSON writes (default: 2)")
    parser.add_argument("--wall-min-size", type=int, default=100, help="Minimum contracts for a wall (default: 100)")
    parser.add_argument("--wall-stale-sec", type=float, default=90.0, help="Seconds before pruning absent levels (default: 90)")
    parser.add_argument("--max-levels", type=int, default=4, help="Max levels per side (default: 4)")
    parser.add_argument("--decay-half-life", type=float, default=120.0, help="Half-life for volume decay in seconds (default: 120)")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _load_env_files()
    args = parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    user = args.user or os.environ.get("RITHMIC_USER", "")
    password = args.password or os.environ.get("RITHMIC_PASSWORD", "")
    system_name = args.system or os.environ.get("RITHMIC_SYSTEM_NAME", "Apex")
    url = args.url or os.environ.get("RITHMIC_URI", "rprotocol.rithmic.com:443")

    if not user or not password:
        print(
            "ERROR: Rithmic credentials required.\n"
            "  Use --user/--password or set RITHMIC_USER/RITHMIC_PASSWORD in .env",
            file=sys.stderr,
        )
        return 1

    service = MBOLevelsService(
        user=user,
        password=password,
        system_name=system_name,
        url=url,
        app_name="migo:DEEP6:mbo",
        symbol=args.symbol,
        exchange=args.exchange,
        output_path=Path(args.output),
        write_interval_sec=max(0.5, args.write_interval),
        wall_min_size=max(1, args.wall_min_size),
        wall_stale_sec=max(5.0, args.wall_stale_sec),
        max_levels_per_side=max(1, args.max_levels),
        decay_half_life_sec=max(10.0, args.decay_half_life),
    )

    loop = asyncio.new_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, service.stop)
        except NotImplementedError:
            signal.signal(sig, service.stop)

    try:
        return loop.run_until_complete(service.run())
    finally:
        loop.close()


if __name__ == "__main__":
    raise SystemExit(main())
