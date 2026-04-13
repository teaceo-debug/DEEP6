"""Weight file routes — GET /weights/current and POST /weights/deploy.

GET /weights/current: Returns the currently deployed weight file JSON,
or default weights (all 1.0) if no file has been deployed.

POST /weights/deploy: Gate skeleton (Plan 03 will implement full WFE
validation + weight swap). Already enforces DEPLOY_SECRET auth per T-09-04
so the security surface is correct before full implementation.

Per D-19: deployment requires operator confirmation token (Plan 03).
Per D-20: weights loaded atomically at next bar boundary.
Per T-09-04: DEPLOY_SECRET env var gates the deploy endpoint.
"""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, Header, HTTPException, status

from deep6.api.schemas import WeightFileOut

router = APIRouter(prefix="/weights", tags=["weights"])

# Default weight file path — overridable via env var
_DEFAULT_WEIGHTS_PATH = "./deep6_weights.json"

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


@router.get("/current", response_model=WeightFileOut)
async def get_current_weights() -> WeightFileOut:
    """Return the currently deployed weight file.

    Reads from WEIGHTS_PATH env var (default ./deep6_weights.json).
    If no file exists, returns default weights (all 1.0) with n_samples=0.
    """
    weights_path = os.environ.get("WEIGHTS_PATH", _DEFAULT_WEIGHTS_PATH)

    if os.path.exists(weights_path):
        try:
            with open(weights_path, "r") as f:
                data = json.load(f)
            return WeightFileOut(
                weights=data.get("weights", _DEFAULT_WEIGHTS),
                regime_adjustments=data.get("regime_adjustments", _DEFAULT_REGIME_ADJUSTMENTS),
                deployed_at=data.get("deployed_at"),
                training_date=data.get("training_date"),
                n_samples=data.get("n_samples", 0),
                wfe=data.get("wfe"),
                metadata=data.get("metadata", {}),
            )
        except (json.JSONDecodeError, KeyError, OSError):
            # Corrupt or unreadable file — fall through to defaults
            pass

    # No file or unreadable: return safe defaults
    return WeightFileOut(
        weights=_DEFAULT_WEIGHTS,
        regime_adjustments=_DEFAULT_REGIME_ADJUSTMENTS,
        deployed_at=None,
        training_date=None,
        n_samples=0,
        wfe=None,
        metadata={},
    )


@router.post("/deploy", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def deploy_weights(
    x_deploy_secret: str | None = Header(default=None),
) -> dict:
    """Deploy a new weight file (skeleton — full implementation in Plan 03).

    Per T-09-04: If DEPLOY_SECRET env var is set, requires matching
    X-Deploy-Secret header. Returns 401 if header is missing or wrong.
    Returns 501 when auth passes (endpoint not yet implemented).

    Per D-19: Full implementation will require WFE >= 0.70 gate +
    operator confirmation token + before/after comparison.
    """
    deploy_secret = os.environ.get("DEPLOY_SECRET")
    if deploy_secret:
        if x_deploy_secret != deploy_secret:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid X-Deploy-Secret header",
            )

    return {
        "status": "not_implemented",
        "message": "See Plan 03 — full WFE gate + weight swap implementation pending",
    }
