"""SD Anchor AI — webhook receiver for Pine Script candidate payloads.

Provides:
  - ``create_webhook_app(sidecar)`` — standalone FastAPI app for __main__.py
  - ``router`` + ``set_sidecar(sidecar)`` — mountable router for the main API app

Pine payload format (from Indicators/sd_anchor_ai.pine):
  The Pine script sends canonical field names (anchor_low_price, pine_confidence_score, etc.)
  plus short aliases (anchorLow, confidence, etc.) in the same JSON.  Normalization below
  maps aliases → canonical names so payloads with only aliases still validate.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from deep6.sd_anchor.sidecar import SDSidecar, validate_candidate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pine alias → canonical field mapping
# ---------------------------------------------------------------------------
# Only exact 1:1 aliases from the Pine payload (line 188 of sd_anchor_ai.pine).
# We never invent mappings — these are the fields Pine actually sends as duplicates.

_PINE_ALIASES: dict[str, str] = {
    "anchorLow": "anchor_low_price",
    "anchorHigh": "anchor_high_price",
    "confidence": "pine_confidence_score",
    "timeframe": "timeframe_primary",
}


def normalize_pine_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Copy alias values into canonical fields when canonical is missing.

    Does NOT overwrite existing canonical values — aliases are fallback only.
    Returns the same dict (mutated in place) for convenience.
    """
    for alias, canonical in _PINE_ALIASES.items():
        if canonical not in raw and alias in raw:
            raw[canonical] = raw[alias]
    return raw


# ---------------------------------------------------------------------------
# Pydantic model for the webhook payload
# ---------------------------------------------------------------------------

class SDCandidatePayload(BaseModel):
    """Webhook payload from TradingView Pine alert (sd_anchor_ai.pine).

    All required fields match sidecar._REQUIRED_CANDIDATE_FIELDS.
    Extra fields (levels, aliases, event type) are passed through.
    """

    # Required by sidecar validation
    anchor_id: str
    symbol: str
    timeframe_primary: str | None = None  # may come via alias "timeframe"
    direction: str
    anchor_low_price: float | None = None  # may come via alias "anchorLow"
    anchor_high_price: float | None = None  # may come via alias "anchorHigh"
    anchor_low_bar_time: int
    anchor_high_bar_time: int
    pine_confidence_score: int | None = None  # may come via alias "confidence"
    pine_state: str = "candidate"

    # Optional fields from Pine
    event: str | None = None
    timeframe: str | None = None
    confidence: int | None = None
    range: float | None = Field(None, alias="range")
    level_minus2: float | None = None
    level_minus2_5: float | None = None
    level_minus4: float | None = None
    level2: float | None = None
    level2_5: float | None = None
    level4: float | None = None
    anchorLow: float | None = None
    anchorHigh: float | None = None
    barTime: int | None = None

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Router (mountable on the main API app)
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/sd-anchor", tags=["sd-anchor"])

# Module-level sidecar reference — set via set_sidecar() or create_webhook_app()
_sidecar: SDSidecar | None = None


def set_sidecar(sidecar: SDSidecar) -> None:
    """Wire a sidecar instance for the router. Call before mounting."""
    global _sidecar
    _sidecar = sidecar


@router.post("/webhook")
async def receive_candidate(payload: SDCandidatePayload) -> dict:
    """Receive a Pine candidate payload and queue it for HERMES review.

    TradingView webhook → POST /api/sd-anchor/webhook
        → normalize aliases → validate → queue into SDSidecar

    Returns 202 on accepted, 422 on validation failure, 503 if sidecar not ready.
    """
    if _sidecar is None:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": "sidecar not initialized"},
        )

    raw = payload.model_dump(exclude_none=True)
    normalized = normalize_pine_payload(raw)

    errors = validate_candidate(normalized)
    if errors:
        logger.warning("sd_anchor.webhook.invalid errors=%s", errors)
        return JSONResponse(
            status_code=422,
            content={"status": "rejected", "errors": errors},
        )

    await _sidecar.receive_candidate(normalized)

    anchor_id = normalized.get("anchor_id", "unknown")
    logger.info(
        "sd_anchor.webhook.accepted anchor_id=%s direction=%s",
        anchor_id,
        normalized.get("direction"),
    )
    return {
        "status": "accepted",
        "anchor_id": anchor_id,
        "queued_at": time.time(),
    }


@router.get("/health")
async def health() -> dict:
    """Sidecar health check."""
    running = _sidecar is not None and _sidecar._running
    return {
        "status": "ok" if running else "idle",
        "sidecar_initialized": _sidecar is not None,
        "sidecar_running": running,
        "ts": time.time(),
    }


# ---------------------------------------------------------------------------
# Standalone app factory (used by __main__.py)
# ---------------------------------------------------------------------------

def create_webhook_app(sidecar: SDSidecar) -> FastAPI:
    """Create a minimal FastAPI app with only the SD Anchor webhook route.

    Used by ``python -m deep6.sd_anchor`` for standalone operation.
    The main DEEP6 API (deep6/api/app.py) can mount the router directly instead.

    Args:
        sidecar: SDSidecar instance to receive candidates.

    Returns:
        Configured FastAPI application.
    """
    set_sidecar(sidecar)

    app = FastAPI(
        title="SD Anchor AI — Webhook Receiver",
        version="0.1.0",
    )
    app.include_router(router)

    @app.get("/health")
    async def root_health() -> dict:
        return {"status": "ok", "service": "sd_anchor", "ts": time.time()}

    return app
