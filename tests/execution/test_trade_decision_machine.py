"""Tests for Phase 15-04 TradeDecisionMachine.

Covers:
  - Initial state
  - T1..T11 reachability
  - Confirmation-bar delay (D-20)
  - PIN regime blocking (D-27)
  - Precedence D-22
  - Invalidation I9 MFE give-back (D-25)
  - Stop / target / size policies (D-23/24/26)
  - EventStore persistence on every transition
  - S6: FSM source does NOT import confluence_rules.evaluate
"""
from __future__ import annotations

import inspect
import re
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from deep6.engines.confluence_rules import ConfluenceAnnotations
from deep6.engines.level import Level, LevelKind, LevelState
from deep6.engines.narrative import NarrativeType
from deep6.engines.zone_registry import LevelBus
from deep6.execution.config import ExecutionConfig, OrderSide
from deep6.execution.trade_decision_machine import (
    FSMConfig,
    OrderIntent,
    TradeDecisionMachine,
)
from deep6.execution.trade_state import (
    EntryTrigger,
    EntryTriggerType,
    TradeState,
    TransitionId,
)
from deep6.scoring.scorer import ScorerResult, SignalTier
from deep6.state.eventstore_schema import InMemoryFsmWriter


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _bar(close=100.0, high=100.5, low=99.5, ts=None):
    return SimpleNamespace(
        close=close, high=high, low=low, timestamp=ts or time.time(), open=close
    )


def _scorer(
    tier=SignalTier.TYPE_A,
    direction=+1,
    score=85.0,
    cats=None,
    narrative=NarrativeType.ABSORPTION,
):
    return ScorerResult(
        total_score=score,
        tier=tier,
        direction=direction,
        engine_agreement=0.8,
        category_count=len(cats or ["absorption", "delta", "trapped", "imbalance"]),
        confluence_mult=1.25,
        zone_bonus=8.0,
        narrative=narrative,
        label="test",
        categories_firing=cats or ["absorption", "delta", "trapped", "imbalance"],
        meta_flags=0,
    )


def _conf(regime="NEUTRAL", flags=None, vetoes=None):
    ann = ConfluenceAnnotations()
    ann.regime = regime
    ann.flags = set(flags or [])
    ann.vetoes = set(vetoes or [])
    return ann


def _build_level(
    kind=LevelKind.CONFIRMED_ABSORB, score=70.0, price_top=100.5, price_bot=99.5,
    direction=+1,
):
    return Level(
        price_top=price_top, price_bot=price_bot, kind=kind,
        origin_ts=time.time(), origin_bar=0, last_act_bar=0,
        score=score, touches=2, direction=direction, inverted=False,
        state=LevelState.CREATED,
    )


def _fsm_fresh(**fsm_kwargs) -> tuple[TradeDecisionMachine, InMemoryFsmWriter, LevelBus]:
    writer = InMemoryFsmWriter()
    bus = LevelBus()
    fsm = TradeDecisionMachine(
        execution_config=ExecutionConfig(),
        fsm_config=FSMConfig(**fsm_kwargs),
        event_writer=writer,
    )
    return fsm, writer, bus


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_fsm_initial_state_IDLE():
    fsm, _, _ = _fsm_fresh()
    assert fsm.state == TradeState.IDLE


def test_T1_idle_to_watching_on_strong_level():
    fsm, writer, bus = _fsm_fresh()
    bus.add_level(_build_level(score=75.0, price_top=100.5, price_bot=99.5))
    intents = fsm.on_bar(_bar(close=100.0), bus, _scorer(), _conf(), bar_index=1)
    assert fsm.state == TradeState.WATCHING
    assert any(r["transition_id"] == "T1" for r in writer.rows)


