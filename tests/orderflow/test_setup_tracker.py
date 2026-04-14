"""Unit tests for SetupTracker — SCANNING → DEVELOPING → TRIGGERED → MANAGING → COOLDOWN.

Phase 12-04, Task 1. Covers all 10 transition rules from 12-04-PLAN.md behavior
spec. Uses lightweight stand-in objects for ScorerResult / SlingshotResult so
the tracker contract is exercised without pulling the full scoring pipeline.

Critical invariants verified here:
- MANAGING → COOLDOWN is NEVER auto (reference-impl footgun fixed)
- Failsafe at 30 bars forces COOLDOWN with warning (prevents wedge)
- Explicit close_trade() is the ONLY normal path out of MANAGING
- 10-bar soak ramps current_weight from 1.0 → 5.0 linearly
- Slingshot bypass skips DEVELOPING entirely (SCANNING → TRIGGERED)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from deep6.orderflow.setup_tracker import (
    SetupTracker,
    SetupTransition,
    ActiveSetup,
)


# -----------------------------------------------------------------------------
# Lightweight scorer / slingshot stand-ins.
#
# The SetupTracker consumes the shape — not the concrete class — so local
# fakes keep these tests fast and decoupled from full scoring machinery.
# Field names mirror ScorerResult (deep6/scoring/scorer.py) and
# SlingshotResult (deep6/orderflow/slingshot.py) exactly.
# -----------------------------------------------------------------------------


@dataclass
class FakeScore:
    tier: str          # "TYPE_A" | "TYPE_B" | "TYPE_C" | "NONE" / "QUIET"
    direction: str     # "LONG" | "SHORT" | "NEUTRAL"
    total_score: float


@dataclass
class FakeSling:
    fired: bool = False
    triggers_state_bypass: bool = False
    direction: Optional[str] = None
    variant: int = 0


def _scanning_tier_b_long(score: float = 50.0) -> FakeScore:
    return FakeScore(tier="TYPE_B", direction="LONG", total_score=score)


def _tier_a_long(score: float = 85.0) -> FakeScore:
    return FakeScore(tier="TYPE_A", direction="LONG", total_score=score)


def _quiet() -> FakeScore:
    return FakeScore(tier="NONE", direction="NEUTRAL", total_score=0.0)


def _no_sling() -> FakeSling:
    return FakeSling()


# -----------------------------------------------------------------------------
# Transition tests
# -----------------------------------------------------------------------------


def test_scanning_to_developing():
    """TYPE_B aligned signal with score >= 35 moves SCANNING → DEVELOPING."""
    tracker = SetupTracker(timeframe="1m")
    assert tracker.state == "SCANNING"

    tr = tracker.update(_scanning_tier_b_long(score=50.0), _no_sling(), current_bar_index=1)

    assert tracker.state == "DEVELOPING"
    assert tracker.active_setup is not None
    assert tracker.active_setup.direction == "LONG"
    assert tracker.active_setup.soak_bars == 1
    assert tr is not None
    assert tr.from_state == "SCANNING"
    assert tr.to_state == "DEVELOPING"


def test_developing_soak_weight_ramps():
    """10 consecutive DEVELOPING bars ramp current_weight 1.0 → 5.0 linearly."""
    tracker = SetupTracker(timeframe="1m")
    # Bar 1 kicks us into DEVELOPING
    tracker.update(_scanning_tier_b_long(score=50.0), _no_sling(), current_bar_index=1)
    assert tracker.state == "DEVELOPING"
    w_after_1 = tracker.current_weight()
    assert w_after_1 == pytest.approx(1.0 + 0.4 * 1, abs=1e-9)  # 1.4

    # Feed 9 more aligned TYPE_B bars → soak should reach 10
    for i in range(2, 11):
        tracker.update(
            _scanning_tier_b_long(score=50.0), _no_sling(), current_bar_index=i
        )

    assert tracker.state == "DEVELOPING"
    assert tracker.active_setup.soak_bars == 10
    assert tracker.current_weight() == pytest.approx(5.0, abs=1e-9)

    # Further bars don't exceed 5.0 (clamped)
    tracker.update(_scanning_tier_b_long(score=50.0), _no_sling(), current_bar_index=11)
    assert tracker.current_weight() == pytest.approx(5.0, abs=1e-9)


def test_developing_to_triggered_on_tier_cross():
    """DEVELOPING with soak >= 10 and score crossing TYPE_A threshold → TRIGGERED."""
    tracker = SetupTracker(timeframe="1m")
    for i in range(1, 11):
        tracker.update(_scanning_tier_b_long(score=50.0), _no_sling(), current_bar_index=i)
    assert tracker.state == "DEVELOPING"
    assert tracker.active_setup.soak_bars == 10

    tr = tracker.update(_tier_a_long(score=85.0), _no_sling(), current_bar_index=11)

    assert tracker.state == "TRIGGERED"
    assert tr is not None
    assert tr.to_state == "TRIGGERED"
    assert tr.trigger in ("TIER_CROSS", "tier_cross")


def test_slingshot_bypass():
    """Slingshot triggers_state_bypass → SCANNING jumps directly to TRIGGERED."""
    tracker = SetupTracker(timeframe="1m")
    assert tracker.state == "SCANNING"

    sling = FakeSling(
        fired=True,
        triggers_state_bypass=True,
        direction="LONG",
        variant=3,
    )
    tr = tracker.update(_quiet(), sling, current_bar_index=1)

    assert tracker.state == "TRIGGERED"
    assert tracker.active_setup is not None
    assert tracker.active_setup.direction == "LONG"
    assert tr is not None
    assert tr.to_state == "TRIGGERED"
    assert "BYPASS" in tr.trigger.upper()


def test_developing_resets_on_direction_flip():
    """TYPE_B LONG for 5 bars, then TYPE_B SHORT → soak resets, state → SCANNING."""
    tracker = SetupTracker(timeframe="1m")
    for i in range(1, 6):
        tracker.update(_scanning_tier_b_long(score=50.0), _no_sling(), current_bar_index=i)
    assert tracker.state == "DEVELOPING"
    assert tracker.active_setup.soak_bars == 5
    assert tracker.active_setup.direction == "LONG"

    short = FakeScore(tier="TYPE_B", direction="SHORT", total_score=50.0)
    tracker.update(short, _no_sling(), current_bar_index=6)

    # Implementation may either (a) drop to SCANNING and re-enter DEVELOPING the
    # same bar under the new direction, or (b) just drop to SCANNING. Either is
    # fine as long as the LONG soak is gone.
    if tracker.state == "DEVELOPING":
        assert tracker.active_setup.direction == "SHORT"
        assert tracker.active_setup.soak_bars == 1
    else:
        assert tracker.state == "SCANNING"
        assert tracker.active_setup is None


def test_triggered_to_managing():
    """1 bar after TRIGGERED (entry confirmed) → MANAGING."""
    tracker = SetupTracker(timeframe="1m")
    # Fast-path into TRIGGERED via slingshot bypass
    sling = FakeSling(fired=True, triggers_state_bypass=True, direction="LONG", variant=2)
    tracker.update(_quiet(), sling, current_bar_index=1)
    assert tracker.state == "TRIGGERED"
    entry_setup_id = tracker.active_setup.setup_id

    # Next bar — no new slingshot, quiet scorer
    tr = tracker.update(_quiet(), _no_sling(), current_bar_index=2)

    assert tracker.state == "MANAGING"
    assert tracker.active_setup.setup_id == entry_setup_id  # same setup instance
    assert tr is not None
    assert tr.from_state == "TRIGGERED"
    assert tr.to_state == "MANAGING"


def test_managing_no_auto_cooldown():
    """
    29 bars in MANAGING without close_trade → still MANAGING.
    This is THE test for the fixed reference-impl footgun.
    """
    tracker = SetupTracker(timeframe="1m")
    sling = FakeSling(fired=True, triggers_state_bypass=True, direction="LONG", variant=2)
    tracker.update(_quiet(), sling, current_bar_index=0)      # TRIGGERED
    tracker.update(_quiet(), _no_sling(), current_bar_index=1)  # → MANAGING
    assert tracker.state == "MANAGING"

    # 28 more bars (total bars_managing = 29 when failsafe is 30)
    for i in range(2, 30):
        tracker.update(_quiet(), _no_sling(), current_bar_index=i)
        assert tracker.state == "MANAGING", (
            f"bar {i}: MANAGING must not auto-transition; got {tracker.state}"
        )

    assert tracker.active_setup is not None
    assert tracker.active_setup.bars_managing >= 28


def test_managing_failsafe_at_31_bars(caplog):
    """
    31+ bars in MANAGING forces COOLDOWN via failsafe with a log warning.
    Guardrail only — real exits go via close_trade().
    """
    import logging as _logging

    tracker = SetupTracker(timeframe="1m", managing_failsafe_bars=30)
    sling = FakeSling(fired=True, triggers_state_bypass=True, direction="LONG", variant=2)
    tracker.update(_quiet(), sling, current_bar_index=0)
    tracker.update(_quiet(), _no_sling(), current_bar_index=1)
    assert tracker.state == "MANAGING"

    caplog.set_level(_logging.WARNING)
    tr_final = None
    for i in range(2, 35):
        tr = tracker.update(_quiet(), _no_sling(), current_bar_index=i)
        if tr is not None and tr.to_state == "COOLDOWN":
            tr_final = tr
            break

    assert tracker.state == "COOLDOWN"
    assert tr_final is not None
    assert tr_final.trigger.upper() in ("FAILSAFE", "MANAGING_FAILSAFE")
    # bars_managing was > 30 at fire
    # One of the captured warnings mentions failsafe
    failsafe_logs = [
        r for r in caplog.records
        if "failsafe" in r.getMessage().lower() or "FAILSAFE" in r.getMessage()
    ]
    assert failsafe_logs, f"no failsafe warning found in {[r.getMessage() for r in caplog.records]}"


def test_explicit_close_transitions_to_cooldown():
    """close_trade(setup_id) is the canonical path from MANAGING to COOLDOWN."""
    tracker = SetupTracker(timeframe="1m")
    sling = FakeSling(fired=True, triggers_state_bypass=True, direction="LONG", variant=2)
    tracker.update(_quiet(), sling, current_bar_index=0)
    tracker.update(_quiet(), _no_sling(), current_bar_index=1)
    assert tracker.state == "MANAGING"
    setup_id = tracker.active_setup.setup_id

    tr = tracker.close_trade(setup_id, outcome="TARGET_HIT")

    assert tracker.state == "COOLDOWN"
    assert tr is not None
    assert tr.from_state == "MANAGING"
    assert tr.to_state == "COOLDOWN"
    assert tr.trigger.upper() == "EXPLICIT_CLOSE"


def test_cooldown_returns_to_scanning():
    """After cooldown_bars elapse, COOLDOWN → SCANNING."""
    tracker = SetupTracker(timeframe="1m", cooldown_bars=5)
    sling = FakeSling(fired=True, triggers_state_bypass=True, direction="LONG", variant=2)
    tracker.update(_quiet(), sling, current_bar_index=0)
    tracker.update(_quiet(), _no_sling(), current_bar_index=1)   # MANAGING
    tracker.close_trade(tracker.active_setup.setup_id, outcome="STOP_HIT")
    assert tracker.state == "COOLDOWN"

    # Advance 5 bars → SCANNING
    for i in range(2, 7):
        tracker.update(_quiet(), _no_sling(), current_bar_index=i)

    assert tracker.state == "SCANNING"
    assert tracker.active_setup is None


def test_close_trade_with_wrong_id_is_noop():
    """close_trade() with an unknown setup_id must NOT transition state.

    Defensive: execution layer may route a stale fill event — the tracker
    must never react to somebody else's setup_id.
    """
    tracker = SetupTracker(timeframe="1m")
    sling = FakeSling(fired=True, triggers_state_bypass=True, direction="LONG", variant=2)
    tracker.update(_quiet(), sling, current_bar_index=0)
    tracker.update(_quiet(), _no_sling(), current_bar_index=1)
    assert tracker.state == "MANAGING"

    tr = tracker.close_trade("not-the-right-id", outcome="TARGET_HIT")

    assert tracker.state == "MANAGING"
    assert tr is None


def test_setup_id_is_prefixed_by_timeframe():
    """Setup IDs prefix the timeframe so cross-TF routing is unambiguous."""
    t1 = SetupTracker(timeframe="1m")
    t5 = SetupTracker(timeframe="5m")
    sling = FakeSling(fired=True, triggers_state_bypass=True, direction="LONG", variant=2)
    t1.update(_quiet(), sling, current_bar_index=0)
    t5.update(_quiet(), sling, current_bar_index=0)

    assert t1.active_setup.setup_id.startswith("1m-")
    assert t5.active_setup.setup_id.startswith("5m-")
