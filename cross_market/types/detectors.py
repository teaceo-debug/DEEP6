"""Detector result models for manipulation pattern detection."""
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class DetectorSide(str, Enum):
    BID = "bid"
    ASK = "ask"
    NEUTRAL = "neutral"


class SpoofResult(BaseModel):
    pattern: str = "spoof"
    side: DetectorSide
    price: float
    order_id: str
    life_ms: float
    size: int
    executed_qty: int = 0
    distance_to_touch_ticks: float
    spoof_probability: float = Field(ge=0, le=1)
    reason_codes: List[str]


class IcebergResult(BaseModel):
    pattern: str = "iceberg"
    price: float
    side: DetectorSide
    traded_cum: int
    peak_visible: int
    ratio: float
    refresh_count: int
    confidence: float = Field(ge=0, le=1)
    reason_codes: List[str]


class AbsorptionResult(BaseModel):
    pattern: str = "absorption"
    price: float
    side: DetectorSide
    aggressive_volume: int
    hold_ratio: float
    touch_count: int
    confidence: float = Field(ge=0, le=1)
    reason_codes: List[str]


class SweepResult(BaseModel):
    pattern: str = "sweep"
    direction: str  # "up" or "down"
    levels_taken: int
    total_volume: int
    time_span_ms: float
    target_reference: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    reason_codes: List[str]


class LayeringResult(BaseModel):
    pattern: str = "layering"
    side: DetectorSide
    n_levels: int
    sizes: List[int]
    top_price: float
    bot_price: float
    confidence: float = Field(ge=0, le=1)
    reason_codes: List[str]


class VacuumResult(BaseModel):
    pattern: str = "vacuum"
    direction: str
    depth_collapse_pct: float
    spread_expansion_ticks: float
    cancel_wave_count: int
    vacuum_probability: float = Field(ge=0, le=1)
    reason_codes: List[str]
