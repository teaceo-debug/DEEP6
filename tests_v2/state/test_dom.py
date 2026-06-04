from __future__ import annotations

import os
import time
from datetime import UTC, datetime

import pytest

from deep6v2.types.dom import DOMSnapshot


def _build_state():
    from deep6v2.state.dom import DOMState

    return DOMState(base_price=20000.0, num_levels=4000)


def test_update_level_bid_ask():
    state = _build_state()

    state.update_level("bid", 20010.0, 100)
    state.update_level("ask", 20010.25, 120)

    assert state.get_best_bid() == 20010.0
    assert state.get_best_ask() == 20010.25


def test_update_level_removes_level():
    state = _build_state()

    state.update_level("bid", 20010.0, 100)
    state.update_level("bid", 20010.0, 0)

    assert state.get_best_bid() is None
    snapshot = state.snapshot()
    assert snapshot.bids == []


def test_snapshot_accuracy():
    state = _build_state()
    timestamp = datetime(2026, 5, 14, 14, 0, tzinfo=UTC)

    state.update_level("bid", 20010.0, 100)
    state.update_level("bid", 20009.75, 50)
    state.update_level("ask", 20010.25, 80)
    state.update_level("ask", 20010.5, 120)

    snapshot = state.snapshot(timestamp=timestamp)

    assert isinstance(snapshot, DOMSnapshot)
    assert snapshot.timestamp == timestamp
    assert [(level.price, level.volume) for level in snapshot.bids] == [
        (20010.0, 100),
        (20009.75, 50),
    ]
    assert [(level.price, level.volume) for level in snapshot.asks] == [
        (20010.25, 80),
        (20010.5, 120),
    ]


def test_depth_imbalance():
    state = _build_state()

    state.update_level("bid", 20010.0, 100)
    state.update_level("bid", 20009.75, 50)
    state.update_level("bid", 20009.5, 200)
    state.update_level("ask", 20010.25, 80)
    state.update_level("ask", 20010.5, 120)

    assert state.depth_imbalance(3) == pytest.approx(1.75)


def test_reset():
    state = _build_state()

    state.update_level("bid", 20010.0, 100)
    state.update_level("ask", 20010.25, 120)

    state.reset()

    assert state.get_best_bid() is None
    assert state.get_best_ask() is None
    assert state.snapshot().bids == []
    assert state.snapshot().asks == []
    assert all(size == 0 for size in state._bid_sizes)
    assert all(size == 0 for size in state._ask_sizes)


@pytest.mark.skipif(
    os.getenv("RUN_PERF_BENCHMARKS") != "1",
    reason="Set RUN_PERF_BENCHMARKS=1 to run performance benchmark",
)
def test_benchmark():
    state = _build_state()
    start = time.perf_counter()

    for i in range(1_000):
        bid_price = 20000.0 + ((i % 100) * 0.25)
        ask_price = bid_price + 0.25
        state.update_level("bid", bid_price, (i % 10) + 1)
        state.update_level("ask", ask_price, (i % 10) + 1)

    elapsed_ms = (time.perf_counter() - start) * 1_000

    assert elapsed_ms < 1.0


def test_best_bid_ask_after_remove():
    state = _build_state()

    state.update_level("bid", 20010.0, 100)
    state.update_level("bid", 20009.75, 90)
    state.update_level("ask", 20010.25, 110)
    state.update_level("ask", 20010.5, 125)

    state.update_level("bid", 20010.0, 0)
    state.update_level("ask", 20010.25, 0)

    assert state.get_best_bid() == 20009.75
    assert state.get_best_ask() == 20010.5


def test_out_of_range_updates_are_ignored():
    state = _build_state()

    state.update_level("bid", 19999.75, 100)
    state.update_level("ask", 21000.0, 120)

    assert state.get_best_bid() is None
    assert state.get_best_ask() is None
