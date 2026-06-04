"""GEX Terminal FastAPI server — health, state, and SSE stream endpoints."""
from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from contextlib import asynccontextmanager
from pathlib import Path
import threading
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from gex_terminal.config import Settings
from gex_terminal.engine.orchestrator import GEXOrchestrator

settings = Settings()
_HTML_RESPONSE = HTMLResponse

# Module-level state — injected by orchestrator at startup
_current_snapshot: dict[str, Any] | None = None
_stream_subscribers: list[asyncio.Queue] = []
_startup_time = time.time()
_orchestrator: GEXOrchestrator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start and stop the polling orchestrator with the FastAPI app lifecycle."""
    del app
    global _orchestrator
    _orchestrator = GEXOrchestrator(settings)
    _orchestrator.set_broadcast(broadcast_snapshot)
    task = asyncio.create_task(_orchestrator.run(), name="gex_terminal_orchestrator")
    try:
        yield
    finally:
        _orchestrator.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

app = FastAPI(title="GEX Doctor v2.0", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> JSONResponse:
    """Health check with per-source status."""
    snapshot = _current_snapshot
    sources: dict[str, Any] = {}
    if snapshot and "sources" in snapshot:
        raw_sources = snapshot["sources"]
        if isinstance(raw_sources, dict):
            sources = raw_sources

    has_error = any(
        isinstance(source, dict) and source.get("status") in ("error", "pending")
        for source in sources.values()
    ) if sources else True

    return JSONResponse({
        "status": "degraded" if has_error else "ok",
        "sources": sources,
        "uptime_sec": int(time.time() - _startup_time),
    })


@app.get("/state")
async def state() -> JSONResponse:
    """Current GEXTerminalSnapshot as JSON. 503 if not initialized."""
    if _current_snapshot is None:
        return JSONResponse(
            {"error": "GEX Terminal not initialized — waiting for first data cycle"},
            status_code=503,
        )
    return JSONResponse(_current_snapshot)


@app.get("/stream")
async def stream() -> StreamingResponse:
    """SSE: pushes full GEXTerminalSnapshot on every analytics cycle."""
    queue: asyncio.Queue = asyncio.Queue()
    _stream_subscribers.append(queue)

    async def event_generator():
        try:
            # Send current state immediately on connect
            if _current_snapshot is not None:
                yield f"data: {json.dumps(_current_snapshot)}\n\n"
            else:
                yield f"data: {json.dumps({'status': 'starting', 'sources': {}})}\n\n"
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=10.0)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            try:
                _stream_subscribers.remove(queue)
            except ValueError:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/shutdown")
async def shutdown():
    """Graceful shutdown endpoint — called by Electron before killing sidecar."""

    def _stop() -> None:
        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=_stop, daemon=True).start()
    return {"status": "shutting down"}


async def broadcast_snapshot(snapshot_dict: dict) -> None:
    """Called by orchestrator after each compute cycle."""
    global _current_snapshot
    _current_snapshot = snapshot_dict
    for q in list(_stream_subscribers):
        try:
            await q.put(snapshot_dict)
        except Exception:
            pass


def set_snapshot(snapshot_dict: dict) -> None:
    """Inject snapshot (used in tests and by orchestrator at startup)."""
    global _current_snapshot
    _current_snapshot = snapshot_dict


__all__ = ["app", "broadcast_snapshot", "set_snapshot", "lifespan"]


def _mount_static_files(app: FastAPI) -> None:
    """Mount Next.js static export if the directory exists."""
    static_dir_env = settings.static_dir
    if static_dir_env:
        static_path = Path(static_dir_env)
    else:
        static_path = Path(__file__).parent / "ui" / "out"

    if static_path.exists() and static_path.is_dir():
        app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")
        print(f"[GEX Terminal] Serving static UI from: {static_path}")
    else:
        print(f"[GEX Terminal] Static UI not found at {static_path} — API-only mode")


_mount_static_files(app)
