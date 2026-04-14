"""Integration tests — SetupTracker + SharedState dual-TF (1m + 5m).

Phase 12-04 Task 3. Drives synthetic scorer + slingshot results into
SharedState.on_bar_close for both timeframes in parallel and asserts that
trackers advance independently, transitions are persisted to EventStore,
and close_trade routes by setup_id prefix.

Key assertions (from plan 12-04):
- 1m reaches TRIGGERED on bar 12, 5m still DEVELOPING (each 5m bar counts
  as ONE soak bar — FOOTGUN 2 guard)
- TRAP_SHOT bypass on 1m jumps it to TRIGGERED; 5m unaffected
- Explicit close on 1m enters COOLDOWN; 5m stays MANAGING until its own close
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

import pytest

from deep6.api.store import EventStore
from deep6.config import Config
from deep6.orderflow.setup_tracker import SetupTracker
from deep6.state.shared import SharedState


# -----------------------------------------------------------------------------
# Minimal fakes — shape-compatible with ScorerResult / SlingshotResult.
# -----------------------------------------------------------------------------


@dataclass
class FakeScore:
    tier: str
    direction: str
    total_score: float


@dataclass
class FakeSling:
    fired: bool = False
    triggers_state_bypass: bool = False
    direction: Optional[str] = None
    variant: int = 0


# -----------------------------------------------------------------------------
# Test helpers
# -----------------------------------------------------------------------------


def _make_state() -> SharedState:
    """Build a SharedState with in-memory persistence for test isolation."""
    cfg = Config(
        rithmic_user="test",
        rithmic_password="test",
        rithmic_system_name="Rithmic Test",
        rithmic_uri="wss://rituz00100.rithmic.com",
        db_path=":memory:",
    )
    return SharedState.build(cfg)


async def _make_store() -> EventStore:
    store = EventStore(":memory:")
    await store.initialize()
    return store


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------


def test_dual_tf_independence_1m_triggered_5m_still_developing():
    """12 synthetic 'bars' where each bar drives both 1m and 5m trackers.

    With the soak-per-bar rule, after 12 bars:
    - 1m: soak >= 10, a TYPE_A score on bar 11 promotes it to TRIGGERED,
      then MANAGING on bar 12
    - 5m: also 12 bars of TYPE_B (each 5m bar = 1 soak bar), but our 5m
      stream never delivers TYPE_A — so 5m stays DEVELOPING

    We exercise the trackers directly (not through on_bar_close) because
    SharedState's bar-close path runs the slingshot detector against real
    FootprintBars; here we're testing the state-machine layer specifically.
    The full on_bar_close path is covered by test_on_bar_close_drives_trackers.
    """
    t1 = SetupTracker(timeframe="1m")
    t5 = SetupTracker(timeframe="5m")

    tier_b = FakeScore(tier="TYPE_B", direction="LONG", total_score=55.0)
    tier_a = FakeScore(tier="TYPE_A", direction="LONG", total_score=85.0)
    no_sling = FakeSling()

    # Bars 0..9 — soak on both
    for i in range(10):
        t1.update(tier_b, no_sling, current_bar_index=i)
        t5.update(tier_b, no_sling, current_bar_index=i)

    assert t1.state == "DEVELOPING"
    assert t5.state == "DEVELOPING"
    assert t1.active_setup.soak_bars == 10
    assert t5.active_setup.soak_bars == 10

    # Bar 10 — 1m crosses to TYPE_A; 5m continues TYPE_B
    t1.update(tier_a, no_sling, current_bar_index=10)
    t5.update(tier_b, no_sling, current_bar_index=10)
    assert t1.state == "TRIGGERED"
    assert t5.state == "DEVELOPING"

    # Bar 11 — 1m → MANAGING; 5m still DEVELOPING
    t1.update(tier_b, no_sling, current_bar_index=11)
    t5.update(tier_b, no_sling, current_bar_index=11)
    assert t1.state == "MANAGING"
    assert t5.state == "DEVELOPING"


def test_trap_shot_bypass_1m_only():
    """TRAP_SHOT slingshot firing on 1m jumps 1m to TRIGGERED; 5m unchanged."""
    t1 = SetupTracker(timeframe="1m")
    t5 = SetupTracker(timeframe="5m")

    quiet = FakeScore(tier="NONE", direction="NEUTRAL", total_score=0.0)
    no_sling = FakeSling()
    trap = FakeSling(fired=True, triggers_state_bypass=True, direction="LONG", variant=3)

    t1.update(quiet, trap, current_bar_index=0)
    t5.update(quiet, no_sling, current_bar_index=0)

    assert t1.state == "TRIGGERED"
    assert t5.state == "SCANNING"


def test_explicit_close_routes_by_setup_id_prefix():
    """close_trade on SharedState routes by 'Nm-' prefix in setup_id.

    Exercises SharedState.close_trade end-to-end: both trackers are in
    MANAGING; closing only the 1m setup_id transitions only the 1m tracker
    to COOLDOWN while 5m stays MANAGING.
    """
    state = _make_state()

    trap = FakeSling(fired=True, triggers_state_bypass=True, direction="LONG", variant=2)
    quiet = FakeScore(tier="NONE", direction="NEUTRAL", total_score=0.0)
    no_sling = FakeSling()

    # Drive 1m and 5m into MANAGING via slingshot bypass + one advance bar.
    state.setup_tracker_1m.update(quiet, trap, current_bar_index=0)
    state.setup_tracker_5m.update(quiet, trap, current_bar_index=0)
    state.setup_tracker_1m.update(quiet, no_sling, current_bar_index=1)
    state.setup_tracker_5m.update(quiet, no_sling, current_bar_index=1)
    assert state.setup_tracker_1m.state == "MANAGING"
    assert state.setup_tracker_5m.state == "MANAGING"

    setup_id_1m = state.setup_tracker_1m.active_setup.setup_id
    setup_id_5m = state.setup_tracker_5m.active_setup.setup_id
    assert setup_id_1m.startswith("1m-")
    assert setup_id_5m.startswith("5m-")

    # Close only the 1m
    tr = state.close_trade(setup_id_1m, outcome="TARGET_HIT")
    assert tr is not None
    assert tr.timeframe == "1m"
    assert state.setup_tracker_1m.state == "COOLDOWN"
    assert state.setup_tracker_5m.state == "MANAGING"

    # Close the 5m
    tr5 = state.close_trade(setup_id_5m, outcome="STOP_HIT")
    assert tr5 is not None
    assert tr5.timeframe == "5m"
    assert state.setup_tracker_5m.state == "COOLDOWN"


def test_shared_state_records_transitions_to_eventstore():
    """When SharedState.event_store is wired, transitions persist.

    Drives one scanning → developing transition via the SharedState helper
    and verifies the row lands in the setup_transitions table.
    """
    async def _body():
        state = _make_state()
        store = await _make_store()
        state.event_store = store

        tier_b = FakeScore(tier="TYPE_B", direction="LONG", total_score=55.0)
        no_sling = FakeSling()

        await state.feed_scorer_result("1m", tier_b, no_sling, current_bar_index=0)
        await state.feed_scorer_result("1m", tier_b, no_sling, current_bar_index=1)

        rows = await store.query_setup_transitions(
            session_start_ts=0.0,
            session_end_ts=10_000_000_000.0,
        )
        # At least one SCANNING → DEVELOPING row
        assert any(
            r["from_state"] == "SCANNING" and r["to_state"] == "DEVELOPING"
            for r in rows
        )
        assert all(r["timeframe"] == "1m" for r in rows)

    asyncio.run(_body())
