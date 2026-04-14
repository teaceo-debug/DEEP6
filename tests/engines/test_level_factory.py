"""Tests for LevelFactory — Plan 15-01, T-15-01-02.

Covers D-07 (wick geometry), D-12 (conversion signatures), D-28/D-29 (GEX).
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from deep6.engines.gex import GexLevels, GexRegime
from deep6.engines.level import LevelKind, LevelState
from deep6.engines.level_factory import (
    from_absorption,
    from_exhaustion,
    from_gex,
    from_momentum,
    from_rejection,
    from_volume_zone,
)
from deep6.engines.volume_profile import VolumeZone, ZoneState, ZoneType
from deep6.state.footprint import FootprintBar


# ---------------------------------------------------------------------------
# Synthetic fixtures (no real engine invocation)
# ---------------------------------------------------------------------------

class _FakeAbsorbType:
    name = "CLASSIC"


@dataclass
class _FakeAbsorptionSignal:
    direction: int
    price: float
    wick: str
    strength: float
    wick_pct: float = 50.0
    delta_ratio: float = 0.1
    bar_type: _FakeAbsorbType = _FakeAbsorbType()


@dataclass
class _FakeExhaustionSignal:
    direction: int
    price: float
    strength: float
    wick: str | None = None


@dataclass
class _FakeNarrativeResult:
    strength: float = 0.8
    direction: int = +1
    label: str = "TEST"


def _make_bar(*, o: float, h: float, l: float, c: float) -> FootprintBar:
    b = FootprintBar(open=o, high=h, low=l, close=c)
    return b


# ---------------------------------------------------------------------------
# from_volume_zone
# ---------------------------------------------------------------------------

def test_from_volume_zone_round_trip() -> None:
    zone = VolumeZone(
        zone_type=ZoneType.LVN, state=ZoneState.DEFENDED,
        top_price=21010.0, bot_price=21000.0, direction=+1,
        origin_bar=3, last_touch_bar=5, touches=2, score=65.0,
        volume_ratio=0.2,
    )
    lv = from_volume_zone(zone)
    assert lv.kind == LevelKind.LVN
    assert lv.price_top == 21010.0
    assert lv.price_bot == 21000.0
    assert lv.direction == +1
    assert lv.score == 65.0
    assert lv.touches == 2
    assert lv.state == LevelState.DEFENDED
    assert lv.origin_bar == 3
    assert lv.last_act_bar == 5
    assert lv.meta["vol_ratio"] == 0.2


def test_from_volume_zone_hvn() -> None:
    zone = VolumeZone(
        zone_type=ZoneType.HVN, state=ZoneState.CREATED,
        top_price=500, bot_price=490, direction=-1,
        origin_bar=0, last_touch_bar=0,
    )
    lv = from_volume_zone(zone)
    assert lv.kind == LevelKind.HVN


# ---------------------------------------------------------------------------
# from_absorption wick geometry (D-07)
# ---------------------------------------------------------------------------

def test_from_absorption_upper_wick_geometry() -> None:
    """UW absorption → top=bar.high, bot=body_top."""
    # bullish bar: body = [open=100, close=110]; wick high = 115
    bar = _make_bar(o=100.0, h=115.0, l=99.0, c=110.0)
    sig = _FakeAbsorptionSignal(direction=-1, price=115.0, wick="upper", strength=0.7)
    lv = from_absorption(sig, bar, bar_index=10, tick_size=0.25)
    assert lv.kind == LevelKind.ABSORB
    assert lv.price_top == 115.0  # bar.high
    assert lv.price_bot == 110.0  # body_top (max(o,c))
    assert lv.direction == -1
    assert lv.score == 70.0  # strength * 100
    assert lv.origin_bar == 10
    assert lv.meta["wick"] == "upper"


def test_from_absorption_lower_wick_geometry() -> None:
    """LW absorption → top=body_bot, bot=bar.low."""
    bar = _make_bar(o=110.0, h=111.0, l=100.0, c=105.0)
    sig = _FakeAbsorptionSignal(direction=+1, price=100.0, wick="lower", strength=0.6)
    lv = from_absorption(sig, bar, bar_index=5, tick_size=0.25)
    assert lv.price_top == 105.0  # body_bot (min(o,c))
    assert lv.price_bot == 100.0  # bar.low
    assert lv.direction == +1


def test_from_absorption_min_tick_width_enforced() -> None:
    """Degenerate bar with no wick → width widened to 1 tick."""
    # Bar with high == body_top (no upper wick)
    bar = _make_bar(o=100.0, h=110.0, l=99.0, c=110.0)
    sig = _FakeAbsorptionSignal(direction=-1, price=110.0, wick="upper", strength=0.5)
    lv = from_absorption(sig, bar, bar_index=1, tick_size=0.25)
    assert lv.price_top - lv.price_bot == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# from_exhaustion
# ---------------------------------------------------------------------------

def test_from_exhaustion_uses_wick_geometry() -> None:
    bar = _make_bar(o=100.0, h=115.0, l=99.0, c=110.0)
    sig = _FakeExhaustionSignal(direction=-1, price=115.0, strength=0.55, wick="upper")
    lv = from_exhaustion(sig, bar, bar_index=7, tick_size=0.25)
    assert lv.kind == LevelKind.EXHAUST
    assert lv.price_top == 115.0
    assert lv.price_bot == 110.0


def test_from_exhaustion_infers_wick_from_direction() -> None:
    """When signal lacks a wick hint, direction chooses the facing wick."""
    bar = _make_bar(o=100.0, h=115.0, l=99.0, c=110.0)
    sig = _FakeExhaustionSignal(direction=-1, price=115.0, strength=0.5)  # wick=None
    lv = from_exhaustion(sig, bar, bar_index=1, tick_size=0.25)
    # direction=-1 → upper wick path
    assert lv.price_top == 115.0


# ---------------------------------------------------------------------------
# from_momentum / from_rejection (body geometry)
# ---------------------------------------------------------------------------

def test_from_momentum_uses_body_geometry() -> None:
    bar = _make_bar(o=100.0, h=115.0, l=99.0, c=110.0)
    r = _FakeNarrativeResult(strength=0.8, direction=+1)
    lv = from_momentum(r, bar, bar_index=3, tick_size=0.25)
    assert lv.kind == LevelKind.MOMENTUM
    assert lv.price_top == 110.0  # max(o,c)
    assert lv.price_bot == 100.0  # min(o,c)
    assert lv.direction == +1


def test_from_rejection_uses_body_geometry_and_min_width() -> None:
    # Doji: o == c → body width 0, must widen to 1 tick
    bar = _make_bar(o=100.0, h=101.0, l=99.0, c=100.0)
    r = _FakeNarrativeResult(strength=0.5, direction=0)
    lv = from_rejection(r, bar, bar_index=1, tick_size=0.25)
    assert lv.kind == LevelKind.REJECTION
    assert lv.price_top - lv.price_bot == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# from_gex (D-28 / D-29)
# ---------------------------------------------------------------------------

def test_from_gex_emits_point_levels_for_populated_fields() -> None:
    """GexLevels with 5 nonzero GEX fields + zero_gamma alias → 5 point-Levels
    (zero_gamma collapses to gamma_flip value; still emits distinct LevelKind).
    When largest_gamma_strike=0 it is skipped."""
    glv = GexLevels(
        call_wall=450.0, put_wall=440.0, gamma_flip=445.0, hvl=448.0,
        regime=GexRegime.POSITIVE_DAMPENING,
    )
    out = from_gex(glv)
    kinds = {lv.kind for lv in out}
    assert LevelKind.CALL_WALL in kinds
    assert LevelKind.PUT_WALL in kinds
    assert LevelKind.GAMMA_FLIP in kinds
    assert LevelKind.HVL in kinds
    assert LevelKind.ZERO_GAMMA in kinds  # alias of gamma_flip emits too
    assert LevelKind.LARGEST_GAMMA not in kinds  # skipped when price==0
    # Each is a point level
    for lv in out:
        assert lv.price_top == lv.price_bot


def test_from_gex_skips_zero_fields() -> None:
    glv = GexLevels(call_wall=0.0, put_wall=440.0, gamma_flip=0.0, hvl=0.0, regime=GexRegime.NEUTRAL)
    out = from_gex(glv)
    kinds = {lv.kind for lv in out}
    assert LevelKind.PUT_WALL in kinds
    assert LevelKind.CALL_WALL not in kinds
    assert LevelKind.GAMMA_FLIP not in kinds


def test_from_gex_point_levels_have_gex_source_meta() -> None:
    glv = GexLevels(call_wall=450.0, regime=GexRegime.NEUTRAL)
    out = from_gex(glv)
    call_wall = next(lv for lv in out if lv.kind == LevelKind.CALL_WALL)
    assert call_wall.meta.get("gex_source") == "call_wall"
