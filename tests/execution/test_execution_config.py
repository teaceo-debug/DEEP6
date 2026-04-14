"""Tests for ExecutionConfig and ExecutionDecision dataclasses — EXEC-01."""
from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError


def test_execution_config_defaults():
    """ExecutionConfig instantiates with correct D-01..D-22 defaults."""
    from deep6.execution.config import ExecutionConfig

    cfg = ExecutionConfig()

    # D-04/D-05: Stop placement
    assert cfg.stop_buffer_ticks == 2
    assert cfg.max_stop_atr_mult == 2.0

    # D-08: Target R:R
    assert cfg.target_rr_min == 1.5

    # D-03: Entry timing
    assert cfg.entry_delay_seconds == 3.0
    assert cfg.entry_prob_threshold == 0.55

    # D-09: Max hold
    assert cfg.max_hold_bars == 10

    # D-10: Daily loss limit
    assert cfg.daily_loss_limit == 500.0

    # D-11: Consecutive loss pause
    assert cfg.consecutive_loss_limit == 3
    assert cfg.pause_minutes == 30.0

    # D-12: Position size
    assert cfg.max_position_contracts == 3

    # D-13: Max trades
    assert cfg.max_trades_per_day == 10

    # D-18/D-19: Paper trading gate
    assert cfg.paper_trading_days == 30
    assert cfg.paper_slippage_fixed_ticks == 1
    assert cfg.paper_slippage_random_ticks == 1


def test_execution_config_is_frozen():
    """ExecutionConfig frozen=True blocks mutation (T-08-01)."""
    from deep6.execution.config import ExecutionConfig

    cfg = ExecutionConfig()
    with pytest.raises(FrozenInstanceError):
        cfg.max_stop_atr_mult = 99.0  # type: ignore[misc]


def test_execution_decision_enter():
    """ExecutionDecision can be constructed with action=ENTER and all fields."""
    from deep6.execution.config import ExecutionDecision, OrderSide

    decision = ExecutionDecision(
        action="ENTER",
        reason="TYPE_A ENTER LONG",
        side=OrderSide.LONG,
        entry_price=18500.0,
        stop_price=18480.0,
        target_price=18530.0,
        stop_ticks=80.0,
        signal_score=85.0,
        signal_tier="TYPE_A",
    )

    assert decision.action == "ENTER"
    assert decision.side == OrderSide.LONG
    assert decision.entry_price == 18500.0
    assert decision.stop_price == 18480.0
    assert decision.target_price == 18530.0


def test_order_side_values():
    """OrderSide enum has LONG and SHORT string values."""
    from deep6.execution.config import OrderSide

    assert OrderSide.LONG == "LONG"
    assert OrderSide.SHORT == "SHORT"


def test_execution_decision_defaults():
    """ExecutionDecision with minimal fields uses correct defaults."""
    from deep6.execution.config import ExecutionDecision

    decision = ExecutionDecision(action="SKIP", reason="test")
    assert decision.side is None
    assert decision.entry_price == 0.0
    assert decision.stop_price == 0.0
    assert decision.target_price == 0.0
    assert decision.stop_ticks == 0.0


def test_execution_module_exports():
    """deep6.execution exports ExecutionConfig, ExecutionDecision, OrderSide."""
    from deep6.execution import ExecutionConfig, ExecutionDecision, OrderSide  # noqa: F401
    assert True
