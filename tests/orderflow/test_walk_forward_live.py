"""Tests for WalkForwardTracker (phase 12-05).

Per-category × per-regime outcome resolution with auto-disable and recovery.
Tests drive the tracker against a real :memory: EventStore — no mocks for
persistence (the whole point of the plan is EventStore-backed, no JSON sink).
"""
from __future__ import annotations

import asyncio

import pytest

from deep6.api.store import EventStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store() -> EventStore:
    store = EventStore(":memory:")
    asyncio.run(store.initialize())
    return store


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Import surface
# ---------------------------------------------------------------------------


def test_import_surface():
    """WalkForwardTracker + result dataclasses are exported from the package."""
    from deep6.orderflow import (
        WalkForwardTracker,
        PendingOutcome,
        ResolvedOutcome,
    )

    assert WalkForwardTracker is not None
    assert PendingOutcome is not None
    assert ResolvedOutcome is not None


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_record_signal_appended_to_pending():
    """record_signal creates one pending entry per horizon."""
    from deep6.orderflow import WalkForwardTracker

    store = _make_store()
    tracker = WalkForwardTracker(store=store)

    async def _drive():
        await tracker.record_signal(
            category="absorption",
            regime="ABSORPTION_FRIENDLY",
            direction="LONG",
            entry_price=100.0,
            bar_index=10,
            session_id="s1",
            signal_event_id=None,
            bars_until_rth_close=100,
        )

    _run(_drive())
    # One pending entry per horizon (3 by default: 5, 10, 20)
    assert len(tracker._pending) == 3
    horizons = sorted(p.horizon for p in tracker._pending)
    assert horizons == [5, 10, 20]


def test_5bar_resolution_correct():
    """LONG signal + 5 upticks → CORRECT outcome at horizon=5."""
    from deep6.orderflow import WalkForwardTracker

    store = _make_store()
    tracker = WalkForwardTracker(store=store)

    async def _drive():
        await tracker.record_signal(
            category="absorption",
            regime="TRENDING",
            direction="LONG",
            entry_price=100.0,
            bar_index=0,
            session_id="s1",
            signal_event_id=None,
            bars_until_rth_close=100,
        )
        resolved: list = []
        for i in range(1, 6):
            r = await tracker.update_price(
                close_price=100.0 + i,
                bar_index=i,
                session_id="s1",
                bars_until_rth_close=100 - i,
            )
            resolved.extend(r)
        return resolved

    resolved = _run(_drive())
    # 5-bar horizon resolves first
    horizon5 = [r for r in resolved if r.horizon == 5]
    assert len(horizon5) == 1
    assert horizon5[0].outcome_label == "CORRECT"
    assert horizon5[0].pnl_ticks > 0


def test_5bar_resolution_incorrect():
    """LONG signal + 5 downticks → INCORRECT."""
    from deep6.orderflow import WalkForwardTracker

    store = _make_store()
    tracker = WalkForwardTracker(store=store)

    async def _drive():
        await tracker.record_signal(
            category="absorption",
            regime="TRENDING",
            direction="LONG",
            entry_price=100.0,
            bar_index=0,
            session_id="s1",
            signal_event_id=None,
            bars_until_rth_close=100,
        )
        resolved: list = []
        for i in range(1, 6):
            r = await tracker.update_price(
                close_price=100.0 - i,
                bar_index=i,
                session_id="s1",
                bars_until_rth_close=100 - i,
            )
            resolved.extend(r)
        return resolved

    resolved = _run(_drive())
    horizon5 = [r for r in resolved if r.horizon == 5]
    assert len(horizon5) == 1
    assert horizon5[0].outcome_label == "INCORRECT"
    assert horizon5[0].pnl_ticks < 0


def test_neutral_resolution():
    """Price unchanged → NEUTRAL (|pnl_ticks| < neutral_threshold)."""
    from deep6.orderflow import WalkForwardTracker

    store = _make_store()
    tracker = WalkForwardTracker(store=store, neutral_threshold_ticks=0.5)

    async def _drive():
        await tracker.record_signal(
            category="absorption",
            regime="TRENDING",
            direction="LONG",
            entry_price=100.0,
            bar_index=0,
            session_id="s1",
            signal_event_id=None,
            bars_until_rth_close=100,
        )
        resolved: list = []
        for i in range(1, 6):
            r = await tracker.update_price(
                close_price=100.0,  # unchanged
                bar_index=i,
                session_id="s1",
                bars_until_rth_close=100 - i,
            )
            resolved.extend(r)
        return resolved

    resolved = _run(_drive())
    horizon5 = [r for r in resolved if r.horizon == 5]
    assert len(horizon5) == 1
    assert horizon5[0].outcome_label == "NEUTRAL"


def test_expired_at_session_boundary():
    """LONG signal 15 bars before RTH close → 20-bar horizon is EXPIRED.

    Critical footgun mitigation (CONTEXT.md FOOTGUN 1): EXPIRED outcomes
    are persisted but excluded from Sharpe stats.
    """
    from deep6.orderflow import WalkForwardTracker

    store = _make_store()
    tracker = WalkForwardTracker(store=store)

    async def _drive():
        # Signal fired with only 15 bars until session close. 5 and 10 horizons
        # are safe; 20 must be labeled EXPIRED.
        await tracker.record_signal(
            category="delta",
            regime="TRENDING",
            direction="LONG",
            entry_price=100.0,
            bar_index=0,
            session_id="s1",
            signal_event_id=None,
            bars_until_rth_close=15,
        )
        resolved: list = []
        # Drive 20 upticks — 5/10 should resolve CORRECT; 20 is EXPIRED.
        for i in range(1, 21):
            r = await tracker.update_price(
                close_price=100.0 + i,
                bar_index=i,
                session_id="s1",
                bars_until_rth_close=max(0, 15 - i),
            )
            resolved.extend(r)
        return resolved

    resolved = _run(_drive())
    labels_by_h = {r.horizon: r.outcome_label for r in resolved}
    assert labels_by_h[5] == "CORRECT"
    assert labels_by_h[10] == "CORRECT"
    assert labels_by_h[20] == "EXPIRED"


