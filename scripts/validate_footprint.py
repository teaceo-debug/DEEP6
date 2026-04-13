#!/usr/bin/env python3
"""Footprint validation script: export FootprintBar data to CSV for TradingView comparison.

Usage:
    python -m scripts.validate_footprint --bars 10 --output footprint_export.csv

Validation methodology (D-09, D-10, D-11):
  1. Run this script alongside a live Rithmic session during RTH
  2. Open the same NQ 1-min chart in TradingView with Bookmap Liquidity Mapper
  3. For each bar, compare bid_vol and ask_vol per price level
  4. Acceptable divergence: <10% per level (D-10 revised to 5-10% for Pine Script)
  5. If divergence >10%, inspect aggressor verification gate output first

Output CSV format:
  timestamp_utc, bar_open, bar_high, bar_low, bar_close, total_vol, bar_delta, cvd, poc_price,
  price_level, ask_vol, bid_vol
  (one row per price level per bar)

Per T-04-02: credentials from Config.from_env() are NEVER written to CSV or logs.
"""
import argparse
import asyncio
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path for script execution
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
import uvloop
from deep6.config import Config
from deep6.data.bar_builder import BarBuilder
from deep6.data.rithmic import connect_rithmic, register_callbacks
from deep6.state.footprint import tick_to_price
from deep6.state.shared import SharedState
from async_rithmic import DataType

log = structlog.get_logger()


async def run_and_collect(config: Config, target_bars: int, output_path: str) -> None:
    """Connect to Rithmic, collect target_bars of 1m bars, export to CSV."""
    state = SharedState.build(config)
    await state.persistence.initialize()

    collected_bars: list = []
    bar_event = asyncio.Event()

    # Capture bars by overriding on_bar_close via _on_bar_close_fn
    async def capturing_on_bar_close(label: str, bar) -> None:
        if label != "1m":
            return
        collected_bars.append(bar)
        log.info(
            "footprint.bar_collected",
            bar_num=len(collected_bars),
            target=target_bars,
            close=bar.close,
            bar_delta=bar.bar_delta,
            total_vol=bar.total_vol,
            poc=bar.poc_price,
        )
        if len(collected_bars) >= target_bars:
            bar_event.set()

    state._on_bar_close_fn = capturing_on_bar_close

    bb_1m = BarBuilder(period_seconds=60, label="1m", state=state)
    bb_5m = BarBuilder(period_seconds=300, label="5m", state=state)
    state.bar_builders = [bb_1m, bb_5m]

    client = await connect_rithmic(config)
    register_callbacks(client, state)
    await client.subscribe_to_market_data(
        config.instrument, config.exchange, DataType.LAST_TRADE
    )
    await client.subscribe_to_market_data(
        config.instrument, config.exchange, DataType.ORDER_BOOK
    )

    session_mgr = state.session_manager()
    tasks = [
        asyncio.create_task(bb_1m.run(), name="bar_builder_1m"),
        asyncio.create_task(bb_5m.run(), name="bar_builder_5m"),
        asyncio.create_task(session_mgr.run(), name="session_manager"),
    ]

    log.info("validate_footprint.waiting_for_bars", target=target_bars)
    try:
        await bar_event.wait()
    finally:
        for task in tasks:
            task.cancel()

    if not collected_bars:
        log.warning("validate_footprint.no_bars_collected")
        print("\nNo bars collected. Ensure the script runs during RTH (9:30-16:00 ET).")
        return

    # Write CSV — price/volume data only; no credentials (T-04-01)
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp_utc", "bar_open", "bar_high", "bar_low", "bar_close",
            "total_vol", "bar_delta", "cvd", "poc_price",
            "price_level", "ask_vol", "bid_vol",
        ])
        for bar in collected_bars:
            ts = datetime.fromtimestamp(bar.timestamp, tz=timezone.utc).isoformat()
            for tick, level in sorted(bar.levels.items()):
                price = tick_to_price(tick)
                writer.writerow([
                    ts, bar.open, bar.high, bar.low, bar.close,
                    bar.total_vol, bar.bar_delta, bar.cvd, bar.poc_price,
                    price, level.ask_vol, level.bid_vol,
                ])

    log.info("validate_footprint.exported", path=output_path, bars=len(collected_bars))
    print(f"\nExported {len(collected_bars)} bars to {output_path}")
    print("Compare price_level / ask_vol / bid_vol columns against TradingView Bookmap indicator.")
    print("Acceptable divergence: <10% per level (D-10).")


def main() -> None:
    """CLI entry point."""
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )
    parser = argparse.ArgumentParser(
        description="Export footprint bars for TradingView validation"
    )
    parser.add_argument(
        "--bars", type=int, default=10,
        help="Number of 1m bars to capture (default: 10)"
    )
    parser.add_argument(
        "--output", default="footprint_export.csv",
        help="Output CSV file path (default: footprint_export.csv)"
    )
    args = parser.parse_args()

    config = Config.from_env()
    with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
        runner.run(run_and_collect(config, args.bars, args.output))


if __name__ == "__main__":
    main()
