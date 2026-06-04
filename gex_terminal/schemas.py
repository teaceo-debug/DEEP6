"""GEX Terminal data contracts — all Pydantic schemas for the system."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from gex_terminal.schemas_institutional import InstitutionalSnapshot


class FrozenBaseModel(BaseModel):
    """Frozen base model that raises TypeError on mutation."""

    model_config = ConfigDict(frozen=True)

    def __setattr__(self, name, value):
        raise TypeError(f"{self.__class__.__name__} is frozen")


class SourceHealth(FrozenBaseModel):
    """Per-source connection and data freshness status."""

    name: str
    status: str  # "ok" | "stale" | "error" | "pending"
    last_update: Optional[float] = None  # Unix timestamp
    ttl_sec: int = 60
    error_msg: str = ""


class GEXLevels(FrozenBaseModel):
    """Key GEX price levels (all in NQ points)."""

    gamma_flip: Optional[float] = None
    call_wall: Optional[float] = None
    put_wall: Optional[float] = None
    hvl: Optional[float] = None  # High Volume Level
    zero_dte_magnet: Optional[float] = None
    expected_move_up: Optional[float] = None
    expected_move_down: Optional[float] = None


class DealerPositioning(FrozenBaseModel):
    """Dealer net exposure across all Greeks."""

    net_gex: Optional[float] = None  # Net Gamma Exposure in dollars
    net_dex: Optional[float] = None  # Net Delta Exposure
    net_vex: Optional[float] = None  # Net Vanna Exposure
    net_chex: Optional[float] = None  # Net Charm Exposure
    regime: str = "neutral"  # "positive" | "negative" | "neutral"
    hedge_direction: str = "neutral"  # "buying" | "selling" | "neutral"


class FlowSummary(FrozenBaseModel):
    """Intraday options flow summary."""

    direction: str = "neutral"  # "bullish" | "bearish" | "neutral"
    intensity: float = 0.0  # 0.0 to 1.0
    sweep_count: int = 0
    block_count: int = 0
    z_score: float = 0.0
    raw_direction: str = "neutral"


class VannaCharmState(FrozenBaseModel):
    """Dealer vanna and charm exposure."""

    vanna_exposure: Optional[float] = None  # dollars
    charm_exposure: Optional[float] = None  # dollars
    net_hedge_direction: str = "neutral"  # "tailwind" | "headwind" | "neutral"


class ZeroDTEState(FrozenBaseModel):
    """0DTE options analytics."""

    gex_pct_of_total: Optional[float] = None  # 0.0 to 1.0
    pin_risk: str = "low"  # "low" | "medium" | "high"
    pin_risk_score: Optional[int] = None  # normalized 0-100
    gamma_acceleration: Optional[float] = None


class DarkPoolData(FrozenBaseModel):
    """Dark pool levels from Unusual Whales."""

    levels_nq: list[float] = Field(default_factory=list)  # Clustered levels in NQ prices
    net_premium: Optional[float] = None
    institutional_bias: str = "neutral"  # "bullish" | "bearish" | "neutral"


class ClaudeNarrative(FrozenBaseModel):
    """Claude API interpretation of current market positioning."""

    text: str = ""  # max 240 chars
    model: str = "claude-haiku-4-5-20251001"
    timestamp: Optional[float] = None  # Unix timestamp
    cached: bool = False
    cost_usd: float = 0.0


class BiasVerdict(FrozenBaseModel):
    """Synthesized directional bias verdict."""

    direction: str = "NEUTRAL"  # "BULLISH" | "BEARISH" | "NEUTRAL"
    confidence: int = 0  # 0-100
    grade: str = "C"  # "A+" | "A" | "B" | "C" | "F"
    regime_name: str = "Unknown"


class GEXTerminalSnapshot(FrozenBaseModel):
    """Top-level immutable snapshot of all GEX analysis dimensions."""

    timestamp: float  # Unix timestamp
    bias: BiasVerdict
    levels: GEXLevels
    dealer: DealerPositioning
    flow: FlowSummary
    vanna_charm: VannaCharmState
    zero_dte: ZeroDTEState
    dark_pool: Optional[DarkPoolData] = None
    institutional: Optional[InstitutionalSnapshot] = None
    narrative: ClaudeNarrative
    sources: dict[str, SourceHealth]
    hmm_regime: str = "UNKNOWN"  # ABSORPTION_FRIENDLY | TRENDING | CHAOTIC | UNKNOWN
    conviction_grade: str = "C"
    conviction_rivers: int = 0
    direction_signal: str = "FLAT"  # LONG | SHORT | FLAT
    direction_confidence: int = 0  # 0-100 unified directional call confidence
    direction_reason: str = ""
    po3_state: str = "UNKNOWN"
    primary_magnet: Optional[float] = None  # anti-flicker magnet level
    magnet_confidence: Optional[float] = None  # 0.0–1.0 magnet score
    deep6_bias_score: Optional[int] = None  # from GET /api/v3/bias
    deep6_bias_label: Optional[str] = None  # e.g. "LEAN_BULL"
    deep6_confidence: Optional[float] = None
    cost_today_usd: float = 0.0


class GEXDoctorPayload(FrozenBaseModel):
    """Payload pushed TO DEEP6 bias engine via POST /api/gex/ingest.

    Fields match deep6.engines.bias_contracts.DomainScore exactly:
    - score: int (not float) — range -3..+3
    - max_range: int (not float) — always 3
    - updated_at: float — Unix timestamp via time.time()
    """

    domain: str = "gex_doctor"
    score: int  # -3..+3 (BULLISH 80%+ → +3, 60-80% → +2, 50-60% → +1; BEARISH mirrors; NEUTRAL → 0)
    max_range: int = 3
    available: bool = True
    stale: bool = False
    detail: dict  # raw GEX data: regime, flip, walls, confidence
    updated_at: float  # Unix timestamp: time.time()


__all__ = [
    "SourceHealth",
    "GEXLevels",
    "DealerPositioning",
    "FlowSummary",
    "VannaCharmState",
    "ZeroDTEState",
    "DarkPoolData",
    "ClaudeNarrative",
    "BiasVerdict",
    "GEXTerminalSnapshot",
    "GEXDoctorPayload",
]
