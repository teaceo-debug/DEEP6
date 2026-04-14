"""Replay endpoints — read historical bar_history from EventStore.

Per D-13: Replay data source is the existing EventStore (aiosqlite bar_history
table added in Phase 11-01). No separate replay service, no new database.

Per D-14: Replay controls (Prev/Next/jump/speed) are UI concerns. The backend
is stateless — it returns a bar by index; the client drives step-through.

Per T-11-04: fetch_signal_events uses limit=50000 cap to prevent unbounded
memory. A follow-up (Phase 12+) should add a SQL ts-filter for O(log n).

Per T-11-05: session_id path param passes through parameterised SQL — no
string concatenation, no injection surface.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/api/replay", tags=["replay"])


@router.get("/sessions")
async def list_sessions(request: Request) -> list[dict]:
    """Return all available session IDs with bar counts and timestamps.

    Returns [] when no bars have been stored yet.
    Ordered by last_ts DESC (most recent session first).
    """
    store = request.app.state.event_store
    return await store.list_sessions()


@router.get("/{session_id}/{bar_index}")
async def replay_bar(
    request: Request,
    session_id: str,
    bar_index: int,
) -> dict:
    """Return one bar and all signals fired at or before that bar's timestamp.

    Client uses this for step-through replay: increment bar_index, render bar.

    Per D-14: stateless — no server-side cursor is maintained.

    Returns 404 if session_id does not exist OR bar_index is out of range.
    """
    store = request.app.state.event_store

    bar = await store.fetch_bar(session_id, bar_index)
    if bar is None:
        raise HTTPException(status_code=404, detail="Bar not found in session")

    # Signals up to and including bar.ts — fetched from signal_events table.
    # Per T-11-04: capped at 50000; follow-up adds SQL ts-filter.
    all_signals = await store.fetch_signal_events(limit=50000)
    signals_up_to = [s for s in all_signals if s["ts"] <= bar["ts"]]

    return {
        "session_id": session_id,
        "bar_index": bar_index,
        "bar": bar,
        "signals_up_to": signals_up_to,
    }


@router.get("/{session_id}")
async def session_range(
    request: Request,
    session_id: str,
    start: int = Query(0, ge=0),
    end: int | None = Query(None, ge=0),
) -> dict:
    """Prefetch a range of bars for replay scrubbing.

    Returns {session_id, total_bars, bars: [...]}.
    Useful for the frontend replay controller to pre-load a sliding window.
    """
    store = request.app.state.event_store

    sessions = await store.list_sessions()
    match = next((s for s in sessions if s["session_id"] == session_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Session not found")

    bars = await store.fetch_bars_for_session(
        session_id, start_index=start, end_index=end
    )
    return {
        "session_id": session_id,
        "total_bars": match["bar_count"],
        "bars": bars,
    }
