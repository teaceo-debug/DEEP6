"""Test suite for all 5 auction theory variants + E9 FSM + persistence (AUCT-01..05, ENG-09).

Covers:
  - AUCT-01: Unfinished Business — non-zero bid at high / ask at low
  - AUCT-02: Finished Auction — zero bid at high / zero ask at low
  - AUCT-03: Poor High / Poor Low — low-volume extreme
  - AUCT-04: Volume Void — LVN gap within bar
  - AUCT-05: Market Sweep — rapid traversal with increasing volume
  - ENG-09: FSM states — EXPLORING_UP, BALANCED, BREAKOUT
  - Unfinished level tracking (get/load/clear)
  - Async persistence round-trip (persist -> restore -> resolve)
  - Config override behavior
  - Edge cases: empty bar, single-level bar
"""
import asyncio
import os
import tempfile
from collections import defaultdict

import pytest

from deep6.engines.auction import (
    AuctionEngine,
    AuctionState,
    AuctionType,
    AuctionSignal,
)
from deep6.engines.signal_config import AuctionConfig
from deep6.state.footprint import FootprintBar, FootprintLevel, price_to_tick, tick_to_price
from deep6.state.persistence import SessionPersistence


# ---------------------------------------------------------------------------
# Helper: build FootprintBar from dict {price: (bid_vol, ask_vol)}
# ---------------------------------------------------------------------------

def make_bar(
    levels_data: dict,
    open_px: float = 21000.0,
    close: float = 21000.0,
) -> FootprintBar:
    """Build a FootprintBar from {price: (bid_vol, ask_vol)} dict.

    open_px and close control bar direction for market sweep tests.
    """
    bar = FootprintBar()
    bar.open = open_px
    bar.close = close
    total_bid = total_ask = 0
    prices = sorted(levels_data.keys())

    for price in prices:
        bid, ask = levels_data[price]
        tick = price_to_tick(price)
        bar.levels[tick] = FootprintLevel(bid_vol=bid, ask_vol=ask)
        total_bid += bid
        total_ask += ask

    bar.total_vol = total_bid + total_ask
    bar.bar_delta = total_ask - total_bid

    if prices:
        bar.high = max(prices)
        bar.low = min(prices)
        bar.bar_range = bar.high - bar.low
        max_tick = max(
            bar.levels.keys(),
            key=lambda t: bar.levels[t].bid_vol + bar.levels[t].ask_vol,
        )
        bar.poc_price = tick_to_price(max_tick)

    return bar


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

def test_empty_bar_returns_no_signals():
    """Empty bar with no levels returns empty signal list."""
    engine = AuctionEngine()
    bar = FootprintBar()
    result = engine.process(bar)
    assert result == []


def test_zero_volume_bar_returns_no_signals():
    """Bar with levels but total_vol == 0 returns empty list."""
    engine = AuctionEngine()
    bar = FootprintBar()
    bar.total_vol = 0
    result = engine.process(bar)
    assert result == []


def test_single_level_bar_returns_no_signals():
    """Single-level bar returns empty list (needs 2+ ticks for most signals)."""
    engine = AuctionEngine()
    bar = make_bar({21000.0: (5, 5)})
    result = engine.process(bar)
    assert result == []


# ---------------------------------------------------------------------------
# AUCT-01: Unfinished Business
# ---------------------------------------------------------------------------

def test_unfinished_business_high():
    """AUCT-01: Non-zero bid_vol at bar high fires UNFINISHED_BUSINESS direction=+1.

    Bid at high = buyers still present = price will return upward.
    """
    engine = AuctionEngine()
    bar = make_bar({
        21000.00: (10, 10),
        21000.25: (5, 0),   # high tick: bid=5, ask=0 -> unfinished upward
    })
    signals = engine.process(bar)
    ub = [s for s in signals if s.auction_type == AuctionType.UNFINISHED_BUSINESS]
    assert len(ub) >= 1
    high_ub = [s for s in ub if s.direction == +1]
    assert len(high_ub) >= 1
    assert high_ub[0].price == pytest.approx(21000.25)


