"""Backtest API routes — replay-backed POST /backtest/run + GET /backtest/results/{job_id}."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, model_validator

from deep6.backtest.research_runner import ReplayRunRequest, ResearchRunner

log = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest", tags=["backtest"])

# In-memory job store: job_id → status dict
_backtest_jobs: dict[str, dict[str, Any]] = {}


class BacktestRequest(BaseModel):
    """Compatibility request body for POST /backtest/run."""

    model_config = ConfigDict(extra="forbid")

    start_date: date = date(2026, 4, 7)
    end_date: date = date(2026, 4, 10)
    bar_seconds: int = 60

    @model_validator(mode="after")
    def _validate_range(self) -> "BacktestRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if self.bar_seconds not in (60, 300):
            raise ValueError("bar_seconds must be 60 or 300")
        return self


def _to_replay_request(req: BacktestRequest, job_id: str) -> ReplayRunRequest:
    start = datetime.fromisoformat(f"{req.start_date}T13:30:00").replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(f"{req.end_date}T20:00:00").replace(tzinfo=timezone.utc)
    if req.bar_seconds == 300:
        tf_list = ["5m"]
    else:
        tf_list = ["1m"]
    return ReplayRunRequest(
        start=start,
        end=end,
        tf_list=tf_list,
        duckdb_path=f"./backtest-{job_id}.duckdb",
        dry_run=True,
    )


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run_backtest_job(req: BacktestRequest) -> dict:
    running = [j for j in _backtest_jobs.values() if j.get("status") == "running"]
    if running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A backtest is already running. Wait for it to complete.",
        )

    job_id = str(uuid.uuid4())
    replay_request = _to_replay_request(req, job_id)
    _backtest_jobs[job_id] = {
        "status": "running",
        "started_at": time.time(),
        "request": replay_request.model_dump(mode="json"),
    }
    log.info("backtest.started", extra={"job_id": job_id, "start": req.start_date, "end": req.end_date})
    asyncio.create_task(_execute_backtest(job_id, replay_request))
    return {"job_id": job_id, "status": "running"}


@router.get("/results/{job_id}")
async def get_backtest_results(job_id: str) -> dict:
    job = _backtest_jobs.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backtest job {job_id!r} not found",
        )
    return job


async def _execute_backtest(job_id: str, req: ReplayRunRequest) -> None:
    try:
        result = await ResearchRunner().run(req)
        _backtest_jobs[job_id].update(result.model_dump(mode="json"))
        log.info(
            "backtest.complete",
            extra={"job_id": job_id, "run_id": result.run_id, "rows": result.total_bars, "summary": result.summary},
        )
    except Exception as exc:
        log.exception("backtest.error", extra={"job_id": job_id, "error": str(exc)})
        _backtest_jobs[job_id].update({
            "status": "error",
            "error": str(exc),
            "completed_at": time.time(),
        })
