"""Tests for ZoneRegistry — merge, confluence, get_near_price (ZONE-01..05)."""
from __future__ import annotations

import time

import pytest

from deep6.engines.gex import GexLevels, GexRegime
from deep6.engines.volume_profile import VolumeZone, ZoneState, ZoneType
from deep6.engines.zone_registry import ZoneRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_zone(
    top: float,
    bot: float,
    zone_type: ZoneType = ZoneType.LVN,
    direction: int = +1,
    score: float = 50.0,
    state: ZoneState = ZoneState.CREATED,
) -> VolumeZone:
    return VolumeZone(
        zone_type=zone_type,
        state=state,
        top_price=top,
        bot_price=bot,
        direction=direction,
        origin_bar=1,
        last_touch_bar=1,
        touches=0,
        score=score,
        volume_ratio=0.5,
    )


def make_gex_levels(
    call_wall: float = 0.0,
    put_wall: float = 0.0,
    gamma_flip: float = 0.0,
    hvl: float = 0.0,
) -> GexLevels:
    return GexLevels(
        call_wall=call_wall,
        put_wall=put_wall,
        gamma_flip=gamma_flip,
        hvl=hvl,
        regime=GexRegime.POSITIVE_DAMPENING,
        net_gex_at_spot=5e9,
        timestamp=time.time(),
        stale=False,
    )


# ---------------------------------------------------------------------------
# ZONE-01: Add / get_near_price
# ---------------------------------------------------------------------------

def test_add_zone_no_overlap():
    """Two non-overlapping zones → 2 active zones."""
    reg = ZoneRegistry()
    reg.add_zone(make_zone(top=100.50, bot=100.00))
    reg.add_zone(make_zone(top=102.50, bot=102.00))
    assert len(reg.get_all_active()) == 2


def test_get_near_price():
    """Zone midpoint at 100.0, query get_near_price(100.25, ticks=4) → zone included."""
    reg = ZoneRegistry()
    # Zone midpoint = (100.25 + 99.75) / 2 = 100.0
    reg.add_zone(make_zone(top=100.25, bot=99.75))
    # Query at 100.25: |100.25 - 100.0| = 0.25 <= 4*0.25=1.0 → included
    nearby = reg.get_near_price(100.25, ticks=4)
    assert len(nearby) == 1


def test_get_near_price_too_far():
    """Zone midpoint at 100.0, query at 105.0 with ticks=2 → not included."""
    reg = ZoneRegistry()
    reg.add_zone(make_zone(top=100.25, bot=99.75))
    nearby = reg.get_near_price(105.0, ticks=2)
    assert len(nearby) == 0


# ---------------------------------------------------------------------------
# ZONE-03: Same-type same-direction merge
# ---------------------------------------------------------------------------

def test_zone_merge_overlap():
    """Two overlapping same-type same-direction zones → 1 merged zone, score = max+5."""
    reg = ZoneRegistry()
    z1 = make_zone(top=100.50, bot=100.00, score=40.0)
    z2 = make_zone(top=100.75, bot=100.25, score=60.0)  # overlaps z1
    reg.add_zone(z1)
    reg.add_zone(z2)
    active = reg.get_all_active()
    assert len(active) == 1
    # score = max(40, 60) + 5 = 65
    assert abs(active[0].score - 65.0) < 0.1


def test_zone_no_merge_different_direction():
    """Same type, different direction — no merge → 2 separate zones."""
    reg = ZoneRegistry()
    z1 = make_zone(top=100.50, bot=100.00, direction=+1)
    z2 = make_zone(top=100.75, bot=100.25, direction=-1)
    reg.add_zone(z1)
    reg.add_zone(z2)
    assert len(reg.get_all_active()) == 2


def test_zone_no_merge_different_type():
    """LVN vs HVN overlapping — no merge → 2 separate zones."""
    reg = ZoneRegistry()
    z1 = make_zone(top=100.50, bot=100.00, zone_type=ZoneType.LVN)
    z2 = make_zone(top=100.75, bot=100.25, zone_type=ZoneType.HVN)
    reg.add_zone(z1)
    reg.add_zone(z2)
    assert len(reg.get_all_active()) == 2


