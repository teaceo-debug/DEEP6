"""Shared bias-engine contracts for v3 domain composition."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Optional


class BiasState(IntEnum):
    STRONG_BEAR = -2
    LEAN_BEAR = -1
    NEUTRAL = 0
    LEAN_BULL = 1
    STRONG_BULL = 2


class BiasMode(str, Enum):
    GO = "GO"
    CAUTION = "CAUTION"
    STOP = "STOP"


@dataclass(slots=True)
class DomainScore:
    domain: str
    score: int
    max_range: int
    available: bool
    stale: bool
    detail: dict
    updated_at: float = field(default_factory=time.time)


@dataclass(slots=True)
class BiasComponentState:
    ict_score: int
    macro_score: int
    flow_score: int
    kronos_score: int
    gex_score: int
    total_score: int
    confidence: float
    setup_quality: int
    bias_state: BiasState
    mode: str
    reason: str


@dataclass(slots=True)
class MarketBiasSnapshot:
    symbol: str
    asof_ts: float
    bias_label: str
    bias_state: BiasState
    bias_score: int
    confidence: float
    setup_quality: int
    mode: str
    mode_reason: str
    session_label: str
    xamd_phase: str
    intermarket_alignment: float
    kronos_confidence: float
    nearest_support: Optional[float]
    nearest_resistance: Optional[float]
    domain_detail: dict
    meta: dict


__all__ = [
    "BiasState",
    "BiasMode",
    "DomainScore",
    "BiasComponentState",
    "MarketBiasSnapshot",
]
