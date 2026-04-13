"""Tests for Position, PositionEvent, and PositionManager (Plan 08-02)."""
from __future__ import annotations

import pytest

from deep6.execution.config import ExecutionConfig, ExecutionDecision, OrderSide
from deep6.execution.position_manager import (
    NQ_DOLLARS_PER_POINT,
    Position,
    PositionEvent,
    PositionEventType,
    PositionManager,
)
from deep6.engines.narrative import NarrativeType
from deep6.scoring.scorer import ScorerResult, SignalTier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scorer_result(
    tier=SignalTier.TYPE_A,
    direction=1,
    categories=None,
    score=80.0,
) -> ScorerResult:
    return ScorerResult(
        total_score=score,
        tier=tier,
        direction=direction,
        engine_agreement=0.8,
        category_count=3,
        confluence_mult=1.25,
        zone_bonus=0.0,
        narrative=NarrativeType.ABSORPTION,
        label="TYPE_A LONG",
        categories_firing=categories or [],
    )


def _make_long_decision(
    entry=19000.0, stop=18990.0, target=19020.0
) -> ExecutionDecision:
    return ExecutionDecision(
        action="ENTER",
        reason="TYPE_A ENTER LONG",
        side=OrderSide.LONG,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        stop_ticks=40.0,
        signal_score=80.0,
        signal_tier="TYPE_A",
    )


def _make_short_decision(
    entry=19000.0, stop=19010.0, target=18980.0
) -> ExecutionDecision:
    return ExecutionDecision(
        action="ENTER",
        reason="TYPE_A ENTER SHORT",
        side=OrderSide.SHORT,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        stop_ticks=40.0,
        signal_score=80.0,
        signal_tier="TYPE_A",
    )


def _make_manager(config=None):
    cfg = config or ExecutionConfig()
    events = []
    pm = PositionManager(cfg, on_event=events.append)
    return pm, events


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------

class TestPositionEventToDict:
    def test_to_dict_serializable(self):
        ev = PositionEvent(
            event_type=PositionEventType.ENTRY,
            position_id="abc",
            side=OrderSide.LONG,
            entry_price=19000.0,
            exit_price=0.0,
            pnl=0.0,
            bars_held=0,
            ts=1000000.0,
            signal_tier="TYPE_A",
        )
        d = ev.to_dict()
        for v in d.values():
            assert not hasattr(v, "value"), f"Enum leaked into to_dict: {v}"
        assert d["event_type"] == "ENTRY"
        assert d["side"] == "LONG"

    def test_position_event_type_values_are_strings(self):
        for pet in PositionEventType:
            assert isinstance(pet.value, str)


class TestPositionUpdatePnl:
    def test_update_pnl_long(self):
        pos = Position(
            id="x",
            side=OrderSide.LONG,
            entry_price=100.0,
            stop_price=99.0,
            target_price=102.0,
            contracts=1,
            signal_score=70.0,
            signal_tier="TYPE_A",
        )
        pos.update_pnl(101.0)
        assert pos.unrealized_pnl == pytest.approx(50.0)

    def test_update_pnl_short(self):
        pos = Position(
            id="y",
            side=OrderSide.SHORT,
            entry_price=100.0,
            stop_price=101.0,
            target_price=98.0,
            contracts=1,
            signal_score=70.0,
            signal_tier="TYPE_A",
        )
        pos.update_pnl(99.0)
        assert pos.unrealized_pnl == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# PositionManager lifecycle tests
# ---------------------------------------------------------------------------

class TestOpenPosition:
    def test_open_position_emits_entry_event(self):
        pm, events = _make_manager()
        pm.open_position(_make_long_decision())
        assert len(events) == 1
        assert events[0].event_type == PositionEventType.ENTRY

    def test_max_position_raises_value_error(self):
        cfg = ExecutionConfig(max_position_contracts=1)
        pm, _ = _make_manager(cfg)
        pm.open_position(_make_long_decision())
        with pytest.raises(ValueError, match="would exceed max"):
            pm.open_position(_make_long_decision())

    def test_positions_property_is_copy(self):
        pm, _ = _make_manager()
        pm.open_position(_make_long_decision())
        positions = pm.positions
        positions.clear()
        assert pm.position_count == 1


