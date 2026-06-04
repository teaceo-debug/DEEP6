from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FARegime(BaseModel):
    model_config = ConfigDict(frozen=True)

    net_gex: float = 0.0
    gex_sign: Literal["positive", "negative"] = "positive"
    net_dex: float | None = None
    gamma_flip: float = 0.0
    call_wall: float | None = None
    put_wall: float | None = None
    max_pain: float | None = None


class FADealerRisk(BaseModel):
    model_config = ConfigDict(frozen=True)

    flow_direction: Literal["amplifying", "dampening", "regime flip", "neutral"] = "neutral"
    flow_gex_pct_shift: float | None = None
    flow_dex_pct_shift: float | None = None
    settled_net_gex: float | None = None
    settled_net_dex: float | None = None
    total_abs_delta_contracts: float | None = None
    description: str | None = None


class FAPinData(BaseModel):
    model_config = ConfigDict(frozen=True)

    pin_risk: float | None = None
    magnet_strike: float | None = None


class FAOISimulator(BaseModel):
    model_config = ConfigDict(frozen=True)

    contracts_with_flow: int | None = None
    intraday_oi_delta: float | None = None
    oi_delta_confidence: float | None = None


class FAProfileShape(BaseModel):
    model_config = ConfigDict(frozen=True)

    distribution: Literal["spread_even", "concentrated"] | None = None
    dominant_strike: float | None = None
    dominant_side: Literal["call", "put", "none"] | None = None


class FAHigherOrder(BaseModel):
    model_config = ConfigDict(frozen=True)

    vex_sign: Literal["positive", "negative", "neutral"] | None = None
    chex_sign: Literal["positive", "negative", "neutral"] | None = None


class FAVolContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    vix: float | None = None
    iv_rank: float | None = None


class FAFeedQuality(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan: Literal["basic", "growth", "alpha"] | None = None
    latency_seconds: float | None = None
    missing_fields: list[str] = Field(default_factory=list)


class FlashAlphaSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: str
    symbol: str
    underlying_price: float
    expiry: str | None = None
    session_phase: Literal["pre_market", "open", "intraday", "into_close"]
    dte: int | None = None
    regime: FARegime
    dealer_risk: FADealerRisk = Field(default_factory=FADealerRisk)
    pin: FAPinData = Field(default_factory=FAPinData)
    oi_simulator: FAOISimulator = Field(default_factory=FAOISimulator)
    profile_shape: FAProfileShape = Field(default_factory=FAProfileShape)
    higher_order: FAHigherOrder = Field(default_factory=FAHigherOrder)
    vol_context: FAVolContext = Field(default_factory=FAVolContext)
    feed_quality: FAFeedQuality = Field(default_factory=FAFeedQuality)


class MagnetCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: float
    level_type: str
    score: float
    confidence: float
    invalidation_level: float | None = None
    invalidation_reason: str


class MagnetResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    primary_magnet: float | None = None
    magnet_confidence: float
    invalidation_level: float | None = None
    invalidation_reason: str
    supporting_levels: list[MagnetCandidate] = Field(default_factory=list)
    status: Literal["valid", "no_magnet", "stale"]


class BiasResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    direction: Literal["bullish", "bearish", "neutral", "no_vote"]
    regime: str
    lean: str
    confidence_label: Literal["low", "medium", "high"]
    caveats: list[str] = Field(default_factory=list)
    price_zone: str


class EnrichedGexOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument: str = "NQ"
    flip: float | None = None
    call_wall: float | None = None
    put_wall: float | None = None
    next_call: float | None = None
    next_put: float | None = None
    net_gex: float | None = None
    regime: str
    primary_magnet: float | None = None
    magnet_confidence: float
    bias_direction: Literal["bullish", "bearish", "neutral", "no_vote"]
    invalidation_level: float | None = None
    invalidation_reason: str
    lean: str
    pin_risk: float | None = None
    max_pain: float | None = None
    caveats: list[str] = Field(default_factory=list)
    as_of: str
    source: str
    stale_after_seconds: int = 300


class NQQuote(BaseModel):
    model_config = ConfigDict(frozen=True)

    nq_price: float
    qqq_price: float | None = None
    ndx_price: float | None = None
    nq_qqq_factor: float | None = None
    nq_ndx_basis: float | None = None
    source: str
    timestamp: str
    stale: bool = False


class SourceHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    fresh_sec: float
    stale: bool
    latency_ms: float
    read_status: Literal["valid", "partial", "stale", "error", "degraded"]


__all__ = [
    "FADealerRisk",
    "FAFeedQuality",
    "FAHigherOrder",
    "FAOISimulator",
    "FAPinData",
    "FAProfileShape",
    "FARegime",
    "FAVolContext",
    "FlashAlphaSnapshot",
    "MagnetCandidate",
    "MagnetResult",
    "BiasResult",
    "EnrichedGexOutput",
    "NQQuote",
    "SourceHealth",
]
