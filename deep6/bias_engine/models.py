"""Pydantic / dataclass schemas for the DEEP6 Daily Bias Engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PO3Phase(str, Enum):
    ACCUMULATION = "ACCUMULATION"   # 18:00–00:00 ET
    MANIPULATION = "MANIPULATION"   # 00:00–07:00 ET  (London sweep)
    DISTRIBUTION = "DISTRIBUTION"   # 07:00–13:00 ET  (NY AM — trade here)
    BETWEEN      = "BETWEEN"        # 13:00–18:00 ET  (afternoon/settlement)


class BiasDirection(str, Enum):
    STRONG_BULL = "STRONG_BULL"   # 5-6 pts
    BULL        = "BULL"          # 3-4 pts
    NEUTRAL     = "NEUTRAL"       # tied
    BEAR        = "BEAR"          # 3-4 pts
    STRONG_BEAR = "STRONG_BEAR"   # 5-6 pts


class JudasStatus(str, Enum):
    NONE            = "NONE"
    SWEPT_LO        = "SWEPT_LO"         # Asia low swept, Judas Bull pending
    SWEPT_HI        = "SWEPT_HI"         # Asia high swept, Judas Bear pending
    BULL_CONFIRMED  = "BULL_CONFIRMED"   # Sweep + close above Asia EQ
    BEAR_CONFIRMED  = "BEAR_CONFIRMED"   # Sweep + close below Asia EQ


@dataclass
class PO3BiasState:
    """Full PO3 bias state at a point in time."""
    bull_pts: int = 0
    bear_pts: int = 0
    direction: BiasDirection = BiasDirection.NEUTRAL
    phase: PO3Phase = PO3Phase.BETWEEN
    above_midnight_open: Optional[bool] = None
    above_weekly_open: Optional[bool] = None
    in_discount: Optional[bool] = None      # True = discount zone (bullish)
    judas_status: JudasStatus = JudasStatus.NONE
    midnight_open: Optional[float] = None
    weekly_open: Optional[float] = None
    asia_high: Optional[float] = None
    asia_low: Optional[float] = None
    asia_eq: Optional[float] = None
    pd_high: Optional[float] = None
    pd_low: Optional[float] = None
    pd_eq: Optional[float] = None
    current_close: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


class TradingViewWebhookPayload(BaseModel):
    """JSON payload from Pine Script via TradingView webhook alert."""
    ticker: str = "NQ1!"
    close: float
    bull_pts: int = Field(ge=0, le=6)
    bear_pts: int = Field(ge=0, le=6)
    bias: str                             # "BULLISH" | "BEARISH" | "NEUTRAL"
    phase: str                            # "Accumulation" | "Manipulation" | "Distribution"
    judas_bull: bool = False
    judas_bear: bool = False
    swept_lo: bool = False
    swept_hi: bool = False
    above_mo: Optional[bool] = None
    above_wo: Optional[bool] = None
    in_discount: Optional[bool] = None
    mo_px: Optional[float] = None
    wo_px: Optional[float] = None
    pd_h: Optional[float] = None
    pd_l: Optional[float] = None
    asia_hi: Optional[float] = None
    asia_lo: Optional[float] = None
    event: str = "bias_update"            # "bias_change" | "judas_confirmed" | "session_start"
    timestamp: Optional[float] = None    # TV timenow in ms


class NewsItem(BaseModel):
    headline: str
    source: str
    sentiment: float                      # -1.0 to +1.0
    sentiment_label: str                  # "positive" | "negative" | "neutral"
    published_at: datetime
    url: str = ""


class MacroEvent(BaseModel):
    name: str
    release_time: datetime
    impact: str                           # "HIGH" | "MEDIUM" | "LOW"
    country: str = "US"
    forecast: Optional[float] = None
    previous: Optional[float] = None
    actual: Optional[float] = None
    minutes_until: Optional[int] = None  # Computed at fetch time


class DailyBiasScore(BaseModel):
    """Final synthesized daily bias — unified output of the full pipeline."""
    direction: BiasDirection
    score: float                          # -100 to +100 (negative = bearish)
    confidence: float                     # 0.0 to 1.0

    # Component breakdown
    technical_score: float = 0.0          # PO3 score normalized -100 to +100
    news_score: float = 0.0               # News sentiment -100 to +100
    ai_score: float = 0.0                 # Claude synthesis -100 to +100

    # Raw inputs
    po3_state: Optional[dict] = None
    news_items: list[NewsItem] = Field(default_factory=list)
    macro_events: list[MacroEvent] = Field(default_factory=list)

    # AI output
    ai_reasoning: str = ""
    ai_key_triggers: str = ""

    # Warnings
    macro_blackout: bool = False
    divergence_warning: Optional[str] = None

    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    source: str = "deep6_bias_engine"
