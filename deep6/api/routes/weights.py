"""Weight file routes — GET /weights/current, POST /weights/deploy, GET /weights/rollback.

GET /weights/current: Returns the currently deployed weight file JSON plus
  previous/backup info for operator comparison.

POST /weights/deploy: Full 3-part gate (Plan 03):
  (a) Operator confirmation token matching DEPLOY_SECRET env var
  (b) WFE >= 0.70 (D-16)
  (c) 200+ total OOS trades from EventStore (D-17)
  (d) Weight cap: no signal > 3x baseline (D-15)
  Atomic write via WeightLoader.write_atomic (T-09-09).

GET /weights/rollback: Restore previous weight file if within 7-day TTL (D-21).

Security:
  T-09-04: DEPLOY_SECRET env var required for deploy token verification.
  T-09-11: All deploy attempts logged with structlog.
"""
from __future__ import annotations

import logging
import os
import time

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from deep6.api.schemas import WeightFileOut
from deep6.ml.deploy_gate import DeployGate
from deep6.ml.lgbm_trainer import WeightFile
from deep6.ml.weight_loader import WeightLoader

log = logging.getLogger(__name__)

router = APIRouter(prefix="/weights", tags=["weights"])

# Default weight file path — overridable via WEIGHTS_PATH env var
_DEFAULT_WEIGHTS_PATH = "./deep6_weights.json"
_DEFAULT_BACKUP_PATH = "./deep6_weights_prev.json"

# Default weights: all signals at 1.0 multiplier (no adjustment)
_DEFAULT_WEIGHTS: dict[str, float] = {
    "absorption": 1.0,
    "exhaustion": 1.0,
    "trapped": 1.0,
    "delta": 1.0,
    "imbalance": 1.0,
    "volume_profile": 1.0,
    "auction": 1.0,
    "poc": 1.0,
}

_DEFAULT_REGIME_ADJUSTMENTS: dict[str, dict[str, float]] = {
    "POSITIVE_DAMPENING": {},
    "NEGATIVE_AMPLIFYING": {},
    "NEUTRAL": {},
}


def _get_loader() -> WeightLoader:
    """Build WeightLoader from env-configured paths."""
    weights_path = os.environ.get("WEIGHTS_PATH", _DEFAULT_WEIGHTS_PATH)
    backup_path = os.environ.get("WEIGHTS_BACKUP_PATH", _DEFAULT_BACKUP_PATH)
    return WeightLoader(weights_path=weights_path, backup_path=backup_path, backup_ttl_days=7)


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------