def test_unfinished_business_low():
    """AUCT-01: Non-zero ask_vol at bar low fires UNFINISHED_BUSINESS direction=-1.

    Ask at low = sellers still present = price will return downward.
    """
    engine = AuctionEngine()
    bar = make_bar({
        21000.00: (0, 5),   # low tick: ask=5, bid=0 -> unfinished downward
        21000.25: (10, 10),
    })
    signals = engine.process(bar)
    ub = [s for s in signals if s.auction_type == AuctionType.UNFINISHED_BUSINESS]
    low_ub = [s for s in ub if s.direction == -1]
    assert len(low_ub) >= 1
    assert low_ub[0].price == pytest.approx(21000.0)


# ---------------------------------------------------------------------------
# AUCT-02: Finished Auction
# ---------------------------------------------------------------------------

def test_finished_auction_high():
    """AUCT-02: bid_vol == 0 and ask_vol > 0 at high fires FINISHED_AUCTION direction=-1.

    Zero bid at high = buyers exhausted = auction complete, price moves down.
    """
    engine = AuctionEngine()
    bar = make_bar({
        21000.00: (10, 10),
        21000.25: (0, 8),   # high tick: bid=0, ask=8 -> finished auction bearish
    })
    signals = engine.process(bar)
    fa = [s for s in signals if s.auction_type == AuctionType.FINISHED_AUCTION]
    bearish_fa = [s for s in fa if s.direction == -1]
    assert len(bearish_fa) >= 1
    assert bearish_fa[0].price == pytest.approx(21000.25)


def test_finished_auction_low():
    """AUCT-02: ask_vol == 0 and bid_vol > 0 at low fires FINISHED_AUCTION direction=+1.

    Zero ask at low = sellers exhausted = auction complete, price moves up.
    """
    engine = AuctionEngine()
    bar = make_bar({
        21000.00: (8, 0),   # low tick: ask=0, bid=8 -> finished auction bullish
        21000.25: (10, 10),
    })
    signals = engine.process(bar)
    fa = [s for s in signals if s.auction_type == AuctionType.FINISHED_AUCTION]
    bullish_fa = [s for s in fa if s.direction == +1]
    assert len(bullish_fa) >= 1
    assert bullish_fa[0].price == pytest.approx(21000.0)


# ---------------------------------------------------------------------------
# AUCT-03: Poor High / Poor Low
# ---------------------------------------------------------------------------

def test_poor_high():
    """AUCT-03: Volume at high < 30% of avg_vol fires POOR_HIGH.

    4 levels: most have high volume, high tick has minimal volume.
    avg_vol = total_vol / num_levels
    high_vol < avg_vol * 0.3 -> POOR_HIGH
    """
    engine = AuctionEngine()
    # Total vol: 3 levels with (50,50)=100 each + high with (1,1)=2
    # avg_vol = (300 + 2) / 4 = 75.5; high_vol = 2; 2 < 75.5 * 0.3 = 22.65 -> POOR_HIGH
    bar = make_bar({
        21000.00: (50, 50),
        21000.25: (50, 50),
        21000.50: (50, 50),
        21000.75: (1, 1),   # high tick: minimal volume
    })
    signals = engine.process(bar)
    poor_high = [s for s in signals if s.auction_type == AuctionType.POOR_HIGH]
    assert len(poor_high) >= 1
    assert poor_high[0].price == pytest.approx(21000.75)


def test_poor_low():
    """AUCT-03: Volume at low < 30% of avg_vol fires POOR_LOW."""
    engine = AuctionEngine()
    bar = make_bar({
        21000.00: (1, 1),   # low tick: minimal volume
        21000.25: (50, 50),
        21000.50: (50, 50),
        21000.75: (50, 50),
    })
    signals = engine.process(bar)
    poor_low = [s for s in signals if s.auction_type == AuctionType.POOR_LOW]
    assert len(poor_low) >= 1
    assert poor_low[0].price == pytest.approx(21000.0)


# ---------------------------------------------------------------------------
# AUCT-04: Volume Void
# ---------------------------------------------------------------------------

