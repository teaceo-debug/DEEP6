"""DEEP6 ML Backend — FastAPI application factory.

Per D-01: FastAPI runs in the same asyncio event loop as the trading engine.
The `create_app()` factory is synchronous setup only; all I/O is async.
No `uvicorn.run()` here — the caller mounts via:

    asyncio.create_task(uvicorn.Server(uvicorn.Config(app)).serve())

or for standalone:

    uvicorn deep6.api.app:app --port 8000

Lifespan:
    - Creates EventStore from DB_PATH env var (default ./deep6_ml.db)
    - Calls await store.initialize() to ensure tables exist
    - Sets app.state.event_store for route handlers
    - No teardown needed (aiosqlite opens/closes per operation)
"""
from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from deep6.api.store import EventStore
from deep6.api.routes import events as events_router
from deep6.api.routes import weights as weights_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize EventStore on startup; nothing to teardown."""
    db_path = os.environ.get("DB_PATH", "./deep6_ml.db")
    store = EventStore(db_path)
    await store.initialize()
    app.state.event_store = store
    yield
    # aiosqlite opens/closes per operation — no explicit teardown required


def create_app() -> FastAPI:
    """Application factory.

    Creates a FastAPI instance with lifespan, health endpoint,
    and event/weight routers mounted.

    Returns:
        Configured FastAPI application (not started — caller provides the runner).
    """
    application = FastAPI(
        title="DEEP6 ML Backend",
        description="Signal event ingestion, ML weight management, and regime detection API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Mount routers
    application.include_router(events_router.router)
    application.include_router(weights_router.router)

    @application.get("/health", tags=["health"])
    async def health() -> dict:
        """Liveness probe. Returns status and current epoch timestamp."""
        return {"status": "ok", "ts": time.time()}

    return application


# Module-level instance — used by uvicorn and importers
app = create_app()
