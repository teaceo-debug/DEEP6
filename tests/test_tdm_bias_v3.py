from __future__ import annotations

import time
from types import SimpleNamespace

from deep6.engines.bias_contracts import BiasMode, BiasState, MarketBiasSnapshot
from deep6.engines.confluence_rules import ConfluenceAnnotations
from deep6.engines.level import Level, LevelKind, LevelState
from deep6.engines.narrative import NarrativeType
from deep6.engines.zone_registry import LevelBus
from deep6.execution.config import ExecutionConfig
from deep6.execution.trade_decision_machine import FSMConfig, TradeDecisionMachine
from deep6.execution.trade_state import TradeState
from deep6.scoring.scorer import ScorerResult, SignalTier
from deep6.state.eventstore_schema import InMemoryFsmWriter


def _bar(close=100.0, high=100.5, low=99.5, ts=None):
    return SimpleNamespace(
        close=close, high=high, low=low, timestamp=ts or time.time(), open=close
    )


def _scorer(
    *,
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


def _build_level(score=80.0):
    return Level(
        price_top=100.5,
        price_bot=99.5,
        kind=LevelKind.CONFIRMED_ABSORB,
        origin_ts=time.time(),
        origin_bar=0,
        last_act_bar=0,
        score=score,
        touches=2,
        direction=+1,
        inverted=False,
        state=LevelState.CREATED,
    )


def _bias_snapshot(mode: BiasMode, reason="test-mode") -> MarketBiasSnapshot:
    return MarketBiasSnapshot(
        symbol="NQ",
        asof_ts=time.time(),
        bias_label="LEAN BULL",
        bias_state=BiasState.LEAN_BULL,
        bias_score=2,
        confidence=0.7,
        setup_quality=3,
        mode=mode.value,
        mode_reason=reason,
        session_label="MID-AM",
        xamd_phase="BETWEEN",
        intermarket_alignment=0.25,
        kronos_confidence=0.6,
        nearest_support=99.0,
        nearest_resistance=101.0,
        domain_detail={},
        meta={},
    )


def _fsm_fresh() -> tuple[TradeDecisionMachine, InMemoryFsmWriter, LevelBus]:
    writer = InMemoryFsmWriter()
    bus = LevelBus()
    bus.add_level(_build_level())
    fsm = TradeDecisionMachine(
        execution_config=ExecutionConfig(),
        fsm_config=FSMConfig(),
        event_writer=writer,
    )
    return fsm, writer, bus


def _enter_watching(fsm: TradeDecisionMachine, bus: LevelBus) -> None:
    fsm.on_bar(_bar(), bus, _scorer(score=85.0), _conf(), bar_index=1)
    assert fsm.state == TradeState.WATCHING


def _enter_armed_without_trigger(fsm: TradeDecisionMachine, bus: LevelBus) -> None:
    _enter_watching(fsm, bus)
    fsm.on_bar(_bar(), bus, _scorer(score=75.0), _conf(), bar_index=2)
    assert fsm.state == TradeState.ARMED
    assert fsm.pending_count == 0


def test_t2_blocked_when_bias_mode_stop() -> None:
    fsm, writer, bus = _fsm_fresh()
    _enter_watching(fsm, bus)
    fsm.update_bias(_bias_snapshot(BiasMode.STOP, reason="risk-off"))

    fsm.on_bar(_bar(), bus, _scorer(score=75.0), _conf(), bar_index=2)

    assert fsm.state == TradeState.WATCHING
    assert not any(row["transition_id"] == "T2" for row in writer.rows)


def test_t2_passes_when_bias_mode_go() -> None:
    fsm, writer, bus = _fsm_fresh()
    _enter_watching(fsm, bus)
    fsm.update_bias(_bias_snapshot(BiasMode.GO))

    fsm.on_bar(_bar(), bus, _scorer(score=75.0), _conf(), bar_index=2)

    assert fsm.state == TradeState.ARMED
    assert any(row["transition_id"] == "T2" for row in writer.rows)


def test_t2_passes_when_bias_not_set() -> None:
    fsm, writer, bus = _fsm_fresh()
    _enter_watching(fsm, bus)

    fsm.on_bar(_bar(), bus, _scorer(score=75.0), _conf(), bar_index=2)

    assert fsm.state == TradeState.ARMED
    assert any(row["transition_id"] == "T2" for row in writer.rows)


def test_t3_blocked_when_bias_mode_caution() -> None:
    fsm, writer, bus = _fsm_fresh()
    _enter_armed_without_trigger(fsm, bus)
    fsm.update_bias(_bias_snapshot(BiasMode.CAUTION, reason="lunch"))

    intents = fsm.on_bar(
        _bar(),
        bus,
        _scorer(score=85.0, cats=["absorption", "delta", "trapped", "imbalance"]),
        _conf(flags={"ABSORB_PUT_WALL"}),
        bar_index=3,
    )

    assert fsm.state == TradeState.ARMED
    assert not intents
    assert not any(row["transition_id"] == "T3" for row in writer.rows)


def test_t3_blocked_when_bias_mode_stop() -> None:
    fsm, writer, bus = _fsm_fresh()
    _enter_armed_without_trigger(fsm, bus)
    fsm.update_bias(_bias_snapshot(BiasMode.STOP, reason="hard-stop"))

    intents = fsm.on_bar(
        _bar(),
        bus,
        _scorer(score=85.0, cats=["absorption", "delta", "trapped", "imbalance"]),
        _conf(flags={"ABSORB_PUT_WALL"}),
        bar_index=3,
    )

    assert fsm.state == TradeState.ARMED
    assert not intents
    assert not any(row["transition_id"] == "T3" for row in writer.rows)


def test_t3_passes_when_bias_mode_go() -> None:
    fsm, writer, bus = _fsm_fresh()
    _enter_armed_without_trigger(fsm, bus)
    fsm.update_bias(_bias_snapshot(BiasMode.GO))

    intents = fsm.on_bar(
        _bar(),
        bus,
        _scorer(score=85.0, cats=["absorption", "delta", "trapped", "imbalance"]),
        _conf(flags={"ABSORB_PUT_WALL"}),
        bar_index=3,
    )

    assert fsm.state == TradeState.TRIGGERED
    assert any(intent.action == "ENTER" for intent in intents)
    assert any(row["transition_id"] == "T3" for row in writer.rows)