def test_volume_void():
    """AUCT-04: 3+ levels with < 5% of max vol fires VOLUME_VOID.

    max_vol level has 200 units; void levels have < 10 units (5% of 200).
    Need >= 3 void levels.
    """
    engine = AuctionEngine()
    bar = make_bar(
        {
            21000.00: (100, 100),  # high vol level, max=200
            21000.25: (2, 3),      # void: 5 < 200*0.05=10
            21000.50: (3, 2),      # void: 5 < 10
            21000.75: (1, 4),      # void: 5 < 10
            21001.00: (80, 80),    # normal level
        },
        open_px=21000.0,
        close=21001.0,  # up bar
    )
    signals = engine.process(bar)
    voids = [s for s in signals if s.auction_type == AuctionType.VOLUME_VOID]
    assert len(voids) >= 1


def test_volume_void_insufficient_levels():
    """AUCT-04: Only 2 void levels (below min_levels=3) does NOT fire VOLUME_VOID."""
    engine = AuctionEngine()
    bar = make_bar(
        {
            21000.00: (100, 100),
            21000.25: (2, 3),      # void 1
            21000.50: (3, 2),      # void 2 — only 2, need 3
            21000.75: (80, 80),    # normal
        },
        open_px=21000.0,
        close=21000.75,
    )
    signals = engine.process(bar)
    voids = [s for s in signals if s.auction_type == AuctionType.VOLUME_VOID]
    assert len(voids) == 0


# ---------------------------------------------------------------------------
# AUCT-05: Market Sweep
# ---------------------------------------------------------------------------

def test_market_sweep_up():
    """AUCT-05: Up bar where second half vol > 1.5x first half fires MARKET_SWEEP +1.

    Need >= sweep_min_levels=10 levels.
    """
    engine = AuctionEngine()
    # 10 levels: first 5 have 20 vol each (total 100), second 5 have 60 vol each (total 300)
    # 300 / 100 = 3.0 > 1.5 -> MARKET_SWEEP
    levels = {}
    for i in range(5):
        levels[21000.0 + i * 0.25] = (10, 10)   # 20 vol each
    for i in range(5, 10):
        levels[21000.0 + i * 0.25] = (30, 30)   # 60 vol each
    bar = make_bar(levels, open_px=21000.0, close=21002.25)  # up bar (close > open)
    signals = engine.process(bar)
    sweeps = [s for s in signals if s.auction_type == AuctionType.MARKET_SWEEP]
    up_sweeps = [s for s in sweeps if s.direction == +1]
    assert len(up_sweeps) >= 1


def test_market_sweep_down():
    """AUCT-05: Down bar where lower-half vol > 1.5x upper-half fires MARKET_SWEEP -1.

    For down sweep: first half of sorted_ticks is UPPER (higher prices),
    second half is LOWER (lower prices). Down sweep checks lower half vol > upper half.

    Note: In AuctionEngine for down bar, first_half_vol = sorted_ticks[half:] (upper),
    second_half_vol = sorted_ticks[:half] (lower).
    """
    engine = AuctionEngine()
    # 10 levels: LOWER 5 (lower prices) have 60 vol, UPPER 5 have 20 vol
    # For down bar: first_half_vol (upper = sorted[half:]) = 5*20=100,
    # second_half_vol (lower = sorted[:half]) = 5*60=300, 300>100*1.5 -> SWEEP
    levels = {}
    for i in range(5):
        levels[21000.0 + i * 0.25] = (30, 30)   # lower prices: 60 vol each
    for i in range(5, 10):
        levels[21000.0 + i * 0.25] = (10, 10)   # upper prices: 20 vol each
    bar = make_bar(levels, open_px=21002.25, close=21000.0)  # down bar
    signals = engine.process(bar)
    sweeps = [s for s in signals if s.auction_type == AuctionType.MARKET_SWEEP]
    down_sweeps = [s for s in sweeps if s.direction == -1]
    assert len(down_sweeps) >= 1


# ---------------------------------------------------------------------------
# ENG-09: FSM State Machine
# ---------------------------------------------------------------------------

