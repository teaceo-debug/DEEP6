"""DEEP6 bidirectional bridge — HTTP client for cross-process integration."""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from gex_terminal.schemas import BiasVerdict, GEXDoctorPayload

logger = logging.getLogger(__name__)

TIMEOUT = 5.0
MAX_RETRIES = 2


class DEEP6Bridge:
    """HTTP bridge: pushes GEXDoctorPayload to DEEP6, reads MarketBiasSnapshot."""

    def __init__(self, deep6_url: str = "http://localhost:8765") -> None:
        self._base_url = deep6_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=TIMEOUT)
        self._last_bias_score: Optional[int] = None
        self._last_bias_label: Optional[str] = None
        self._last_confidence: Optional[float] = None
        self._connected = False

    async def push_gex_snapshot(self, bias: BiasVerdict, detail: dict) -> bool:
        """Push current GEX analysis to DEEP6 bias engine.

        Returns True on success, False on failure (non-blocking).
        """
        score = self._verdict_to_score(bias)
        payload = GEXDoctorPayload(
            domain="gex_doctor",
            score=score,
            max_range=3,
            available=True,
            stale=False,
            detail=detail,
            updated_at=time.time(),
        )

        try:
            response = await self._client.post(
                f"{self._base_url}/api/gex/ingest",
                json=payload.model_dump(),
            )
            response.raise_for_status()
            self._connected = True
            return True
        except Exception as exc:
            logger.debug("DEEP6 push failed (non-blocking): %s", exc)
            self._connected = False
            return False

    async def read_bias(self) -> tuple[Optional[int], Optional[str], Optional[float]]:
        """Read current bias from DEEP6 bias engine.

        Returns (bias_score, bias_label, confidence) or (None, None, None) on failure.
        """
        try:
            response = await self._client.get(f"{self._base_url}/api/v3/bias")
            response.raise_for_status()
            data = response.json()

            bias_score = data.get("bias_score")
            bias_label = data.get("bias_label")
            confidence = data.get("confidence")

            self._last_bias_score = bias_score
            self._last_bias_label = bias_label
            self._last_confidence = confidence
            self._connected = True

            return bias_score, bias_label, confidence
        except Exception as exc:
            logger.debug("DEEP6 read failed (non-blocking): %s", exc)
            self._connected = False
            return None, None, None

    def _verdict_to_score(self, bias: BiasVerdict) -> int:
        """Convert BiasVerdict to integer score -3..+3."""
        if bias.direction == "NEUTRAL":
            return 0

        sign = 1 if bias.direction == "BULLISH" else -1
        if bias.confidence >= 80:
            magnitude = 3
        elif bias.confidence >= 65:
            magnitude = 2
        elif bias.confidence >= 50:
            magnitude = 1
        else:
            return 0

        return sign * magnitude

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def last_bias_score(self) -> Optional[int]:
        return self._last_bias_score

    @property
    def last_bias_label(self) -> Optional[str]:
        return self._last_bias_label

    @property
    def last_confidence(self) -> Optional[float]:
        return self._last_confidence

    async def close(self) -> None:
        await self._client.aclose()


__all__ = ["DEEP6Bridge"]
