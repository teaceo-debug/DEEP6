"""Tests for replay endpoints.

TDD — covers all 6 behaviors from Task 3 spec:
  1. GET /api/replay/sessions returns [] when no bars stored
  2. After inserting bars for two sessions, returns 2 entries ordered by last_ts DESC
  3. GET /api/replay/{session}/{bar_index} returns bar + signals_up_to
  4. Missing session → 404 with detail "Bar not found in session"
  5. bar_index beyond session length → 404
  6. GET /api/replay/{session}?start=&end= returns range {session_id, total_bars, bars}

Uses TestClient (sync) which handles the event loop and triggers lifespan.
The seeded store is injected by overriding app.state.event_store after lifespan.
"""
from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from deep6.api.store import EventStore
from deep6.state.footprint import FootprintBar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bar(ts: float = 1_000_000.0) -> FootprintBar:
    bar = FootprintBar(timestamp=ts)
    bar.add_trade(21000.00, 50, aggressor=1)
    bar.add_trade(21000.25, 50, aggressor=2)
    bar.finalize(prior_cvd=0)
    return bar


def _seed_store() -> EventStore:
    """Build and populate an in-memory EventStore synchronously."""
    async def _build():
        store = EventStore(":memory:")
        await store.initialize()
        # Session A: 3 bars at higher timestamps
        base_a = 2_000_000.0
        for i in range(3):
            await store.insert_bar("2026-04-13", i, _make_bar(ts=base_a + i))
        # Session B: 2 bars at lower timestamps
        base_b = 1_000_000.0
        for i in range(2):
            await store.insert_bar("2026-04-10", i, _make_bar(ts=base_b + i))
        return store

    return asyncio.run(_build())


def _get_client_with_store(store: EventStore):
    """Return a TestClient whose app.state.event_store is the given store."""
    from deep6.api.app import create_app
    from deep6.api.ws_manager import WSManager

    app = create_app()
    client = TestClient(app)
    # TestClient __enter__ triggers lifespan — we then override state
    client.__enter__()
    app.state.event_store = store
    app.state.ws_manager = WSManager()
    return client, app


# ---------------------------------------------------------------------------
# Test 1: empty sessions list
# ---------------------------------------------------------------------------

def test_list_sessions_empty():
    from deep6.api.app import create_app
    from deep6.api.ws_manager import WSManager

    app = create_app()
    with TestClient(app) as client:
        empty_store = asyncio.run(_async_empty_store())
        app.state.event_store = empty_store
        app.state.ws_manager = WSManager()
        resp = client.get("/api/replay/sessions")
    assert resp.status_code == 200
    assert resp.json() == []


async def _async_empty_store():
    store = EventStore(":memory:")
    await store.initialize()
    return store


# ---------------------------------------------------------------------------
# Test 2: two sessions ordered by last_ts DESC
# ---------------------------------------------------------------------------

def test_list_sessions_ordered():
    from deep6.api.app import create_app
    from deep6.api.ws_manager import WSManager

    store = _seed_store()
    app = create_app()
    with TestClient(app) as client:
        app.state.event_store = store
        app.state.ws_manager = WSManager()
        resp = client.get("/api/replay/sessions")

    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) == 2
    assert sessions[0]["session_id"] == "2026-04-13"
    assert sessions[1]["session_id"] == "2026-04-10"
    assert sessions[0]["bar_count"] == 3
    assert sessions[1]["bar_count"] == 2


# ---------------------------------------------------------------------------
# Test 3: /api/replay/{session}/{bar_index} returns bar + signals_up_to
# ---------------------------------------------------------------------------

def test_replay_bar_returns_bar_and_signals():
    from deep6.api.app import create_app
    from deep6.api.ws_manager import WSManager

    store = _seed_store()
    app = create_app()
    with TestClient(app) as client:
        app.state.event_store = store
        app.state.ws_manager = WSManager()
        resp = client.get("/api/replay/2026-04-13/0")

    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "2026-04-13"
    assert body["bar_index"] == 0
    assert "bar" in body
    assert body["bar"]["bar_index"] == 0
    assert "signals_up_to" in body
    assert isinstance(body["signals_up_to"], list)


# ---------------------------------------------------------------------------
# Test 4: missing session → 404 with correct detail
# ---------------------------------------------------------------------------

def test_replay_bar_missing_session_returns_404():
    from deep6.api.app import create_app
    from deep6.api.ws_manager import WSManager

    store = _seed_store()
    app = create_app()
    with TestClient(app) as client:
        app.state.event_store = store
        app.state.ws_manager = WSManager()
        resp = client.get("/api/replay/DOES-NOT-EXIST/0")

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 5: bar_index beyond session length → 404
# ---------------------------------------------------------------------------

def test_replay_bar_out_of_range_returns_404():
    from deep6.api.app import create_app
    from deep6.api.ws_manager import WSManager

    store = _seed_store()
    app = create_app()
    with TestClient(app) as client:
        app.state.event_store = store
        app.state.ws_manager = WSManager()
        # Session "2026-04-13" has bars 0,1,2 → index 99 doesn't exist
        resp = client.get("/api/replay/2026-04-13/99")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 6: range query GET /api/replay/{session}?start=&end= returns range
# ---------------------------------------------------------------------------

def test_replay_session_range_query():
    from deep6.api.app import create_app
    from deep6.api.ws_manager import WSManager

    store = _seed_store()
    app = create_app()
    with TestClient(app) as client:
        app.state.event_store = store
        app.state.ws_manager = WSManager()
        resp = client.get("/api/replay/2026-04-13?start=1&end=2")

    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "2026-04-13"
    assert body["total_bars"] == 3
    bars = body["bars"]
    assert len(bars) == 2
    assert all(1 <= b["bar_index"] <= 2 for b in bars)


# ---------------------------------------------------------------------------
# Test 7: range query for missing session → 404
# ---------------------------------------------------------------------------

def test_replay_session_range_missing_session():
    from deep6.api.app import create_app
    from deep6.api.ws_manager import WSManager

    store = _seed_store()
    app = create_app()
    with TestClient(app) as client:
        app.state.event_store = store
        app.state.ws_manager = WSManager()
        resp = client.get("/api/replay/NO-SESSION")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Session not found"
