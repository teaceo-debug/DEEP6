"""LVN/HVN Volume Profile with Zone Lifecycle FSM.

Session volume profile built from FootprintBar history. Detects:
- LVN (Low Volume Nodes): bins < 30% of average — liquidity vacuums, price accelerates through
- HVN (High Volume Nodes): bins > 170% of average — acceptance zones, price gravitates to

Zone Lifecycle (VPRO-04):
  Created → Defended → Broken → Flipped → Invalidated

Zone Scoring (VPRO-05):
  score = type_weight(0.35) + recency(0.25) + touches(0.25) + defense(0.15)

Per user: "LVN is extremely reactive in my testing" — LVN zones get priority treatment.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import numpy as np

from deep6.state.footprint import FootprintBar, price_to_tick, tick_to_price


class ZoneState(Enum):
    CREATED = auto()
    DEFENDED = auto()
    BROKEN = auto()
    FLIPPED = auto()
    INVALIDATED = auto()


class ZoneType(Enum):
    LVN = auto()
    HVN = auto()


@dataclass
class VolumeZone:
    """A detected LVN or HVN zone with lifecycle state."""
    zone_type: ZoneType
    state: ZoneState
    top_price: float
    bot_price: float
    direction: int           # +1 = support, -1 = resistance (for LVN)
    origin_bar: int          # bar index when created
    last_touch_bar: int      # bar index of last interaction
    touches: int = 0         # successful defense count
    score: float = 0.0       # composite strength 0-100
    volume_ratio: float = 0.0  # how thin (LVN) or thick (HVN) relative to average
    inverted: bool = False   # True if zone has been flipped once


@dataclass
class SessionProfile:
    """Maintains cumulative session volume profile and zone registry."""
    tick_size: float = 0.25
    bins: dict[int, float] = field(default_factory=lambda: defaultdict(float))
    zones: list[VolumeZone] = field(default_factory=list)
    bar_count: int = 0

    # Detection thresholds
    lvn_threshold: float = 0.30   # bins < 30% of average = LVN
    hvn_threshold: float = 1.70   # bins > 170% of average = HVN
    min_zone_ticks: int = 2       # minimum zone width in ticks
    max_zones: int = 80           # cap on active zones

    # Scoring weights (VPRO-05)
    w_type: float = 0.35
    w_recency: float = 0.25
    w_touches: float = 0.25
    w_defense: float = 0.15

    # Decay
    zone_decay_rate: float = 0.005  # per bar (~140 bar half-life)

    def add_bar(self, bar: FootprintBar) -> None:
        """Accumulate one bar's volume into the session profile."""
        for tick, level in bar.levels.items():
            self.bins[tick] += level.ask_vol + level.bid_vol
        self.bar_count += 1

    def detect_zones(self, current_price: float) -> list[VolumeZone]:
        """Scan profile for LVN and HVN zones. Returns newly created zones."""
        if not self.bins or self.bar_count < 5:
            return []

        ticks = sorted(self.bins.keys())
        volumes = np.array([self.bins[t] for t in ticks], dtype=np.float64)
        avg_vol = volumes.mean()

        if avg_vol == 0:
            return []

        new_zones: list[VolumeZone] = []

        # --- LVN Detection (VPRO-02) ---
        lvn_mask = volumes < avg_vol * self.lvn_threshold
        new_zones.extend(
            self._merge_zones(ticks, volumes, lvn_mask, ZoneType.LVN, current_price, avg_vol)
        )

        # --- HVN Detection (VPRO-03) ---
        hvn_mask = volumes > avg_vol * self.hvn_threshold
        new_zones.extend(
            self._merge_zones(ticks, volumes, hvn_mask, ZoneType.HVN, current_price, avg_vol)
        )

        return new_zones

    def _merge_zones(
        self, ticks: list[int], volumes: np.ndarray, mask: np.ndarray,
        zone_type: ZoneType, current_price: float, avg_vol: float,
    ) -> list[VolumeZone]:
        """Merge adjacent qualifying bins into zones."""
        new_zones: list[VolumeZone] = []
        run_start = None

        for i, qualifies in enumerate(mask):
            if qualifies:
                if run_start is None:
                    run_start = i
            else:
                if run_start is not None:
                    run_len = i - run_start
                    if run_len >= self.min_zone_ticks:
                        zone = self._create_zone(
                            ticks, volumes, run_start, i, zone_type, current_price, avg_vol
                        )
                        if zone and not self._overlaps_existing(zone):
                            new_zones.append(zone)
                            self.zones.append(zone)
                    run_start = None

        # Handle run at end
        if run_start is not None:
            run_len = len(ticks) - run_start
            if run_len >= self.min_zone_ticks:
                zone = self._create_zone(
                    ticks, volumes, run_start, len(ticks), zone_type, current_price, avg_vol
                )
                if zone and not self._overlaps_existing(zone):
                    new_zones.append(zone)
                    self.zones.append(zone)

        return new_zones

    def _create_zone(
        self, ticks: list[int], volumes: np.ndarray,
        start_idx: int, end_idx: int, zone_type: ZoneType,
        current_price: float, avg_vol: float,
    ) -> VolumeZone | None:
        """Create a VolumeZone from a run of qualifying bins."""
        bot_price = tick_to_price(ticks[start_idx])
        top_price = tick_to_price(ticks[end_idx - 1]) + self.tick_size
        mid_price = (top_price + bot_price) / 2
        zone_vol = float(volumes[start_idx:end_idx].mean())

        # Direction: above price = resistance, below = support
        direction = +1 if mid_price < current_price else -1

        return VolumeZone(
            zone_type=zone_type,
            state=ZoneState.CREATED,
            top_price=top_price,
            bot_price=bot_price,
            direction=direction,
            origin_bar=self.bar_count,
            last_touch_bar=self.bar_count,
            volume_ratio=zone_vol / avg_vol if avg_vol > 0 else 0,
            score=self._initial_score(zone_type, zone_vol, avg_vol),
        )

    def _initial_score(self, zone_type: ZoneType, vol: float, avg: float) -> float:
        """Compute initial zone score."""
        if zone_type == ZoneType.LVN:
            type_pts = self.w_type * 100 * (1.0 - min(vol / avg, 1.0))  # thinner = higher
        else:
            type_pts = self.w_type * 100 * min(vol / avg / 3.0, 1.0)    # thicker = higher
        recency_pts = self.w_recency * 100  # brand new = full recency
        return type_pts + recency_pts

    def _overlaps_existing(self, zone: VolumeZone) -> bool:
        """Check if zone overlaps any existing same-type zone."""
        for z in self.zones:
            if z.zone_type == zone.zone_type and z.state != ZoneState.INVALIDATED:
                if z.top_price >= zone.bot_price and z.bot_price <= zone.top_price:
                    return True
        return False

    def update_zones(self, bar: FootprintBar, bar_index: int) -> list[str]:
        """Update zone lifecycle based on current bar. Returns event descriptions."""
        events: list[str] = []

        for zone in self.zones:
            if zone.state == ZoneState.INVALIDATED:
                continue

            # Decay score over time
            bars_ago = bar_index - zone.last_touch_bar
            zone.score *= (1.0 - self.zone_decay_rate) ** max(bars_ago - 1, 0)

            # Check if bar interacts with zone
            touches_zone = bar.high >= zone.bot_price and bar.low <= zone.top_price

            if not touches_zone:
                continue

            # Break: close through zone boundary with conviction
            close_through = (zone.direction == +1 and bar.close < zone.bot_price) or \
                           (zone.direction == -1 and bar.close > zone.top_price)

            if close_through:
                if zone.inverted:
                    # Second break — invalidate
                    zone.state = ZoneState.INVALIDATED
                    events.append(f"ZONE INVALIDATED: {zone.zone_type.name} "
                                  f"{zone.bot_price:.2f}-{zone.top_price:.2f} broken twice")
                else:
                    # First break — flip
                    zone.state = ZoneState.FLIPPED
                    zone.direction *= -1
                    zone.inverted = True
                    zone.last_touch_bar = bar_index
                    events.append(f"ZONE FLIPPED: {zone.zone_type.name} "
                                  f"{zone.bot_price:.2f}-{zone.top_price:.2f} → "
                                  f"{'support' if zone.direction > 0 else 'resistance'}")
            else:
                # Touch but held — defense
                zone.touches += 1
                zone.last_touch_bar = bar_index
                touch_pts = self.w_touches * 100 * min(zone.touches / 3.0, 1.0)
                defense_pts = self.w_defense * 100
                zone.score = min(zone.score + touch_pts * 0.1 + defense_pts * 0.1, 100.0)

                if zone.state in (ZoneState.CREATED, ZoneState.FLIPPED):
                    zone.state = ZoneState.DEFENDED
                events.append(f"ZONE DEFENDED x{zone.touches}: {zone.zone_type.name} "
                              f"{zone.bot_price:.2f}-{zone.top_price:.2f} "
                              f"(score={zone.score:.1f})")

        # Evict lowest-scoring zones if over capacity
        active = [z for z in self.zones if z.state != ZoneState.INVALIDATED]
        if len(active) > self.max_zones:
            active.sort(key=lambda z: z.score)
            for z in active[:len(active) - self.max_zones]:
                z.state = ZoneState.INVALIDATED

        return events

    def get_active_zones(self, min_score: float = 0.0) -> list[VolumeZone]:
        """Return all non-invalidated zones above min_score."""
        return [
            z for z in self.zones
            if z.state != ZoneState.INVALIDATED and z.score >= min_score
        ]

    def reset(self) -> None:
        """Reset for new session."""
        self.bins.clear()
        self.zones.clear()
        self.bar_count = 0
