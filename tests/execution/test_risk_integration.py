"""Integration: ExecutionEngine gate + RiskManager circuit breaker in sequence.

Verifies the full pre-entry check pipeline:
  1. ExecutionEngine.evaluate() produces ENTER for TYPE_A
  2. RiskManager.can_enter() is checked next
  3. After daily loss limit, RiskManager blocks even valid TYPE_A signals
"""
from __future__ import annotations

import pytest

from deep6.execution import (
    ExecutionConfig,
    ExecutionDecision,
    ExecutionEngine,
    GateResult,
    OrderSide,
    Position,
    PositionEvent,
    PositionEventType,
    PositionManager,
    RiskManager,
    RiskState,
)
from deep6.engines.narrative import NarrativeType
from deep6.scoring.scorer import ScorerResult, SignalTier
from deep6.state.connection import FreezeGuard


def _make_type_a_result(direction=1) -> ScorerResult:
    return ScorerResult(
        total_score=85.0,
        tier=SignalTier.TYPE_A,
        direction=direction,
        engine_agreement=0.85,
        category_count=3,
        confluence_mult=1.25,
        zone_bonus=0.0,
        narrative=NarrativeType.ABSORPTION,
        label="TYPE_A LONG",
        categories_firing=["absorption", "exhaustion", "delta"],
    )


def _make_engine(config=None) -> ExecutionEngine:
    cfg = config or ExecutionConfig()
    fg = FreezeGuard()
    return ExecutionEngine(cfg, fg)


class TestFullEntryPipeline:
    def test_full_entry_pipeline_ok(self):
        cfg = ExecutionConfig()
        engine = _make_engine(cfg)
        rm = RiskManager(cfg)

        result = _make_type_a_result(direction=1)
        decision = engine.evaluate(
            result=result,
            entry_price=19000.0,
            bar_high=19005.0,
            bar_low=18990.0,
            atr=20.0,
        )
        assert decision.action == "ENTER"
        gate = rm.can_enter(result)
        assert gate.allowed is True

    def test_risk_blocks_after_daily_loss(self):
        cfg = ExecutionConfig(daily_loss_limit=500.0)
        engine = _make_engine(cfg)
        rm = RiskManager(cfg)

        result = _make_type_a_result(direction=1)
        decision = engine.evaluate(
            result=result,
            entry_price=19000.0,
            bar_high=19005.0,
            bar_low=18990.0,
            atr=20.0,
        )
        assert decision.action == "ENTER"

        # Simulate hitting the daily loss limit
        rm.record_trade(-500.0)

        gate = rm.can_enter(result)
        assert gate.allowed is False
        assert "Daily loss" in gate.reason

    def test_all_symbols_importable(self):
        """Verify all 11 Phase 8 execution symbols are accessible from deep6.execution."""
        symbols = [
            ExecutionConfig,
            ExecutionDecision,
            OrderSide,
            ExecutionEngine,
            PositionManager,
            Position,
            PositionEvent,
            PositionEventType,
            RiskManager,
            RiskState,
            GateResult,
        ]
        assert len(symbols) == 11
        for sym in symbols:
            assert sym is not None
