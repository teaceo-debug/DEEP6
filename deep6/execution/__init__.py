"""deep6.execution — auto-execution and risk layer (Phase 8).

Exports the core contracts consumed by PaperTrader, RiskManager, PositionManager.
"""
from deep6.execution.config import ExecutionConfig, ExecutionDecision, OrderSide

__all__ = ["ExecutionConfig", "ExecutionDecision", "OrderSide"]