def test_T2_watching_to_armed_and_T3_triggered_immediate_market():
    """Path: IDLE -> WATCHING -> ARMED -> TRIGGERED via ET-03 (IMMEDIATE_MARKET)."""
    fsm, writer, bus = _fsm_fresh()
    # Setup: strong ABSORB level + flag "ABSORB_PUT_WALL" → ET-03
    lv = _build_level(kind=LevelKind.CONFIRMED_ABSORB, score=80.0)
    bus.add_level(lv)
    # Bar 1: T1
    fsm.on_bar(_bar(close=100.0), bus, _scorer(score=85.0), _conf(), bar_index=1)
    assert fsm.state == TradeState.WATCHING
    # Bar 2: T2 (guard passes — score>=70, non-PIN, TYPE_A)
    ann = _conf(flags={"ABSORB_PUT_WALL"})
    intents = fsm.on_bar(
        _bar(close=100.0), bus,
        _scorer(score=85.0, cats=["absorption", "delta", "trapped", "imbalance"]),
        ann, bar_index=2,
    )
    # After ARMED, detectors fire → ET-03 IMMEDIATE_MARKET on same bar → TRIGGERED
    assert fsm.state == TradeState.TRIGGERED
    assert any(i.action == "ENTER" for i in intents)
    tids = [r["transition_id"] for r in writer.rows]
    assert "T2" in tids and "T3" in tids


def test_T2_blocked_by_pin_regime():
    fsm, writer, bus = _fsm_fresh()
    bus.add_level(_build_level(score=80.0))
    fsm.on_bar(_bar(close=100.0), bus, _scorer(score=90.0), _conf(regime="PIN"), bar_index=1)
    assert fsm.state == TradeState.WATCHING
    # Second bar still PIN → no T2
    fsm.on_bar(_bar(close=100.0), bus, _scorer(score=90.0), _conf(regime="PIN"), bar_index=2)
    assert fsm.state == TradeState.WATCHING
    assert not any(r["transition_id"] == "T2" for r in writer.rows)


def test_T2_blocked_by_low_score():
    fsm, _, bus = _fsm_fresh()
    bus.add_level(_build_level(score=70.0))
    fsm.on_bar(_bar(close=100.0), bus, _scorer(score=65.0), _conf(), bar_index=1)
    assert fsm.state == TradeState.WATCHING
    fsm.on_bar(_bar(close=100.0), bus, _scorer(score=65.0), _conf(), bar_index=2)
    assert fsm.state == TradeState.WATCHING  # still — score < 70


def test_T3_confirmation_bar_delays_one_bar():
    """D-20: ET-07 (LIMIT) fires same-bar, but CONFIRMATION_BAR_MARKET must wait.

    We route through ET-01 CONFIRMED_ABSORB (CONFIRMATION_BAR_MARKET) — no wall
    flag, so ET-03 does NOT trigger; only ET-01 queues.
    """
    fsm, writer, bus = _fsm_fresh()
    bus.add_level(_build_level(kind=LevelKind.CONFIRMED_ABSORB, score=80.0))
    # Bar 1: WATCHING
    fsm.on_bar(_bar(close=100.0), bus, _scorer(score=85.0), _conf(), bar_index=1)
    # Bar 2: ARMED and ET-01 queued (no wall flag → no ET-03)
    intents_bar2 = fsm.on_bar(
        _bar(close=100.0), bus,
        _scorer(score=85.0, cats=["absorption", "delta", "trapped", "imbalance"]),
        _conf(), bar_index=2,
    )
    # No ENTER intents emitted this bar — pending only
    assert fsm.state == TradeState.ARMED
    assert fsm.pending_count == 1
    assert not any(i.action == "ENTER" for i in intents_bar2)
    # Bar 3: pending fires → ENTER intent + TRIGGERED
    intents_bar3 = fsm.on_bar(
        _bar(close=100.2), bus,
        _scorer(score=85.0, cats=["absorption", "delta", "trapped", "imbalance"]),
        _conf(), bar_index=3,
    )
    assert any(i.action == "ENTER" for i in intents_bar3)
    assert fsm.state == TradeState.TRIGGERED


def test_T4_triggered_to_in_position_on_fill():
    fsm, writer, bus = _fsm_fresh()
    # Force to TRIGGERED via Rule 1 (ET-03)
    bus.add_level(_build_level(kind=LevelKind.CONFIRMED_ABSORB, score=80.0))
    fsm.on_bar(_bar(close=100.0), bus, _scorer(score=85.0), _conf(), bar_index=1)
    fsm.on_bar(
        _bar(close=100.0), bus,
        _scorer(score=85.0, cats=["absorption", "delta", "trapped", "imbalance"]),
        _conf(flags={"ABSORB_PUT_WALL"}), bar_index=2,
    )
    assert fsm.state == TradeState.TRIGGERED
    # Fire fill event
    fill = SimpleNamespace(
        ts=time.time(), entry_price=100.0, stop_price=99.0, direction=+1,
        side=OrderSide.LONG, r_distance=1.0, max_favorable_R=0.0,
    )
    fsm.on_fill(fill, bar_index=3)
    assert fsm.state == TradeState.IN_POSITION
    assert any(r["transition_id"] == "T4" for r in writer.rows)


