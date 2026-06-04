"""DEEP6 v2 API — FastAPI application with SSE and WebSocket endpoints."""

from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from deep6v2.api.replay import router as replay_router

app = FastAPI(title="DEEP6 v2 API", version="2.0.0")
app.include_router(replay_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev
    allow_methods=["*"],
    allow_headers=["*"],
)


class SystemState:
    """Shared mutable state for broadcasting events to subscribers."""

    def __init__(self) -> None:
        self.signal_subscribers: list[asyncio.Queue[dict]] = []
        self.score_subscribers: list[asyncio.Queue[dict]] = []
        self.bar_connections: list[WebSocket] = []
        self.last_position: dict = {
            "symbol": "NQ",
            "size": 0,
            "avg_price": 0.0,
            "unrealized_pnl": 0.0,
        }
        self.system_status: str = "idle"
        self.rithmic_connected: bool = False
        self.bars_processed: int = 0
        self.start_time: float = 0.0


state = SystemState()


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "system_status": state.system_status,
        "rithmic_connected": state.rithmic_connected,
        "bars_processed": state.bars_processed,
    }


@app.get("/position")
async def position() -> dict:
    return state.last_position


@app.get("/config")
async def config() -> dict:
    """Read-only configuration view."""
    return {
        "scoring": {"type_a": 80, "type_b": 72, "type_c": 50},
        "execution": {"dry_run": True},
    }


@app.post("/kill-switch")
async def kill_switch() -> dict:
    """Manual kill switch activation."""
    state.system_status = "killed"
    return {"status": "killed", "message": "Kill switch activated"}


# ---------------------------------------------------------------------------
# SSE streams
# ---------------------------------------------------------------------------


@app.get("/signals/stream")
async def signal_stream() -> StreamingResponse:
    """SSE stream of signal events."""
    queue: asyncio.Queue[dict] = asyncio.Queue()
    state.signal_subscribers.append(queue)

    async def event_generator():  # type: ignore[return]
        try:
            while True:
                data = await queue.get()
                yield f"data: {json.dumps(data)}\n\n"
        except asyncio.CancelledError:
            state.signal_subscribers.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/scores/stream")
async def score_stream() -> StreamingResponse:
    """SSE stream of scoring events."""
    queue: asyncio.Queue[dict] = asyncio.Queue()
    state.score_subscribers.append(queue)

    async def event_generator():  # type: ignore[return]
        try:
            while True:
                data = await queue.get()
                yield f"data: {json.dumps(data)}\n\n"
        except asyncio.CancelledError:
            state.score_subscribers.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


@app.websocket("/bars")
async def bar_stream(websocket: WebSocket) -> None:
    """WebSocket for real-time FootprintBar data."""
    await websocket.accept()
    state.bar_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()  # keepalive
    except Exception:
        state.bar_connections.remove(websocket)


# ---------------------------------------------------------------------------
# Broadcast helpers
# ---------------------------------------------------------------------------


async def broadcast_signal(signal_data: dict) -> None:
    for q in state.signal_subscribers:
        await q.put(signal_data)


async def broadcast_score(score_data: dict) -> None:
    for q in state.score_subscribers:
        await q.put(score_data)


async def broadcast_bar(bar_data: dict) -> None:
    for ws in state.bar_connections[:]:
        try:
            await ws.send_json(bar_data)
        except Exception:
            state.bar_connections.remove(ws)


__all__ = [
    "app",
    "broadcast_bar",
    "broadcast_score",
    "broadcast_signal",
    "replay_router",
    "state",
]
