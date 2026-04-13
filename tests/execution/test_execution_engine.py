"""Tests for ExecutionEngine gate checks and bracket parameter computation — EXEC-03/04/05."""
from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from deep6.execution.config import ExecutionConfig, ExecutionDecision, OrderSide
from deep6.scoring.scorer import ScorerResult, SignalTier
from deep6.engines.narrative import NarrativeType


def _make_scorer_result(
    tier: SignalTier,
    direction: int,
    score: float = 85.0,
) -> ScorerResult:
    """Helper: build a minimal ScorerResult for engine tests."""
    return ScorerResult(
        total_score=score,
        tier=tier,
        direction=direction,
        engine_agreement=0.8,
        category_count=5,
        confluence_mult=1.25,
        zone_bonus=8.0,
        narrative=NarrativeType.ABSORPTION,
        label="test",
        categories_firing=["absorption", "exhaustion", "delta", "trapped", "volume_profile"],
    )


def _make_freeze_guard(is_frozen: bool) -> MagicMock:
    """Helper: mock FreezeGuard with controlled is_frozen value."""
    fg = MagicMock()
    type(fg).is_frozen = PropertyMock(return_value=is_frozen)
    return fg


def test_frozen_returns_frozen_action():
    """When FreezeGuard is frozen, evaluate() returns action=FROZEN immediately (D-14)."""
    from deep6.execution.engine import ExecutionEngine

    engine = ExecutionEngine(
        config=ExecutionConfig(),
        freeze_guard=_make_freeze_guard(is_frozen=True),
    )
    result = _make_scorer_result(SignalTier.TYPE_A, +1)
    decision = engine.evaluate(
        result=result,
        entry_price=18500.0,
        bar_high=18510.0,
        bar_low=18490.0,
        atr=5.0,
    )
    assert decision.action == "FROZEN"
    assert "FreezeGuard" in decision.reason or "FROZEN" in decision.reason


def test_quiet_tier_returns_skip():
    """QUIET tier always returns SKIP."""
    from deep6.execution.engine import ExecutionEngine

    engine = ExecutionEngine(
        config=ExecutionConfig(),
        freeze_guard=_make_freeze_guard(is_frozen=False),
    )
    result = _make_scorer_result(SignalTier.QUIET, 0, score=10.0)
    decision = engine.evaluate(
        result=result,
        entry_price=18500.0,
        bar_high=18510.0,
        bar_low=18490.0,
        atr=5.0,
    )
    assert decision.action == "SKIP"


def test_type_c_returns_skip():
    """TYPE_C tier returns SKIP — alert only, no execution."""
    from deep6.execution.engine import ExecutionEngine

    engine = ExecutionEngine(
        config=ExecutionConfig(),
        freeze_guard=_make_freeze_guard(is_frozen=False),
    )
    result = _make_scorer_result(SignalTier.TYPE_C, +1, score=55.0)
    decision = engine.evaluate(
        result=result,
        entry_price=18500.0,
        bar_high=18510.0,
        bar_low=18490.0,
        atr=5.0,
    )
    assert decision.action == "SKIP"
    assert "TYPE_C" in decision.reason


def test_type_b_returns_wait_confirm():
    """TYPE_B returns WAIT_CONFIRM with operator confirmation reason (D-02)."""
    from deep6.execution.engine import ExecutionEngine

    engine = ExecutionEngine(
        config=ExecutionConfig(),
        freeze_guard=_make_freeze_guard(is_frozen=False),
    )
    result = _make_scorer_result(SignalTier.TYPE_B, +1, score=70.0)
    decision = engine.evaluate(
        result=result,
        entry_price=18500.0,
        bar_high=18510.0,
        bar_low=18490.0,
        atr=10.0,
    )
    assert decision.action == "WAIT_CONFIRM"
    assert "TYPE_B" in decision.reason
    assert decision.side == OrderSide.LONG
    assert decision.entry_price == 18500.0


