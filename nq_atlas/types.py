from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class BiasDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class OptionsContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    strike: float
    expiry: str
    call_put: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[int] = None
    oi: Optional[int] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    iv: Optional[float] = None
    vanna: Optional[float] = None
    charm: Optional[float] = None


class ChainSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    underlying: str
    spot_price: float
    timestamp: datetime
    contracts: list[OptionsContract]


class NQLevels(BaseModel):
    model_config = ConfigDict(frozen=True)

    gex_flip: Optional[float] = None
    call_wall: Optional[float] = None
    put_wall: Optional[float] = None
    support: Optional[float] = None
    resistance: Optional[float] = None


class GEXResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    spot: float
    flip_level: Optional[float] = None
    call_wall: Optional[float] = None
    put_wall: Optional[float] = None
    net_gex: float = 0.0
    regime_sign: int = 0
    by_expiry: dict[str, float] = Field(default_factory=dict)


class VannaCharmResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    net_vanna_exposure: float = 0.0
    net_charm_exposure: float = 0.0
    dealer_hedge_direction: int = 0
    vanna_per_iv_bp: float = 0.0


class FlowResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    signed_premium_5m: float = 0.0
    signed_premium_15m: float = 0.0
    net_direction: int = 0
    z_score: float = 0.0


class BiasOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    direction: BiasDirection
    conviction: int = Field(ge=0, le=100)
    levels: NQLevels
    narrative: str
    updated_at: datetime
    degraded: bool = False
    risk_flags: list[str] = Field(default_factory=list)


__all__ = [
    "BiasDirection",
    "BiasOutput",
    "ChainSnapshot",
    "FlowResult",
    "GEXResult",
    "NQLevels",
    "OptionsContract",
    "VannaCharmResult",
]
