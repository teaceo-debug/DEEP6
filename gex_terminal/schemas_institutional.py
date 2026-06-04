"""Institutional intelligence data models for dark pool ultra system."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class InstitutionalHolder(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    shares: int = 0
    value_usd: float = 0.0
    change_shares: int = 0
    pct_of_float: float = 0.0


class Filing13F(BaseModel):
    model_config = ConfigDict(frozen=True)

    institution_name: str
    filing_date: str = ""
    total_value_usd: float = 0.0
    action: str = ""


class FloorTrade(BaseModel):
    model_config = ConfigDict(frozen=True)

    price: float
    size: int
    premium: float = 0.0
    timestamp: str = ""
    side: str = ""


class DarkPoolSession(BaseModel):
    model_config = ConfigDict(frozen=True)

    print_count: int = 0
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    net_premium: float = 0.0
    bias: str = "NEUTRAL"
    accumulation_pct: float = 0.0


class MarketTide(BaseModel):
    model_config = ConfigDict(frozen=True)

    call_premium: float = 0.0
    put_premium: float = 0.0
    direction: str = "MIXED"
    strength_pct: float = 0.0


class DarkPoolLevel(BaseModel):
    model_config = ConfigDict(frozen=True)

    price_nq: float
    total_premium: float = 0.0
    print_count: int = 0
    volume: float = 0.0
    multiplier: float = 1.0
    std_dev: float = 0.0
    level_type: str = "NEUTRAL"


class SignalGridRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal_id: str
    label: str
    state: str = "NEUTRAL"
    score: int = 0
    stale: bool = False


class SignalGrid(BaseModel):
    model_config = ConfigDict(frozen=True)

    rows: list[SignalGridRow] = Field(default_factory=list)
    confluence_buy: int = 0
    confluence_sell: int = 0
    total_signals: int = 0


class SwingEquilibrium(BaseModel):
    model_config = ConfigDict(frozen=True)

    price_nq: float = 0.0
    period_days: int = 4
    confidence: float = 0.0


class InstitutionalSnapshot(BaseModel):
    """Top-level institutional intelligence snapshot."""

    model_config = ConfigDict(frozen=True)

    timestamp: float
    inst_flow_direction: str = "NEUTRAL"
    top_holders: list[InstitutionalHolder] = Field(default_factory=list)
    recent_filings: list[Filing13F] = Field(default_factory=list)
    floor_trades: list[FloorTrade] = Field(default_factory=list)
    dark_pool_session: DarkPoolSession = Field(default_factory=DarkPoolSession)
    market_tide: MarketTide = Field(default_factory=MarketTide)
    signal_grid: SignalGrid = Field(default_factory=SignalGrid)
    dp_levels: list[DarkPoolLevel] = Field(default_factory=list)
    swing_equilibrium: SwingEquilibrium = Field(default_factory=SwingEquilibrium)
    dp_bias: str = "NEUTRAL"


__all__ = [
    "InstitutionalHolder",
    "Filing13F",
    "FloorTrade",
    "DarkPoolSession",
    "MarketTide",
    "DarkPoolLevel",
    "SignalGridRow",
    "SignalGrid",
    "SwingEquilibrium",
    "InstitutionalSnapshot",
]
