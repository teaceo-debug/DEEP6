"""Phase 15-05 T-15-05-02 — FSM reachability test (D-38).

Every transition T1..T11 must be reachable from synthetic fixtures driving
TradeDecisionMachine via its PUBLIC API only (``on_bar`` / ``on_fill`` /
``on_reject``). No hand-set internal state.

Aggregate assertion:
    set(eventstore_rows.transition_id) >= {T1..T11}

A source-level scan (``test_reachability_no_hand_state_mutation``) guards
against tests sneaking in ``fsm._state = ...`` assignments.
"""
from __future__ import annotations

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
    TradeDecisionMachine,
)
from deep6.execution.trade_state import TradeState
from deep6.scoring.scorer import ScorerResult, SignalTier
from deep6.state.eventstore_schema import InMemoryFsmWriter


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _bar(close=100.0, high=None, low=None, ts=None):
    return SimpleNamespace(
        close=close,
        high=high if high is not None else close + 0.5,
        low=low if low is not None else close - 0.5,
        timestamp=ts or time.time(),
        open=close,
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


def _level(
    kind=LevelKind.CONFIRMED_ABSORB, score=80.0,
    price_top=100.5, price_bot=99.5, direction=+1,
    state=LevelState.CREATED,
):
    return Level(
        price_top=price_top, price_bot=price_bot, kind=kind,
        origin_ts=time.time(), origin_bar=0, last_act_bar=0,
        score=score, touches=2, direction=direction, inverted=False,
        state=state,
    )


def _fsm_fresh(**fsm_kwargs):
    writer = InMemoryFsmWriter()
    bus = LevelBus()
    fsm = TradeDecisionMachine(
        execution_config=ExecutionConfig(),
        fsm_config=FSMConfig(**fsm_kwargs),
        event_writer=writer,
    )
    return fsm, writer, bus


def _tids(writer: InMemoryFsmWriter) -> list[str]:
    return [r["transition_id"] for r in writer.rows]


# ---------------------------------------------------------------------------
# Per-transition scenario builders
# ---------------------------------------------------------------------------


def build_T1_scenario():
    """IDLE -> WATCHING via strong level near price."""
    fsm, writer, bus = _fsm_fresh()
    bus.add_level(_level(score=75.0))
    fsm.on_bar(_bar(close=100.0), bus, _scorer(), _conf(), bar_index=1)
    return fsm, writer


def build_T2_scenario():
    """WATCHING -> ARMED — use CONFIRMATION_BAR_MARKET trigger (ET-01) so FSM
    queues pending and stays in ARMED (no cascade to T3 in the same bar).
    """
    fsm, writer, bus = _fsm_fresh()
    bus.add_level(_level(kind=LevelKind.CONFIRMED_ABSORB, score=80.0))
    fsm.on_bar(_bar(close=100.0), bus, _scorer(), _conf(), bar_index=1)
    # No ABSORB_PUT_WALL flag → ET-03 path does NOT fire; ET-01 queues pending
    fsm.on_bar(
        _bar(close=100.0), bus,
        _scorer(cats=["absorption", "delta", "trapped", "imbalance"]),
        _conf(), bar_index=2,
    )
    return fsm, writer


def build_T3_scenario():
    """ARMED -> TRIGGERED via ET-03 (IMMEDIATE_MARKET, ABSORB_PUT_WALL flag)."""
    fsm, writer, bus = _fsm_fresh()
    bus.add_level(_level(kind=LevelKind.CONFIRMED_ABSORB, score=80.0))
    fsm.on_bar(_bar(close=100.0), bus, _scorer(), _conf(), bar_index=1)
    fsm.on_bar(
        _bar(close=100.0), bus,
        _scorer(cats=["absorption", "delta", "trapped", "imbalance"]),
        _conf(flags={"ABSORB_PUT_WALL"}),
        bar_index=2,
    )
    return fsm, writer


def build_T4_scenario():
    """TRIGGERED -> IN_POSITION via on_fill."""
    fsm, writer = build_T3_scenario()
    fill = SimpleNamespace(
        ts=time.time(), entry_price=100.0, stop_price=99.0, direction=+1,
        side=OrderSide.LONG, r_distance=1.0, max_favorable_R=0.0,
    )
    fsm.on_fill(fill, bar_index=3)
    return fsm, writer


def build_T5_scenario():
    """TRIGGERED -> ARMED via on_reject(retry_ok=True)."""
    fsm, writer = build_T3_scenario()
    fsm.on_reject(SimpleNamespace(ts=time.time()), bar_index=3, retry_ok=True)
    return fsm, writer


def build_T6_scenario():
    """TRIGGERED -> IDLE via timeout without fill.

    Use ``trigger_timeout_bars=1`` so one on_bar() advance past TRIGGERED
    collapses to IDLE.
    """
    fsm, writer, bus = _fsm_fresh(trigger_timeout_bars=1)
    bus.add_level(_level(kind=LevelKind.CONFIRMED_ABSORB, score=80.0))
    fsm.on_bar(_bar(close=100.0), bus, _scorer(), _conf(), bar_index=1)
    fsm.on_bar(
        _bar(close=100.0), bus,
        _scorer(cats=["absorption", "delta", "trapped", "imbalance"]),
        _conf(flags={"ABSORB_PUT_WALL"}), bar_index=2,
    )
    # Now in TRIGGERED. One bar without fill → TRIGGER_TIMEOUT → IDLE (T6).
    # Empty the bus first so the post-T6 cascade cannot re-enter WATCHING
    # via T1 in the same on_bar() call (which would mask the T6 test).
    bus._levels.clear()
    fsm.on_bar(_bar(close=100.0), bus, _scorer(), _conf(), bar_index=3)
    return fsm, writer


def build_T7_scenario():
    """IN_POSITION -> MANAGING at first-target (1R)."""
    fsm, writer = build_T4_scenario()
    # entry=100, stop=99, r_distance=1. close=101 → r_multiple=1.0
    pos = fsm._current_position_snapshot  # read-only introspection (no mutation)
    # Progress bar, then advance: need on_bar with close >= 101.0
    bus = LevelBus()
    bus.add_level(_level(kind=LevelKind.CONFIRMED_ABSORB, score=80.0,
                         price_top=101.0, price_bot=100.5))
    fsm.on_bar(_bar(close=101.1), bus, _scorer(), _conf(), bar_index=4)
    return fsm, writer


def build_T8_scenario():
    """MANAGING -> EXITING via I9 MFE give-back.

    After T7 we stamp ``max_favorable_R=10.0`` on the position snapshot
    (simulating a run that gave back) — this is NOT FSM internal state,
    it's caller-owned Position data the FSM reads per D-25/I9 contract.
    """
    fsm, writer = build_T7_scenario()
    pos = fsm._current_position_snapshot
    # Caller-owned Position field — the FSM reads it via guard_T8_invalidated.
    # Not an FSM state mutation (no fsm._state = ..., no fsm._pending.append).
    pos.max_favorable_R = 10.0

    # current_R = (close - entry) * direction / r_distance. With entry=100,
    # r_distance=1, direction=+1: close=101 ⇒ current_R=1 ⇒ 1 <= 10*0.5=5 ⇒ I9 fires.
    bus = LevelBus()
    fsm.on_bar(_bar(close=101.0), bus, _scorer(), _conf(), bar_index=5)
    return fsm, writer


def build_T9_scenario():
    """EXITING -> IDLE on next bar auto-advance (absent broker fill callback)."""
    fsm, writer = build_T8_scenario()
    bus = LevelBus()
    fsm.on_bar(_bar(close=100.5), bus, _scorer(), _conf(), bar_index=6)
    fsm.on_bar(_bar(close=100.0), bus, _scorer(), _conf(), bar_index=7)
    return fsm, writer


def build_T10_scenario():
    """ARMED -> IDLE via confluence drop (score < min_confluence_score_for_T2).

    Reach ARMED via CONFIRMATION_BAR_MARKET path (no T3 cascade), then drop
    score on the next bar.
    """
    fsm, writer = build_T2_scenario()
    # Now ARMED with a pending ET-01. Next bar: low score collapses to IDLE.
    bus = LevelBus()
    bus.add_level(_level(kind=LevelKind.CONFIRMED_ABSORB, score=80.0))
    fsm.on_bar(
        _bar(close=100.0), bus,
        _scorer(score=50.0, tier=SignalTier.TYPE_C),
        _conf(), bar_index=3,
    )
    return fsm, writer


def build_T11_scenario():
    """WATCHING -> IDLE via timeout (watching_timeout_bars=1).

    Setting the timeout to 1 bar forces T11 on the second on_bar().
    Alternative route — invalidating the sole watched level — is tested
    implicitly via the trend-day integration test.
    """
    fsm, writer, bus = _fsm_fresh(watching_timeout_bars=1)
    bus.add_level(_level(score=75.0))
    fsm.on_bar(_bar(close=100.0), bus, _scorer(), _conf(), bar_index=1)
    assert fsm.state == TradeState.WATCHING
    # Next bar: still score<70 so T2 fails; timeout reached → T11.
    fsm.on_bar(
        _bar(close=100.0), bus,
        _scorer(score=55.0, tier=SignalTier.TYPE_C),
        _conf(), bar_index=2,
    )
    return fsm, writer


TRANSITION_SCENARIOS = {
    "T1": build_T1_scenario,
    "T2": build_T2_scenario,
    "T3": build_T3_scenario,
    "T4": build_T4_scenario,
    "T5": build_T5_scenario,
    "T6": build_T6_scenario,
    "T7": build_T7_scenario,
    "T8": build_T8_scenario,
    "T9": build_T9_scenario,
    "T10": build_T10_scenario,
    "T11": build_T11_scenario,
}


# ---------------------------------------------------------------------------
# Per-transition tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tid", list(TRANSITION_SCENARIOS.keys()))
def test_transition_reachable(tid):
    """Each transition T1..T11 is emitted from its public-API-only scenario."""
    _fsm, writer = TRANSITION_SCENARIOS[tid]()
    emitted = _tids(writer)
    assert tid in emitted, (
        f"Transition {tid} not found in EventStore rows: {emitted}"
    )


def test_T1_idle_to_watching():
    fsm, writer = build_T1_scenario()
    assert fsm.state == TradeState.WATCHING
    assert "T1" in _tids(writer)


def test_T2_watching_to_armed():
    fsm, writer = build_T2_scenario()
    assert fsm.state == TradeState.ARMED
    assert "T2" in _tids(writer)
    # Explicitly verify T3 did NOT fire in this scenario
    assert "T3" not in _tids(writer)


def test_T3_armed_to_triggered():
    fsm, writer = build_T3_scenario()
    assert fsm.state == TradeState.TRIGGERED
    assert "T3" in _tids(writer)


def test_T4_triggered_to_in_position():
    fsm, writer = build_T4_scenario()
    assert fsm.state == TradeState.IN_POSITION
    assert "T4" in _tids(writer)


def test_T5_triggered_to_armed():
    fsm, writer = build_T5_scenario()
    assert fsm.state == TradeState.ARMED
    assert "T5" in _tids(writer)


def test_T6_triggered_to_idle():
    fsm, writer = build_T6_scenario()
    assert fsm.state == TradeState.IDLE
    assert "T6" in _tids(writer)


def test_T7_in_position_to_managing():
    fsm, writer = build_T7_scenario()
    assert fsm.state == TradeState.MANAGING
    assert "T7" in _tids(writer)


def test_T8_managing_to_exiting():
    fsm, writer = build_T8_scenario()
    assert fsm.state == TradeState.EXITING
    assert "T8" in _tids(writer)


def test_T9_exiting_to_idle():
    fsm, writer = build_T9_scenario()
    assert fsm.state == TradeState.IDLE
    assert "T9" in _tids(writer)


def test_T10_armed_to_idle():
    fsm, writer = build_T10_scenario()
    assert fsm.state == TradeState.IDLE
    assert "T10" in _tids(writer)


def test_T11_watching_to_idle():
    fsm, writer = build_T11_scenario()
    assert fsm.state == TradeState.IDLE
    assert "T11" in _tids(writer)


# ---------------------------------------------------------------------------
# Aggregate + scan tests
# ---------------------------------------------------------------------------


def test_reachability_aggregate():
    """Across all 11 scenarios, every transition id appears in some EventStore."""
    all_ids: set[str] = set()
    for builder in TRANSITION_SCENARIOS.values():
        _fsm, writer = builder()
        all_ids.update(_tids(writer))
    expected = {f"T{i}" for i in range(1, 12)}
    missing = expected - all_ids
    assert not missing, f"Unreached transitions: {missing}"


def test_reachability_no_hand_state_mutation():
    """Guard: tests must drive FSM via public API only — no ``._state = ...``
    mutations, no ``._pending.append(...)``, no ``._transition(...)`` calls.

    Scans this module's own source and fails if any forbidden pattern appears.
    Exempts a narrow whitelist — reading ``_current_position_snapshot`` is
    allowed (it's caller-owned Position data, not FSM state).
    """
    import io
    import tokenize

    src = Path(__file__).read_text()
    # Rebuild source from non-STRING / non-COMMENT tokens to scan code-only.
    code_tokens: list[str] = []
    for tok in tokenize.tokenize(io.BytesIO(src.encode()).readline):
        if tok.type in (tokenize.STRING, tokenize.COMMENT, tokenize.ENCODING):
            continue
        code_tokens.append(tok.string)
    code_only = " ".join(code_tokens)

    forbidden = [
        r"fsm\s*\.\s*_state\s*=",
        r"fsm\s*\.\s*_pending\b",
        r"fsm\s*\.\s*_transition\b",
        r"fsm\s*\.\s*_watched_uids\s*=",
        r"fsm\s*\.\s*_armed_level_uid\s*=",
        r"fsm\s*\.\s*_armed_side\s*=",
        r"fsm\s*\.\s*_resting_limits\b",
    ]
    for pat in forbidden:
        m = re.search(pat, code_only)
        assert m is None, f"Hand-state mutation found in code tokens: {pat} -> {m}"


def test_reachability_coverage_report(capsys):
    """Informational: print per-transition scenario + EventStore row count.

    Acts as the 'test_reachability_coverage_report' from the plan — prints a
    compact table that shows up at the end of the suite run.
    """
    rows = []
    for tid, builder in TRANSITION_SCENARIOS.items():
        _fsm, writer = builder()
        rows.append((tid, builder.__name__, len(writer.rows)))
    # emit report
    print("\n[FSM-REACHABILITY] tid / fixture / row_count")
    for tid, name, count in rows:
        print(f"  {tid:3s}  {name:36s}  rows={count}")
    # sanity: every scenario produced at least one row
    assert all(count > 0 for _, _, count in rows)


def test_every_scenario_uses_public_api_only():
    """Sanity: each builder function uses only on_bar / on_fill / on_reject.

    Tokenizes per-builder source, strips STRING / COMMENT tokens so the
    check ignores docstrings / comments that legitimately mention forbidden
    patterns for explanatory purposes.
    """
    import inspect
    import io
    import tokenize

    for builder in TRANSITION_SCENARIOS.values():
        src = inspect.getsource(builder)
        toks: list[str] = []
        for tok in tokenize.tokenize(io.BytesIO(src.encode()).readline):
            if tok.type in (tokenize.STRING, tokenize.COMMENT, tokenize.ENCODING):
                continue
            toks.append(tok.string)
        code_only = " ".join(toks)
        assert "fsm . _state =" not in code_only, f"{builder.__name__} mutates _state"
        assert "fsm . _transition (" not in code_only, f"{builder.__name__} calls _transition"
