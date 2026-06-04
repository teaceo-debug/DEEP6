"""Tests for the lightweight OHLCV bar accumulator."""
from __future__ import annotations

import pytest

from deep6.engines.ohlcv_accumulator import OHLCVAccumulator, OHLCVBar


BASE_TS = 1_800_000_000.0  # epoch anchor aligned to 60s boundary (1800000000 % 60 == 0)


class TestOHLCVAccumulator:
    """Core accumulator behaviour."""

    def test_first_tick_opens_bar_returns_none(self):
        acc = OHLCVAccumulator("ES", interval_sec=60)
        result = acc.feed_tick(price=4500.0, volume=3.0, timestamp=BASE_TS + 5)
        assert result is None
        assert acc.current_bar_start is not None

    def test_ten_ticks_in_single_bar(self):
        """10 ticks within 60s should NOT close a bar (all return None)."""
        acc = OHLCVAccumulator("ES", interval_sec=60)
        bar_start = BASE_TS
        for i in range(10):
            result = acc.feed_tick(
                price=4500.0 + i, volume=1.0, timestamp=bar_start + i * 5
            )
            assert result is None

    def test_boundary_crossing_returns_completed_bar(self):
        """Tick in next interval closes the previous bar."""
        acc = OHLCVAccumulator("ES", interval_sec=60)
        # Feed ticks in first bar
        acc.feed_tick(price=4500.0, volume=2.0, timestamp=BASE_TS + 1)
        acc.feed_tick(price=4510.0, volume=3.0, timestamp=BASE_TS + 30)
        acc.feed_tick(price=4495.0, volume=1.0, timestamp=BASE_TS + 55)

        # Tick that crosses into next bar
        bar = acc.feed_tick(price=4520.0, volume=4.0, timestamp=BASE_TS + 61)
        assert bar is not None
        assert isinstance(bar, OHLCVBar)
        assert bar.symbol == "ES"
        assert bar.open == 4500.0
        assert bar.high == 4510.0
        assert bar.low == 4495.0
        assert bar.close == 4495.0
        assert bar.volume == 6.0
        assert bar.tick_count == 3

    def test_ohlcv_correct_after_ten_ticks(self):
        """10 ticks in one bar, then boundary cross → verify OHLCV."""
        acc = OHLCVAccumulator("YM", interval_sec=60)
        prices = [100.0, 105.0, 98.0, 102.0, 110.0, 99.0, 103.0, 107.0, 95.0, 101.0]
        bar_start = BASE_TS
        for i, p in enumerate(prices):
            acc.feed_tick(price=p, volume=1.0, timestamp=bar_start + i)

        # Cross boundary
        bar = acc.feed_tick(price=200.0, volume=1.0, timestamp=bar_start + 61)
        assert bar is not None
        assert bar.open == 100.0
        assert bar.high == 110.0
        assert bar.low == 95.0
        assert bar.close == 101.0
        assert bar.volume == 10.0
        assert bar.tick_count == 10

    def test_flush_returns_partial_bar(self):
        acc = OHLCVAccumulator("RTY", interval_sec=60)
        acc.feed_tick(price=2000.0, volume=5.0, timestamp=BASE_TS + 10)
        acc.feed_tick(price=2005.0, volume=3.0, timestamp=BASE_TS + 20)

        bar = acc.flush()
        assert bar is not None
        assert bar.open == 2000.0
        assert bar.high == 2005.0
        assert bar.low == 2000.0
        assert bar.close == 2005.0
        assert bar.volume == 8.0
        assert bar.tick_count == 2

    def test_flush_empty_returns_none(self):
        acc = OHLCVAccumulator("ES", interval_sec=60)
        assert acc.flush() is None

    def test_high_low_tracking(self):
        """High and low are correctly tracked through varying prices."""
        acc = OHLCVAccumulator("NQ", interval_sec=60)
        bar_start = BASE_TS
        acc.feed_tick(price=18000.0, volume=1.0, timestamp=bar_start + 1)
        acc.feed_tick(price=18050.0, volume=1.0, timestamp=bar_start + 2)  # new high
        acc.feed_tick(price=17900.0, volume=1.0, timestamp=bar_start + 3)  # new low
        acc.feed_tick(price=17950.0, volume=1.0, timestamp=bar_start + 4)  # mid
        acc.feed_tick(price=18100.0, volume=1.0, timestamp=bar_start + 5)  # new high
        acc.feed_tick(price=17850.0, volume=1.0, timestamp=bar_start + 6)  # new low

        bar = acc.flush()
        assert bar is not None
        assert bar.high == 18100.0
        assert bar.low == 17850.0
        assert bar.open == 18000.0
        assert bar.close == 17850.0

    def test_bar_end_ts_equals_start_plus_interval(self):
        acc = OHLCVAccumulator("ES", interval_sec=30)
        acc.feed_tick(price=4500.0, volume=1.0, timestamp=BASE_TS + 1)
        bar = acc.feed_tick(price=4510.0, volume=1.0, timestamp=BASE_TS + 31)
        assert bar is not None
        assert bar.bar_end_ts == bar.bar_start_ts + 30

    def test_flush_resets_state(self):
        """After flush, accumulator is empty — next tick starts fresh."""
        acc = OHLCVAccumulator("ES", interval_sec=60)
        acc.feed_tick(price=4500.0, volume=1.0, timestamp=BASE_TS + 1)
        acc.flush()

        assert acc.current_bar_start is None
        assert acc.flush() is None  # double flush → None

    def test_multiple_bar_closures(self):
        """Feed ticks across 3 intervals, expect 2 completed bars."""
        acc = OHLCVAccumulator("ES", interval_sec=60)
        bars = []
        # Bar 1: ts 0-59
        acc.feed_tick(price=100.0, volume=1.0, timestamp=BASE_TS + 5)
        # Bar 2 tick closes bar 1
        b = acc.feed_tick(price=200.0, volume=1.0, timestamp=BASE_TS + 65)
        if b:
            bars.append(b)
        # Bar 3 tick closes bar 2
        b = acc.feed_tick(price=300.0, volume=1.0, timestamp=BASE_TS + 125)
        if b:
            bars.append(b)

        assert len(bars) == 2
        assert bars[0].close == 100.0
        assert bars[1].close == 200.0