class TestOnBar:
    def test_stop_hit_long_closes_position(self):
        pm, events = _make_manager()
        pm.open_position(_make_long_decision(entry=19000.0, stop=18990.0, target=19020.0))
        result = _make_scorer_result()
        # bar_low <= stop_price
        fired = pm.on_bar(bar_close=18985.0, bar_high=19000.0, bar_low=18988.0, result=result)
        stop_events = [e for e in fired if e.event_type == PositionEventType.STOP_HIT]
        assert len(stop_events) == 1
        assert pm.position_count == 0
        # P&L should be negative (stop hit below entry for LONG)
        assert stop_events[0].pnl < 0

    def test_target_hit_long_closes_position(self):
        pm, events = _make_manager()
        pm.open_position(_make_long_decision(entry=19000.0, stop=18990.0, target=19020.0))
        result = _make_scorer_result()
        # bar_high >= target_price
        fired = pm.on_bar(bar_close=19015.0, bar_high=19025.0, bar_low=18999.0, result=result)
        target_events = [e for e in fired if e.event_type == PositionEventType.TARGET_HIT]
        assert len(target_events) == 1
        assert pm.position_count == 0
        assert target_events[0].pnl > 0

    def test_timeout_exit_after_max_bars(self):
        cfg = ExecutionConfig(max_hold_bars=3)
        pm, events = _make_manager(cfg)
        pm.open_position(_make_long_decision(entry=19000.0, stop=18900.0, target=19100.0))
        result = _make_scorer_result()
        # Run 3 bars with no stop/target hit
        for i in range(3):
            fired = pm.on_bar(19005.0, 19010.0, 19001.0, result)
        timeout_events = [e for e in fired if e.event_type == PositionEventType.TIMEOUT_EXIT]
        assert len(timeout_events) == 1
        assert pm.position_count == 0

    def test_breakeven_after_3_bars_absorption(self):
        pm, events = _make_manager()
        dec = _make_long_decision(entry=19000.0, stop=18990.0, target=19050.0)
        pos = pm.open_position(dec)
        assert pos.entry_price == 19000.0
        result_with_absorption = _make_scorer_result(categories=["absorption"])
        # Run 3 bars with absorption
        for _ in range(3):
            pm.on_bar(19005.0, 19010.0, 18995.0, result_with_absorption)
        # After 3 bars with absorption, stop should move to entry_price
        # Position may still be open (no stop/target hit in these prices)
        if pm.position_count > 0:
            pos_list = pm.positions
            assert pos_list[0].is_breakeven
            assert pos_list[0].stop_price == pos_list[0].entry_price
        # Check BREAKEVEN_MOVE event fired
        breakeven_events = [e for e in events if e.event_type == PositionEventType.BREAKEVEN_MOVE]
        assert len(breakeven_events) >= 1

    def test_breakeven_not_triggered_without_absorption(self):
        pm, events = _make_manager()
        pm.open_position(_make_long_decision(entry=19000.0, stop=18990.0, target=19050.0))
        result_no_absorption = _make_scorer_result(categories=["imbalance"])
        for _ in range(5):
            pm.on_bar(19005.0, 19010.0, 18995.0, result_no_absorption)
        breakeven_events = [e for e in events if e.event_type == PositionEventType.BREAKEVEN_MOVE]
        assert len(breakeven_events) == 0


class TestClosePosition:
    def test_manual_exit_emits_event(self):
        pm, events = _make_manager()
        pos = pm.open_position(_make_long_decision())
        ev = pm.close_position(pos.id, exit_price=19015.0, reason="Test manual close")
        assert ev is not None
        assert ev.event_type == PositionEventType.MANUAL_EXIT
        assert pm.position_count == 0

    def test_close_nonexistent_position_returns_none(self):
        pm, _ = _make_manager()
        result = pm.close_position("nonexistent-id", 19000.0)
        assert result is None
