"""Backtest API routes — POST /backtest/run + GET /backtest/results/{job_id}.

Triggers async backtest job using the DEEP6 signal pipeline on historical bars.
Returns job_id immediately (non-blocking). Caller polls status via GET.

Dry-run mode (no DATABENTO_API_KEY):
    Uses _make_synthetic_bars() from sweep_thresholds for CI / local dev.

Per D-20: /backtest/run endpoint
Per D-21: /backtest/results/{job_id} endpoint
Per T-10-02: 409 gate prevents concurrent backtest jobs.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

# Ensure project root is on sys.path for scripts/ imports
_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest", tags=["backtest"])

# In-memory job store: job_id → status dict
# Single-operator system (D-24) — non-durable in-process state.
_backtest_jobs: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------

class BacktestRequest(BaseModel):
    """Request body for POST /backtest/run."""
    start_date: str = "2026-04-07"
    end_date: str = "2026-04-10"
    bar_seconds: int = 60


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run_backtest_job(req: BacktestRequest) -> dict:
    """Trigger an async backtest job.

    Returns job_id immediately. Poll GET /backtest/results/{job_id} for status.

    Per T-10-02: Returns 409 Conflict if a backtest is already running.
    """
    running = [j for j in _backtest_jobs.values() if j.get("status") == "running"]
    if running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A backtest is already running. Wait for it to complete.",
        )

    job_id = str(uuid.uuid4())
    _backtest_jobs[job_id] = {
        "status": "running",
        "started_at": time.time(),
        "request": req.model_dump(),
    }

    log.info("backtest.started", extra={"job_id": job_id, "start": req.start_date, "end": req.end_date})
    asyncio.create_task(_execute_backtest(job_id, req))

    return {"job_id": job_id, "status": "running"}


@router.get("/results/{job_id}")
async def get_backtest_results(job_id: str) -> dict:
    """Return status and results for a backtest job.

    Returns 404 if job_id is unknown.
    """
    job = _backtest_jobs.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backtest job {job_id!r} not found",
        )
    return job


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def _execute_backtest(job_id: str, req: BacktestRequest) -> None:
    """Run backtest in executor thread; update job store on completion or error.

    Dry-run mode: if DATABENTO_API_KEY is not set, uses synthetic bars
    (via _make_synthetic_bars from sweep_thresholds) so the endpoint works
    in CI / local dev without a Databento account.
    """
    loop = asyncio.get_event_loop()
    try:
        api_key = os.environ.get("DATABENTO_API_KEY", "")
        if not api_key:
            log.info("backtest.dry_run", extra={"job_id": job_id, "bars": 100})
            bars = await loop.run_in_executor(None, _make_synthetic_bars_sync, 100)
        else:
            bars = await loop.run_in_executor(None, _load_databento_bars, req)

        # Run backtest in executor (CPU-bound)
        results = await loop.run_in_executor(None, _run_backtest_sync, bars)

        # Compute tier summary
        summary: dict[str, int] = {}
        for row in results:
            tier = row.get("tier", "QUIET")
            summary[tier] = summary.get(tier, 0) + 1

        _backtest_jobs[job_id].update({
            "status": "complete",
            "completed_at": time.time(),
            "rows": results,
            "summary": summary,
            "total_bars": len(results),
        })
        log.info(
            "backtest.complete",
            extra={"job_id": job_id, "rows": len(results), "summary": summary},
        )

    except Exception as exc:
        log.exception("backtest.error", extra={"job_id": job_id, "error": str(exc)})
        _backtest_jobs[job_id].update({
            "status": "error",
            "error": str(exc),
            "completed_at": time.time(),
        })


def _make_synthetic_bars_sync(n: int) -> list:
    """Create synthetic bars for dry-run (blocking — runs in executor)."""
    from scripts.sweep_thresholds import _make_synthetic_bars
    return _make_synthetic_bars(n)


def _load_databento_bars(req: BacktestRequest) -> list:
    """Load historical bars from Databento (blocking — runs in executor)."""
    import databento as db
    from scripts.backtest_signals import build_bars

    api_key = os.environ.get("DATABENTO_API_KEY", "")
    client = db.Historical(key=api_key)
    data = client.timeseries.get_range(
        dataset="GLBX.MDP3",
        schema="trades",
        stype_in="continuous",
        symbols=["NQ.c.0"],
        start=f"{req.start_date}T13:30:00",
        end=f"{req.end_date}T20:00:00",
    )
    return build_bars(data, bar_seconds=req.bar_seconds)


def _run_backtest_sync(bars: list) -> list[dict]:
    """Run the backtest signal pipeline (blocking — runs in executor)."""
    from scripts.backtest_signals import run_backtest
    return run_backtest(bars)
