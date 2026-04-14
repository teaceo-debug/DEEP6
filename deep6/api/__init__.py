"""DEEP6 ML Backend API package.

Exports the FastAPI application instance and factory function.

Quick start:
    uvicorn deep6.api.app:app --port 8765

Programmatic (same event loop):
    from deep6.api.app import app, create_app
    import asyncio, uvicorn
    asyncio.create_task(uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8765)).serve())
"""
from deep6.api.app import app, create_app

__all__ = ["app", "create_app"]
