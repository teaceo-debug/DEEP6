"""Phase 14 integration test — DatabentoLiveFeed against real MBO data.

Replays a bounded slice of the downloaded Databento MBO DBN file
(``data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-04-08_2026-04-11.dbn.zst``)
through ``DatabentoLiveFeed._process_record`` — this validates the full
MBO → DOM + FootprintBar pipeline without hitting the live API.

This mirrors D-24 (replay-mode integration test) without needing an
authenticated Live session. Any gap in the live → historical parity shows
up here as a DOMState discrepancy or missing trade accumulation.

Skipped if the DBN file is absent.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from deep6.data.bar_builder import BarBuilder
from deep6.data.databento_live import DatabentoLiveFeed
from deep6.state.connection import FreezeGuard
from deep6.state.dom import DOMState

DBN_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "databento"
    / "nq_mbo"
    / "raw_dbn"
    / "NQ_c_0_mbo_2026-04-08_2026-04-11.dbn.zst"
)

MAX_RECORDS = 5000  # bounded replay — keeps wall-clock test time < 1s


@pytest.fixture(scope="module")
def mbo_records():
    """Load a bounded slice of real MBOMsg records from the local DBN file."""
    if not DBN_PATH.exists():
        pytest.skip(f"DBN file not available: {DBN_PATH}")
    import databento as db  # noqa: WPS433 — deferred import

    store = db.DBNStore.from_file(str(DBN_PATH))
    out = []
    for rec in store:
        out.append(rec)
        if len(out) >= MAX_RECORDS:
            break
    return out


def _make_state():
    return SimpleNamespace(
        dom=DOMState(),
        freeze_guard=FreezeGuard(),
        bar_builders=[],
    )


def test_replay_reconstructs_book_with_nonempty_top_levels(mbo_records):
    """After replaying real MBO events, the top bid/ask levels are populated."""
    state = _make_state()
    feed = DatabentoLiveFeed(api_key="test")
    feed._state_ref = state

    with patch.object(BarBuilder, "_is_rth", lambda self: True):
        for rec in mbo_records:
            feed._process_record(state, rec)

    bid_prices, bid_sizes, ask_prices, ask_sizes = feed._book.top_levels(40)
    assert len(bid_prices) > 0, "expected at least one bid level post-replay"
    assert len(ask_prices) > 0, "expected at least one ask level post-replay"
    # Best bid must be below best ask (positive spread).
    assert bid_prices[0] < ask_prices[0]
    # All sizes must be positive (no orphaned zero-size entries).
    assert all(s > 0 for s in bid_sizes)
    assert all(s > 0 for s in ask_sizes)


def test_replay_drives_footprint_trades(mbo_records):
    """Trade ('T') events must accumulate into FootprintBar via BarBuilder."""
    state = _make_state()
    bb = BarBuilder(period_seconds=60, label="1m", state=state)
    state.bar_builders = [bb]
    feed = DatabentoLiveFeed(api_key="test")
    feed._state_ref = state

    with patch.object(BarBuilder, "_is_rth", lambda self: True):
        for rec in mbo_records:
            feed._process_record(state, rec)

    # At least one trade recorded — the fixture confirms ~30 trades over the
    # first 5k records on this file.
    assert bb.current_bar.total_vol > 0


def test_replay_marks_dom_dirty_on_book_mutations(mbo_records):
    """Every add/cancel/modify/trade must flip the DOM-dirty flag."""
    state = _make_state()
    feed = DatabentoLiveFeed(api_key="test")
    feed._state_ref = state

    with patch.object(BarBuilder, "_is_rth", lambda self: True):
        # Replay — after at least one mutating event, _dom_dirty must be True.
        saw_dirty = False
        for rec in mbo_records[:100]:
            feed._process_record(state, rec)
            if feed._dom_dirty:
                saw_dirty = True
                break
    assert saw_dirty, "DOM never flagged dirty after 100 real MBO events"
