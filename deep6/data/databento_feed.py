"""Databento historical data feed for development and backtesting.

Replays CME MBO (Market-by-Order) data through the same FootprintBar
pipeline as live Rithmic data. Uses identical trade classification
(aggressor field A=ask/B=bid from CME native data).

Usage:
    feed = DatabentoFeed(api_key="...", dataset="GLBX.MDP3")
    async for bar in feed.replay_bars("NQ.c.0", "2026-04-10", "2026-04-10", bar_seconds=60):
        # bar is a finalized FootprintBar
        signals = engine.process(bar)
"""
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import AsyncIterator

import databento as db

from deep6.state.footprint import FootprintBar, FootprintLevel, price_to_tick


class DatabentoFeed:
    """Replay historical CME data through FootprintBar accumulator."""

    def __init__(self, api_key: str, dataset: str = "GLBX.MDP3"):
        self.client = db.Historical(key=api_key)
        self.dataset = dataset

    async def replay_bars(
        self,
        symbol: str,
        start: str,
        end: str,
        bar_seconds: int = 60,
        tick_size: float = 0.25,
    ) -> AsyncIterator[FootprintBar]:
        """Replay trades and yield FootprintBars at bar boundaries.

        Args:
            symbol: Databento symbol (e.g., "NQ.c.0" for NQ front month)
            start: Start date/time ISO format
            end: End date/time ISO format
            bar_seconds: Bar duration in seconds (default 60 = 1-min bars)
            tick_size: Instrument tick size (NQ = 0.25)

        Yields:
            FootprintBar for each completed bar
        """
        data = self.client.timeseries.get_range(
            dataset=self.dataset,
            schema="trades",
            stype_in="continuous",
            symbols=[symbol],
            start=start,
            end=end,
        )

        current_bar = FootprintBar(tick_size=tick_size)
        current_boundary = None
        bar_count = 0

        for record in data:
            price = record.price / 1e9
            size = record.size
            side = chr(record.side)  # 'A' = ask aggressor, 'B' = bid aggressor
            ts_ns = record.ts_event
            ts = datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc)

            # Determine bar boundary
            bar_epoch = int(ts.timestamp()) // bar_seconds * bar_seconds
            if current_boundary is None:
                current_boundary = bar_epoch
                current_bar.open_time = datetime.fromtimestamp(bar_epoch, tz=timezone.utc)

            # Bar closed — finalize and yield
            if bar_epoch > current_boundary:
                current_bar.close_time = datetime.fromtimestamp(current_boundary + bar_seconds, tz=timezone.utc)
                current_bar.finalize()
                bar_count += 1
                yield current_bar

                # Start new bar
                current_bar = FootprintBar(tick_size=tick_size)
                current_bar.open_time = datetime.fromtimestamp(bar_epoch, tz=timezone.utc)
                current_boundary = bar_epoch

            # Accumulate trade into footprint
            # Databento: A=ask aggressor (buyer), B=bid aggressor (seller)
            # FootprintBar: 1=BUY (ask aggressor), 2=SELL (bid aggressor)
            aggressor = 1 if side == "A" else 2
            current_bar.add_trade(price, size, aggressor)

        # Yield final partial bar if it has data
        if current_bar.total_volume > 0:
            current_bar.close_time = datetime.fromtimestamp(
                (current_boundary or 0) + bar_seconds, tz=timezone.utc
            )
            current_bar.finalize()
            yield current_bar