class DeployRequest(BaseModel):
    """Request body for POST /weights/deploy.

    candidate_weights: WeightFile.to_json() payload from LGBMTrainer.
    confirmation_token: Must match DEPLOY_SECRET env var (T-09-04).
    override_weight_cap: If True, bypass 3x weight cap gate (requires explicit opt-in).
    """
    candidate_weights: dict
    confirmation_token: str
    override_weight_cap: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reconstruct_weight_file(data: dict) -> WeightFile:
    """Reconstruct a WeightFile from a WeightFile.to_json() dict.

    WeightFile.to_json() excludes model_path for portability.
    We set model_path to empty string since it's not needed for gate evaluation.
    """
    return WeightFile(
        weights=data.get("weights", {}),
        regime_adjustments=data.get("regime_adjustments", {}),
        feature_importances=data.get("feature_importances", {}),
        training_date=data.get("training_date", ""),
        n_samples=int(data.get("n_samples", 0)),
        metrics=data.get("metrics", {}),
        wfe=data.get("wfe"),
        model_path=data.get("model_path", ""),
        model_checksum=data.get("model_checksum", ""),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/current")
async def get_current_weights() -> dict:
    """Return the currently deployed weight file plus backup comparison.

    Response includes:
      current: active weights JSON (or defaults if no file deployed)
      previous: backup weights JSON (or null)
      backup_age_days: age of backup file in days (or null)

    This replaces the Plan 01 WeightFileOut response with richer context
    to support the before/after comparison flow.
    """
    loader = _get_loader()
    current = loader.read_current()
    previous = loader.read_previous()

    if current is None:
        current_payload = {
            "weights": _DEFAULT_WEIGHTS,
            "regime_adjustments": _DEFAULT_REGIME_ADJUSTMENTS,
            "deployed_at": None,
            "training_date": None,
            "n_samples": 0,
            "wfe": None,
            "metadata": {},
        }
    else:
        current_payload = current

    return {
        "current": current_payload,
        "previous": previous,
        "backup_age_days": loader.backup_age_days(),
    }


@router.post("/deploy")
async def deploy_weights(req: DeployRequest, request: Request) -> dict:
    """Deploy new weights after passing all 3 gate conditions.

    Gate:
      1. confirmation_token must match DEPLOY_SECRET env var
      2. candidate WFE >= 0.70
      3. Total OOS trades from EventStore >= 200
      4. No signal weight > 3x baseline (unless override_weight_cap=True)

    On success: writes weight file atomically to WEIGHTS_PATH.
    On gate failure: raises 422 with gate reason.
    On missing DEPLOY_SECRET: 500 (misconfiguration).

    T-09-11: All deploy attempts logged.
    """
    # Load server-side expected token from env (T-09-04)
    deploy_secret = os.environ.get("DEPLOY_SECRET", "")
    if not deploy_secret:
        log.error("weights.deploy.no_secret_configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DEPLOY_SECRET env var not configured",
        )

    # Reconstruct candidate WeightFile from request payload
    try:
        candidate = _reconstruct_weight_file(req.candidate_weights)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid candidate_weights payload: {exc}",
        )

    # Override weight cap if operator explicitly opted in
    gate = DeployGate(
        wfe_threshold=0.70,
        min_oos_trades=200,
        weight_cap=999.0 if req.override_weight_cap else 3.0,
    )

    # Load OOS trade counts from EventStore
    store = request.app.state.event_store
    try:
        oos_counts: dict[str, int] = await store.count_oos_trades_per_signal()
    except Exception as exc:
        log.warning("weights.deploy.oos_count_failed", extra={"exc": str(exc)})
        oos_counts = {}

    # Load current weights for before/after comparison
    loader = _get_loader()
    current_data = loader.read_current()
    current: WeightFile | None = None
    if current_data is not None:
        try:
            current = _reconstruct_weight_file(current_data)
        except Exception:
            current = None

    # Evaluate gate
    decision = gate.evaluate(
        candidate=candidate,
        current=current,
        oos_counts=oos_counts,
        confirmation_token=req.confirmation_token,
        expected_token=deploy_secret,
    )

    # T-09-11: log all deploy attempts
    log.info(
        "weights.deploy.attempt",
        extra={
            "allowed": decision.allowed,
            "reason": decision.reason,
            "wfe": decision.wfe,
            "oos_total": sum(oos_counts.values()),
            "n_samples": candidate.n_samples,
        },
    )

    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=decision.reason,
        )

    # Write atomically (T-09-09)
    loader.write_atomic(candidate)

    log.info(
        "weights.deployed",
        extra={
            "wfe": decision.wfe,
            "n_samples": candidate.n_samples,
            "training_date": candidate.training_date,
            "by": "operator",
        },
    )

    return {
        "status": "deployed",
        "before_after": decision.before_after,
        "wfe": decision.wfe,
        "training_date": candidate.training_date,
        "deployed_at": time.time(),
    }


@router.get("/rollback")
async def rollback_weights() -> dict:
    """Restore the previous weight file if within 7-day TTL.

    D-21: Previous weights are kept for 7 days after each deploy.
    Rollback atomically replaces current weights with the backup.

    Returns:
        {"status": "rolled_back"} on success.
        {"status": "no_backup_available"} if no valid backup exists.
    """
    loader = _get_loader()
    ok = loader.rollback()

    if ok:
        log.info("weights.rollback.complete")
        return {"status": "rolled_back"}

    return {"status": "no_backup_available"}
