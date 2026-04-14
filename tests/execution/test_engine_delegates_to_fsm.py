"""Tests for Phase 15-04 D-18: ExecutionEngine owns a TradeDecisionMachine and
exposes a forward ``on_bar_via_fsm`` path while preserving legacy evaluate().
"""
from __future__ import annotations

import time
import warnings
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock

import pytest

from deep6.engines.confluence_rules import ConfluenceAnnotations
from deep6.engines.level import Level, LevelKind, LevelState
from deep6.engines.narrative import NarrativeType
from deep6.engines.zone_registry import LevelBus
from deep6.execution.config import ExecutionConfig, OrderSide
from deep6.execution.engine import ExecutionEngine
from deep6.execution.trade_decision_machine import FSMConfig, TradeDecisionMachine
from deep6.scoring.scorer import ScorerResult, SignalTier
from deep6.state.eventstore_schema import InMemoryFsmWriter


def _scorer(tier=SignalTier.TYPE_A, direction=+1, score=85.0, cats=None):
    return ScorerResult(
        total_score=score,
        tier=tier,
        direction=direction,
        engine_agreement=0.8,
        category_count=len(cats or ["absorption", "delta", "trapped", "imbalance"]),
        confluence_mult=1.25,
        zone_bonus=8.0,
        narrative=NarrativeType.ABSORPTION,
        label="test",
        categories_firing=cats or ["absorption", "delta", "trapped", "imbalance"],
        meta_flags=0,
    )


def _fg(is_frozen=False):
    fg = MagicMock()
    type(fg).is_frozen = PropertyMock(return_value=is_frozen)
    return fg


def test_engine_constructs_trade_machine_when_none_provided():
    """D-18 compat path: engine builds a default FSM when trade_machine=None."""
    engine = ExecutionEngine(config=ExecutionConfig(), freeze_guard=_fg())
    assert engine.trade_machine is not None
    assert isinstance(engine.trade_machine, TradeDecisionMachine)


def test_engine_accepts_custom_trade_machine():
    """Injection path: caller supplies TradeDecisionMachine (wired to EventStore etc)."""
    writer = InMemoryFsmWriter()
    fsm = TradeDecisionMachine(
        execution_config=ExecutionConfig(),
        fsm_config=FSMConfig(),
        event_writer=writer,
    )
    engine = ExecutionEngine(config=ExecutionConfig(), freeze_guard=_fg(), trade_machine=fsm)
    assert engine.trade_machine is fsm


def test_deprecation_warning_emitted_once():
    """Compat evaluate() emits DeprecationWarning at most once per process."""
    # Reset the module-level flag for this test — we may have been called earlier.
    import deep6.execution.engine as mod
    mod._DEPRECATION_WARNED = False
    engine = ExecutionEngine(config=ExecutionConfig(), freeze_guard=_fg())
    res = _scorer(tier=SignalTier.TYPE_A, direction=+1, score=85.0)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        engine.evaluate(res, 100.0, 100.5, 99.5, atr=5.0)
        engine.evaluate(res, 100.0, 100.5, 99.5, atr=5.0)
    # Exactly one DeprecationWarning captured
    dep = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(dep) == 1, f"expected 1 DeprecationWarning, got {len(dep)}"


def test_on_bar_via_fsm_forwards_to_trade_machine():
    """D-18: forward path returns FSM OrderIntent list."""
    writer = InMemoryFsmWriter()
    fsm = TradeDecisionMachine(
        execution_config=ExecutionConfig(),
        fsm_config=FSMConfig(),
        event_writer=writer,
    )
    engine = ExecutionEngine(config=ExecutionConfig(), freeze_guard=_fg(), trade_machine=fsm)

    bus = LevelBus()
    bus.add_level(Level(
        price_top=100.5, price_bot=99.5,
        kind=LevelKind.CONFIRMED_ABSORB,
        origin_ts=time.time(), origin_bar=0, last_act_bar=0,
        score=80.0, touches=2, direction=+1, inverted=False,
        state=LevelState.CREATED,
    ))
    bar = SimpleNamespace(close=100.0, high=100.5, low=99.5, open=100.0,
                         timestamp=time.time())
    ann = ConfluenceAnnotations()
    intents = engine.on_bar_via_fsm(
        bar, bus, _scorer(score=85.0), ann, bar_index=1,
    )
    # Bar 1 should move IDLE -> WATCHING; no entry intents emitted on this bar.
    assert intents == []
    assert fsm.state.name == "WATCHING"


def test_legacy_evaluate_preserves_enter_shape():
    """Existing Phase-08 behavior: TYPE_A + clean direction -> ENTER with bracket."""
    engine = ExecutionEngine(config=ExecutionConfig(), freeze_guard=_fg())
    res = _scorer(tier=SignalTier.TYPE_A, direction=+1, score=85.0)
    decision = engine.evaluate(
        res, entry_price=100.0, bar_high=100.5, bar_low=99.0, atr=5.0,
    )
    assert decision.action == "ENTER"
    assert decision.side == OrderSide.LONG
    assert decision.entry_price == 100.0
    assert decision.signal_tier == "TYPE_A"


def test_legacy_type_b_wait_confirm_preserved():
    """D-02: TYPE_B produces WAIT_CONFIRM."""
    engine = ExecutionEngine(config=ExecutionConfig(), freeze_guard=_fg())
    res = _scorer(tier=SignalTier.TYPE_B, direction=+1, score=72.0)
    decision = engine.evaluate(res, 100.0, 100.5, 99.5, atr=5.0)
    assert decision.action == "WAIT_CONFIRM"
    assert decision.signal_tier == "TYPE_B"


def test_legacy_freeze_guard_short_circuits_before_fsm():
    """D-14: FreezeGuard frozen -> FROZEN; FSM never invoked on legacy path."""
    writer = InMemoryFsmWriter()
    fsm = TradeDecisionMachine(
        execution_config=ExecutionConfig(),
        fsm_config=FSMConfig(),
        event_writer=writer,
    )
    engine = ExecutionEngine(
        config=ExecutionConfig(), freeze_guard=_fg(is_frozen=True), trade_machine=fsm,
    )
    res = _scorer(tier=SignalTier.TYPE_A, direction=+1, score=85.0)
    decision = engine.evaluate(res, 100.0, 100.5, 99.5, atr=5.0)
    assert decision.action == "FROZEN"
    # FSM should have recorded zero transitions
    assert writer.rows == []


def test_disqualified_tier_skipped():
    """15-03 meta-tier: DISQUALIFIED (veto latch) always SKIP."""
    engine = ExecutionEngine(config=ExecutionConfig(), freeze_guard=_fg())
    res = _scorer(tier=SignalTier.DISQUALIFIED, direction=+1, score=85.0)
    decision = engine.evaluate(res, 100.0, 100.5, 99.5, atr=5.0)
    assert decision.action == "SKIP"
    assert "DISQUALIFIED" in decision.reason
