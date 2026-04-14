"""LevelBus — upgraded ZoneRegistry (Phase 15, D-09/D-10/D-11).

Centralized store for all 17 ``LevelKind`` variants — volume-profile zones,
narrative zones (ABSORB/EXHAUST/MOMENTUM/REJECTION/FLIPPED/CONFIRMED_ABSORB),
VA extremes (VPOC/VAH/VAL), and GEX point levels (CALL_WALL/PUT_WALL/
GAMMA_FLIP/ZERO_GAMMA/HVL/LARGEST_GAMMA).

Per ZONE-01..05 (preserved from Phase 5):
  ZONE-01: Single store for all zone types.
  ZONE-02: Cross-type confluence scoring (``get_confluence``).
  ZONE-03: Same-type + same-direction overlap → merge (score max + 5 bonus).
  ZONE-04: Zone data available for dashboard.
  ZONE-05: Peak bucket — merged zones narrow to volume-concentration peak.

New in Phase 15:
  D-09: In-place rename ``ZoneRegistry`` → ``LevelBus``. An
        ``ZoneRegistry = LevelBus`` alias is exported for one release
        window so existing imports keep working.
  D-10: ``add_level(level)`` subsumes ``add_zone`` / ``add_gex_levels``.
        Dispatches on kind — zone kinds merge on overlap; point kinds
        (GEX) dedupe by (kind, price). New queries:
        ``query_near(price, ticks) -> list[Level]``,
        ``query_by_kind(kind) -> list[Level]``,
        ``get_top_n(n=6) -> list[Level]``.
  D-11: ``max_levels = 80`` cap. Eviction prefers lowest-score ACTIVE first;
        DEFENDED / FLIPPED preserved until their score falls below an
        evict candidate.

C5 identity guarantee:
  Merging an incoming Level into an existing Level preserves the EXISTING
  Level.uid. Downstream mutation keys (ConfluenceRules.score_mutations)
  snapshot uids BEFORE calling evaluate/score_bar and remain valid across
  merges during the same bar.

get_all_active() returns ``list[Level]`` (C3/C5). Consumers that previously
read ``VolumeZone`` fields should migrate to reading ``Level.price_top /
price_bot / score / state``. The ``add_zone`` / ``add_gex_levels`` wrappers
remain for source compatibility.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from deep6.engines.gex import GexLevels
from deep6.engines.level import Level, LevelKind, LevelState
from deep6.engines.volume_profile import VolumeZone, ZoneState, ZoneType


_ZONE_KINDS: frozenset[LevelKind] = frozenset({
    LevelKind.LVN, LevelKind.HVN,
    LevelKind.ABSORB, LevelKind.EXHAUST, LevelKind.MOMENTUM, LevelKind.REJECTION,
    LevelKind.FLIPPED, LevelKind.CONFIRMED_ABSORB,
})

_POINT_KINDS: frozenset[LevelKind] = frozenset({
    LevelKind.VPOC, LevelKind.VAH, LevelKind.VAL,
    LevelKind.CALL_WALL, LevelKind.PUT_WALL,
    LevelKind.GAMMA_FLIP, LevelKind.ZERO_GAMMA,
    LevelKind.HVL, LevelKind.LARGEST_GAMMA,
})


@dataclass
class ConfluenceResult:
    """Result of ``get_confluence()`` — cross-type zone + GEX overlap at price."""
    has_confluence: bool
    score_bonus: int
    zone_types: list[str]
    near_zones: list[Level]       # C3/C5: now list[Level], not list[VolumeZone]
    detail: str


class LevelBus:
    """Centralized store for all active Levels (D-09/D-10/D-11).

    Thread-safety: not required — runs in asyncio event loop (single-threaded).
    """

    # GEX level names tracked (compat with legacy ZoneRegistry.GEX_LEVELS)
    GEX_LEVELS = ("call_wall", "put_wall", "gamma_flip", "hvl")

    #: Maximum concurrent active Levels before eviction (D-11).
    max_levels: int = 80

    def __init__(self, tick_size: float = 0.25):
        self.tick_size = tick_size
        self._levels: list[Level] = []

    # ------------------------------------------------------------------
    # Primary API — D-10
    # ------------------------------------------------------------------

    def add_level(self, level: Level) -> None:
        """Add a Level, dispatching on kind.

        Zone kinds (LVN/HVN/ABSORB/EXHAUST/MOMENTUM/REJECTION/FLIPPED/CONFIRMED_ABSORB):
            Overlap + same direction + same kind → widen-or-tighten +
            combine scores + sum touches (ZONE-03 + ZONE-05). The existing
            Level.uid is PRESERVED (C5 identity guarantee).
        Point kinds (VPOC/VAH/VAL/CALL_WALL/PUT_WALL/GAMMA_FLIP/ZERO_GAMMA/HVL/LARGEST_GAMMA):
            Dedupe by (kind, price_top). Duplicate (kind, price) replaces
            the existing point-Level (no accumulating noise).
        After insertion, evict to ``max_levels`` (D-11).
        """
        if level.kind in _ZONE_KINDS:
            existing = self._find_overlap(level)
            if existing is not None:
                self._merge_into(existing, level)
            else:
                self._levels.append(level)
        elif level.kind in _POINT_KINDS:
            for i, lv in enumerate(self._levels):
                if lv.kind == level.kind and lv.price_top == level.price_top:
                    # Replace: keep original uid (C5) but overwrite other fields.
                    original_uid = lv.uid
                    self._levels[i] = level
                    self._levels[i].uid = original_uid
                    return
            self._levels.append(level)
        else:  # pragma: no cover — safety
            self._levels.append(level)

        # D-11 eviction
        self._evict_if_over_cap()

    def query_near(self, price: float, ticks: int = 4) -> list[Level]:
        """Levels whose [bot, top] expanded by ``ticks`` includes ``price``.

        Excludes INVALIDATED. Single predicate handles both zone and
        point geometry (point levels have top == bot).
        """
        thr = ticks * self.tick_size
        return [
            lv for lv in self._levels
            if lv.state != LevelState.INVALIDATED
            and (lv.price_bot - thr) <= price <= (lv.price_top + thr)
        ]

    def query_by_kind(self, kind: LevelKind) -> list[Level]:
        """All active (non-INVALIDATED) Levels of a given kind."""
        return [lv for lv in self._levels if lv.kind == kind and lv.state != LevelState.INVALIDATED]

    def get_top_n(self, n: int = 6) -> list[Level]:
        """Top-N Levels by score desc, excluding INVALIDATED (Pine ``max_visible``)."""
        active = [lv for lv in self._levels if lv.state != LevelState.INVALIDATED]
        active.sort(key=lambda lv: lv.score, reverse=True)
        return active[:n]

    # ------------------------------------------------------------------
    # Legacy API — retained as thin wrappers (D-09 compat)
    # ------------------------------------------------------------------

    def add_zone(self, zone: VolumeZone) -> None:
        """Legacy path: convert VolumeZone → Level via factory, then add_level."""
        # Lazy import avoids cycle (level_factory imports from this module transitively).
        from deep6.engines.level_factory import from_volume_zone
        self.add_level(from_volume_zone(zone))

    def add_gex_levels(self, levels: GexLevels) -> None:
        """Legacy path: expand GexLevels → up-to-6 point-Levels."""
        from deep6.engines.level_factory import from_gex
        for lv in from_gex(levels):
            self.add_level(lv)

    def get_gex_level(self, name: str) -> float:
        """Return the price of a stored GEX point-Level by field name, or 0.0.

        Legacy API — GEX levels are now full Level objects. This returns the
        most recent price for the named kind.
        """
        name_to_kind = {
            "call_wall": LevelKind.CALL_WALL,
            "put_wall": LevelKind.PUT_WALL,
            "gamma_flip": LevelKind.GAMMA_FLIP,
            "zero_gamma": LevelKind.ZERO_GAMMA,
            "hvl": LevelKind.HVL,
            "largest_gamma_strike": LevelKind.LARGEST_GAMMA,
        }
        kind = name_to_kind.get(name)
        if kind is None:
            return 0.0
        matches = self.query_by_kind(kind)
        return matches[0].price_top if matches else 0.0

    def get_near_price(self, price: float, ticks: int = 4) -> list[Level]:
        """Legacy: active Levels near ``price`` (zone midpoint-based for zones).

        Retained for backward compatibility with Phase 5 call sites. Behavior:
        a Level qualifies when its midpoint is within ``ticks`` of ``price``
        (preserves old ZoneRegistry semantics for VolumeZone consumers).
        """
        thr = ticks * self.tick_size
        return [
            lv for lv in self._levels
            if lv.state != LevelState.INVALIDATED
            and abs(lv.midpoint() - price) <= thr
        ]

    def get_all_active(self, min_score: float = 0.0) -> list[Level]:
        """All non-INVALIDATED Levels above ``min_score``.

        Phase 15 change: returns ``list[Level]`` (was ``list[VolumeZone]``).
        Consumers of ``VPContextResult.active_zones`` must migrate to read
        Level fields (``price_top`` / ``price_bot`` / ``score`` / ``state``).
        """
        return [
            lv for lv in self._levels
            if lv.state != LevelState.INVALIDATED and lv.score >= min_score
        ]

    def get_confluence(self, price: float, ticks: int = 4) -> ConfluenceResult:
        """Cross-type zone + GEX confluence at ``price``.

        Confluence = at least one zone-kind Level near price AND at least
        one GEX point-kind Level near price.  +6 for single zone type,
        +8 for multi-type.
        """
        near = self.query_near(price, ticks)
        near_zones = [lv for lv in near if lv.kind in _ZONE_KINDS]
        near_points = [lv for lv in near if lv.kind in _POINT_KINDS and _is_gex_kind(lv.kind)]

        if not near_zones or not near_points:
            return ConfluenceResult(
                has_confluence=False, score_bonus=0, zone_types=[],
                near_zones=near_zones, detail="no confluence",
            )

        zone_type_names = sorted({lv.kind.name for lv in near_zones})
        gex_type_names = [f"GEX_{lv.kind.name}" for lv in near_points]
        all_types = zone_type_names + gex_type_names
        score_bonus = 8 if len(zone_type_names) > 1 else 6

        detail = (
            f"CONFLUENCE @{price:.2f}: "
            + ", ".join(zone_type_names)
            + " + "
            + ", ".join(gex_type_names)
            + f" -> +{score_bonus} bonus"
        )
        return ConfluenceResult(
            has_confluence=True, score_bonus=score_bonus, zone_types=all_types,
            near_zones=near_zones, detail=detail,
        )

    def clear(self) -> None:
        """Reset for new session."""
        self._levels.clear()

    def bulk_load(self, zones: list[VolumeZone]) -> None:
        """Load a list of VolumeZones through the legacy wrapper."""
        for z in zones:
            self.add_zone(z)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_overlap(self, incoming: Level) -> Level | None:
        """Same kind + same direction + price-range overlap + not INVALIDATED."""
        for lv in self._levels:
            if lv.state == LevelState.INVALIDATED:
                continue
            if lv.kind != incoming.kind:
                continue
            if lv.direction != incoming.direction:
                continue
            if lv.price_top >= incoming.price_bot and lv.price_bot <= incoming.price_top:
                return lv
        return None

    def _merge_into(self, existing: Level, incoming: Level) -> None:
        """Merge ``incoming`` into ``existing`` in-place (ZONE-03 + ZONE-05 + C5).

        - Combined score = min(max(a, b) + 5, 100).
        - Peak bucket: keep the higher-score operand's price range.
        - Touches accumulate.
        - existing.uid is preserved (C5 identity guarantee — downstream
          mutation keys remain valid).
        """
        combined_score = min(max(existing.score, incoming.score) + 5.0, 100.0)
        if incoming.score >= existing.score:
            existing.price_top = incoming.price_top
            existing.price_bot = incoming.price_bot
        existing.score = combined_score
        existing.touches += incoming.touches
        existing.last_act_bar = max(existing.last_act_bar, incoming.last_act_bar)
        # state, direction, origin_bar, uid stay on `existing` (C5).

    def _evict_if_over_cap(self) -> None:
        """Evict lowest-score ACTIVE Levels when over cap (D-11).

        Priority: CREATED > DEFENDED > FLIPPED (preserve DEFENDED/FLIPPED
        unless their score falls below an evict candidate). BROKEN and
        INVALIDATED are skipped (INVALIDATED already excluded from active
        queries; BROKEN Levels are retained for post-mortem but evictable
        if over cap).
        """
        active = [lv for lv in self._levels if lv.state != LevelState.INVALIDATED]
        if len(active) <= self.max_levels:
            return

        # Sort by (preservation_priority, score) — lower first (evict first).
        # preservation_priority: CREATED=0, BROKEN=1, FLIPPED=2, DEFENDED=3.
        priority = {
            LevelState.CREATED: 0,
            LevelState.BROKEN: 1,
            LevelState.FLIPPED: 2,
            LevelState.DEFENDED: 3,
        }

        def evict_key(lv: Level) -> tuple[int, float]:
            return (priority.get(lv.state, 0), lv.score)

        active.sort(key=evict_key)
        over = len(active) - self.max_levels
        for lv in active[:over]:
            lv.state = LevelState.INVALIDATED


def _is_gex_kind(kind: LevelKind) -> bool:
    return kind in (
        LevelKind.CALL_WALL, LevelKind.PUT_WALL,
        LevelKind.GAMMA_FLIP, LevelKind.ZERO_GAMMA,
        LevelKind.HVL, LevelKind.LARGEST_GAMMA,
    )


# D-09 compatibility alias — existing imports keep working.
ZoneRegistry = LevelBus


__all__ = ["LevelBus", "ZoneRegistry", "ConfluenceResult"]
