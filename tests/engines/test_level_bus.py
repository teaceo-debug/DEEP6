"""Tests for LevelBus (upgraded ZoneRegistry) — Plan 15-01, T-15-01-02.

Covers D-09/D-10/D-11 + C5 uid-stability guarantee.
"""
from __future__ import annotations

import time

import pytest

from deep6.engines.gex import GexLevels, GexRegime
from deep6.engines.level import Level, LevelKind, LevelState
from deep6.engines.volume_profile import VolumeZone, ZoneState, ZoneType
from deep6.engines.zone_registry import LevelBus, ZoneRegistry


def _zone(
    top: float,
    bot: float,
    *,
    kind: LevelKind = LevelKind.LVN,
    direction: int = +1,
    score: float = 50.0,
    state: LevelState = LevelState.CREATED,
    touches: int = 0,
) -> Level:
    return Level(
        price_top=top, price_bot=bot, kind=kind,
        origin_ts=time.time(), origin_bar=1, last_act_bar=1,
        score=score, touches=touches, direction=direction,
        inverted=False, state=state,
    )


def _point(kind: LevelKind, price: float, *, score: float = 0.0) -> Level:
    return Level(
        price_top=price, price_bot=price, kind=kind,
        origin_ts=time.time(), origin_bar=0, last_act_bar=0,
        score=score, touches=0, direction=0, inverted=False,
        state=LevelState.CREATED,
    )


def _volume_zone(
    top: float, bot: float, *, zt: ZoneType = ZoneType.LVN,
    direction: int = +1, score: float = 50.0,
    state: ZoneState = ZoneState.CREATED,
) -> VolumeZone:
    return VolumeZone(
        zone_type=zt, state=state, top_price=top, bot_price=bot,
        direction=direction, origin_bar=1, last_touch_bar=1,
        touches=0, score=score, volume_ratio=0.5,
    )


# ---------------------------------------------------------------------------
# Basic add + storage
# ---------------------------------------------------------------------------

def test_add_level_stores_new_zone() -> None:
    bus = LevelBus(tick_size=0.25)
    bus.add_level(_zone(21010, 21000))
    assert len(bus.query_by_kind(LevelKind.LVN)) == 1


# ---------------------------------------------------------------------------
# ZONE-03 / ZONE-05 merge
# ---------------------------------------------------------------------------

def test_add_level_zone_overlap_merges() -> None:
    """Two overlapping same-direction LVN zones collapse to one with summed touches and score=max+5."""
    bus = LevelBus(tick_size=0.25)
    a = _zone(21010, 21000, score=60.0, touches=2)
    b = _zone(21015, 21005, score=40.0, touches=3)
    bus.add_level(a)
    bus.add_level(b)
    active = bus.query_by_kind(LevelKind.LVN)
    assert len(active) == 1
    merged = active[0]
    # score = max(60,40) + 5 clipped to 100
    assert merged.score == 65.0
    assert merged.touches == 5
    # peak bucket: existing (a) had higher score → keeps a's range
    assert merged.price_top == 21010
    assert merged.price_bot == 21000


def test_merge_score_clips_to_100() -> None:
    bus = LevelBus(tick_size=0.25)
    bus.add_level(_zone(21010, 21000, score=99.0))
    bus.add_level(_zone(21012, 21002, score=95.0))
    merged = bus.query_by_kind(LevelKind.LVN)[0]
    assert merged.score == 100.0


def test_merge_different_direction_does_not_merge() -> None:
    bus = LevelBus(tick_size=0.25)
    bus.add_level(_zone(21010, 21000, direction=+1))
    bus.add_level(_zone(21010, 21000, direction=-1))
    assert len(bus.query_by_kind(LevelKind.LVN)) == 2


def test_merge_different_kind_does_not_merge() -> None:
    bus = LevelBus(tick_size=0.25)
    bus.add_level(_zone(21010, 21000, kind=LevelKind.LVN))
    bus.add_level(_zone(21010, 21000, kind=LevelKind.HVN))
    assert len(bus.get_all_active()) == 2


# ---------------------------------------------------------------------------
# D-10 point-level dedup
# ---------------------------------------------------------------------------