def test_fsm_exploring_up():
    """ENG-09: Bar making new high (but range < breakout_range_threshold) -> EXPLORING_UP."""
    engine = AuctionEngine()

    # First bar establishes range
    bar1 = make_bar({21000.0: (10, 10), 21001.0: (10, 10)})
    bar1.high = 21001.0
    bar1.low = 21000.0
    engine.process(bar1)

    # Second bar makes new high (above 21001), small range -> EXPLORING_UP
    bar2 = make_bar({21001.0: (10, 10), 21001.5: (10, 10)})
    bar2.high = 21001.5
    bar2.low = 21001.0
    engine.process(bar2)

    assert engine.state == AuctionState.EXPLORING_UP


def test_fsm_balanced():
    """ENG-09: 3+ bars inside prior range -> BALANCED state."""
    engine = AuctionEngine()

    # Establish range with bar 1
    bar1 = make_bar({21000.0: (10, 10), 21002.0: (10, 10)})
    bar1.high = 21002.0
    bar1.low = 21000.0
    engine.process(bar1)

    # balance_count_threshold default = 3: process 3 bars inside range
    for _ in range(3):
        inside_bar = make_bar({21000.5: (10, 10), 21001.5: (10, 10)})
        inside_bar.high = 21001.5
        inside_bar.low = 21000.5
        engine.process(inside_bar)

    assert engine.state == AuctionState.BALANCED


def test_fsm_exploring_down():
    """ENG-09: Bar making new low -> EXPLORING_DOWN state."""
    engine = AuctionEngine()

    bar1 = make_bar({21000.0: (10, 10), 21001.0: (10, 10)})
    bar1.high = 21001.0
    bar1.low = 21000.0
    engine.process(bar1)

    bar2 = make_bar({20999.5: (10, 10), 21000.0: (10, 10)})
    bar2.high = 21000.0
    bar2.low = 20999.5
    engine.process(bar2)

    assert engine.state == AuctionState.EXPLORING_DOWN


def test_fsm_breakout():
    """ENG-09: Bar making new high with large range expansion -> BREAKOUT state.

    breakout_range_threshold default = 2.0 (bar range >= 2x prior range).
    """
    config = AuctionConfig(breakout_range_threshold=2.0)
    engine = AuctionEngine(config)

    # Establish narrow range: 21000.0 - 21001.0, bar_range = 1.0
    bar1 = make_bar({21000.0: (10, 10), 21001.0: (10, 10)})
    bar1.high = 21001.0
    bar1.low = 21000.0
    bar1.bar_range = 1.0
    engine.process(bar1)

    # Breakout bar: new high AND range >= 2.0 * prior_range
    # prev_high - prev_low = 21001.0 - 21000.0 = 1.0
    # bar_range / prev_range = 3.0 / 1.0 = 3.0 >= 2.0 -> BREAKOUT
    bar2 = make_bar({21001.0: (10, 10), 21004.0: (10, 10)})
    bar2.high = 21004.0
    bar2.low = 21001.0
    bar2.bar_range = 3.0
    engine.process(bar2)

    assert engine.state == AuctionState.BREAKOUT


def test_fsm_resets_balance_count_on_expansion():
    """ENG-09: Expanding bar resets balance_count to 0."""
    engine = AuctionEngine()

    # Establish range
    bar1 = make_bar({21000.0: (10, 10), 21002.0: (10, 10)})
    bar1.high = 21002.0
    bar1.low = 21000.0
    engine.process(bar1)

    # 2 inside bars (balance_count = 2, but threshold=3)
    for _ in range(2):
        inside_bar = make_bar({21000.5: (10, 10), 21001.5: (10, 10)})
        inside_bar.high = 21001.5
        inside_bar.low = 21000.5
        engine.process(inside_bar)

    assert engine.balance_count == 2

    # Expanding bar resets balance_count
    expanding = make_bar({21002.0: (10, 10), 21003.0: (10, 10)})
    expanding.high = 21003.0
    expanding.low = 21002.0
    engine.process(expanding)

    assert engine.balance_count == 0


# ---------------------------------------------------------------------------
# Unfinished level tracking
# ---------------------------------------------------------------------------

