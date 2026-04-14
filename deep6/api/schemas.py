"""Pydantic v2 models for all DEEP6 ML Backend API payloads.

SignalEventIn  — matches ScorerResult shape from deep6.scoring.scorer
TradeEventIn   — matches PositionEvent.to_dict() shape from deep6.execution.position_manager
WeightFileOut  — weight file JSON returned by GET /weights/current

Phase 11-01 additions:
BarLevelOut        — bid/ask volume at one tick level
BarEventIn         — full FootprintBar wire shape (ingest + WS push)
ReplayBarOut       — same shape, returned by replay endpoints
LiveBarMessage     — WS multiplexed bar message (type="bar")
LiveSignalMessage  — WS multiplexed signal message (type="signal")
LiveScoreMessage   — WS multiplexed confluence score message (type="score")
LiveStatusMessage  — WS multiplexed connection/status message (type="status")
LiveTapeMessage    — WS multiplexed T&S trade print message (type="tape")
LiveMessage        — discriminated Union of the five live message types
"""
from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, Field


class SignalEventIn(BaseModel):
    """Payload for POST /events/signal.

    Mirrors ScorerResult fields plus session/context metadata.
    """
    ts: float                        # bar close epoch timestamp
    bar_index_in_session: int        # 0 = first bar at 9:30 RTH
    total_score: float               # 0-100
    tier: str                        # "TYPE_A", "TYPE_B", "TYPE_C", "QUIET"
    direction: int                   # +1 bull, -1 bear, 0 neutral
    engine_agreement: float          # 0-1 ratio of engines agreeing
    category_count: int
    categories_firing: list[str]
    gex_regime: str = "NEUTRAL"      # GexRegime.value
    kronos_bias: float = 0.0         # E10 score 0-100 (0.0 if unavailable)


class TradeEventIn(BaseModel):
    """Payload for POST /events/trade.

    Mirrors PositionEvent.to_dict() shape.
    """
    ts: float
    position_id: str
    event_type: str                  # PositionEventType.value e.g. "STOP_HIT"
    side: str                        # "LONG" or "SHORT"
    entry_price: float
    exit_price: float
    pnl: float
    bars_held: int
    signal_tier: str
    signal_score: float
    regime_label: str = "UNKNOWN"    # HMM regime at time of trade (D-23)


class WeightFileOut(BaseModel):
    """Response for GET /weights/current."""
    weights: dict[str, float]                        # signal_name → weight multiplier
    regime_adjustments: dict[str, dict[str, float]]  # regime → {signal → adj}
    deployed_at: float | None
    training_date: str | None
    n_samples: int
    wfe: float | None
    metadata: dict = {}


# ---------------------------------------------------------------------------
# Phase 11-01: Bar + Live WebSocket message models
# ---------------------------------------------------------------------------

class BarLevelOut(BaseModel):
    """Bid and ask volume at a single price level (one tick width)."""
    bid_vol: int
    ask_vol: int


class BarEventIn(BaseModel):
    """Wire shape for a closed FootprintBar.

    Used both for HTTP ingest (POST /events/bar) and WebSocket push
    (LiveBarMessage.bar). Tick keys in ``levels`` are strings so the JSON
    round-trip is lossless; clients convert tick → price via tick_int * 0.25
    (D-11: backend pushes complete FootprintBar objects on bar close).
    """
    session_id: str
    bar_index: int
    ts: float
    open: float
    high: float
    low: float
    close: float
    total_vol: int
    bar_delta: int
    cvd: int
    poc_price: float
    bar_range: float
    running_delta: int = 0
    max_delta: int = 0
    min_delta: int = 0
    levels: dict[str, BarLevelOut] = Field(default_factory=dict)  # key = str(tick_int)


class ReplayBarOut(BarEventIn):
    """Same shape as BarEventIn — returned by the replay endpoints.

    Separate class so the API router can annotate response types distinctly
    while sharing the validation logic.
    """
    pass


# --- Live WebSocket discriminated union (D-10: single multiplexed WS) ------

class LiveBarMessage(BaseModel):
    """Backend → client: a closed FootprintBar on bar close."""
    type: Literal["bar"] = "bar"
    session_id: str
    bar_index: int
    bar: BarEventIn


class LiveSignalMessage(BaseModel):
    """Backend → client: a signal event from the confluence scorer."""
    type: Literal["signal"] = "signal"
    event: SignalEventIn
    narrative: str = ""    # human label e.g. "ABSORBED @VAH"


class LiveScoreMessage(BaseModel):
    """Backend → client: confluence score update after each bar close."""
    type: Literal["score"] = "score"
    total_score: float
    tier: str
    direction: int
    categories_firing: list[str]
    category_scores: dict[str, float] = Field(default_factory=dict)  # 8 buckets
    kronos_bias: float = 0.0          # E10 score 0-100
    kronos_direction: str = "NEUTRAL"  # "LONG" | "SHORT" | "NEUTRAL"
    gex_regime: str = "NEUTRAL"


class LiveStatusMessage(BaseModel):
    """Backend → client: connection / P&L / circuit-breaker state.

    Sent immediately on WS connect and whenever connection state changes.
    Per D-05: minimal status widget — live P&L total + circuit breaker state.

    Extended fields (all optional with safe defaults for backward-compat):
    - session_start_ts: epoch when the current trading session started
    - bars_received:    authoritative backend bar count
    - signals_fired:    authoritative backend signal count
    - last_signal_tier: most recent signal tier ("TYPE_A" | "TYPE_B" | "TYPE_C" | "")
    - uptime_seconds:   backend process uptime in seconds
    - active_clients:   number of WebSocket clients currently connected
    """
    type: Literal["status"] = "status"
    connected: bool
    pnl: float = 0.0
    circuit_breaker_active: bool = False
    feed_stale: bool = False        # True when no update in > 10 s
    ts: float
    # --- observability fields (Phase 11.3-r3) ---
    session_start_ts: float = 0.0   # epoch when session started
    bars_received: int = 0          # backend bar count
    signals_fired: int = 0          # backend signal count
    last_signal_tier: str = ""      # "" | "TYPE_A" | "TYPE_B" | "TYPE_C"
    uptime_seconds: int = 0         # backend process uptime
    active_clients: int = 0         # connected WS clients


class TapeEventIn(BaseModel):
    """A single trade print (time & sales entry)."""
    ts: float                                                  # epoch seconds
    price: float
    size: int
    side: Literal["BID", "ASK"]                               # who hit: BID=seller hit bid, ASK=buyer lifted ask
    marker: Literal["", "SWEEP", "ICEBERG", "KRONOS"] = ""   # optional annotation


class LiveTapeMessage(BaseModel):
    """Backend → client: single trade print for T&S feed."""
    type: Literal["tape"] = "tape"
    event: TapeEventIn


#: Discriminated union of all live message types.
#: Client dispatches on the ``type`` field.
LiveMessage = Union[LiveBarMessage, LiveSignalMessage, LiveScoreMessage, LiveStatusMessage, LiveTapeMessage]