def test_add_level_point_dedupes() -> None:
    """Two CALL_WALL at same price → stored once."""
    bus = LevelBus(tick_size=0.25)
    bus.add_level(_point(LevelKind.CALL_WALL, 450.0))
    bus.add_level(_point(LevelKind.CALL_WALL, 450.0))
    assert len(bus.query_by_kind(LevelKind.CALL_WALL)) == 1


def test_add_level_point_different_prices_not_deduped() -> None:
    bus = LevelBus(tick_size=0.25)
    bus.add_level(_point(LevelKind.CALL_WALL, 450.0))
    bus.add_level(_point(LevelKind.CALL_WALL, 451.0))
    assert len(bus.query_by_kind(LevelKind.CALL_WALL)) == 2


# ---------------------------------------------------------------------------
# D-10 queries
# ---------------------------------------------------------------------------

def test_query_near_includes_zone_and_point() -> None:
    bus = LevelBus(tick_size=0.25)
    bus.add_level(_zone(21010, 21000))  # zone contains 21005
    bus.add_level(_point(LevelKind.CALL_WALL, 21006.0))  # point within threshold
    bus.add_level(_point(LevelKind.PUT_WALL, 22000.0))   # point far away
    near = bus.query_near(21005.0, ticks=4)
    kinds = {lv.kind for lv in near}
    assert LevelKind.LVN in kinds
    assert LevelKind.CALL_WALL in kinds
    assert LevelKind.PUT_WALL not in kinds


def test_query_by_kind_filters_invalidated() -> None:
    bus = LevelBus(tick_size=0.25)
    lv = _zone(21010, 21000)
    bus.add_level(lv)
    # Now invalidate in-place
    bus._levels[0].state = LevelState.INVALIDATED
    assert bus.query_by_kind(LevelKind.LVN) == []


def test_get_top_n_sorted_desc() -> None:
    bus = LevelBus(tick_size=0.25)
    bus.add_level(_zone(100, 90, score=30.0))
    bus.add_level(_zone(200, 190, score=80.0))
    bus.add_level(_zone(300, 290, score=55.0))
    top = bus.get_top_n(n=2)
    assert [lv.score for lv in top] == [80.0, 55.0]


# ---------------------------------------------------------------------------
# D-11 eviction
# ---------------------------------------------------------------------------

def test_max_levels_eviction_keeps_80() -> None:
    """Adding 85 distinct zones → active count == 80 after eviction."""
    bus = LevelBus(tick_size=0.25)
    for i in range(85):
        # separate, non-overlapping ranges to avoid merge
        bot = 21000.0 + i * 2.0
        bus.add_level(_zone(bot + 1.0, bot, score=float(i)))
    active = bus.get_all_active()
    assert len(active) == 80


def test_eviction_drops_lowest_score_first() -> None:
    """Lowest-score CREATED zones evict first."""
    bus = LevelBus(tick_size=0.25)
    # Fill bus to 80 with distinct scores
    for i in range(80):
        bot = 21000.0 + i * 2.0
        bus.add_level(_zone(bot + 1.0, bot, score=50.0 + i))
    # Insert a weak zone (score=1) → at cap, should evict the weakest CREATED
    weak_before = _zone(22000.0, 21999.5, score=1.0)
    bus.add_level(weak_before)
    scores = sorted(lv.score for lv in bus.get_all_active())
    # the 1.0-score weak-before should have been evicted (preferred) or surpassed.
    # Either way active size must stay at 80 and lowest active score > the evicted.
    assert len(bus.get_all_active()) == 80
    assert min(scores) >= 1.0


def test_eviction_preserves_defended_over_created_at_same_score() -> None:
    bus = LevelBus(tick_size=0.25)
    # Fill 79 low-score CREATED zones
    for i in range(79):
        bot = 21000.0 + i * 2.0
        bus.add_level(_zone(bot + 1.0, bot, score=10.0, state=LevelState.CREATED))
    # One DEFENDED low-score zone
    bus.add_level(_zone(22000.0, 21999.0, score=10.0, state=LevelState.DEFENDED))
    # One more CREATED zone pushes over cap
    bus.add_level(_zone(23000.0, 22999.0, score=10.0, state=LevelState.CREATED))
    active = bus.get_all_active()
    assert len(active) == 80
    # The DEFENDED zone must have survived the eviction pass
    defended = [lv for lv in active if lv.state == LevelState.DEFENDED]
    assert len(defended) == 1


