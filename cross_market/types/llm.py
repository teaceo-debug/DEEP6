"""LLM input/output types for the expert assessment pipeline."""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal


class LLMInput(BaseModel):
    symbol: str
    timestamp: str
    price: float
    spread_ticks: float
    dom_snapshot: dict
    mbo_evidence: dict
    flow_state: dict
    gex_context: dict
    level_registry: dict
    context: dict
    exemplars: List[dict] = []


class LLMAssessment(BaseModel):
    primary_pattern: Literal[
        "spoof", "iceberg", "absorption", "sweep", "layering", "vacuum", "none"
    ]
    evidence: List[str]
    confidence: Literal["high", "medium", "low"]
    trader_read: str
    confirmation_criteria: str
    invalidation_criteria: str
    do_not_trade: bool = False
    do_not_trade_reason: Optional[str] = None

    @field_validator("trader_read")
    @classmethod
    def no_trade_commands(cls, v: str) -> str:
        forbidden = ["buy", "sell", "long", "short", "enter", "exit"]
        v_lower = v.lower()
        for word in forbidden:
            if word in v_lower.split():
                raise ValueError(f"trader_read must not contain '{word}' — WATCH only")
        return v
