from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

from nq_atlas.state import AtlasState

logger = logging.getLogger(__name__)

# Module-level state reference — injected by orchestrator at startup
# Tests can replace this before making requests
atlas_state: AtlasState = AtlasState()

# SSE subscriber queues
_stream_subscribers: list[asyncio.Queue] = []

app = FastAPI(title="NQ ATLAS", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # LAN-trust; no auth
    allow_methods=["GET"],
    allow_headers=["*"],
)

_STARTUP_TIME = time.time()
_DASHBOARD_PATH = Path(__file__).parent / "dashboard.html"


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")


@app.get("/health")
async def health() -> JSONResponse:
    state = atlas_state
    return JSONResponse({
        "status": "degraded" if state.degraded() else "ok",
        "massive_connected": state.last_chain_ts is not None,
        "last_chain_ts": state.last_chain_ts,
        "last_ai_ts": state.last_ai_ts,
        "uptime_sec": int(time.time() - _STARTUP_TIME),
        "degraded": state.degraded(),
    })


@app.get("/bias")
async def bias() -> JSONResponse:
    b = atlas_state.bias
    if b is None:
        return JSONResponse({
            "direction": "NEUTRAL",
            "conviction": 0,
            "levels": {},
            "narrative": "Initializing...",
            "updated_at": None,
            "degraded": True,
        })
    return JSONResponse(json.loads(b.model_dump_json()))


@app.get("/state")
async def state_snapshot() -> JSONResponse:
    return JSONResponse(atlas_state.snapshot_dict())


@app.get("/gex")
async def gex() -> JSONResponse:
    g = atlas_state.gex
    if g is None:
        return JSONResponse({"error": "no GEX data"}, status_code=503)
    return JSONResponse(g.model_dump())


@app.get("/dashboard")
async def dashboard() -> HTMLResponse:
    if _DASHBOARD_PATH.exists():
        return HTMLResponse(_DASHBOARD_PATH.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<html><body><h1>NQ ATLAS</h1><p>Dashboard loading...</p></body></html>"
    )


@app.get("/stream")
async def stream() -> StreamingResponse:
    """SSE: pushes full state on every analytics compute cycle."""
    queue: asyncio.Queue = asyncio.Queue()
    _stream_subscribers.append(queue)

    async def event_generator():
        try:
            # Send current state immediately on connect
            current = atlas_state.snapshot_dict()
            yield f"data: {json.dumps(current)}\n\n"
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=10.0)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    # keepalive ping
                    yield ": keepalive\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            try:
                _stream_subscribers.remove(queue)
            except ValueError:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")


async def broadcast_state(data: dict) -> None:
    """Called by orchestrator after each compute cycle to push to SSE subscribers."""
    for q in list(_stream_subscribers):
        try:
            await q.put(data)
        except Exception:
            pass


def set_state(state: AtlasState) -> None:
    """Inject AtlasState at startup (called by orchestrator). Also usable in tests."""
    global atlas_state
    atlas_state = state


__all__ = ["app", "atlas_state", "broadcast_state", "set_state"]
