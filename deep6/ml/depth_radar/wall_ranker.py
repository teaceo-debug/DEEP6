"""Trader-facing wall scoring for DEEP6 Depth Radar.

The ranker intentionally emits probabilistic evidence scores instead of making
binary spoof/iceberg claims.  It can run on true order-id MBO or lower-confidence
L2 approximation feeds; source quality scales confidence and is surfaced in the
payload so the UI cannot overstate certainty.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any


class SourceQuality(StrEnum):
    TRUE_MBO = "TRUE_MBO"
    L2_APPROX = "L2_APPROX"
    STALE = "STALE"
    DEGRADED = "DEGRADED"


_CONFIDENCE_MULTIPLIER: dict[SourceQuality, float] = {
    SourceQuality.TRUE_MBO: 1.0,
    SourceQuality.L2_APPROX: 0.65,
    SourceQuality.DEGRADED: 0.45,
    SourceQuality.STALE: 0.15,
}


def _num(wall: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = wall.get(key, default)
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _flag(wall: dict[str, Any], key: str) -> bool:
    value = wall.get(key, False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _clamp_score(value: float) -> int:
    return int(round(max(0.0, min(100.0, value))))


def _norm(value: float, scale: float) -> float:
    if scale <= 0:
        return 0.0
    return max(0.0, min(1.0, value / scale))


class WallRanker:
    """Score Depth Radar walls as quality/spoof/iceberg/genuine/migration evidence."""

    def __init__(self, source_quality: SourceQuality | str = SourceQuality.TRUE_MBO) -> None:
        self.source_quality = self._coerce_source_quality(source_quality)
        self.confidence_multiplier = _CONFIDENCE_MULTIPLIER[self.source_quality]

    def rank(self, wall: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of *wall* with scores, source quality, and reason-code evidence."""
        ranked = dict(wall)
        evidence: list[str] = []

        intent = str(wall.get("intent", "")).upper()
        classification = str(wall.get("classification", "")).upper()
        state = str(wall.get("state", "")).upper()

        size = max(_num(wall, "size"), _num(wall, "current_size"))
        max_size = max(_num(wall, "max_size"), _num(wall, "max_size_so_far"), size)
        duration = max(_num(wall, "duration_sec"), _num(wall, "age_sec"), _num(wall, "age_seconds"))
        refills = max(_num(wall, "refill_count"), _num(wall, "refills_so_far"))
        cancels = _num(wall, "cancel_reappear_count")
        reprices = _num(wall, "repricing_count")
        filled = max(_num(wall, "filled_volume"), _num(wall, "executed_volume"))
        absorbed = _num(wall, "absorbed_volume")
        absorption_ratio = max(_num(wall, "absorption_ratio"), absorbed / max(size, 1.0))
        pull_approach = _flag(wall, "pull_approach_flag") or "PULLED" in state
        in_touch = _flag(wall, "in_touch_band")
        recovered = _flag(wall, "recovery_after_test")
        distance_ticks = max(_num(wall, "distance_ticks"), _num(wall, "distance_from_mid_ticks"), _num(wall, "distance_from_mid"))

        size_score = 100.0 * _norm(max_size, 300.0)
        current_size_score = 100.0 * _norm(size, 200.0)
        persistence_score = 100.0 * _norm(duration, 5.0)
        refill_score = 100.0 * _norm(refills, 6.0)
        fill_score = 100.0 * _norm(filled, max(max_size * 2.5, 1.0))
        absorption_score = 100.0 * _norm(absorption_ratio, 3.0)
        repeated_score = 100.0 * _norm(cancels, 4.0)
        migration_score_raw = 100.0 * _norm(reprices, 4.0)
        proximity_bonus = 12.0 if in_touch or (0 < distance_ticks <= 8) else 0.0

        low_fill = filled <= max(max_size * 0.05, 1.0)
        if max_size >= 150:
            evidence.append("large_relative_size")
        if in_touch:
            evidence.append("in_touch_band")
        if pull_approach:
            evidence.append("pulled_on_approach")
        if low_fill and max_size >= 100:
            evidence.append("low_fill_ratio")
        if cancels >= 2:
            evidence.append(f"repeated_reappear_{int(cancels)}")
        if refills >= 2:
            evidence.append("reloaded_after_hits")
        if filled >= max(max_size * 0.5, 50):
            evidence.append("meaningful_fill_interaction")
        if absorption_ratio >= 1.0:
            evidence.append("absorption_active")
        if recovered:
            evidence.append("recovered_after_test")
        if reprices >= 2:
            evidence.append("migrated_across_prices")

        spoof = (
            0.25 * size_score
            + (25.0 if pull_approach else 0.0)
            + 0.20 * repeated_score
            + (18.0 if low_fill else 0.0)
            + (10.0 if duration <= 1.0 and max_size >= 100 else 0.0)
            + proximity_bonus
            + (12.0 if "SPOOF" in intent or "SPOOF" in classification else 0.0)
            - (22.0 if filled >= max(max_size * 0.25, 25) else 0.0)
            - (16.0 if recovered else 0.0)
        )

        iceberg = (
            0.30 * refill_score
            + 0.25 * fill_score
            + 0.20 * absorption_score
            + (15.0 if recovered else 0.0)
            + (12.0 if "RESERVE" in intent or "ICEBERG" in classification else 0.0)
            + proximity_bonus
            - (18.0 if pull_approach and low_fill else 0.0)
        )

        genuine = (
            0.25 * persistence_score
            + 0.20 * current_size_score
            + 0.20 * fill_score
            + 0.15 * refill_score
            + (15.0 if in_touch and not pull_approach else 0.0)
            + (12.0 if recovered else 0.0)
            + (10.0 if "PASSIVE_REAL" in intent or "GENUINE" in classification else 0.0)
            - (22.0 if pull_approach else 0.0)
        )

        migration = (
            0.55 * migration_score_raw
            + 0.15 * repeated_score
            + (15.0 if "MIGRATORY" in intent else 0.0)
            + (10.0 if duration <= 3.0 and reprices >= 1 else 0.0)
        )

        defense = max(genuine, iceberg) - (20.0 if pull_approach and low_fill else 0.0)
        break_risk = max(spoof, 100.0 - max(genuine, iceberg)) if pull_approach or low_fill else max(0.0, 70.0 - defense)
        quality = max(genuine, iceberg, 0.6 * migration) - 0.35 * spoof

        scores = {
            "quality": _clamp_score(quality * self.confidence_multiplier),
            "genuine": _clamp_score(genuine * self.confidence_multiplier),
            "spoof": _clamp_score(spoof * self.confidence_multiplier),
            "iceberg": _clamp_score(iceberg * self.confidence_multiplier),
            "migration": _clamp_score(migration * self.confidence_multiplier),
            "defense": _clamp_score(defense * self.confidence_multiplier),
            "break_risk": _clamp_score(break_risk * self.confidence_multiplier),
        }

        ranked["scores"] = scores
        ranked["source_quality"] = self.source_quality.value
        ranked["confidence_multiplier"] = self.confidence_multiplier
        ranked["evidence"] = sorted(set(str(item) for item in evidence))
        return ranked

    @staticmethod
    def _coerce_source_quality(value: SourceQuality | str) -> SourceQuality:
        if isinstance(value, SourceQuality):
            return value
        text = str(value or "").strip().upper()
        try:
            return SourceQuality(text)
        except ValueError:
            return SourceQuality.DEGRADED


def rank_wall(wall: dict[str, Any], source_quality: SourceQuality | str = SourceQuality.TRUE_MBO) -> dict[str, Any]:
    return WallRanker(source_quality=source_quality).rank(wall)


__all__ = ["SourceQuality", "WallRanker", "rank_wall"]
