"""DEEP6 v3 market bias routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from deep6.api.routes.gex_ingest import get_latest_as_domain_score

router = APIRouter(prefix="/api/v3/bias", tags=["bias-v3"])

_latest_snapshot = None
_snapshot_history: list[Any] = []
_domain_scores: dict[str, Any] = {}


def update_snapshot(snapshot, domain_scores: dict | None = None):
    """Called by MarketBiasEngine after each compute_bias()."""
    global _latest_snapshot, _domain_scores

    _latest_snapshot = snapshot
    if domain_scores is not None:
        _domain_scores = dict(domain_scores)

    if len(_snapshot_history) >= 100:
        _snapshot_history.pop(0)
    _snapshot_history.append(snapshot)


@router.get("")
def get_bias():
    """Latest MarketBiasSnapshot as JSON dict. 503 if not initialized."""
    if _latest_snapshot is None:
        raise HTTPException(503, detail="Bias engine not initialized")
    return _snapshot_to_dict(_latest_snapshot)


@router.get("/domains")
def get_domain_scores():
    """Latest domain scores breakdown. 503 if not initialized."""
    scores = dict(_domain_scores)
    gex_doctor = get_latest_as_domain_score()
    if gex_doctor is not None:
        scores["gex_doctor"] = gex_doctor
    if not scores:
        raise HTTPException(503, detail="Bias engine not initialized")
    return scores


@router.get("/history")
def get_bias_history(limit: int = 20):
    """Last N bias snapshots."""
    return [_snapshot_to_dict(s) for s in _snapshot_history[-limit:]]


def _snapshot_to_dict(snapshot) -> dict:
    """Convert MarketBiasSnapshot to JSON-serializable dict."""
    return {
        "symbol": snapshot.symbol,
        "asof_ts": snapshot.asof_ts,
        "bias_label": snapshot.bias_label,
        "bias_state": snapshot.bias_state,
        "bias_score": snapshot.bias_score,
        "confidence": snapshot.confidence,
        "setup_quality": snapshot.setup_quality,
        "mode": snapshot.mode,
        "mode_reason": snapshot.mode_reason,
        "session_label": snapshot.session_label,
        "xamd_phase": snapshot.xamd_phase,
        "intermarket_alignment": snapshot.intermarket_alignment,
        "kronos_confidence": snapshot.kronos_confidence,
        "nearest_support": snapshot.nearest_support,
        "nearest_resistance": snapshot.nearest_resistance,
        "domain_detail": snapshot.domain_detail,
        "meta": snapshot.meta,
    }


__all__ = ["router", "update_snapshot"]
