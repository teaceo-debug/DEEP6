"""Centralized ZoneRegistry — consolidates all zone types for Phase 5 confluence scoring.

Manages VolumeZone (LVN/HVN from SessionProfile), GEX price levels (call wall, put wall,
gamma flip, HVL), and absorption/exhaustion zone annotations.

Per ZONE-01..05:
  ZONE-01: Single store for all zone types
  ZONE-02: Cross-type confluence scoring
  ZONE-03: Same-type same-direction overlap merge
  ZONE-04: Zone data available for dashboard (visual layer in Phase 10)
  ZONE-05: Peak bucket — merged zones narrow to volume concentration peak
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from deep6.engines.gex import GexLevels
from deep6.engines.volume_profile import VolumeZone, ZoneState, ZoneType


@dataclass
class ConfluenceResult:
    """Result of get_confluence() — cross-type zone overlap at a price level."""
    has_confluence: bool
    score_bonus: int        # +6 single-type, +8 multi-type (ZONE-02)
    zone_types: list[str]   # e.g. ["LVN", "GEX_CALL_WALL"]
    near_zones: list[VolumeZone]
    detail: str


class ZoneRegistry:
    """Centralized store for all active zone types.

    Thread-safety: not required — runs in asyncio event loop (single-threaded).
    """

    # GEX level names tracked
    GEX_LEVELS = ("call_wall", "put_wall", "gamma_flip", "hvl")

    def __init__(self, tick_size: float = 0.25):
        self.tick_size = tick_size
        self._zones: list[VolumeZone] = []
        self._gex: dict[str, float] = {}   # name -> price

    # ------------------------------------------------------------------
    # Zone management
    # ------------------------------------------------------------------

    def add_zone(self, zone: VolumeZone) -> None:
        """Add a zone; merge with overlapping same-type same-direction zone if present.

        ZONE-03: overlapping same-direction zones consolidate with combined score.
        ZONE-05: peak bucket — merged zone narrows to higher-score zone's range.
        """
        overlap = self._find_overlap(zone)
        if overlap is not None:
            self._merge_into(overlap, zone)
        else:
            self._zones.append(zone)

    def add_gex_levels(self, levels: GexLevels) -> None:
        """Store GEX price levels for confluence queries. GEX-02."""
        if levels.call_wall > 0:
            self._gex["call_wall"] = levels.call_wall
        if levels.put_wall > 0:
            self._gex["put_wall"] = levels.put_wall
        if levels.gamma_flip > 0:
            self._gex["gamma_flip"] = levels.gamma_flip
        if levels.hvl > 0:
            self._gex["hvl"] = levels.hvl

    def get_gex_level(self, name: str) -> float:
        """Return stored GEX price level by name, or 0.0 if not set."""
        return self._gex.get(name, 0.0)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_near_price(self, price: float, ticks: int = 4) -> list[VolumeZone]:
        """Return active zones whose midpoint is within `ticks` ticks of price. ZONE-01."""
        threshold = ticks * self.tick_size
        result = []
        for z in self._zones:
            if z.state == ZoneState.INVALIDATED:
                continue
            mid = (z.top_price + z.bot_price) / 2.0
            if abs(mid - price) <= threshold:
                result.append(z)
        return result

    def get_all_active(self, min_score: float = 0.0) -> list[VolumeZone]:
        """Return all non-invalidated zones above min_score. ZONE-04 data source."""
        return [
            z for z in self._zones
            if z.state != ZoneState.INVALIDATED and z.score >= min_score
        ]

    def get_confluence(self, price: float, ticks: int = 4) -> ConfluenceResult:
        """Check for cross-type zone confluence at price.

        Confluence = VolumeZone near price AND GEX level near same price.
        score_bonus: +6 if single zone type + GEX, +8 if multiple zone types + GEX.
        ZONE-02, ZONE-05.
        """
        threshold = ticks * self.tick_size
        near_zones = self.get_near_price(price, ticks)

        # Which GEX levels are near?
        near_gex: list[str] = []
        for name, level_price in self._gex.items():
            if level_price > 0 and abs(level_price - price) <= threshold:
                near_gex.append(f"GEX_{name.upper()}")

        if not near_zones or not near_gex:
            return ConfluenceResult(
                has_confluence=False,
                score_bonus=0,
                zone_types=[],
                near_zones=near_zones,
                detail="no confluence",
            )

        zone_type_names = list({z.zone_type.name for z in near_zones})
        all_types = zone_type_names + near_gex
        score_bonus = 8 if len(zone_type_names) > 1 else 6

        detail = (
            f"CONFLUENCE @{price:.2f}: "
            + ", ".join(zone_type_names)
            + " + "
            + ", ".join(near_gex)
            + f" -> +{score_bonus} bonus"
        )

        return ConfluenceResult(
            has_confluence=True,
            score_bonus=score_bonus,
            zone_types=all_types,
            near_zones=near_zones,
            detail=detail,
        )

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Reset registry for new session."""
        self._zones.clear()
        self._gex.clear()

    def bulk_load(self, zones: list[VolumeZone]) -> None:
        """Load zones from SessionProfile into registry (with merge)."""
        for z in zones:
            self.add_zone(z)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_overlap(self, zone: VolumeZone) -> VolumeZone | None:
        """Find first active zone of same type and direction that overlaps zone."""
        for z in self._zones:
            if z.state == ZoneState.INVALIDATED:
                continue
            if z.zone_type != zone.zone_type:
                continue
            if z.direction != zone.direction:
                continue
            # Price overlap check
            if z.top_price >= zone.bot_price and z.bot_price <= zone.top_price:
                return z
        return None

    def _merge_into(self, existing: VolumeZone, incoming: VolumeZone) -> None:
        """Merge incoming zone into existing in-place.

        ZONE-03: combined score = max(a,b) + 5 bonus.
        ZONE-05: peak bucket — keep higher-score zone's price range (tighter focus).
        """
        combined_score = min(max(existing.score, incoming.score) + 5.0, 100.0)

        if incoming.score >= existing.score:
            # Incoming is stronger — use its range (peak bucket)
            existing.top_price = incoming.top_price
            existing.bot_price = incoming.bot_price
        # else: keep existing range

        existing.score = combined_score
        existing.touches += incoming.touches
        # Keep existing state, direction, origin_bar
