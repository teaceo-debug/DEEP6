"""Metrics routes — GET /metrics/signals and GET /metrics/regimes.

GET /metrics/signals — per-tier rolling-window performance for all windows,
                       aggregated across all HMM regimes.
GET /metrics/regimes — same metrics sliced by HMM regime label.

Per D-22/D-23: Uses PerformanceTracker to compute win_rate, profit_factor,
Sharpe for rolling windows of 50 / 200 / 500 trades.

Per T-09-13: Endpoints return only aggregated metrics — no individual
trade details are exposed.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Request

from deep6.ml.performance_tracker import PerformanceTracker, _REGIMES

router = APIRouter(prefix="/metrics", tags=["metrics"])

_tracker = PerformanceTracker(windows=[50, 200, 500])


@router.get("/signals")
async def get_signal_metrics(request: Request) -> dict:
    """Return per-tier rolling-window performance metrics (all-regime aggregate).

    Computes win_rate, profit_factor, Sharpe for TYPE_A / TYPE_B / TYPE_C
    across rolling windows of 50, 200, and 500 closed trades.

    Returns:
        {
            "tiers": [TierMetrics.to_dict(), ...],   # regime=None entries only
            "generated_at": float
        }
    """
    store = request.app.state.event_store
    metrics = await _tracker.fetch_and_compute(store)
    tier_metrics = [m.to_dict() for m in metrics if m.regime is None]
    return {"tiers": tier_metrics, "generated_at": time.time()}


@router.get("/regimes")
async def get_regime_metrics(request: Request) -> dict:
    """Return per-tier performance metrics sliced by HMM regime.

    Returns the same computation as /metrics/signals but grouped by
    regime label (ABSORPTION_FRIENDLY, TRENDING, CHAOTIC).

    Returns:
        {
            "by_regime": {
                "ABSORPTION_FRIENDLY": [TierMetrics.to_dict(), ...],
                "TRENDING": [...],
                "CHAOTIC": [...]
            },
            "generated_at": float
        }
    """
    store = request.app.state.event_store
    metrics = await _tracker.fetch_and_compute(store)
    by_regime: dict[str, list[dict]] = {regime: [] for regime in _REGIMES}
    for m in metrics:
        if m.regime is not None and m.regime in by_regime:
            by_regime[m.regime].append(m.to_dict())
    return {"by_regime": by_regime, "generated_at": time.time()}