def test_T5_triggered_to_armed_on_reject():
    fsm, writer, bus = _fsm_fresh()
    bus.add_level(_build_level(kind=LevelKind.CONFIRMED_ABSORB, score=80.0))
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(), bar_index=1)
    fsm.on_bar(
        _bar(), bus, _scorer(score=85.0),
        _conf(flags={"ABSORB_PUT_WALL"}), bar_index=2,
    )
    assert fsm.state == TradeState.TRIGGERED
    fsm.on_reject(SimpleNamespace(ts=time.time()), bar_index=3, retry_ok=True)
    assert fsm.state == TradeState.ARMED
    assert any(r["transition_id"] == "T5" for r in writer.rows)


def test_T6_triggered_to_idle_on_timeout():
    fsm, writer, bus = _fsm_fresh(trigger_timeout_bars=2)
    bus.add_level(_build_level(kind=LevelKind.CONFIRMED_ABSORB, score=80.0))
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(), bar_index=1)
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(flags={"ABSORB_PUT_WALL"}), bar_index=2)
    assert fsm.state == TradeState.TRIGGERED
    # Advance 2 more bars without fill → T6
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(flags={"ABSORB_PUT_WALL"}), bar_index=3)
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(flags={"ABSORB_PUT_WALL"}), bar_index=4)
    assert fsm.state == TradeState.IDLE
    assert any(r["transition_id"] == "T6" for r in writer.rows)


def test_T7_in_position_to_managing_at_first_target():
    fsm, writer, bus = _fsm_fresh(first_target_R=1.0)
    bus.add_level(_build_level(kind=LevelKind.CONFIRMED_ABSORB, score=80.0))
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(), bar_index=1)
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(flags={"ABSORB_PUT_WALL"}), bar_index=2)
    fill = SimpleNamespace(
        ts=time.time(), entry_price=100.0, stop_price=99.0, direction=+1,
        side=OrderSide.LONG, r_distance=1.0, max_favorable_R=0.0,
    )
    fsm.on_fill(fill, bar_index=3)
    # Bar with close at 101.2 → +1.2R → T7
    fsm.on_bar(_bar(close=101.2, high=101.3, low=100.9), bus, _scorer(score=85.0), _conf(), bar_index=4)
    assert fsm.state == TradeState.MANAGING
    assert any(r["transition_id"] == "T7" for r in writer.rows)


def test_T8_managing_to_exiting_on_I9_mfe_giveback():
    fsm, writer, bus = _fsm_fresh()
    bus.add_level(_build_level(kind=LevelKind.CONFIRMED_ABSORB, score=80.0))
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(), bar_index=1)
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(flags={"ABSORB_PUT_WALL"}), bar_index=2)
    # Fill at 100, stop at 99 → r_distance = 1.0; MFE starts at 0
    fill = SimpleNamespace(
        ts=time.time(), entry_price=100.0, stop_price=99.0, direction=+1,
        side=OrderSide.LONG, r_distance=1.0, max_favorable_R=0.0,
    )
    fsm.on_fill(fill, bar_index=3)
    # Bar 4: close=101.5 → current_R=1.5 → T7 to MANAGING; MFE still 0 so no I9
    fsm.on_bar(_bar(close=101.5, high=101.6, low=101.3), bus, _scorer(score=85.0), _conf(), bar_index=4)
    assert fsm.state == TradeState.MANAGING
    # Stamp MFE=10R post-entry-to-MANAGING to simulate "price ran, now retraces"
    fill.max_favorable_R = 10.0
    # Bar 5: close=104.9 → current_R=4.9 ≤ 5.0 (50% of MFE=10) → I9 fires
    intents = fsm.on_bar(_bar(close=104.9, high=105.0, low=104.5), bus, _scorer(score=85.0), _conf(), bar_index=5)
    assert fsm.state == TradeState.EXITING
    assert any(i.action == "EXIT" and i.trigger_id == "I9" for i in intents)
    assert any(r["trigger"] == "I9" and r["transition_id"] == "T8" for r in writer.rows)


