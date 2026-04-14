"""Tests for Phase 15-04 TradeState enums + transition table + guards.

Covers D-17 (7 states), D-18 (11 transitions), D-21 (4 trigger types × 17 ET-XX),
D-22/D-27 (guard_T2_ready), D-42 (E10 gating behind flag),
D-25 / §6 I9 (MFE give-back guard).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from deep6.execution.trade_state import (
    ALLOWED_TRANSITIONS,
    TRANSITION_TABLE,
    EntryTrigger,
    EntryTriggerType,
    NARRATIVE_KIND_PRIORITY,
    TradeState,
    TransitionId,
    guard_T2_ready,
    guard_T8_invalidated,
    narrative_priority,
)
from deep6.scoring.scorer import SignalTier


# ---------------------------------------------------------------------------
# State + transition table
# ---------------------------------------------------------------------------


def test_trade_state_members():
    """D-17: exactly 7 states with the expected names."""
    names = [s.name for s in TradeState]
    assert names == [
        "IDLE",
        "WATCHING",
        "ARMED",
        "TRIGGERED",
        "IN_POSITION",
        "MANAGING",
        "EXITING",
    ]
    assert len(TradeState) == 7


def test_transition_table_completeness():
    """D-18: exactly 11 (src, dst) -> TransitionId entries covering T1..T11."""
    assert len(TRANSITION_TABLE) == 11
    tids = {t.name for t in TRANSITION_TABLE.values()}
    assert tids == {f"T{i}" for i in range(1, 12)}
    # Every transition appears exactly once
    assert len({v for v in TRANSITION_TABLE.values()}) == 11


def test_allowed_transitions_derived_correctly():
    """ALLOWED_TRANSITIONS is a derived view matching TRANSITION_TABLE keys."""
    assert TradeState.WATCHING in ALLOWED_TRANSITIONS[TradeState.IDLE]
    assert TradeState.ARMED in ALLOWED_TRANSITIONS[TradeState.WATCHING]
    assert TradeState.IDLE in ALLOWED_TRANSITIONS[TradeState.WATCHING]  # T11
    # IDLE has no predecessor in the table; outgoing set exists
    assert TradeState.TRIGGERED in ALLOWED_TRANSITIONS[TradeState.ARMED]
    # Invalid transition e.g. IDLE -> TRIGGERED must NOT be allowed
    assert TradeState.TRIGGERED not in ALLOWED_TRANSITIONS[TradeState.IDLE]


# ---------------------------------------------------------------------------
# Entry trigger taxonomy (D-21)
# ---------------------------------------------------------------------------


def test_entry_trigger_taxonomy_counts():
    """D-21: 17 ET-XX triggers, each mapped to one of 4 trigger types."""
    assert len(EntryTrigger) == 17
    assert len(EntryTriggerType) == 4
    for et in EntryTrigger:
        assert isinstance(et.trigger_type, EntryTriggerType)


def test_entry_trigger_type_assignment_matches_research():
    """D-21: per-trigger classification is golden from trade_logic.md §3."""
    golden = {
        # Confirmation-bar market (Dante / Dale pattern)
        EntryTrigger.ET_01: EntryTriggerType.CONFIRMATION_BAR_MARKET,
        EntryTrigger.ET_02: EntryTriggerType.CONFIRMATION_BAR_MARKET,
        EntryTrigger.ET_08: EntryTriggerType.CONFIRMATION_BAR_MARKET,
        EntryTrigger.ET_10: EntryTriggerType.CONFIRMATION_BAR_MARKET,
        EntryTrigger.ET_11: EntryTriggerType.CONFIRMATION_BAR_MARKET,
        EntryTrigger.ET_16: EntryTriggerType.CONFIRMATION_BAR_MARKET,
        # Immediate-market — Rule 1/2 absorption at PUT/CALL wall
        EntryTrigger.ET_03: EntryTriggerType.IMMEDIATE_MARKET,
        EntryTrigger.ET_04: EntryTriggerType.IMMEDIATE_MARKET,
        # Stop-after-confirmation — breakouts
        EntryTrigger.ET_05: EntryTriggerType.STOP_AFTER_CONFIRMATION,
        EntryTrigger.ET_06: EntryTriggerType.STOP_AFTER_CONFIRMATION,
        EntryTrigger.ET_13: EntryTriggerType.STOP_AFTER_CONFIRMATION,
        EntryTrigger.ET_14: EntryTriggerType.STOP_AFTER_CONFIRMATION,
        # Limit-at-level — rotation / pin
        EntryTrigger.ET_07: EntryTriggerType.LIMIT_AT_LEVEL,
        EntryTrigger.ET_09: EntryTriggerType.LIMIT_AT_LEVEL,
        EntryTrigger.ET_12: EntryTriggerType.LIMIT_AT_LEVEL,
        EntryTrigger.ET_15: EntryTriggerType.LIMIT_AT_LEVEL,
        EntryTrigger.ET_17: EntryTriggerType.LIMIT_AT_LEVEL,
    }
    for et, expected in golden.items():
        assert et.trigger_type is expected, f"{et.name} expected {expected.name}"


# ---------------------------------------------------------------------------
# Guard T2 (WATCHING -> ARMED) — D-22 / D-27 / D-42
# ---------------------------------------------------------------------------


def _sr(tier=SignalTier.TYPE_A, direction=+1, score=85.0):
    return SimpleNamespace(tier=tier, direction=direction, total_score=score, meta_flags=0)


def _conf(regime="NEUTRAL", vetoes=None):
    return SimpleNamespace(regime=regime, vetoes=vetoes or set())


def test_guard_T2_pin_regime_blocks():
    """D-27: PIN regime blocks T2 even with a high score / TYPE_A tier."""
    assert (
        guard_T2_ready(_sr(score=95.0), _conf(regime="PIN"), min_score=70.0) is False
    )


def test_guard_T2_non_pin_allows():
    """NEUTRAL regime + score >= threshold + TYPE_A + directional -> True."""
    assert guard_T2_ready(_sr(score=85.0), _conf(regime="NEUTRAL"), min_score=70.0) is True


def test_guard_T2_veto_blocks():
    """Any veto in ConfluenceAnnotations forces T2 = False (SPOOF_DETECTED)."""
    assert (
        guard_T2_ready(
            _sr(score=95.0), _conf(regime="NEUTRAL", vetoes={"SPOOF_DETECTED"})
        )
        is False
    )


def test_guard_T2_low_score_blocks():
    """Score below min_score -> False (D-27 also references this under PIN)."""
    assert guard_T2_ready(_sr(score=65.0), _conf(), min_score=70.0) is False


def test_guard_T2_disqualified_tier_blocks():
    """DISQUALIFIED tier (scorer veto latch) always blocks T2."""
    assert guard_T2_ready(_sr(tier=SignalTier.DISQUALIFIED), _conf()) is False


def test_guard_T2_neutral_direction_blocks():
    """direction=0 always blocks T2."""
    assert guard_T2_ready(_sr(direction=0), _conf()) is False


def test_guard_T2_e10_opposite_blocks_when_enabled():
    """D-42: when E10 gating ON and E10 opposes with conf>=0.75, T2 = False."""
    assert (
        guard_T2_ready(
            _sr(direction=+1, score=85.0),
            _conf(),
            min_score=70.0,
            enable_e10_gating=True,
            e10_direction=-1,
            e10_confidence=0.80,
        )
        is False
    )


def test_guard_T2_e10_default_off():
    """D-42: with gating flag default False, same E10-opposite case -> True."""
    assert (
        guard_T2_ready(
            _sr(direction=+1, score=85.0),
            _conf(),
            min_score=70.0,
            enable_e10_gating=False,
            e10_direction=-1,
            e10_confidence=0.80,
        )
        is True
    )


# ---------------------------------------------------------------------------
# Guard T8 (MANAGING -> EXITING) — D-25 I1-I9
# ---------------------------------------------------------------------------


def _pos(direction=+1, entry=100.0, stop=99.0, mfe_R=0.0, entry_level_state="CREATED"):
    return SimpleNamespace(
        direction=direction,
        entry_price=entry,
        stop_price=stop,
        initial_stop_price=stop,
        max_favorable_R=mfe_R,
        bars_held=5,
        entry_level_state=entry_level_state,
    )


def _bar(close=100.0, high=100.5, low=99.5):
    return SimpleNamespace(close=close, high=high, low=low)


def test_guard_T8_invalidation_I9_mfe_giveback():
    """D-25 §6 I9: MFE=10R, current=4.9R => I9 fires (current <= 50% of MFE)."""
    # r_distance = 1 point; mfe=10R; current close should be <= 5R = entry+5
    pos = _pos(direction=+1, entry=100.0, stop=99.0, mfe_R=10.0)
    # current price at 104.9 => (104.9 - 100)/1 = 4.9R <= 10 * 0.5 = 5R -> I9
    fired, rid = guard_T8_invalidated(
        pos, _bar(close=104.9), r_distance=1.0
    )
    assert fired is True and rid == "I9"


def test_guard_T8_invalidation_I1_broken_level():
    """I1: entry-creating Level went BROKEN -> exit."""
    pos = _pos(entry_level_state="BROKEN")
    fired, rid = guard_T8_invalidated(pos, _bar(), r_distance=1.0)
    assert fired is True and rid == "I1"


def test_guard_T8_no_invalidation_baseline():
    """Baseline: healthy position in a quiet bar -> no invalidation fired."""
    pos = _pos(mfe_R=0.3)
    fired, rid = guard_T8_invalidated(pos, _bar(close=100.2), r_distance=1.0)
    assert fired is False and rid == ""


# ---------------------------------------------------------------------------
# Narrative priority (D-22 tie-breaker)
# ---------------------------------------------------------------------------


def test_narrative_priority_order_matches_D22():
    """D-22: ABSORB > EXHAUST > MOMENTUM > REJECTION."""
    assert narrative_priority("ABSORB") > narrative_priority("EXHAUST")
    assert narrative_priority("EXHAUST") > narrative_priority("MOMENTUM")
    assert narrative_priority("MOMENTUM") > narrative_priority("REJECTION")
    assert narrative_priority("CONFIRMED_ABSORB") == narrative_priority("ABSORB")
    assert narrative_priority("UNKNOWN_KIND") == 0
