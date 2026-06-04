from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from deep6v2.types.signal import SignalResult


class SignalTier(str, Enum):
    TYPE_A = "TYPE_A"
    TYPE_B = "TYPE_B"
    TYPE_C = "TYPE_C"
    QUIET = "QUIET"


SignalTier.TYPE_A_MIN_SCORE = 80
SignalTier.TYPE_B_MIN_SCORE = 72
SignalTier.TYPE_C_MIN_SCORE = 50


class ScorerResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    tier: SignalTier
    raw_score: float
    final_score: float
    category_scores: dict[str, float]
    category_count: int
    confluence_mult: float
    zone_bonus: float
    gex_mult: float
    agreement_mult: float
    ib_mult: float
    vpin_mult: float
    midday_blocked: bool
    active_signals: list[SignalResult]
    veto_reasons: list[str]
    e10_agreement: bool | None
    e10_caution: bool
    wall_context_applied: bool = False
    wall_context_details: list[str] = []


__all__ = ["ScorerResult", "SignalTier"]
