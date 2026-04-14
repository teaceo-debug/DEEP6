"""Cross-session narrative-Level decay tests (Plan 15-02, T-15-02-02).

Covers D-08: narrative Levels with score >= 60 carry over into next session
with score * 0.70; below threshold are GC'd by the existing registry.clear().
"""
from __future__ import annotations

import time

import pytest

from deep6.engines.level import Level, LevelKind, LevelState
from deep6.engines.vp_context_engine import E6VPContextEngine


NARRATIVE_KINDS = (
    LevelKind.ABSORB,
    LevelKind.EXHAUST,
    LevelKind.MOMENTUM,
    LevelKind.REJECTION,
    LevelKind.CONFIRMED_ABSORB,
    LevelKind.FLIPPED,
)


def _engine() -> E6VPContextEngine:
    return E6VPContextEngine(gex_api_key="test-key")


def _lvl(
    *,
    kind: LevelKind,
    score: float,
    top: float = 101.0,
    bot: float = 100.0,
    direction: int = +1,
    state: LevelState = LevelState.CREATED,
    touches: int = 0,
    origin_bar: int = 1,
) -> Level:
    return Level(
        price_top=top,
        price_bot=bot,
        kind=kind,
        origin_ts=time.time(),
        origin_bar=origin_bar,
        last_act_bar=origin_bar,
        score=score,
        touches=touches,
        direction=direction,
        inverted=False,
        state=state,
        meta={},
    )


# ---------------------------------------------------------------------------
# D-08 core behaviours
# ---------------------------------------------------------------------------

def test_carry_over_score_decayed() -> None:
    """Level(score=80, ABSORB) → on_session_start → score == 80 * 0.70 == 56.0."""
    eng = _engine()
    eng.registry.add_level(_lvl(kind=LevelKind.ABSORB, score=80.0))
    eng.on_session_start()
    survivors = eng.registry.query_by_kind(LevelKind.ABSORB)
    assert len(survivors) == 1
    assert survivors[0].score == pytest.approx(56.0)


def test_carry_over_below_threshold_dropped() -> None:
    """Level(score=55, ABSORB) < 60 → not carried; registry ABSORB empty."""
    eng = _engine()
    eng.registry.add_level(_lvl(kind=LevelKind.ABSORB, score=55.0))
    eng.on_session_start()
    assert eng.registry.query_by_kind(LevelKind.ABSORB) == []


def test_carry_over_threshold_boundary() -> None:
    """score == 60 exactly → carried (>= 60)."""
    eng = _engine()
    eng.registry.add_level(_lvl(kind=LevelKind.ABSORB, score=60.0))
    eng.on_session_start()
    survivors = eng.registry.query_by_kind(LevelKind.ABSORB)
    assert len(survivors) == 1
    assert survivors[0].score == pytest.approx(42.0)  # 60 * 0.70


def test_carry_over_kinds_filtered() -> None:
    """Only narrative-kinds carry. LVN (VP origin) + CALL_WALL (GEX) drop."""
    eng = _engine()
    eng.registry.add_level(_lvl(kind=LevelKind.ABSORB, score=80.0))
    eng.registry.add_level(_lvl(kind=LevelKind.LVN, score=80.0))
    eng.registry.add_level(
        _lvl(kind=LevelKind.CALL_WALL, score=80.0, top=100.0, bot=100.0)
    )
    eng.on_session_start()
    assert len(eng.registry.query_by_kind(LevelKind.ABSORB)) == 1
    assert eng.registry.query_by_kind(LevelKind.LVN) == []
    assert eng.registry.query_by_kind(LevelKind.CALL_WALL) == []


def test_carry_over_state_reset_to_active() -> None:
    """DEFENDED(score=80) → carry → state == CREATED (active / fresh)."""
    eng = _engine()
    eng.registry.add_level(
        _lvl(kind=LevelKind.ABSORB, score=80.0, state=LevelState.DEFENDED)
    )
    eng.on_session_start()
    survivors = eng.registry.query_by_kind(LevelKind.ABSORB)
    assert len(survivors) == 1
    assert survivors[0].state == LevelState.CREATED


def test_carry_over_touches_halved() -> None:
    """touches=5 → halved to 2 (floor div)."""
    eng = _engine()
    eng.registry.add_level(
        _lvl(kind=LevelKind.ABSORB, score=80.0, touches=5)
    )
    eng.on_session_start()
    survivors = eng.registry.query_by_kind(LevelKind.ABSORB)
    assert len(survivors) == 1
    assert survivors[0].touches == 2


def test_carry_over_multiple_narrative_kinds() -> None:
    """ABSORB, EXHAUST, MOMENTUM, REJECTION all carry when score ≥ 60."""
    eng = _engine()
    for k in (
        LevelKind.ABSORB,
        LevelKind.EXHAUST,
        LevelKind.MOMENTUM,
        LevelKind.REJECTION,
        LevelKind.FLIPPED,
        LevelKind.CONFIRMED_ABSORB,
    ):
        eng.registry.add_level(_lvl(kind=k, score=70.0))
    eng.on_session_start()
    for k in (
        LevelKind.ABSORB,
        LevelKind.EXHAUST,
        LevelKind.MOMENTUM,
        LevelKind.REJECTION,
        LevelKind.FLIPPED,
        LevelKind.CONFIRMED_ABSORB,
    ):
        assert len(eng.registry.query_by_kind(k)) == 1, f"kind {k} not carried"


def test_carry_over_invalidated_not_carried() -> None:
    """INVALIDATED Levels not carried regardless of score."""
    eng = _engine()
    eng.registry.add_level(
        _lvl(kind=LevelKind.ABSORB, score=80.0, state=LevelState.INVALIDATED)
    )
    eng.on_session_start()
    assert eng.registry.query_by_kind(LevelKind.ABSORB) == []


def test_vpro_07_prior_bins_path_untouched() -> None:
    """Passing prior_bins still routes through SessionProfile constructor."""
    eng = _engine()
    eng.registry.add_level(_lvl(kind=LevelKind.ABSORB, score=80.0))
    # prior_bins must be a dict of {tick_key: volume} to satisfy SessionProfile;
    # an empty dict exercises the code path without any real bin work.
    eng.on_session_start(prior_bins={})
    # narrative carry-over still applied
    assert len(eng.registry.query_by_kind(LevelKind.ABSORB)) == 1
    # bar_count reset, poc engine reset (smoke)
    assert eng._bar_count == 0
