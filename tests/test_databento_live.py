"""Unit tests for Databento live feed adapter (phase 14).

Drives the feed with synthetic MBO-shaped records — no live Databento session
required. Exercises:
    - Order-book reconstruction (add / modify / cancel)
    - Trade accumulation into FootprintBar via BarBuilder
    - Aggressor side mapping (A → 1 BUY, B → 2 SELL)
    - RTH filter (BarBuilder gates overnight trades)
    - Reconnection flips FreezeGuard CONNECTED → FROZEN and back
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from deep6.data.bar_builder import BarBuilder
from deep6.data.databento_live import DatabentoLiveFeed, _OrderBookState
from deep6.state.connection import ConnectionState, FreezeGuard
from deep6.state.dom import DOMState
from deep6.state.footprint import price_to_tick


@dataclass
class _FakeRecord:
    action: str
    side: str
    order_id: int
    price: float          # plain price (float), not 1e-9 scaled
    size: int
    ts_event: int = 0     # ns


def _make_state(freeze: bool = False):
    """Minimal shared-state stub accepted by the feed + bar builders."""
    fg = FreezeGuard()
    if freeze:
        fg.on_disconnect(ts=1.0)
    state = SimpleNamespace(
        dom=DOMState(),
        freeze_guard=fg,
        bar_builders=[],
    )
    return state


# ---------------------------------------------------------------------------
# _OrderBookState reconstruction
# ---------------------------------------------------------------------------
def test_orderbook_add_increments_level_size():
    book = _OrderBookState()
    book.apply(order_id=1, price=21000.0, size=5, side="B", action="A")
    book.apply(order_id=2, price=21000.0, size=3, side="B", action="A")

    bid_prices, bid_sizes, ask_prices, ask_sizes = book.top_levels(40)
    assert bid_prices == [21000.0]
    assert bid_sizes == [8]
    assert ask_prices == []
    assert ask_sizes == []


def test_orderbook_cancel_removes_size():
    book = _OrderBookState()
    book.apply(1, 21000.0, 5, "B", "A")
    book.apply(2, 21000.0, 3, "B", "A")
    book.apply(1, 21000.0, 5, "B", "C")  # cancel order 1

    _bp, bid_sizes, _ap, _as = book.top_levels(40)
    assert bid_sizes == [3]


def test_orderbook_modify_moves_size():
    book = _OrderBookState()
    book.apply(1, 21000.0, 5, "B", "A")
    book.apply(1, 20999.75, 4, "B", "M")  # modify to new price/size

    bid_prices, bid_sizes, _ap, _as = book.top_levels(40)
    assert bid_prices == [20999.75]
    assert bid_sizes == [4]


def test_orderbook_trade_fill_reduces_resting_size():
    book = _OrderBookState()
    book.apply(1, 21000.0, 10, "A", "A")  # add ask order size 10
    book.apply(1, 21000.0, 3, "A", "T")   # 3 traded against it

    _bp, _bs, ask_prices, ask_sizes = book.top_levels(40)
    assert ask_prices == [21000.0]
    assert ask_sizes == [7]


def test_orderbook_clear_on_book_reset():
    book = _OrderBookState()
    book.apply(1, 21000.0, 5, "B", "A")
    book.apply(2, 21001.0, 3, "A", "A")
    book.clear()
    assert book.top_levels(40) == ([], [], [], [])


def test_orderbook_top_levels_sorts_best_first():
    book = _OrderBookState()
    # Bids should sort descending
    book.apply(1, 20999.0, 1, "B", "A")
    book.apply(2, 21000.0, 2, "B", "A")
    book.apply(3, 20998.0, 3, "B", "A")
    # Asks should sort ascending
    book.apply(4, 21002.0, 4, "A", "A")
    book.apply(5, 21001.0, 5, "A", "A")

    bid_prices, bid_sizes, ask_prices, ask_sizes = book.top_levels(40)
    assert bid_prices == [21000.0, 20999.0, 20998.0]
    assert bid_sizes == [2, 1, 3]
    assert ask_prices == [21001.0, 21002.0]
    assert ask_sizes == [5, 4]


# ---------------------------------------------------------------------------
# Trade accumulation + aggressor mapping
# ---------------------------------------------------------------------------
def _patch_rth(is_rth: bool):
    """Patch BarBuilder._is_rth so trades are (not) gated by RTH."""
    return patch.object(BarBuilder, "_is_rth", lambda self: is_rth)


def test_trade_ask_side_maps_to_buy_aggressor():
    state = _make_state()
    bb = BarBuilder(period_seconds=60, label="1m", state=state)
    state.bar_builders = [bb]

    feed = DatabentoLiveFeed(api_key="test")
    feed._state_ref = state  # type: ignore[attr-defined]

    record = _FakeRecord(action="T", side="A", order_id=1, price=21000.0, size=4)
    with _patch_rth(True):
        feed._process_record(state, record)

    tick = price_to_tick(21000.0)
    lv = bb.current_bar.levels[tick]
    assert lv.ask_vol == 4   # aggressor=1 (BUY) accumulates into ask_vol
    assert lv.bid_vol == 0


def test_trade_bid_side_maps_to_sell_aggressor():
    state = _make_state()
    bb = BarBuilder(period_seconds=60, label="1m", state=state)
    state.bar_builders = [bb]

    feed = DatabentoLiveFeed(api_key="test")
    feed._state_ref = state  # type: ignore[attr-defined]

    record = _FakeRecord(action="T", side="B", order_id=1, price=21000.25, size=7)
    with _patch_rth(True):
        feed._process_record(state, record)

    tick = price_to_tick(21000.25)
    lv = bb.current_bar.levels[tick]
    assert lv.bid_vol == 7   # aggressor=2 (SELL) accumulates into bid_vol
    assert lv.ask_vol == 0


def test_trade_accumulates_into_footprint_bar():
    state = _make_state()
    bb = BarBuilder(period_seconds=60, label="1m", state=state)
    state.bar_builders = [bb]

    feed = DatabentoLiveFeed(api_key="test")
    feed._state_ref = state  # type: ignore[attr-defined]

    trades = [
        _FakeRecord("T", "A", 1, 21000.00, 2),
        _FakeRecord("T", "A", 2, 21000.25, 3),
        _FakeRecord("T", "B", 3, 21000.00, 1),
    ]
    with _patch_rth(True):
        for r in trades:
            feed._process_record(state, r)

    assert bb.current_bar.total_vol == 6
    # bar_delta = sum(ask - bid) across levels = (2-1) + (3-0) = 4
    # (bar_delta is computed in finalize(), but we can inspect running_delta)
    assert bb.current_bar.running_delta == 2 + 3 - 1


# ---------------------------------------------------------------------------
# RTH filtering
# ---------------------------------------------------------------------------
def test_rth_filter_rejects_overnight_trade():
    state = _make_state()
    bb = BarBuilder(period_seconds=60, label="1m", state=state)
    state.bar_builders = [bb]

    feed = DatabentoLiveFeed(api_key="test")
    feed._state_ref = state  # type: ignore[attr-defined]

    record = _FakeRecord("T", "A", 1, 21000.0, 5)
    with _patch_rth(False):  # outside RTH
        feed._process_record(state, record)

    assert bb.current_bar.total_vol == 0
    assert len(bb.current_bar.levels) == 0


def test_freeze_guard_blocks_accumulation():
    """When FreezeGuard is FROZEN, BarBuilder.on_trade silently drops ticks."""
    state = _make_state(freeze=True)
    bb = BarBuilder(period_seconds=60, label="1m", state=state)
    state.bar_builders = [bb]

    feed = DatabentoLiveFeed(api_key="test")
    feed._state_ref = state  # type: ignore[attr-defined]

    record = _FakeRecord("T", "A", 1, 21000.0, 5)
    with _patch_rth(True):
        feed._process_record(state, record)

    assert bb.current_bar.total_vol == 0


# ---------------------------------------------------------------------------
# Reconnection — FreezeGuard flips
# ---------------------------------------------------------------------------
def test_disconnect_sets_freeze_guard_frozen():
    state = _make_state()
    feed = DatabentoLiveFeed(api_key="test")
    feed._state_ref = state  # type: ignore[attr-defined]

    assert state.freeze_guard.get_state() == ConnectionState.CONNECTED
    feed._handle_disconnect()
    assert state.freeze_guard.is_frozen is True
    assert state.freeze_guard.get_state() == ConnectionState.FROZEN
    assert feed._disconnect_ts is not None


def test_reconnect_restores_connected_state():
    state = _make_state()
    feed = DatabentoLiveFeed(api_key="test")
    feed._state_ref = state  # type: ignore[attr-defined]

    feed._handle_disconnect()
    assert state.freeze_guard.is_frozen is True

    feed._handle_reconnect()
    assert state.freeze_guard.is_frozen is False
    assert state.freeze_guard.get_state() == ConnectionState.CONNECTED
    assert feed._disconnect_ts is None


# ---------------------------------------------------------------------------
# End-to-end: book updates flag DOM dirty
# ---------------------------------------------------------------------------
def test_book_updates_mark_dom_dirty():
    state = _make_state()
    feed = DatabentoLiveFeed(api_key="test")
    feed._state_ref = state  # type: ignore[attr-defined]

    assert feed._dom_dirty is False
    feed._process_record(state, _FakeRecord("A", "B", 1, 21000.0, 5))
    assert feed._dom_dirty is True


def test_integer_price_scaled_from_databento_native():
    """Native Databento MBO prices are int64 in 1e-9 units — feed divides."""
    state = _make_state()
    bb = BarBuilder(period_seconds=60, label="1m", state=state)
    state.bar_builders = [bb]

    feed = DatabentoLiveFeed(api_key="test")
    feed._state_ref = state  # type: ignore[attr-defined]

    # price=21000.0 in 1e-9 units = 21_000_000_000_000
    record = _FakeRecord("T", "A", 1, price=0, size=1)
    record.price = 21_000_000_000_000  # type: ignore[assignment]

    with _patch_rth(True):
        feed._process_record(state, record)

    tick = price_to_tick(21000.0)
    assert bb.current_bar.levels[tick].ask_vol == 1