def test_rolling_sharpe_per_category_regime():
    """200 synthetic signals in one cell → non-None rolling Sharpe.

    Cells below sharpe_window samples should return None / neutral; cells
    at/above should return a real float.
    """
    from deep6.orderflow import WalkForwardTracker

    store = _make_store()
    tracker = WalkForwardTracker(store=store, sharpe_window=200)

    async def _drive():
        for i in range(210):
            # Alternating +/− pnl so Sharpe is near 0
            pnl = 1.0 if i % 2 == 0 else -1.0
            await tracker.record_signal(
                category="delta",
                regime="TRENDING",
                direction="LONG",
                entry_price=100.0,
                bar_index=i * 10,
                session_id="s1",
                signal_event_id=None,
                bars_until_rth_close=1000,
            )
            # Drive 5 bars to resolve the 5-bar horizon
            for j in range(1, 6):
                await tracker.update_price(
                    close_price=100.0 + pnl * j,
                    bar_index=i * 10 + j,
                    session_id="s1",
                    bars_until_rth_close=1000,
                )

    _run(_drive())
    sharpe = tracker._compute_rolling_sharpe("delta", "TRENDING")
    assert sharpe is not None
    # Under-sampled cell returns None
    none_cell = tracker._compute_rolling_sharpe("absorption", "CHAOTIC")
    assert none_cell is None


def test_auto_disable_below_threshold():
    """Bad rolling Sharpe → get_weights_override puts 0 in that cell."""
    from deep6.orderflow import WalkForwardTracker

    store = _make_store()
    tracker = WalkForwardTracker(
        store=store,
        sharpe_window=20,  # small window for fast test
        disable_sharpe_threshold=0.0,
    )

    async def _drive():
        # 25 resolved outcomes, all INCORRECT (negative pnl) → Sharpe very negative.
        for i in range(25):
            await tracker.record_signal(
                category="trapped",
                regime="CHAOTIC",
                direction="LONG",
                entry_price=100.0,
                bar_index=i * 10,
                session_id="s1",
                signal_event_id=None,
                bars_until_rth_close=1000,
            )
            for j in range(1, 6):
                await tracker.update_price(
                    close_price=100.0 - j,  # tanking
                    bar_index=i * 10 + j,
                    session_id="s1",
                    bars_until_rth_close=1000,
                )

    _run(_drive())
    overrides = tracker.get_weights_override()
    assert "CHAOTIC" in overrides
    assert overrides["CHAOTIC"].get("trapped", 1.0) == 0.0
    assert tracker.is_disabled("trapped", "CHAOTIC") is True


def test_auto_recovery_above_threshold():
    """After disable, 50-signal window with good Sharpe re-enables the cell."""
    from deep6.orderflow import WalkForwardTracker

    store = _make_store()
    tracker = WalkForwardTracker(
        store=store,
        sharpe_window=20,
        disable_sharpe_threshold=0.0,
        recovery_window=20,
        recovery_sharpe_threshold=0.3,
    )

    async def _drive_bad():
        for i in range(25):
            await tracker.record_signal(
                category="imbalance",
                regime="CHAOTIC",
                direction="LONG",
                entry_price=100.0,
                bar_index=i * 10,
                session_id="s1",
                signal_event_id=None,
                bars_until_rth_close=1000,
            )
            for j in range(1, 6):
                await tracker.update_price(
                    close_price=100.0 - j,
                    bar_index=i * 10 + j,
                    session_id="s1",
                    bars_until_rth_close=1000,
                )

    async def _drive_good(offset):
        for i in range(offset, offset + 25):
            await tracker.record_signal(
                category="imbalance",
                regime="CHAOTIC",
                direction="LONG",
                entry_price=100.0,
                bar_index=i * 10,
                session_id="s1",
                signal_event_id=None,
                bars_until_rth_close=1000,
            )
            for j in range(1, 6):
                await tracker.update_price(
                    close_price=100.0 + j,  # winning
                    bar_index=i * 10 + j,
                    session_id="s1",
                    bars_until_rth_close=1000,
                )

    _run(_drive_bad())
    assert tracker.is_disabled("imbalance", "CHAOTIC") is True
    _run(_drive_good(offset=25))
    # After good streak, cell should be re-enabled
    assert tracker.is_disabled("imbalance", "CHAOTIC") is False


def test_bounded_pending():
    """pending cap at max_pending — oldest dropped when exceeded."""
    from deep6.orderflow import WalkForwardTracker

    store = _make_store()
    tracker = WalkForwardTracker(store=store, max_pending=10)

    async def _drive():
        # Each record_signal appends 3 pending entries (3 horizons).
        # 5 signals → 15 pending → must cap at 10.
        for i in range(5):
            await tracker.record_signal(
                category="absorption",
                regime="TRENDING",
                direction="LONG",
                entry_price=100.0,
                bar_index=i,
                session_id="s1",
                signal_event_id=None,
                bars_until_rth_close=1000,
            )

    _run(_drive())
    assert len(tracker._pending) <= 10
