"""MBOAdapter.run() integration — synthetic event streams, no network.

Verifies:
  - trade (T) events dispatched to on_tick with correct aggressor
  - add (A) events mutate book and dispatch on_dom
  - reset (R) events clear book
  - EventClock advances with event timestamps
  - Symbol roll (instrument_id change) clears the book
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from deep6.backtest.clock import EventClock
from deep6.backtest.mbo_adapter import MBOAdapter


@pytest.mark.asyncio
async def test_adapter_dispatches_trade_to_on_tick(make_event) -> None:
    clock = EventClock()
    ev = make_event(action="T", side="A", price=21000.0, size=3)
    adapter = MBOAdapter(
        dataset="GLBX.MDP3", symbol="NQ.c.0",
        start="", end="", clock=clock, event_source=[ev],
    )
    on_tick = AsyncMock()
    on_dom = AsyncMock()
    await adapter.run(on_tick, on_dom)
    on_tick.assert_awaited_once()
    args, _ = on_tick.call_args
    price, size, aggressor = args
    assert price == pytest.approx(21000.0)
    assert size == 3
    assert aggressor == "BUY"  # side='A' → ask-side → BUY aggressor


@pytest.mark.asyncio
async def test_adapter_trade_side_b_maps_to_sell(make_event) -> None:
    clock = EventClock()
    ev = make_event(action="T", side="B", price=21000.0, size=1)
    adapter = MBOAdapter(
        dataset="GLBX.MDP3", symbol="NQ.c.0",
        start="", end="", clock=clock, event_source=[ev],
    )
    on_tick = AsyncMock()
    on_dom = AsyncMock()
    await adapter.run(on_tick, on_dom)
    _, _, aggressor = on_tick.call_args[0]
    assert aggressor == "SELL"


@pytest.mark.asyncio
async def test_adapter_dispatches_add_to_on_dom(make_event) -> None:
    clock = EventClock()
    ev = make_event(action="A", side="B", price=20999.75, size=5)
    adapter = MBOAdapter(
        dataset="GLBX.MDP3", symbol="NQ.c.0",
        start="", end="", clock=clock, event_source=[ev],
    )
    on_tick = AsyncMock()
    on_dom = AsyncMock()
    await adapter.run(on_tick, on_dom)
    on_tick.assert_not_called()
    on_dom.assert_awaited_once()
    bids, asks = on_dom.call_args[0]
    assert bids == [(20999.75, 5)]
    assert asks == []


@pytest.mark.asyncio
async def test_adapter_clear_on_R(make_event) -> None:
    clock = EventClock()
    events = [
        make_event(ts_ns=1_000_000_000, action="A", side="B", price=20999.75, size=5),
        make_event(ts_ns=2_000_000_000, action="A", side="A", price=21000.00, size=3),
        make_event(ts_ns=3_000_000_000, action="R", side="N", price=0.0, size=0),
    ]
    adapter = MBOAdapter(
        dataset="GLBX.MDP3", symbol="NQ.c.0",
        start="", end="", clock=clock, event_source=events,
    )
    on_tick = AsyncMock()
    on_dom = AsyncMock()
    await adapter.run(on_tick, on_dom)
    # Last on_dom call after R should be empty books.
    last_bids, last_asks = on_dom.call_args_list[-1][0]
    assert last_bids == []
    assert last_asks == []


@pytest.mark.asyncio
async def test_adapter_advances_clock(make_event) -> None:
    clock = EventClock()
    events = [
        make_event(ts_ns=1_700_000_000_000_000_000, action="T", side="A",
                   price=21000.0, size=1),
        make_event(ts_ns=1_700_000_005_000_000_000, action="T", side="A",
                   price=21000.25, size=1),
    ]
    adapter = MBOAdapter(
        dataset="GLBX.MDP3", symbol="NQ.c.0",
        start="", end="", clock=clock, event_source=events,
    )
    await adapter.run(AsyncMock(), AsyncMock())
    assert clock.now() == pytest.approx(1_700_000_005.0)


@pytest.mark.asyncio
async def test_adapter_symbol_roll_clears_book(make_event) -> None:
    clock = EventClock()
    events = [
        make_event(ts_ns=1_000_000_000, action="A", side="B",
                   price=20999.75, size=5, instrument_id=1),
        make_event(ts_ns=2_000_000_000, action="A", side="B",
                   price=20999.50, size=3, instrument_id=1),
        # Symbol roll — new instrument_id
        make_event(ts_ns=3_000_000_000, action="A", side="B",
                   price=21500.00, size=1, instrument_id=2),
    ]
    adapter = MBOAdapter(
        dataset="GLBX.MDP3", symbol="NQ.c.0",
        start="", end="", clock=clock, event_source=events,
    )
    on_tick = AsyncMock()
    on_dom = AsyncMock()
    await adapter.run(on_tick, on_dom)
    # Final DOM should contain only the post-roll level (book cleared
    # between the 2nd and 3rd adds).
    final_bids, _ = on_dom.call_args_list[-1][0]
    assert final_bids == [(21500.00, 1)]
