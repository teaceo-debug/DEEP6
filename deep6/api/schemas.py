"""Pydantic v2 models for all DEEP6 ML Backend API payloads.

SignalEventIn  — matches ScorerResult shape from deep6.scoring.scorer
TradeEventIn   — matches PositionEvent.to_dict() shape from deep6.execution.position_manager
WeightFileOut  — weight file JSON returned by GET /weights/current
"""
from __future__ import annotations

from pydantic import BaseModel


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


class WeightFileOut(BaseModel):
    """Response for GET /weights/current."""
    weights: dict[str, float]                        # signal_name → weight multiplier
    regime_adjustments: dict[str, dict[str, float]]  # regime → {signal → adj}
    deployed_at: float | None
    training_date: str | None
    n_samples: int
    wfe: float | None
    metadata: dict = {}
