"""GEX Doctor ingest endpoint — accepts GEXDoctorPayload from gex_terminal."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/gex", tags=["gex-ingest"])

_latest_gex_doctor: Optional["GEXDoctorPayload"] = None


class GEXDoctorPayload(BaseModel):
    """Payload from GEX Doctor — matches DomainScore interface exactly."""

    domain: str = "gex_doctor"
    score: int
    max_range: int = 3
    available: bool = True
    stale: bool = False
    detail: dict[str, Any]
    updated_at: float


@router.post("/ingest")
async def ingest_gex_doctor(payload: GEXDoctorPayload) -> dict[str, Any]:
    """Accept GEX Doctor positioning data and store for bias engine consumption."""
    global _latest_gex_doctor
    _latest_gex_doctor = payload
    return {"status": "ok", "domain": payload.domain, "score": payload.score}


@router.get("/latest")
async def get_latest() -> dict[str, Any]:
    """Return latest GEX Doctor payload. 503 if not yet received."""
    if _latest_gex_doctor is None:
        return {"status": "pending", "message": "No GEX Doctor data received yet"}
    return {
        "status": "ok",
        "domain": _latest_gex_doctor.domain,
        "score": _latest_gex_doctor.score,
        "max_range": _latest_gex_doctor.max_range,
        "available": _latest_gex_doctor.available,
        "stale": _latest_gex_doctor.stale,
        "detail": _latest_gex_doctor.detail,
        "updated_at": _latest_gex_doctor.updated_at,
    }


def get_latest_as_domain_score() -> Optional[dict[str, Any]]:
    """Called by bias_v3.py to include gex_doctor in domain scores."""
    if _latest_gex_doctor is None:
        return None
    return {
        "domain": _latest_gex_doctor.domain,
        "score": _latest_gex_doctor.score,
        "max_range": _latest_gex_doctor.max_range,
        "available": _latest_gex_doctor.available,
        "stale": _latest_gex_doctor.stale,
        "detail": _latest_gex_doctor.detail,
        "updated_at": _latest_gex_doctor.updated_at,
    }


__all__ = ["router", "GEXDoctorPayload", "get_latest_as_domain_score"]
