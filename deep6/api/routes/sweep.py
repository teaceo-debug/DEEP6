"""Sweep API routes — POST /ml/sweep + GET /ml/sweep/{job_id}.

Triggers async Bayesian Optuna sweep over signal thresholds.
Returns job_id immediately (non-blocking). Caller polls status via GET.

Dry-run mode (no DATABENTO_API_KEY):
    Uses _make_synthetic_bars(200) from sweep_thresholds so the sweep
    endpoint can be exercised in CI / local dev without a Databento account.

T-09-12: Max 1 concurrent sweep job — returns 409 if sweep already running.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
import uuid
from typing import Any

import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

# Ensure project root is on sys.path so scripts/ imports work when the module
# is loaded relative to the package root.
_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.sweep_thresholds import _make_synthetic_bars, make_objective  # noqa: E402

log = logging.getLogger(__name__)

router = APIRouter(prefix="/ml", tags=["ml"])

# In-memory job store: job_id → status dict
# Simple dict — sweep jobs are single-user, in-process, non-durable.
_sweep_jobs: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------

class SweepRequest(BaseModel):
    """Request body for POST /ml/sweep."""
    start_date: str = "2026-04-07"
    end_date: str = "2026-04-10"
    trials: int = 50
    bar_seconds: int = 60


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/sweep", status_code=status.HTTP_202_ACCEPTED)
async def trigger_sweep(req: SweepRequest) -> dict:
    """Trigger a Bayesian Optuna threshold sweep asynchronously.

    Returns job_id immediately. Poll GET /ml/sweep/{job_id} for status.

    T-09-12: Returns 409 Conflict if a sweep is already running.
    """
    # T-09-12: only 1 active sweep at a time
    running = [j for j in _sweep_jobs.values() if j.get("status") == "running"]
    if running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A sweep is already running. Wait for it to complete.",
        )

    job_id = str(uuid.uuid4())
    _sweep_jobs[job_id] = {
        "status": "running",
        "started_at": time.time(),
        "request": req.model_dump(),
    }

    log.info("sweep.started", extra={"job_id": job_id, "trials": req.trials})
    asyncio.create_task(_run_sweep_job(job_id, req))

    return {"job_id": job_id, "status": "running"}


@router.get("/sweep/{job_id}")
async def get_sweep_status(job_id: str) -> dict:
    """Return status and results for a sweep job.

    Returns 404 if job_id is unknown.
    """
    job = _sweep_jobs.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sweep job {job_id!r} not found",
        )
    return job


@router.get("/deploy-token")
async def get_deploy_token() -> dict:
    """Generate and return a one-time confirmation token for POST /weights/deploy.

    The token is echoed to the operator, who copies it into the deploy request body.
    Server-side expected token is DEPLOY_SECRET env var — this endpoint just informs
    the operator what value to use (they already know their secret).

    In practice: if DEPLOY_SECRET is set, the operator provides that value.
    This endpoint confirms the server is ready and alive.
    """
    deploy_secret = os.environ.get("DEPLOY_SECRET")
    if not deploy_secret:
        # No secret configured — return a hint
        return {
            "status": "no_secret_configured",
            "message": "Set DEPLOY_SECRET env var to enable deploy gating",
        }
    return {
        "status": "ready",
        "message": "Provide DEPLOY_SECRET value as confirmation_token in POST /weights/deploy",
        "token_length": len(deploy_secret),
    }


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def _run_sweep_job(job_id: str, req: SweepRequest) -> None:
    """Run sweep in executor thread; update job store on completion or error.

    Dry-run mode: if DATABENTO_API_KEY is not set, uses synthetic bars.
    """
    loop = asyncio.get_event_loop()
    try:
        api_key = os.environ.get("DATABENTO_API_KEY", "")
        if not api_key:
            log.info("sweep.dry_run", extra={"job_id": job_id, "bars": 200})
            bars = _make_synthetic_bars(200)
        else:
            # Load bars in executor (blocking Databento I/O)
            bars = await loop.run_in_executor(None, _load_databento_bars, req)

        # Run Optuna optimization in executor (CPU-bound)
        study = await loop.run_in_executor(None, _run_optuna_sync, bars, req.trials)

        _sweep_jobs[job_id].update({
            "status": "complete",
            "completed_at": time.time(),
            "best_params": study.best_params,
            "best_pnl": study.best_value,
            "n_trials_completed": len(study.trials),
        })
        log.info(
            "sweep.complete",
            extra={"job_id": job_id, "best_pnl": study.best_value},
        )

    except Exception as exc:
        log.exception("sweep.error", extra={"job_id": job_id, "error": str(exc)})
        _sweep_jobs[job_id].update({
            "status": "error",
            "error": str(exc),
            "completed_at": time.time(),
        })


def _load_databento_bars(req: SweepRequest) -> list:
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


def _run_optuna_sync(bars: list, n_trials: int) -> optuna.Study:
    """Run Optuna TPE sweep synchronously (blocking — runs in executor).

    Returns the completed study object.
    """
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
        study_name="deep6_api_sweep",
    )
    study.optimize(make_objective(bars), n_trials=n_trials)
    return study