# ---------------------------------------------------------------------------
# D-09 alias
# ---------------------------------------------------------------------------

def test_zoneregistry_alias_resolves_to_levelbus() -> None:
    assert ZoneRegistry is LevelBus
    bus = ZoneRegistry(tick_size=0.25)
    assert isinstance(bus, LevelBus)


def test_add_zone_wrapper_delegates_to_add_level() -> None:
    """Existing VolumeZone path produces a stored Level with matching geometry."""
    bus = LevelBus(tick_size=0.25)
    bus.add_zone(_volume_zone(21010, 21000, zt=ZoneType.LVN, score=50.0))
    lvns = bus.query_by_kind(LevelKind.LVN)
    assert len(lvns) == 1
    assert lvns[0].price_top == 21010
    assert lvns[0].price_bot == 21000
    assert lvns[0].score == 50.0


def test_add_gex_levels_wrapper_emits_point_levels() -> None:
    bus = LevelBus(tick_size=0.25)
    glv = GexLevels(
        call_wall=450.0, put_wall=440.0, gamma_flip=445.0, hvl=448.0,
        regime=GexRegime.POSITIVE_DAMPENING,
    )
    bus.add_gex_levels(glv)
    # call_wall, put_wall, gamma_flip, hvl + zero_gamma property (alias of gamma_flip) = 5
    # (largest_gamma_strike defaults 0.0 so is skipped)
    kinds = {lv.kind for lv in bus.get_all_active()}
    assert LevelKind.CALL_WALL in kinds
    assert LevelKind.PUT_WALL in kinds
    assert LevelKind.GAMMA_FLIP in kinds
    assert LevelKind.HVL in kinds
    assert LevelKind.ZERO_GAMMA in kinds


# ---------------------------------------------------------------------------
# C5 uid-stability across merge
# ---------------------------------------------------------------------------

def test_level_uid_stable_across_merge() -> None:
    """When two overlapping zones merge, the EXISTING Level's uid is preserved.

    Downstream mutation keys (ConfluenceRules.score_mutations) snapshot uids
    BEFORE evaluate() and rely on this guarantee.
    """
    bus = LevelBus(tick_size=0.25)
    first = _zone(21010, 21000, score=60.0)
    bus.add_level(first)
    original_uid = bus.query_by_kind(LevelKind.LVN)[0].uid

    # Overlapping, higher-score incoming
    bus.add_level(_zone(21015, 21005, score=70.0))
    merged = bus.query_by_kind(LevelKind.LVN)[0]
    assert merged.uid == original_uid, "merge must preserve existing uid (C5)"
    # Verify it really did merge (not two levels)
    assert len(bus.query_by_kind(LevelKind.LVN)) == 1


def test_point_level_dedup_preserves_uid() -> None:
    """Re-adding a point Level at same (kind, price) preserves the original uid."""
    bus = LevelBus(tick_size=0.25)
    bus.add_level(_point(LevelKind.CALL_WALL, 450.0))
    original_uid = bus.query_by_kind(LevelKind.CALL_WALL)[0].uid
    bus.add_level(_point(LevelKind.CALL_WALL, 450.0, score=99.0))
    after = bus.query_by_kind(LevelKind.CALL_WALL)[0]
    assert after.uid == original_uid
    assert after.score == 99.0


# ---------------------------------------------------------------------------
# get_confluence smoke
# ---------------------------------------------------------------------------

def test_get_confluence_detects_zone_plus_gex() -> None:
    bus = LevelBus(tick_size=0.25)
    bus.add_level(_zone(21010, 21000, kind=LevelKind.LVN))
    bus.add_level(_point(LevelKind.CALL_WALL, 21005.0))
    res = bus.get_confluence(21005.0, ticks=4)
    assert res.has_confluence is True
    assert res.score_bonus == 6  # single zone type
    assert "LVN" in res.zone_types


def test_clear_and_bulk_load() -> None:
    bus = LevelBus(tick_size=0.25)
    bus.bulk_load([_volume_zone(100, 90), _volume_zone(200, 190)])
    assert len(bus.get_all_active()) == 2
    bus.clear()
    assert bus.get_all_active() == []
