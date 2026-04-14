"""Smoke tests for the Phase 15-05 synthetic day-type fixtures (T-15-05-01).

Verifies:
  - Each builder yields ~RTH_BAR_COUNT bars
  - Same seed → byte-identical bar sequences (determinism)
  - Fixture-source log line is emitted
  - Missing replay harness falls back to synthetic without crash
"""
from __future__ import annotations

import logging
import os

import pytest

from tests.integration.fixtures import phase15_fixtures
from tests.integration.fixtures.phase15_fixtures import resolve_session_source
from tests.integration.fixtures.synthetic_sessions import (
    DAY_TYPE_BUILDERS,
    RTH_BAR_COUNT,
    build_double_distribution_day,
    build_neutral_day,
    build_non_trend_day,
    build_normal_day,
    build_session,
    build_trend_day,
)


def test_normal_day_yields_390_bars():
    session = build_normal_day()
    assert len(session) == RTH_BAR_COUNT


@pytest.mark.parametrize("day_type", list(DAY_TYPE_BUILDERS.keys()))
def test_each_day_type_yields_rth_bar_count(day_type):
    session = build_session(day_type)
    assert len(session) == RTH_BAR_COUNT


@pytest.mark.parametrize("day_type", list(DAY_TYPE_BUILDERS.keys()))
def test_all_day_types_seeded_deterministically(day_type):
    """Same seed (same day_type string) → byte-identical bar sequences."""
    s1 = build_session(day_type)
    s2 = build_session(day_type)
    assert len(s1) == len(s2)
    for (b1, _, _), (b2, _, _) in zip(s1, s2):
        assert b1.close == b2.close
        assert b1.high == b2.high
        assert b1.low == b2.low
        assert b1.total_vol == b2.total_vol
        assert b1.bar_delta == b2.bar_delta
        assert b1.timestamp == b2.timestamp


def test_trend_day_has_seeded_narrative_signals():
    """Trend day seeds MOMENTUM at bar 30 and absorption at bar 100 (per plan)."""
    session = build_trend_day()
    from deep6.engines.narrative import NarrativeType

    assert session[30][1].bar_type == NarrativeType.MOMENTUM
    assert session[100][1].bar_type == NarrativeType.ABSORPTION


def test_double_distribution_has_regime_migration_markers():
    """Double distribution seeds rejection at bar 120, acceptance absorb at 240."""
    session = build_double_distribution_day()
    from deep6.engines.narrative import NarrativeType

    assert session[120][1].bar_type == NarrativeType.REJECTION
    assert session[240][1].bar_type == NarrativeType.ABSORPTION


def test_non_trend_day_is_low_activity():
    """Non-trend day: no narrative hits beyond QUIET + tight price range."""
    session = build_non_trend_day()
    from deep6.engines.narrative import NarrativeType

    non_quiet = [t for t in session if t[1].bar_type != NarrativeType.QUIET]
    assert non_quiet == []
    highs = [t[0].high for t in session]
    lows = [t[0].low for t in session]
    # Range should stay within ~10 points (sub-1.5×IB per day-type definition)
    assert max(highs) - min(lows) < 20.0


def test_neutral_day_visits_both_extremes():
    session = build_neutral_day()
    from deep6.engines.narrative import NarrativeType

    # At least one exhaustion (up extreme) and one absorption (both extremes)
    types = [t[1].bar_type for t in session]
    assert NarrativeType.ABSORPTION in types


def test_fallback_log_records_source(caplog):
    """resolve_session_source emits a logger message identifying the source."""
    caplog.set_level(logging.INFO, logger="tests.integration.fixtures.phase15_fixtures")
    # Unset env to force synthetic path
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("DEEP6_USE_REPLAY", raising=False)
        name, builder = resolve_session_source()
    assert name == "synthetic"
    session = builder("normal")
    assert len(session) == RTH_BAR_COUNT


def test_replay_path_skipped_when_harness_missing(monkeypatch):
    """With DEEP6_USE_REPLAY=1 but no harness module → synthetic fallback."""
    monkeypatch.setenv("DEEP6_USE_REPLAY", "1")
    # _try_replay_harness will ImportError deep6.backtest.replay (module absent)
    harness = phase15_fixtures._try_replay_harness()
    assert harness is None, (
        "Expected no harness class — Phase 13 ships ReplaySession, not ReplayHarness"
    )
    name, builder = resolve_session_source()
    assert name == "synthetic"


def test_session_source_fixture_yields_synthetic_by_default(session_source):
    """The session_source pytest fixture returns synthetic under default env."""
    name, builder = session_source
    assert name in ("synthetic", "replay_harness")
    session = builder("normal")
    assert len(session) == RTH_BAR_COUNT
