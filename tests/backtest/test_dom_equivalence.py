"""DOM equivalence: bmoscon.OrderBook → DOMState byte-exact.

Phase 13-01 FOOTGUN 1: bmoscon.OrderBook stores levels in a SortedDict
keyed by price; our DOMState is indexed by sorted-rank (best → worst).
This test suite is the single correctness gate on the conversion — any
offset bug silently shifts the book and causes DOM-dependent signals
(E2/E3/E4) to fire on the wrong price bucket.

Five scenarios:
  1. empty book → all-zero DOMState
  2. single bid level
  3. 10 bid + 10 ask levels dense around mid
  4. cancel then re-add same level (most recent wins)
  5. levels beyond LEVELS (40) silently truncated

The conversion contract (LOCKED for phase 13):
  DOMState.bid_prices/bid_sizes  — index 0 = best bid (highest price)
  DOMState.ask_prices/ask_sizes  — index 0 = best ask (lowest price)
  Beyond LEVELS: drop with structlog debug log.
"""
from __future__ import annotations

import array

import pytest
from order_book import OrderBook

from deep6.backtest.mbo_adapter import _book_to_domstate
from deep6.state.dom import DOMState, LEVELS


def _empty_dom() -> DOMState:
    return DOMState()


def test_empty_book_yields_zero_domstate() -> None:
    book = OrderBook(max_depth=LEVELS)
    dom = _book_to_domstate(book)
    assert isinstance(dom.bid_prices, array.array)
    assert list(dom.bid_prices) == [0.0] * LEVELS
    assert list(dom.bid_sizes) == [0.0] * LEVELS
    assert list(dom.ask_prices) == [0.0] * LEVELS
    assert list(dom.ask_sizes) == [0.0] * LEVELS


def test_single_bid_level() -> None:
    book = OrderBook(max_depth=LEVELS)
    book.bids[21000.0] = 5
    dom = _book_to_domstate(book)
    assert dom.bid_prices[0] == 21000.0
    assert dom.bid_sizes[0] == 5.0
    # Slot 1+ remain zero (no level)
    assert dom.bid_prices[1] == 0.0
    # Ask side fully zero
    assert list(dom.ask_prices) == [0.0] * LEVELS
    assert list(dom.ask_sizes) == [0.0] * LEVELS


def test_ten_bid_ten_ask_dense_around_mid() -> None:
    book = OrderBook(max_depth=LEVELS)
    # 10 bid levels descending 20999.75 down to 20997.50
    bid_prices = [20999.75 - 0.25 * i for i in range(10)]
    bid_sizes = [10 + i for i in range(10)]
    for p, s in zip(bid_prices, bid_sizes):
        book.bids[p] = s
    # 10 ask levels ascending 21000.00 up to 21002.25
    ask_prices = [21000.00 + 0.25 * i for i in range(10)]
    ask_sizes = [20 + i for i in range(10)]
    for p, s in zip(ask_prices, ask_sizes):
        book.asks[p] = s

    dom = _book_to_domstate(book)
    # Best bid at index 0 (highest price)
    for i in range(10):
        assert dom.bid_prices[i] == bid_prices[i], f"bid[{i}] price mismatch"
        assert dom.bid_sizes[i] == float(bid_sizes[i]), f"bid[{i}] size mismatch"
    # Best ask at index 0 (lowest price)
    for i in range(10):
        assert dom.ask_prices[i] == ask_prices[i], f"ask[{i}] price mismatch"
        assert dom.ask_sizes[i] == float(ask_sizes[i]), f"ask[{i}] size mismatch"
    # Rest zero
    for i in range(10, LEVELS):
        assert dom.bid_prices[i] == 0.0
        assert dom.ask_prices[i] == 0.0


def test_cancel_then_readd_same_level() -> None:
    book = OrderBook(max_depth=LEVELS)
    book.bids[21000.0] = 10
    del book.bids[21000.0]
    book.bids[21000.0] = 7  # re-add with different size
    dom = _book_to_domstate(book)
    assert dom.bid_prices[0] == 21000.0
    assert dom.bid_sizes[0] == 7.0


def test_levels_beyond_range_are_truncated() -> None:
    book = OrderBook(max_depth=LEVELS * 2)
    # Add LEVELS + 5 bid levels — only top LEVELS should survive
    for i in range(LEVELS + 5):
        book.bids[21000.0 - 0.25 * i] = 1 + i
    dom = _book_to_domstate(book)
    # Top LEVELS positions populated (best 40 prices)
    for i in range(LEVELS):
        assert dom.bid_prices[i] == 21000.0 - 0.25 * i
        assert dom.bid_sizes[i] == float(1 + i)
    # Array length strictly LEVELS — no overflow
    assert len(dom.bid_prices) == LEVELS
    assert len(dom.bid_sizes) == LEVELS