def test_unfinished_levels_tracking():
    """After processing a bar with UNFINISHED_BUSINESS at high, get_unfinished_levels() returns it."""
    engine = AuctionEngine()
    bar = make_bar({
        21000.00: (10, 10),
        21000.25: (5, 0),  # bid at high -> UNFINISHED +1
    })
    engine.process(bar)
    levels = engine.get_unfinished_levels()
    prices = [l["price"] for l in levels]
    assert 21000.25 in prices


def test_load_unfinished_levels():
    """load_unfinished_levels() populates engine correctly from list of dicts."""
    engine = AuctionEngine()
    test_levels = [
        {"price": 21000.25, "direction": +1, "strength": 0.6, "timestamp": 1234567.0},
        {"price": 20999.75, "direction": -1, "strength": 0.7, "timestamp": 1234568.0},
    ]
    engine.load_unfinished_levels(test_levels)
    levels = engine.get_unfinished_levels()
    prices = {l["price"] for l in levels}
    assert 21000.25 in prices
    assert 20999.75 in prices
    # Verify direction was preserved
    level_map = {l["price"]: l for l in levels}
    assert level_map[21000.25]["direction"] == +1
    assert level_map[20999.75]["direction"] == -1


def test_clear_finished_level():
    """clear_finished_level() removes the price from unfinished_levels tracking."""
    engine = AuctionEngine()
    bar = make_bar({
        21000.00: (10, 10),
        21000.25: (5, 0),  # unfinished at high
    })
    engine.process(bar)
    assert 21000.25 in {l["price"] for l in engine.get_unfinished_levels()}

    engine.clear_finished_level(21000.25)
    assert 21000.25 not in {l["price"] for l in engine.get_unfinished_levels()}


def test_clear_nonexistent_level_no_error():
    """clear_finished_level() on a non-tracked price does not raise."""
    engine = AuctionEngine()
    engine.clear_finished_level(99999.0)  # should not raise


# ---------------------------------------------------------------------------
# Config override tests
# ---------------------------------------------------------------------------

def test_config_overrides_poor_extreme_ratio():
    """AuctionConfig(poor_extreme_vol_ratio=0.1) changes poor high/low threshold.

    With default 0.3: vol=15, avg=50 -> 15 < 50*0.3=15 barely fires (== not <).
    With 0.4: 15 < 50*0.4=20 -> POOR_HIGH fires.
    With 0.1: 15 < 50*0.1=5 -> does NOT fire (15 >= 5).
    """
    # Build bar: 3 levels with 50 vol each + high with 15 vol
    # avg_vol = (150 + 15) / 4 = 41.25
    # high_vol = 15; 15 < 41.25 * 0.3 = 12.375 -> False (15 > 12.375) -> NOT poor at 0.3
    # With 0.5: 15 < 41.25 * 0.5 = 20.625 -> True -> POOR_HIGH fires
    bar = make_bar({
        21000.00: (25, 25),  # 50 vol
        21000.25: (25, 25),  # 50 vol
        21000.50: (25, 25),  # 50 vol
        21000.75: (7, 8),    # 15 vol at high
    })

    # Default config (0.3): 15 > 12.375 -> NO poor_high
    engine_default = AuctionEngine()
    sigs_default = engine_default.process(bar)
    poor_default = [s for s in sigs_default if s.auction_type == AuctionType.POOR_HIGH]
    assert len(poor_default) == 0  # 15 is not < 12.375

    # Strict config (0.5): 15 < 20.625 -> POOR_HIGH fires
    engine_strict = AuctionEngine(AuctionConfig(poor_extreme_vol_ratio=0.5))
    sigs_strict = engine_strict.process(bar)
    poor_strict = [s for s in sigs_strict if s.auction_type == AuctionType.POOR_HIGH]
    assert len(poor_strict) >= 1


