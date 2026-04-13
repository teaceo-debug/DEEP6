"""Tests for SessionProfile — LVN/HVN detection, zone FSM, decay, scoring (VPRO-01..08)."""
from __future__ import annotations

from collections import defaultdict

import pytest

from deep6.engines.signal_config import VolumeProfileConfig
from deep6.engines.volume_profile import SessionProfile, VolumeZone, ZoneState, ZoneType
from deep6.state.footprint import FootprintBar, FootprintLevel, price_to_tick, tick_to_price


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_levels(price_vol_pairs: list[tuple[float, int, int]]) -> dict[int, FootprintLevel]:
    levels = {}
    for price, bid, ask in price_vol_pairs:
        levels[price_to_tick(price)] = FootprintLevel(bid_vol=bid, ask_vol=ask)
    return levels


def make_bar(
    open_: float = 100.0,
    high: float = 100.75,
    low: float = 99.75,
    close: float = 100.5,
    poc_price: float = 100.25,
    levels: dict | None = None,
) -> FootprintBar:
    if levels is None:
        levels = make_levels([(100.0, 50, 100), (100.25, 80, 120)])
    total = sum(lv.bid_vol + lv.ask_vol for lv in levels.values())
    return FootprintBar(
        open=open_, high=high, low=low, close=close,
        total_vol=total, poc_price=poc_price,
        bar_range=high - low, levels=levels,
    )