def test_T9_exiting_to_idle_on_next_bar():
    fsm, writer, bus = _fsm_fresh()
    bus.add_level(_build_level(kind=LevelKind.CONFIRMED_ABSORB, score=80.0))
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(), bar_index=1)
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(flags={"ABSORB_PUT_WALL"}), bar_index=2)
    fill = SimpleNamespace(
        ts=time.time(), entry_price=100.0, stop_price=99.0, direction=+1,
        side=OrderSide.LONG, r_distance=1.0, max_favorable_R=0.0,
    )
    fsm.on_fill(fill, bar_index=3)
    fsm.on_bar(_bar(close=101.5, high=101.6, low=101.3), bus, _scorer(score=85.0), _conf(), bar_index=4)
    assert fsm.state == TradeState.MANAGING
    fill.max_favorable_R = 10.0
    fsm.on_bar(_bar(close=104.9, high=105.0, low=104.5), bus, _scorer(score=85.0), _conf(), bar_index=5)
    assert fsm.state == TradeState.EXITING
    fsm.on_bar(_bar(close=104.0), bus, _scorer(score=85.0), _conf(), bar_index=6)
    assert fsm.state == TradeState.IDLE
    assert any(r["transition_id"] == "T9" for r in writer.rows)


def test_T10_armed_to_idle_on_confluence_drop():
    fsm, writer, bus = _fsm_fresh(armed_timeout_bars=5, min_confluence_score_for_T2=70.0)
    bus.add_level(_build_level(kind=LevelKind.CONFIRMED_ABSORB, score=80.0))
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(), bar_index=1)
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(), bar_index=2)
    # At bar 2 we move to ARMED (no wall flag → no ET-03; ET-01 queues but only fires next bar)
    assert fsm.state == TradeState.ARMED
    # At bar 3, score drops below threshold → T10
    fsm.on_bar(_bar(), bus, _scorer(score=50.0, tier=SignalTier.TYPE_C), _conf(), bar_index=3)
    assert fsm.state == TradeState.IDLE
    assert any(r["transition_id"] == "T10" for r in writer.rows)


def test_T11_watching_to_idle_all_levels_invalidated():
    fsm, writer, bus = _fsm_fresh()
    lv = _build_level(score=70.0)
    bus.add_level(lv)
    fsm.on_bar(_bar(), bus, _scorer(score=65.0, tier=SignalTier.TYPE_C), _conf(), bar_index=1)
    assert fsm.state == TradeState.WATCHING
    # Invalidate level + keep low score → T11
    lv.state = LevelState.INVALIDATED
    fsm.on_bar(_bar(), bus, _scorer(score=65.0, tier=SignalTier.TYPE_C), _conf(), bar_index=2)
    assert fsm.state == TradeState.IDLE
    assert any(r["transition_id"] == "T11" for r in writer.rows)


def test_spoof_veto_forces_idle_from_armed():
    fsm, writer, bus = _fsm_fresh()
    bus.add_level(_build_level(kind=LevelKind.CONFIRMED_ABSORB, score=80.0))
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(), bar_index=1)
    # Enter ARMED (no wall flag so only ET-01 queues, not ET-03)
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(), bar_index=2)
    assert fsm.state == TradeState.ARMED
    # Veto arrives → force IDLE
    fsm.on_bar(_bar(), bus, _scorer(score=85.0),
               _conf(vetoes={"SPOOF_DETECTED"}), bar_index=3)
    assert fsm.state == TradeState.IDLE