def test_config_balance_count_threshold():
    """AuctionConfig(balance_count_threshold=2) reaches BALANCED faster."""
    config = AuctionConfig(balance_count_threshold=2)
    engine = AuctionEngine(config)

    bar1 = make_bar({21000.0: (10, 10), 21002.0: (10, 10)})
    bar1.high = 21002.0
    bar1.low = 21000.0
    engine.process(bar1)

    # Only 2 inside bars needed (threshold=2)
    for _ in range(2):
        inside_bar = make_bar({21000.5: (10, 10), 21001.5: (10, 10)})
        inside_bar.high = 21001.5
        inside_bar.low = 21000.5
        engine.process(inside_bar)

    assert engine.state == AuctionState.BALANCED


# ---------------------------------------------------------------------------
# Async persistence round-trip (AUCT cross-session)
# ---------------------------------------------------------------------------

def test_auction_persistence_roundtrip():
    """Persist -> restore -> resolve cycle with a temp-file SQLite DB.

    aiosqlite opens a new connection per operation, so :memory: creates a fresh
    empty DB each call. Use a real temp file to test persistence across connections.

    Verifies that unfinished auction levels survive a process restart
    (simulated as persist then restore in a fresh engine).
    """
    async def _run(db_path: str):
        persistence = SessionPersistence(db_path)
        await persistence.initialize()

        # Session 1: Engine processes bar with unfinished business
        engine1 = AuctionEngine()
        bar = make_bar({
            21000.00: (10, 10),
            21000.25: (5, 0),   # unfinished at high +1
            21000.50: (0, 5),   # We'll check this is added differently
        })
        # Manually add a bar with unfinished at low too
        bar2 = make_bar({
            20999.75: (0, 5),   # unfinished at low -1
            21000.00: (10, 10),
        })
        engine1.process(bar)
        engine1.process(bar2)

        levels = engine1.get_unfinished_levels()
        assert len(levels) >= 1

        # Persist to SQLite
        await persistence.persist_auction_levels("20260413", levels)

        # Session 2: Fresh engine restores from SQLite
        engine2 = AuctionEngine()
        assert len(engine2.get_unfinished_levels()) == 0

        restored = await persistence.restore_auction_levels(max_sessions=5)
        assert len(restored) >= 1

        engine2.load_unfinished_levels(restored)
        restored_prices = {l["price"] for l in engine2.get_unfinished_levels()}
        # At least one price from session 1 should be restored
        original_prices = {l["price"] for l in levels}
        assert len(restored_prices & original_prices) >= 1

        # Resolve one level (price returned to it)
        price_to_resolve = next(iter(restored_prices & original_prices))
        await persistence.resolve_auction_level(price_to_resolve)
        engine2.clear_finished_level(price_to_resolve)

        # Verify it's gone from engine
        remaining = {l["price"] for l in engine2.get_unfinished_levels()}
        assert price_to_resolve not in remaining

        # Verify it's resolved in DB
        still_unresolved = await persistence.restore_auction_levels(max_sessions=5)
        unresolved_prices = {l["price"] for l in still_unresolved}
        assert price_to_resolve not in unresolved_prices

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        pass  # just get the path
        db_path = f.name
    try:
        asyncio.run(_run(db_path))
    finally:
        os.unlink(db_path)


def test_auction_persistence_empty_session():
    """Restoring from a fresh DB returns empty list (no error)."""
    async def _run(db_path: str):
        persistence = SessionPersistence(db_path)
        await persistence.initialize()
        levels = await persistence.restore_auction_levels(max_sessions=5)
        assert levels == []

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        asyncio.run(_run(db_path))
    finally:
        os.unlink(db_path)


def test_engine_reset():
    """reset() clears all engine state."""
    engine = AuctionEngine()

    # Process a bar to set some state
    bar = make_bar({21000.0: (10, 10), 21002.0: (10, 10)})
    bar.high = 21002.0
    bar.low = 21000.0
    engine.process(bar)

    # Manually add an unfinished level
    engine.unfinished_levels[21002.0] = {"direction": +1, "strength": 0.6, "timestamp": 0.0}
    engine.balance_count = 5

    engine.reset()

    assert engine.state == AuctionState.BALANCED
    assert engine.prev_high == 0.0
    assert engine.prev_low == float("inf")
    assert engine.balance_count == 0
    assert engine.unfinished_levels == {}
