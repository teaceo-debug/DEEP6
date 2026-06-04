"""Shared type definitions for the DEEP6 AI Chart Copilot."""

from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MADLevel:
    """A price level from the madlevels.com indicator."""
    price: float
    label: str = ""
    level_type: str = ""  # support, resistance, pivot


@dataclass(frozen=True)
class CalendarEvent:
    """An economic calendar event."""
    name: str
    time: str
    impact: str = "medium"  # high, medium, low
    actual: str = ""
    forecast: str = ""
    previous: str = ""
    nq_relevance: float = 0.5


@dataclass(frozen=True)
class NewsItem:
    """A news headline with NQ relevance scoring."""
    headline: str
    source: str
    timestamp: float = 0.0
    url: str = ""
    nq_relevance_score: float = 0.3


@dataclass(frozen=True)
class UnusualTrade:
    """An unusual options trade from flow data."""
    strike: float = 0.0
    expiry: str = ""
    trade_type: str = ""  # call, put
    premium: float = 0.0
    volume: int = 0
    oi_ratio: float = 0.0
    sentiment: str = ""  # bullish, bearish


@dataclass(frozen=True)
class SentimentSnapshot:
    """Social sentiment aggregate."""
    bullish_pct: float = 50.0
    bearish_pct: float = 50.0
    volume: int = 0
    trending_topics: tuple[str, ...] = field(default_factory=tuple)
    timestamp: float = 0.0


@dataclass(frozen=True)
class OptionsFlowSnapshot:
    """Options flow data from Massive.com."""
    unusual_trades: list[UnusualTrade] = field(default_factory=list)
    net_premium: float = 0.0
    put_call_ratio: float = 1.0
    largest_trade: UnusualTrade | None = None
    timestamp: float = 0.0


@dataclass(frozen=True)
class MarketInternals:
    """NYSE market internals (TICK, ADD, VOLD)."""
    tick_value: float = 0.0
    tick_direction: str = "neutral"
    add_value: float = 0.0
    add_direction: str = "neutral"
    vold_value: float = 0.0
    vold_ratio: float = 1.0
    timestamp: float = 0.0


@dataclass(frozen=True)
class ChartAnalysis:
    """Result of vision analysis on a chart screenshot."""
    mad_levels: tuple[MADLevel, ...] = field(default_factory=tuple)
    price_action: str = ""
    visual_patterns: tuple[str, ...] = field(default_factory=tuple)
    support_resistance: tuple[float, ...] = field(default_factory=tuple)
    confidence: float = 0.0
    raw_analysis: str = ""


@dataclass(frozen=True)
class PriceSnapshot:
    """Current price state."""
    current: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    atr: float = 0.0
    session_change_pct: float = 0.0


@dataclass(frozen=True)
class GEXSummary:
    """GEX regime summary."""
    call_wall: float = 0.0
    put_wall: float = 0.0
    gamma_flip: float = 0.0
    hvl: float = 0.0
    regime: str = "unknown"


@dataclass(frozen=True)
class KronosBias:
    """Kronos E10 directional bias."""
    direction: str = "neutral"
    confidence: float = 0.0


@dataclass(frozen=True)
class SignalSummary:
    """Summary of a signal from the 44-engine stack."""
    name: str = ""
    direction: str = ""
    strength: float = 0.0
    category: str = ""
    timestamp: float = 0.0


@dataclass(frozen=True)
class DataSourceStatus:
    """Health status of a data source."""
    source_name: str = ""
    last_update: float = 0.0
    is_stale: bool = False
    error: str | None = None


@dataclass(frozen=True)
class BudgetStatus:
    """Token budget usage snapshot."""

    used_tokens: int = 0
    budget_per_hour: int = 0
    remaining_tokens: int = 0
    calls_this_hour: int = 0
    pct_used: float = 0.0
    reset_at: datetime | None = None


@dataclass(frozen=True)
class MarketNarrative:
    """AI-generated market narrative."""
    text: str = ""
    timestamp: float = 0.0
    confidence: float = 0.0
    referenced_levels: tuple[MADLevel, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TradeCall:
    """AI-generated trade recommendation."""
    direction: str = ""  # LONG, SHORT
    entry: float = 0.0
    stop: float = 0.0
    target: float = 0.0
    confidence: float = 0.0
    mad_levels: tuple[MADLevel, ...] = field(default_factory=tuple)
    signals: tuple[str, ...] = field(default_factory=tuple)
    rationale: str = ""
    timestamp: float = 0.0


@dataclass(frozen=True)
class MarketContext:
    """Aggregated market context from all data sources."""
    signals: tuple[SignalSummary, ...] = field(default_factory=tuple)
    gex: GEXSummary | None = None
    kronos_bias: KronosBias | None = None
    internals: MarketInternals | None = None
    calendar: tuple[CalendarEvent, ...] = field(default_factory=tuple)
    news: tuple[NewsItem, ...] = field(default_factory=tuple)
    sentiment: SentimentSnapshot | None = None
    options_flow: OptionsFlowSnapshot | None = None
    price: PriceSnapshot | None = None
    source_statuses: tuple[DataSourceStatus, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class OverlayState:
    """Current state of the overlay UI."""
    narrative: MarketNarrative | None = None
    active_calls: tuple[TradeCall, ...] = field(default_factory=tuple)
    countdowns: tuple[CalendarEvent, ...] = field(default_factory=tuple)
    source_statuses: tuple[DataSourceStatus, ...] = field(default_factory=tuple)
