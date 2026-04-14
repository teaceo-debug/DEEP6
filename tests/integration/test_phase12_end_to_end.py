"""End-to-end phase-12 pipeline integration test (plan 12-05 task 3).

Drives a synthetic 3-session bar stream through:

- SharedState.on_bar_close (VPIN feed + SlingshotDetector + walk-forward price
  stream advancement)
- SharedState.feed_scorer_result (setup state machine + walk-forward
  record_signal per voting category)
- EventStore persistence (setup_transitions + walk_forward_outcomes)
- weight_loader.apply_walk_forward_overrides feedback

Assertions:
- walk_forward_outcomes table receives rows
- setup_transitions table receives rows
- At least one (regime, category) cell auto-disables then recovers
- EXPIRED outcomes appear for signals fired within the final horizon of a session
- apply_walk_forward_overrides propagates 0.0 for disabled cells

No network, no real scoring pipeline — uses a lightweight fake ScorerResult
(shape-based consumption matches phase 12-04 SetupTracker + phase 12-05 wiring).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import IntEnum

import pytest

from deep6.api.store import EventStore
from deep6.config import Config
from deep6.ml.lgbm_trainer import WeightFile
from deep6.ml.weight_loader import apply_walk_forward_overrides
from deep6.state.shared import SharedState


# ---------------------------------------------------------------------------
# Test fakes — shape-only; mirror ScorerResult / SlingshotResult API
# ---------------------------------------------------------------------------


class _FakeTier(IntEnum):
    QUIET = 0
    TYPE_C = 1
    TYPE_B = 2
    TYPE_A = 3


@dataclass
class _FakeScorerResult:
    total_score: float
    tier: _FakeTier
    direction: int
    engine_agreement: float = 0.8
    category_count: int = 3
    confluence_mult: float = 1.0
    zone_bonus: float = 0.0
    narrative: object = None
    label: str = "fake"
    categories_firing: list = field(default_factory=list)
    session_id: str = "s1"
    entry_price: float = 100.0
    signal_event_id: int | None = None


@dataclass
class _FakeSlingshot:
    fired: bool = False
    variant: int = 0
    direction: str | None = None
    bias: float = 0.0
    strength: float = 0.0
    triggers_state_bypass: bool = False


class _SyntheticBar:
    __slots__ = (
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "bar_delta",
        "cvd",
        "poc_price",
        "total_vol",
        "bar_range",
        "bar_index_in_session",
        "session_id",
    )

    def __init__(self, close: float, bar_index: int, session_id: str, bar_delta: int = 0):
        self.timestamp = 0.0
        self.open = close
        self.high = close
        self.low = close
        self.close = close
        self.bar_delta = bar_delta
        self.cvd = 0
        self.poc_price = close
        self.total_vol = 0
        self.bar_range = 0.0
        self.bar_index_in_session = bar_index
        self.session_id = session_id


def _make_config() -> Config:
    return Config(
        rithmic_user="u",
        rithmic_password="p",
        rithmic_system_name="test",
        rithmic_uri="wss://test",
        db_path=":memory:",
    )


def _build_state_with_store() -> tuple[SharedState, EventStore]:
    store = EventStore(":memory:")
    asyncio.run(store.initialize())
    state = SharedState.build(_make_config())
    state.attach_event_store(store)
    # Wire the test regime + session-close providers
    state.current_regime_provider = lambda: "TRENDING"
    state.bars_until_rth_close_provider = lambda: 100
    return state, store


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_walk_forward_records_outcomes_end_to_end():
    """Stream bars + scorer results — outcomes persist in walk_forward_outcomes."""
    state, store = _build_state_with_store()

    async def _drive():
        # 1-session stream, 30 bars. Feed scorer result on bar 0 (LONG absorption),
        # then drive 10 up-bars — expect CORRECT outcome for the 5-bar horizon.
        session_id = "s1"
        bar = _SyntheticBar(close=100.0, bar_index=0, session_id=session_id)
        await state.on_bar_close("1m", bar)
        scorer = _FakeScorerResult(
            total_score=70.0,
            tier=_FakeTier.TYPE_B,
            direction=1,
            categories_firing=["absorption"],
            session_id=session_id,
            entry_price=100.0,
        )
        await state.feed_scorer_result("1m", scorer, _FakeSlingshot(), current_bar_index=0)
        for i in range(1, 11):
            bar_i = _SyntheticBar(close=100.0 + i, bar_index=i, session_id=session_id)
            await state.on_bar_close("1m", bar_i)

    asyncio.run(_drive())

    rows = asyncio.run(store.query_walk_forward_outcomes())
    assert len(rows) >= 1
    labels = {r["horizon"]: r["outcome_label"] for r in rows}
    assert labels.get(5) == "CORRECT"


def test_expired_at_session_boundary_end_to_end():
    """Signal fired with bars_until_rth_close < horizon → EXPIRED row persisted."""
    state, store = _build_state_with_store()
    # Set provider so the signal is fired with 7 bars remaining (< 10, < 20).
    state.bars_until_rth_close_provider = lambda: 7

    async def _drive():
        session_id = "boundary"
        scorer = _FakeScorerResult(
            total_score=70.0,
            tier=_FakeTier.TYPE_B,
            direction=1,
            categories_firing=["delta"],
            session_id=session_id,
            entry_price=100.0,
        )
        await state.feed_scorer_result("1m", scorer, _FakeSlingshot(), current_bar_index=0)
        # Drive 25 bars so all 3 horizons (5/10/20) resolve.
        for i in range(1, 26):
            bar_i = _SyntheticBar(close=100.0 + i, bar_index=i, session_id=session_id)
            await state.on_bar_close("1m", bar_i)

    asyncio.run(_drive())

    rows = asyncio.run(
        store.query_walk_forward_outcomes(category="delta")
    )
    labels_by_h = {r["horizon"]: r["outcome_label"] for r in rows}
    # Horizons 10 and 20 should be EXPIRED (bars_until_close=7 < 10/20).
    # Horizon 5 should resolve normally (7 >= 5).
    assert labels_by_h.get(5) == "CORRECT"
    assert labels_by_h.get(10) == "EXPIRED"
    assert labels_by_h.get(20) == "EXPIRED"


def test_auto_disable_and_recovery_end_to_end():
    """Bad streak disables a cell; good streak recovers it; override map reflects it."""
    state, store = _build_state_with_store()
    # Tighten thresholds for fast feedback.
    from deep6.orderflow.walk_forward_live import WalkForwardTracker

    state.walk_forward = WalkForwardTracker(
        store=store,
        sharpe_window=20,
        disable_sharpe_threshold=0.0,
        recovery_window=20,
        recovery_sharpe_threshold=0.3,
    )

    async def _drive_losing():
        session_id = "losing"
        for i in range(25):
            scorer = _FakeScorerResult(
                total_score=70.0,
                tier=_FakeTier.TYPE_B,
                direction=1,
                categories_firing=["trapped"],
                session_id=session_id,
                entry_price=100.0,
            )
            await state.feed_scorer_result(
                "1m", scorer, _FakeSlingshot(), current_bar_index=i * 10
            )
            for j in range(1, 6):
                bar_j = _SyntheticBar(
                    close=100.0 - j,  # tanking
                    bar_index=i * 10 + j,
                    session_id=session_id,
                )
                await state.on_bar_close("1m", bar_j)

    async def _drive_winning(offset: int):
        session_id = "winning"
        for i in range(offset, offset + 25):
            scorer = _FakeScorerResult(
                total_score=70.0,
                tier=_FakeTier.TYPE_B,
                direction=1,
                categories_firing=["trapped"],
                session_id=session_id,
                entry_price=100.0,
            )
            await state.feed_scorer_result(
                "1m", scorer, _FakeSlingshot(), current_bar_index=i * 10
            )
            for j in range(1, 6):
                bar_j = _SyntheticBar(
                    close=100.0 + j,
                    bar_index=i * 10 + j,
                    session_id=session_id,
                )
                await state.on_bar_close("1m", bar_j)

    asyncio.run(_drive_losing())
    assert state.walk_forward.is_disabled("trapped", "TRENDING") is True

    # apply_walk_forward_overrides must propagate disable as a 0.0 multiplier.
    base = WeightFile(
        weights={"trapped": 1.0, "absorption": 1.0},
        regime_adjustments={},
        feature_importances={},
        training_date="2026-04-13",
        n_samples=100,
        metrics={},
        wfe=None,
        model_path="",
        model_checksum="",
    )
    merged = apply_walk_forward_overrides(base, state.walk_forward)
    assert merged.regime_adjustments["TRENDING"]["trapped"] == 0.0

    asyncio.run(_drive_winning(offset=25))
    assert state.walk_forward.is_disabled("trapped", "TRENDING") is False


def test_setup_transitions_recorded_on_end_to_end():
    """Transitions land in the setup_transitions table when scorer feeds trigger them."""
    state, store = _build_state_with_store()

    async def _drive():
        session_id = "setup"
        scorer = _FakeScorerResult(
            total_score=55.0,
            tier=_FakeTier.TYPE_B,
            direction=1,
            categories_firing=["absorption"],
            session_id=session_id,
        )
        await state.feed_scorer_result(
            "1m", scorer, _FakeSlingshot(), current_bar_index=1
        )

    asyncio.run(_drive())
    # query_setup_transitions spans a wide window
    import time as _t

    rows = asyncio.run(
        store.query_setup_transitions(
            session_start_ts=_t.time() - 60.0,
            session_end_ts=_t.time() + 60.0,
        )
    )
    assert len(rows) >= 1


def test_apply_walk_forward_overrides_none_tracker_is_noop():
    """Defensive: no tracker means no change."""
    base = WeightFile(
        weights={"absorption": 1.0},
        regime_adjustments={"TRENDING": {"absorption": 0.5}},
        feature_importances={},
        training_date="2026-04-13",
        n_samples=0,
        metrics={},
        wfe=None,
        model_path="",
        model_checksum="",
    )
    merged = apply_walk_forward_overrides(base, None)
    assert merged is base
