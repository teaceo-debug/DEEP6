"""Tests for EventStore bar_history table + Pydantic live-message schemas.

TDD — RED phase: these tests must fail before Task 1 implementation.

Covers:
  1. bar_history table created by initialize()
  2. insert_bar() stores a row; returns lastrowid
  3. fetch_bars_for_session() round-trips levels JSON correctly
  4. fetch_bars_for_session(start_index, end_index) range filtering
  5. list_sessions() returns aggregate stats ordered by last_ts DESC
  6. fetch_bar() returns one bar dict or None for missing
  7. Pydantic live-message models are importable with correct 'type' discriminators
"""
from __future__ import annotations

import asyncio
import json
import time

import pytest

from deep6.api.store import EventStore
from deep6.state.footprint import FootprintBar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bar(ts: float = 1_000_000.0, vol: int = 100) -> FootprintBar:
    """Build a minimal finalized FootprintBar."""
    bar = FootprintBar(timestamp=ts)
    bar.add_trade(21000.00, vol // 2, aggressor=1)  # buy
    bar.add_trade(21000.25, vol // 2, aggressor=2)  # sell
    bar.finalize(prior_cvd=0)
    return bar


async def _initialized_store() -> EventStore:
    store = EventStore(":memory:")
    await store.initialize()
    return store


# ---------------------------------------------------------------------------
# Test 1: bar_history table created by initialize()
# ---------------------------------------------------------------------------

def test_bar_history_table_exists():
    async def run():
        store = await _initialized_store()
        async with store._conn() as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='bar_history'"
            ) as cur:
                row = await cur.fetchone()
        assert row is not None, "bar_history table was not created"

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 2: insert_bar() stores a row; returns lastrowid
# ---------------------------------------------------------------------------

def test_insert_bar_returns_rowid():
    async def run():
        store = await _initialized_store()
        bar = _make_bar(ts=1_000_001.0)
        row_id = await store.insert_bar(session_id="2026-04-13", bar_index=0, bar=bar)
        assert isinstance(row_id, int)
        assert row_id >= 1

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 3: fetch_bars_for_session() round-trips levels JSON
# ---------------------------------------------------------------------------

def test_fetch_bars_round_trips_levels():
    async def run():
        store = await _initialized_store()
        bar = _make_bar(ts=1_000_002.0, vol=100)
        await store.insert_bar(session_id="2026-04-13", bar_index=0, bar=bar)
        rows = await store.fetch_bars_for_session("2026-04-13")
        assert len(rows) == 1
        fetched = rows[0]
        # Levels round-trip
        levels: dict = fetched["levels"]
        assert len(levels) > 0
        total_from_levels = sum(
            v["bid_vol"] + v["ask_vol"] for v in levels.values()
        )
        assert total_from_levels == bar.total_vol

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 4: fetch_bars_for_session with start/end range filtering
# ---------------------------------------------------------------------------

def test_fetch_bars_range_filter():
    async def run():
        store = await _initialized_store()
        for i in range(10):
            bar = _make_bar(ts=1_000_000.0 + i)
            await store.insert_bar("2026-04-13", bar_index=i, bar=bar)

        # Bars 0-9 exist; requesting start=5, end=10 → 5,6,7,8,9 (5 rows; bar_index 10 absent)
        rows = await store.fetch_bars_for_session("2026-04-13", start_index=5, end_index=10)
        assert len(rows) == 5
        indices = [r["bar_index"] for r in rows]
        assert indices == sorted(indices), "Results should be ordered ASC by bar_index"
        assert all(5 <= idx <= 9 for idx in indices)

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 5: list_sessions() returns aggregates ordered by last_ts DESC
# ---------------------------------------------------------------------------

def test_list_sessions_aggregates():
    async def run():
        store = await _initialized_store()
        # Insert 3 bars for session A and 2 bars for session B
        base_a = 2_000_000.0
        base_b = 1_000_000.0  # older session
        for i in range(3):
            await store.insert_bar("2026-04-13", i, _make_bar(ts=base_a + i))
        for i in range(2):
            await store.insert_bar("2026-04-10", i, _make_bar(ts=base_b + i))

        sessions = await store.list_sessions()
        assert len(sessions) == 2

        session_ids = [s["session_id"] for s in sessions]
        # 2026-04-13 should come first (higher last_ts)
        assert session_ids[0] == "2026-04-13"
        assert session_ids[1] == "2026-04-10"

        a = next(s for s in sessions if s["session_id"] == "2026-04-13")
        b = next(s for s in sessions if s["session_id"] == "2026-04-10")
        assert a["bar_count"] == 3
        assert b["bar_count"] == 2
        assert a["first_ts"] == pytest.approx(base_a, abs=0.01)
        assert a["last_ts"] == pytest.approx(base_a + 2, abs=0.01)

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 6: fetch_bar() returns one bar or None
# ---------------------------------------------------------------------------

def test_fetch_bar_single_and_missing():
    async def run():
        store = await _initialized_store()
        bar = _make_bar(ts=3_000_000.0)
        await store.insert_bar("2026-04-13", bar_index=7, bar=bar)

        result = await store.fetch_bar("2026-04-13", 7)
        assert result is not None
        assert result["bar_index"] == 7
        assert result["ts"] == pytest.approx(3_000_000.0)

        missing = await store.fetch_bar("2026-04-13", 999)
        assert missing is None

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 7: insert_bar is idempotent (INSERT OR REPLACE)
# ---------------------------------------------------------------------------

def test_insert_bar_idempotent():
    async def run():
        store = await _initialized_store()
        bar = _make_bar(ts=4_000_000.0, vol=100)
        await store.insert_bar("2026-04-13", bar_index=0, bar=bar)
        # Second insert with different ts — should replace, not duplicate
        bar2 = _make_bar(ts=4_000_001.0, vol=200)
        await store.insert_bar("2026-04-13", bar_index=0, bar=bar2)

        rows = await store.fetch_bars_for_session("2026-04-13")
        assert len(rows) == 1
        assert rows[0]["total_vol"] == 200  # replaced with bar2

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 8: Pydantic live-message schemas importable + discriminators correct
# ---------------------------------------------------------------------------

def test_pydantic_live_message_schemas():
    from deep6.api.schemas import (
        BarEventIn,
        ReplayBarOut,
        LiveBarMessage,
        LiveSignalMessage,
        LiveScoreMessage,
        LiveStatusMessage,
    )
    import time as _time

    # LiveStatusMessage
    status_msg = LiveStatusMessage(connected=True, ts=_time.time())
    assert status_msg.model_dump()["type"] == "status"

    # LiveBarMessage shape (no actual BarEventIn validation needed here)
    bar_event_payload = dict(
        session_id="2026-04-13",
        bar_index=0,
        ts=_time.time(),
        open=21000.0,
        high=21010.0,
        low=20990.0,
        close=21005.0,
        total_vol=500,
        bar_delta=100,
        cvd=100,
        poc_price=21000.0,
        bar_range=20.0,
        levels={},
    )
    bar_ev = BarEventIn(**bar_event_payload)
    live_bar = LiveBarMessage(session_id="2026-04-13", bar_index=0, bar=bar_ev)
    assert live_bar.model_dump()["type"] == "bar"

    # LiveScoreMessage
    score_msg = LiveScoreMessage(
        total_score=75.0,
        tier="TYPE_A",
        direction=1,
        categories_firing=["absorption"],
    )
    assert score_msg.model_dump()["type"] == "score"

    # ReplayBarOut is subclass of BarEventIn
    replay = ReplayBarOut(**bar_event_payload)
    assert replay.total_vol == 500

    print("OK")