# ---------------------------------------------------------------------------
# ZONE-05: Peak bucket — stronger zone's range used
# ---------------------------------------------------------------------------

def test_peak_bucket_keeps_stronger_range():
    """When incoming has higher score, merged zone uses incoming zone's range."""
    reg = ZoneRegistry()
    z1 = make_zone(top=100.50, bot=100.00, score=30.0)   # weaker
    z2 = make_zone(top=100.75, bot=100.25, score=70.0)   # stronger (incoming)
    reg.add_zone(z1)
    reg.add_zone(z2)
    active = reg.get_all_active()
    assert len(active) == 1
    # Incoming (z2) had higher score → its range is used
    assert active[0].top_price == 100.75
    assert active[0].bot_price == 100.25


def test_peak_bucket_keeps_existing_range_when_weaker():
    """When incoming has lower score, merged zone keeps existing range."""
    reg = ZoneRegistry()
    z1 = make_zone(top=100.50, bot=100.00, score=80.0)   # stronger (existing)
    z2 = make_zone(top=100.75, bot=100.25, score=30.0)   # weaker (incoming)
    reg.add_zone(z1)
    reg.add_zone(z2)
    active = reg.get_all_active()
    assert len(active) == 1
    # Existing (z1) had higher score → its range is kept
    assert active[0].top_price == 100.50
    assert active[0].bot_price == 100.00


# ---------------------------------------------------------------------------
# ZONE-02: Confluence
# ---------------------------------------------------------------------------

def test_confluence_zone_and_gex():
    """VolumeZone near 100.0 + GexLevels(call_wall=100.0) → has_confluence=True, bonus=6."""
    reg = ZoneRegistry()
    # Zone midpoint at 100.0
    reg.add_zone(make_zone(top=100.25, bot=99.75))
    # GEX call wall at 100.0 (in QQQ units — same scale as zone prices here)
    reg.add_gex_levels(make_gex_levels(call_wall=100.0))
    result = reg.get_confluence(price=100.0, ticks=4)
    assert result.has_confluence is True
    assert result.score_bonus == 6


def test_confluence_no_gex():
    """VolumeZone near 100.0, no GEX loaded → has_confluence=False."""
    reg = ZoneRegistry()
    reg.add_zone(make_zone(top=100.25, bot=99.75))
    result = reg.get_confluence(price=100.0, ticks=4)
    assert result.has_confluence is False


def test_confluence_multi_type_bonus():
    """LVN + HVN both near price + GEX → score_bonus=8 (multi-type)."""
    reg = ZoneRegistry()
    reg.add_zone(make_zone(top=100.25, bot=99.75, zone_type=ZoneType.LVN))
    reg.add_zone(make_zone(top=100.50, bot=100.00, zone_type=ZoneType.HVN))
    reg.add_gex_levels(make_gex_levels(call_wall=100.0))
    result = reg.get_confluence(price=100.0, ticks=4)
    assert result.has_confluence is True
    assert result.score_bonus == 8


# ---------------------------------------------------------------------------
# Bulk operations
# ---------------------------------------------------------------------------

def test_bulk_load():
    """bulk_load([z1, z2]) with non-overlapping → 2 active zones."""
    reg = ZoneRegistry()
    zones = [
        make_zone(top=100.50, bot=100.00),
        make_zone(top=103.00, bot=102.50),
    ]
    reg.bulk_load(zones)
    assert len(reg.get_all_active()) == 2


def test_clear():
    """After clear(), get_all_active() returns empty list."""
    reg = ZoneRegistry()
    reg.add_zone(make_zone(top=100.50, bot=100.00))
    reg.add_zone(make_zone(top=103.00, bot=102.50))
    reg.clear()
    assert reg.get_all_active() == []