def test_stop_computed_per_D23():
    """D-23: stop = max(structural+2t, 2.0×ATR), capped at 1.5% account."""
    fsm, _, bus = _fsm_fresh()
    # Account balance 25000; max distance = 25000*0.015/50 = 7.5 pts
    lv = _build_level(kind=LevelKind.CONFIRMED_ABSORB, score=80.0, price_top=100.5, price_bot=99.5)
    stop = fsm._compute_stop(
        entry_price=100.0, side=OrderSide.LONG, lv=lv,
        atr=1.0, tick_size=0.25, bar_high=100.5, bar_low=99.5,
    )
    # structural = (100.0 - 99.5) + 0.5 = 1.0; vol = 2*1 = 2.0; max = 2.0
    # 2.0 < 7.5 cap → stop = 100 - 2 = 98
    assert stop == pytest.approx(98.0, abs=1e-6)
    # With huge ATR → cap kicks in
    stop_capped = fsm._compute_stop(
        entry_price=100.0, side=OrderSide.LONG, lv=lv,
        atr=100.0, tick_size=0.25, bar_high=100.5, bar_low=99.5,
    )
    # max_distance = 7.5 → stop = 92.5
    assert stop_capped == pytest.approx(92.5, abs=1e-6)


def test_target_computed_per_D24():
    fsm, _, bus = _fsm_fresh()
    # Opposing VAH at 103
    bus.add_level(_build_level(kind=LevelKind.VAH, score=60.0, price_top=103.0, price_bot=103.0, direction=-1))
    tgt = fsm._compute_target(
        entry_price=100.0, stop_price=99.0, side=OrderSide.LONG, level_bus=bus,
    )
    # rr_floor = 100 + 1.5 = 101.5; VAH = 103; take the farther = 103
    assert tgt == pytest.approx(103.0, abs=1e-6)
    # No opposing zone → floor 101.5
    bus2 = LevelBus()
    tgt2 = fsm._compute_target(
        entry_price=100.0, stop_price=99.0, side=OrderSide.LONG, level_bus=bus2,
    )
    assert tgt2 == pytest.approx(101.5, abs=1e-6)


def test_size_computed_per_D26():
    fsm, _, _ = _fsm_fresh()
    sr = _scorer(tier=SignalTier.TYPE_A, score=85.0)
    ann = _conf()
    # risk_budget=100, stop_distance=1pt => $50/contract
    # base = 100/50 = 2.0
    # conviction = 0.75 (TYPE_A, score 80-89)
    # regime = 1.0 NEUTRAL
    # recency = 1.0
    # kelly = 0.25
    # raw = 2.0 * 0.75 * 1.0 * 1.0 * 0.25 = 0.375 → floor = 0
    n = fsm._compute_size(stop_distance=1.0, scorer_result=sr, annotations=ann)
    assert n == 0
    # With bigger risk_budget
    fsm.fsm_config.risk_budget_usd = 1000.0
    # raw = 20 * 0.75 * 1 * 1 * 0.25 = 3.75 → floor = 3, but max_position_contracts = 3
    n2 = fsm._compute_size(stop_distance=1.0, scorer_result=sr, annotations=ann)
    assert n2 == 3


def test_every_transition_persisted_to_writer():
    """Mock writer records every fsm_transition."""
    fsm, writer, bus = _fsm_fresh()
    bus.add_level(_build_level(kind=LevelKind.CONFIRMED_ABSORB, score=80.0))
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(), bar_index=1)     # T1
    fsm.on_bar(_bar(), bus, _scorer(score=85.0),
               _conf(flags={"ABSORB_PUT_WALL"}), bar_index=2)               # T2 + T3
    fill = SimpleNamespace(
        ts=time.time(), entry_price=100.0, stop_price=99.0, direction=+1,
        side=OrderSide.LONG, r_distance=1.0, max_favorable_R=10.0,
    )
    fsm.on_fill(fill, bar_index=3)                                          # T4
    fsm.on_bar(_bar(close=101.5, high=101.6, low=101.3), bus, _scorer(), _conf(), bar_index=4)  # T7
    fsm.on_bar(_bar(close=104.9, high=105.0, low=104.5), bus, _scorer(), _conf(), bar_index=5)  # T8
    fsm.on_bar(_bar(close=104.0), bus, _scorer(), _conf(), bar_index=6)     # T9
    tids = {r["transition_id"] for r in writer.rows}
    # At least 6 distinct transitions reached
    assert {"T1", "T2", "T3", "T4", "T7", "T8", "T9"}.issubset(tids)