def build_profile_with_volume(avg_vol: int = 50, num_ticks: int = 20) -> SessionProfile:
    """Create a SessionProfile with uniform volume across ticks (for zone detection).

    We need bar_count >= 5 before detect_zones() works.
    """
    sp = SessionProfile()
    # Feed 5+ bars with uniform volume across num_ticks price levels
    base_price = 100.0
    for bar_i in range(6):
        pairs = [(base_price + i * 0.25, avg_vol // 2, avg_vol // 2) for i in range(num_ticks)]
        lvls = make_levels(pairs)
        bar = make_bar(
            open_=base_price, high=base_price + num_ticks * 0.25,
            low=base_price, close=base_price + num_ticks * 0.25 * 0.5,
            poc_price=base_price + num_ticks * 0.25 * 0.25, levels=lvls
        )
        sp.add_bar(bar)
    return sp


# ---------------------------------------------------------------------------
# VPRO-02: LVN Detection
# ---------------------------------------------------------------------------

def test_lvn_detection():
    """Consecutive thin bins (vol << avg) are detected as LVN zone.

    LVN requires min_zone_ticks=2 — two adjacent qualifying bins.
    5/50 = 10% which is well below the 30% LVN threshold.
    """
    sp = SessionProfile()
    base = 100.0
    avg_vol = 50

    # 6 bars to get bar_count >= 5 for detect_zones()
    for bar_i in range(6):
        # Build 20 ticks with avg volume, two consecutive thin ticks at 100.75 and 101.00
        pairs = []
        for i in range(20):
            price = base + i * 0.25
            if price in (100.75, 101.00):
                # Very low volume — LVN candidate (2 consecutive = meets min_zone_ticks=2)
                pairs.append((price, 2, 3))  # vol=5 << avg=50
            else:
                pairs.append((price, avg_vol // 2, avg_vol // 2))
        lvls = make_levels(pairs)
        bar = make_bar(
            open_=base, high=base + 5.0, low=base, close=base + 2.5,
            poc_price=base + 1.25, levels=lvls,
        )
        sp.add_bar(bar)

    zones = sp.detect_zones(current_price=base + 2.5)
    lvn_zones = [z for z in zones if z.zone_type == ZoneType.LVN]
    assert len(lvn_zones) >= 1, f"Expected at least one LVN zone, found {len(zones)} total zones"


# ---------------------------------------------------------------------------
# VPRO-03: HVN Detection
# ---------------------------------------------------------------------------

def test_hvn_detection():
    """Consecutive heavy bins (vol >> avg) are detected as HVN zone.

    HVN requires min_zone_ticks=2 — two adjacent qualifying bins.
    200/50 = 400% which is well above the 170% HVN threshold.
    """
    sp = SessionProfile()
    base = 100.0
    avg_vol = 50

    for bar_i in range(6):
        pairs = []
        for i in range(20):
            price = base + i * 0.25
            if price in (102.0, 102.25):
                # Very high volume — HVN candidate (2 consecutive ticks)
                pairs.append((price, 100, 100))  # vol=200 >> avg≈50
            else:
                pairs.append((price, avg_vol // 2, avg_vol // 2))
        lvls = make_levels(pairs)
        bar = make_bar(
            open_=base, high=base + 5.0, low=base, close=base + 2.5,
            poc_price=base + 1.25, levels=lvls,
        )
        sp.add_bar(bar)

    zones = sp.detect_zones(current_price=base + 2.5)
    hvn_zones = [z for z in zones if z.zone_type == ZoneType.HVN]
    assert len(hvn_zones) >= 1, f"Expected at least one HVN zone, found {len(zones)} total zones"


# ---------------------------------------------------------------------------
# VPRO-04: Zone FSM
# ---------------------------------------------------------------------------

def _make_simple_zone(top: float, bot: float, direction: int = +1) -> VolumeZone:
    """Create a VolumeZone for FSM testing."""
    return VolumeZone(
        zone_type=ZoneType.LVN,
        state=ZoneState.CREATED,
        top_price=top,
        bot_price=bot,
        direction=direction,
        origin_bar=1,
        last_touch_bar=1,
        score=50.0,
    )


def test_zone_fsm_defended():
    """Bar high/low touches zone but close doesn't break → state=DEFENDED, touches+=1."""
    sp = SessionProfile()
    # Zone: support from 99.75 to 100.25, direction=+1 (support, below price)
    zone = _make_simple_zone(top=100.25, bot=99.75, direction=+1)
    sp.zones.append(zone)
    sp.bar_count = 5

    # Bar that wicks into zone but closes above (holds as support)
    bar = make_bar(
        open_=100.50, high=101.00, low=99.90, close=100.50,
        poc_price=100.50,
    )
    events = sp.update_zones(bar, bar_index=6)
    assert zone.state == ZoneState.DEFENDED
    assert zone.touches >= 1


def test_zone_fsm_flipped():
    """Bar close through support boundary → state=FLIPPED, direction inverted."""
    sp = SessionProfile()
    # Zone: support from 99.75 to 100.25, direction=+1 (support)
    zone = _make_simple_zone(top=100.25, bot=99.75, direction=+1)
    sp.zones.append(zone)
    sp.bar_count = 5

    # Bar that closes BELOW zone bot (breaks support)
    bar = make_bar(
        open_=100.50, high=100.50, low=99.50, close=99.50,
        poc_price=100.00,
    )
    events = sp.update_zones(bar, bar_index=6)
    assert zone.state == ZoneState.FLIPPED
    assert zone.direction == -1  # was +1, now inverted


def test_zone_fsm_invalidated():
    """Second break after flip → state=INVALIDATED."""
    sp = SessionProfile()
    # Zone already flipped once (now resistance, direction=-1, inverted=True)
    zone = _make_simple_zone(top=100.25, bot=99.75, direction=-1)
    zone.state = ZoneState.FLIPPED
    zone.inverted = True
    sp.zones.append(zone)
    sp.bar_count = 5

    # Bar that closes ABOVE zone top (breaks resistance — second break)
    bar = make_bar(
        open_=99.50, high=100.50, low=99.50, close=100.50,
        poc_price=100.00,
    )
    events = sp.update_zones(bar, bar_index=6)
    assert zone.state == ZoneState.INVALIDATED


# ---------------------------------------------------------------------------
# VPRO-05: Zone Scoring
# ---------------------------------------------------------------------------

def test_zone_scoring_initial():
    """New LVN and HVN zones both have score > 0."""
    sp = SessionProfile()
    base = 100.0
    avg_vol = 50

    for _ in range(6):
        pairs = []
        for i in range(20):
            price = base + i * 0.25
            if price == 100.75:
                pairs.append((price, 1, 2))   # LVN: vol=3 << avg
            elif price == 103.0:
                pairs.append((price, 100, 100))  # HVN: vol=200 >> avg
            else:
                pairs.append((price, avg_vol // 2, avg_vol // 2))
        lvls = make_levels(pairs)
        bar = make_bar(
            open_=base, high=base + 5.0, low=base, close=base + 2.5,
            poc_price=base + 1.25, levels=lvls,
        )
        sp.add_bar(bar)

    zones = sp.detect_zones(current_price=base + 2.5)
    for z in zones:
        assert z.score > 0, f"Zone {z.zone_type.name} has score=0"


def test_zone_decay():
    """Zone score decreases after many bars without interaction."""
    sp = SessionProfile()
    zone = _make_simple_zone(top=200.0, bot=199.75, direction=+1)  # far from test bar
    zone.score = 80.0
    sp.zones.append(zone)
    sp.bar_count = 10

    # Process many bars that don't touch the zone
    for idx in range(11, 61):
        bar = make_bar(open_=100.0, high=101.0, low=99.75, close=100.5)
        sp.update_zones(bar, bar_index=idx)

    assert zone.score < 80.0, f"Expected score decay, got {zone.score}"


# ---------------------------------------------------------------------------
# VPRO-07: Multi-session decay
# ---------------------------------------------------------------------------

def test_multi_session_decay():
    """SessionProfile(prior_bins={tick: 1000.0}) → bins[tick] ≈ 700.0."""
    tick = price_to_tick(100.0)
    sp = SessionProfile(prior_bins={tick: 1000.0})
    assert abs(sp.bins[tick] - 700.0) < 1.0, f"Expected ~700.0, got {sp.bins[tick]}"


def test_multi_session_accumulates():
    """After add_bar(), new volume adds on top of decayed prior."""
    tick = price_to_tick(100.0)
    sp = SessionProfile(prior_bins={tick: 1000.0})
    initial = sp.bins[tick]  # ~700.0

    # Add a bar with volume at the same tick
    lvls = {tick: FootprintLevel(bid_vol=50, ask_vol=50)}
    bar = make_bar(levels=lvls)
    sp.add_bar(bar)

    assert sp.bins[tick] > initial, "Volume should have accumulated on top of decayed prior"
    assert abs(sp.bins[tick] - (initial + 100)) < 1.0


# ---------------------------------------------------------------------------
# Config threshold override
# ---------------------------------------------------------------------------

def test_config_thresholds():
    """VolumeProfileConfig(lvn_threshold=0.20) → zones only detected at < 20%."""
    config = VolumeProfileConfig(lvn_threshold=0.20)
    sp = SessionProfile(config=config)
    base = 100.0
    avg_vol = 50

    for _ in range(6):
        pairs = []
        for i in range(20):
            price = base + i * 0.25
            if price == 100.75:
                # vol ratio = 15/50 = 30% — above 20% threshold, should NOT be LVN
                pairs.append((price, 7, 8))   # vol≈15
            else:
                pairs.append((price, avg_vol // 2, avg_vol // 2))
        lvls = make_levels(pairs)
        bar = make_bar(
            open_=base, high=base + 5.0, low=base, close=base + 2.5,
            poc_price=base + 1.25, levels=lvls,
        )
        sp.add_bar(bar)

    zones = sp.detect_zones(current_price=base + 2.5)
    # The 30%-ratio tick should not be flagged as LVN with 20% threshold
    # (it would be flagged with default 30% threshold)
    lvn_zones = [z for z in zones if z.zone_type == ZoneType.LVN]
    # All LVN zones should be well under 20% ratio
    for z in lvn_zones:
        assert z.volume_ratio < 0.20, f"LVN zone has ratio {z.volume_ratio:.2f} > threshold 0.20"