def test_type_a_short_bracket_computation():
    """TYPE_A SHORT: stop_price = bar_high + buffer, target at 1.5x risk distance."""
    from deep6.execution.engine import ExecutionEngine

    cfg = ExecutionConfig()
    engine = ExecutionEngine(
        config=cfg,
        freeze_guard=_make_freeze_guard(is_frozen=False),
    )
    result = _make_scorer_result(SignalTier.TYPE_A, -1, score=85.0)

    bar_high = 100.0
    entry = 99.5
    tick_size = 0.25
    atr = 5.0

    decision = engine.evaluate(
        result=result,
        entry_price=entry,
        bar_high=bar_high,
        bar_low=98.0,
        atr=atr,
        tick_size=tick_size,
    )

    assert decision.action == "ENTER"
    assert decision.side == OrderSide.SHORT

    # D-04: stop = bar_high + stop_buffer_ticks*tick_size + 0.50
    expected_buffer = cfg.stop_buffer_ticks * tick_size + 0.50
    expected_stop = bar_high + expected_buffer
    assert abs(decision.stop_price - expected_stop) < 1e-9, (
        f"stop_price={decision.stop_price} != expected {expected_stop}"
    )

    # stop_distance = stop - entry
    stop_distance = expected_stop - entry

    # D-08: target = entry - 1.5 * stop_distance (for SHORT)
    expected_target = entry - stop_distance * cfg.target_rr_min
    assert abs(decision.target_price - expected_target) < 1e-9, (
        f"target_price={decision.target_price} != expected {expected_target}"
    )


def test_type_a_long_bracket_computation():
    """TYPE_A LONG: stop_price = bar_low - buffer, target at 1.5x risk distance above entry."""
    from deep6.execution.engine import ExecutionEngine

    cfg = ExecutionConfig()
    engine = ExecutionEngine(
        config=cfg,
        freeze_guard=_make_freeze_guard(is_frozen=False),
    )
    result = _make_scorer_result(SignalTier.TYPE_A, +1, score=85.0)

    bar_low = 98.0
    entry = 98.5
    tick_size = 0.25
    atr = 5.0

    decision = engine.evaluate(
        result=result,
        entry_price=entry,
        bar_high=100.0,
        bar_low=bar_low,
        atr=atr,
        tick_size=tick_size,
    )

    assert decision.action == "ENTER"
    assert decision.side == OrderSide.LONG

    expected_buffer = cfg.stop_buffer_ticks * tick_size + 0.50
    expected_stop = bar_low - expected_buffer
    assert abs(decision.stop_price - expected_stop) < 1e-9

    stop_distance = entry - expected_stop
    expected_target = entry + stop_distance * cfg.target_rr_min
    assert abs(decision.target_price - expected_target) < 1e-9


def test_stop_too_wide_returns_skip():
    """TYPE_A returns SKIP when stop_distance > max_stop_atr_mult * atr (D-05)."""
    from deep6.execution.engine import ExecutionEngine

    engine = ExecutionEngine(
        config=ExecutionConfig(),
        freeze_guard=_make_freeze_guard(is_frozen=False),
    )
    result = _make_scorer_result(SignalTier.TYPE_A, -1, score=85.0)

    # bar_high very far from entry → stop_distance > 2 * atr
    decision = engine.evaluate(
        result=result,
        entry_price=99.0,
        bar_high=120.0,    # 21+ pts above entry → stop > 2*atr=10
        bar_low=97.0,
        atr=5.0,
    )

    assert decision.action == "SKIP"
    assert "ATR" in decision.reason or "atr" in decision.reason.lower() or "2x" in decision.reason


def test_neutral_direction_returns_skip():
    """direction=0 returns SKIP regardless of tier."""
    from deep6.execution.engine import ExecutionEngine

    engine = ExecutionEngine(
        config=ExecutionConfig(),
        freeze_guard=_make_freeze_guard(is_frozen=False),
    )
    result = _make_scorer_result(SignalTier.TYPE_A, 0, score=85.0)
    decision = engine.evaluate(
        result=result,
        entry_price=18500.0,
        bar_high=18510.0,
        bar_low=18490.0,
        atr=5.0,
    )
    assert decision.action == "SKIP"
    assert "neutral" in decision.reason.lower() or "direction" in decision.reason.lower()