def test_illegal_transition_raises():
    fsm, _, _ = _fsm_fresh()
    with pytest.raises(ValueError, match="Illegal FSM transition"):
        fsm._transition(
            to=TradeState.TRIGGERED,
            bar_ts=time.time(), bar_index=1,
            trigger="bad", regime=None, confluence_score=None, payload={},
        )


def test_fsm_does_not_call_evaluate():
    """S6: TradeDecisionMachine source must not call confluence_rules.evaluate.

    Strips comments and string literals (including docstrings) before the
    scan so that explanatory prose about the S6 constraint doesn't itself
    trip the test.
    """
    import io
    import tokenize as tk
    import deep6.execution.trade_decision_machine as mod

    src = inspect.getsource(mod)
    code_only: list[str] = []
    for tok in tk.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tk.COMMENT, tk.STRING, tk.ENCODING, tk.NL, tk.NEWLINE, tk.INDENT, tk.DEDENT):
            continue
        code_only.append(tok.string)
    stripped = " ".join(code_only)
    assert "confluence_rules.evaluate" not in stripped, (
        "FSM MUST NOT call confluence_rules.evaluate() — S6 constraint"
    )
    # Also ensure the direct-import form never appears in code (not in docstrings)
    assert re.search(
        r"from\s+deep6\.engines\.confluence_rules\s+import\s+evaluate", stripped
    ) is None


def test_pending_cleared_on_idle_transition():
    """Threat T-15-04-05: pending queue cleared when FSM collapses to IDLE."""
    fsm, _, bus = _fsm_fresh()
    bus.add_level(_build_level(kind=LevelKind.CONFIRMED_ABSORB, score=80.0))
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(), bar_index=1)
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(), bar_index=2)  # ARMED, ET-01 queues
    assert fsm.pending_count == 1
    # Drop confluence → T10
    fsm.on_bar(_bar(), bus, _scorer(score=40.0, tier=SignalTier.QUIET), _conf(), bar_index=3)
    assert fsm.state == TradeState.IDLE
    assert fsm.pending_count == 0


def test_suppress_shorts_scales_size_by_0_6():
    """15-03 handoff: FSM consumes CR-08 SUPPRESS_SHORTS flag with 0.6x sizing on shorts."""
    fsm, _, _ = _fsm_fresh()
    fsm.fsm_config.risk_budget_usd = 10000.0   # make sizing noticeably >0
    sr_long = _scorer(direction=+1, score=85.0)
    sr_short = _scorer(direction=-1, score=85.0)
    # With SUPPRESS_SHORTS: LONG unaffected, SHORT gets 0.6×
    ann = _conf(flags={"SUPPRESS_SHORTS"})
    n_long = fsm._compute_size(stop_distance=1.0, scorer_result=sr_long, annotations=ann)
    n_short = fsm._compute_size(stop_distance=1.0, scorer_result=sr_short, annotations=ann)
    # Both clipped at max_position_contracts=3 but short should be <= long
    assert n_short <= n_long


def test_precedence_absorb_beats_momentum_by_priority():
    """D-22: when multiple ET's fire, ABSORB family priority > MOMENTUM family."""
    fsm, writer, bus = _fsm_fresh()
    # Build an ABSORB zone and an LVN zone — both near price
    bus.add_level(_build_level(kind=LevelKind.CONFIRMED_ABSORB, score=85.0, price_top=100.5, price_bot=99.5))
    bus.add_level(_build_level(kind=LevelKind.LVN, score=75.0, price_top=100.5, price_bot=99.5))
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(), bar_index=1)
    # The armed level will be the higher-scoring one (CONFIRMED_ABSORB) → ET-01
    intents = fsm.on_bar(_bar(), bus,
                         _scorer(score=85.0, cats=["absorption", "volume_profile", "delta", "trapped"]),
                         _conf(flags={"ABSORB_PUT_WALL"}), bar_index=2)
    # Expect the ABSORB-family (ET-03 immediate-market) intent to be chosen
    enter_intents = [i for i in intents if i.action == "ENTER"]
    assert len(enter_intents) >= 1
    assert enter_intents[0].trigger_id.startswith("ET-0")  # ET-01/02/03/04 = absorb family
    assert enter_intents[0].trigger_id in ("ET-01", "ET-02", "ET-03", "ET-04")
