"""DEEP6 v2 API — Session replay endpoints.

Provides read-only access to historical session data from DuckDB
for the session replay dashboard.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

router = APIRouter(prefix="/replay", tags=["replay"])


@router.get("/sessions")
async def list_sessions(
    limit: int = Query(default=50, ge=1, le=500),
) -> dict:
    """List available replay sessions.

    Returns session IDs with metadata (bar count, time range).
    Real implementation queries DuckDB ``bars`` and ``signals`` tables.
    """
    # Stub — real implementation queries EventWriter/DuckDB
    return {"sessions": [], "total": 0}


@router.get("/{session_id}/bars")
async def get_bars(
    session_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict:
    """Return footprint bars for a session with pagination."""
    return {"session_id": session_id, "bars": [], "total": 0, "offset": offset, "limit": limit}


@router.get("/{session_id}/signals")
async def get_signals(
    session_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict:
    """Return signals fired during a session with pagination."""
    return {"session_id": session_id, "signals": [], "total": 0, "offset": offset, "limit": limit}


@router.get("/{session_id}/scores")
async def get_scores(session_id: str) -> dict:
    """Return scorer results for a session."""
    return {"session_id": session_id, "scores": [], "total": 0}


@router.get("/{session_id}/trades")
async def get_trades(session_id: str) -> dict:
    """Return executions/trades for a session."""
    return {"session_id": session_id, "trades": [], "total": 0}


__all__ = ["router"]
