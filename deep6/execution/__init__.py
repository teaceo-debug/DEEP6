"""deep6.execution — auto-execution and risk layer (Phase 8).

Public API:
  ExecutionConfig   — all thresholds in one frozen dataclass
  ExecutionDecision — gate output with bracket params
  OrderSide         — LONG/SHORT enum
  ExecutionEngine   — evaluates ScorerResult → ExecutionDecision
  PositionManager   — tracks open positions, emits PositionEvents
  Position          — single position state
  PositionEvent     — lifecycle event (entry/stop/target/timeout/manual/breakeven)
  PositionEventType — event type enum
  RiskManager       — circuit breakers and GEX regime gate
  RiskState         — mutable intraday risk accumulator
  GateResult        — namedtuple(allowed, reason) from RiskManager.can_enter()
"""
from deep6.execution.config import ExecutionConfig, ExecutionDecision, OrderSide
from deep6.execution.engine import ExecutionEngine
from deep6.execution.position_manager import (
    PositionManager,
    Position,
    PositionEvent,
    PositionEventType,
)
from deep6.execution.risk_manager import RiskManager, RiskState, GateResult

__all__ = [
    "ExecutionConfig",
    "ExecutionDecision",
    "OrderSide",
    "ExecutionEngine",
    "PositionManager",
    "Position",
    "PositionEvent",
    "PositionEventType",
    "RiskManager",
    "RiskState",
    "GateResult",
]
