from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


EPSILON_SCALE = 1e-6
MAX_ACTIVE_ZONES = 8
REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]


@dataclass
class Zone:
    kind: Literal["RBR", "DBD"]
    timeframe_min: int
    top: float
    bottom: float
    entry_price: float
    created_bar_idx: int
    created_at: pd.Timestamp
    score: int
    score_freshness: int
    score_departure: int
    score_base: int
    score_trend: int
    score_height: int
    touch_count: int = 0
    is_active: bool = True
    departure_body_bp: int = 0
    departure_ext_bp: int = 0
    base_body_bp: int = 0
    zone_height_ticks: int = 0
    trend_close_ok: bool = False
    trend_slope_ok: bool = False


def _round_half_away_from_zero(value: float) -> int:
    return int(np.sign(value) * np.floor(np.abs(value) + 0.5))


def _round_half_away_from_zero_array(values: np.ndarray) -> np.ndarray:
    return np.sign(values) * np.floor(np.abs(values) + 0.5)


def _to_basis_points(numerator: float, denominator: float) -> int:
    if denominator <= 0:
        return 0
    return _round_half_away_from_zero((numerator / denominator) * 10000.0)


def _to_tick_count(price_distance: float, tick_size: float) -> int:
    return _round_half_away_from_zero(price_distance / tick_size)


def score_continuation_zone(
    *,
    timeframe_min: int,
    touch_count: int,
    departure_body_to_height_bp: int,
    departure_close_extension_to_height_bp: int,
    base_candle_count: int,
    max_base_body_ratio_bp: int,
    trend_close_side_ok: bool,
    trend_slope_ok: bool,
    zone_height_ticks: int,
) -> tuple[int, dict[str, int]]:
    """Standalone scoring function — identical logic to NinjaScript ScoreZone methods."""
    freshness = 2 if touch_count == 0 else 1 if touch_count == 1 else 0
    departure = (
        2
        if departure_body_to_height_bp >= 15000
        and departure_close_extension_to_height_bp >= 5000
        else 1
        if departure_body_to_height_bp >= 10000
        and departure_close_extension_to_height_bp > 0
        else 0
    )
    base_quality = (
        2
        if base_candle_count <= 2 and max_base_body_ratio_bp <= 3500
        else 1
        if base_candle_count <= 3 and max_base_body_ratio_bp <= 5000
        else 0
    )
    trend_alignment = (
        2
        if trend_close_side_ok and trend_slope_ok
        else 1
        if trend_close_side_ok != trend_slope_ok
        else 0
    )
    if timeframe_min == 5:
        zone_height = 2 if 4 <= zone_height_ticks <= 10 else 1 if 3 <= zone_height_ticks <= 12 else 0
    elif timeframe_min == 15:
        zone_height = 2 if 6 <= zone_height_ticks <= 14 else 1 if 5 <= zone_height_ticks <= 18 else 0
    else:
        raise ValueError(f"timeframe_min must be 5 or 15, got {timeframe_min}")

    total = freshness + departure + base_quality + trend_alignment + zone_height
    return total, {
        "freshness": freshness,
        "departure": departure,
        "base_quality": base_quality,
        "trend_alignment": trend_alignment,
        "zone_height": zone_height,
    }


class ContinuationZoneDetector:
    def __init__(
        self,
        small_body_ratio: float = 0.35,
        min_zone_ticks: int = 2,
        max_zone_age_bars: int = 300,
        max_touch_count: int = 3,
        min_score: int = 5,
        tick_size: float = 0.25,
        ema_period: int = 50,
    ):
        self.small_body_ratio = small_body_ratio
        self.min_zone_ticks = min_zone_ticks
        self.max_zone_age_bars = max_zone_age_bars
        self.max_touch_count = max_touch_count
        self.min_score = min_score
        self.tick_size = tick_size
        self.ema_period = ema_period

    def detect(self, df: pd.DataFrame, timeframe_min: int) -> list[Zone]:
        """
        Detect RBR and DBD continuation zones in a OHLCV DataFrame.

        df: pandas DataFrame with columns [open, high, low, close, volume]
            and UTC DatetimeIndex named ts_event.
        timeframe_min: 5 or 15

        Returns list of Zone objects (all zones, including expired ones).
        Active zones: [z for z in zones if z.is_active]
        """
        if timeframe_min not in {5, 15}:
            raise ValueError(f"timeframe_min must be 5 or 15, got {timeframe_min}")

        missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
        if missing:
            raise ValueError(f"df missing required columns: {missing}")

        frame = df.loc[:, REQUIRED_COLUMNS].copy()
        frame[f"ema{self.ema_period}"] = frame["close"].ewm(span=self.ema_period, adjust=False).mean()
        if len(frame) < 3:
            return []

        candidate_map = self._build_candidate_map(frame)
        zones: list[Zone] = []
        active_zones: list[Zone] = []
        prior_inside: dict[int, bool] = {}
        epsilon = self.tick_size * EPSILON_SCALE

        for current_idx in range(len(frame)):
            for kind, top, bottom in candidate_map.get(current_idx, []):
                zone = self._build_zone(frame, timeframe_min, current_idx, kind, top, bottom)
                if zone is None:
                    continue
                if self._has_overlap(active_zones, zone, epsilon):
                    continue
                zones.append(zone)
                active_zones.append(zone)
                prior_inside[id(zone)] = False

            if not active_zones:
                continue

            bar = frame.iloc[current_idx]
            body_max = max(float(bar["open"]), float(bar["close"]))
            body_min = min(float(bar["open"]), float(bar["close"]))
            high = float(bar["high"])
            low = float(bar["low"])

            next_active: list[Zone] = []
            for zone in active_zones:
                if not zone.is_active:
                    continue

                if current_idx <= zone.created_bar_idx:
                    next_active.append(zone)
                    continue

                invalidated = (
                    body_min < zone.bottom - epsilon
                    if zone.kind == "RBR"
                    else body_max > zone.top + epsilon
                )
                if invalidated:
                    zone.is_active = False
                    continue

                overlaps = high >= zone.bottom - epsilon and low <= zone.top + epsilon
                previous_overlap = prior_inside.get(id(zone), False)
                if overlaps and not previous_overlap:
                    zone.touch_count += 1
                prior_inside[id(zone)] = overlaps

                self._update_dynamic_score(zone)

                age_bars = current_idx - zone.created_bar_idx
                max_age = self.max_zone_age_bars if zone.timeframe_min == 5 else 100
                if age_bars > max_age or zone.touch_count >= self.max_touch_count:
                    zone.is_active = False
                    continue

                next_active.append(zone)

            active_zones = self._enforce_active_zone_cap(next_active, current_idx)

        return zones

    def _build_candidate_map(self, df: pd.DataFrame) -> dict[int, list[tuple[str, float, float]]]:
        prev_open = df["open"].shift(2)
        prev_close = df["close"].shift(2)
        base_open = df["open"].shift(1)
        base_close = df["close"].shift(1)
        base_high = df["high"].shift(1)
        base_low = df["low"].shift(1)

        next_open = df["open"]
        next_close = df["close"]
        next_body_max = pd.concat([next_open, next_close], axis=1).max(axis=1)
        next_body_min = pd.concat([next_open, next_close], axis=1).min(axis=1)

        base_range = base_high - base_low
        base_body = (base_close - base_open).abs()
        base_body_ratio = np.divide(
            base_body.to_numpy(dtype=float),
            base_range.to_numpy(dtype=float),
            out=np.zeros(len(df), dtype=float),
            where=base_range.to_numpy(dtype=float) > 0,
        )
        base_body_bp = _round_half_away_from_zero_array(base_body_ratio * 10000.0)
        base_range_ticks = _round_half_away_from_zero_array(base_range.to_numpy(dtype=float) / self.tick_size)

        ratio_limit_bp = _round_half_away_from_zero(self.small_body_ratio * 10000.0)
        valid_base = (base_range.to_numpy(dtype=float) > 0) & (base_body_bp <= ratio_limit_bp) & (
            base_range_ticks >= self.min_zone_ticks
        )
        prev_up = (prev_close > prev_open).to_numpy(dtype=bool)
        prev_down = (prev_close < prev_open).to_numpy(dtype=bool)
        epsilon = self.tick_size * EPSILON_SCALE

        rbr_mask = valid_base & prev_up & (next_body_max.to_numpy(dtype=float) > base_high.to_numpy(dtype=float) + epsilon)
        dbd_mask = valid_base & prev_down & (next_body_min.to_numpy(dtype=float) < base_low.to_numpy(dtype=float) - epsilon)

        candidate_map: dict[int, list[tuple[str, float, float]]] = defaultdict(list)
        for idx in np.flatnonzero(rbr_mask):
            candidate_map[int(idx)].append(
                (
                    "RBR",
                    float(max(base_open.iat[idx], base_close.iat[idx])),
                    float(base_low.iat[idx]),
                )
            )
        for idx in np.flatnonzero(dbd_mask):
            candidate_map[int(idx)].append(
                (
                    "DBD",
                    float(base_high.iat[idx]),
                    float(min(base_open.iat[idx], base_close.iat[idx])),
                )
            )
        return candidate_map

    def _build_zone(
        self,
        df: pd.DataFrame,
        timeframe_min: int,
        bar_idx: int,
        kind: Literal["RBR", "DBD"],
        top: float,
        bottom: float,
    ) -> Zone | None:
        if top <= bottom or bar_idx < 1:
            return None

        zone = Zone(
            kind=kind,
            timeframe_min=timeframe_min,
            top=top,
            bottom=bottom,
            entry_price=bottom if kind == "RBR" else top,
            created_bar_idx=bar_idx - 1,
            created_at=pd.Timestamp(df.index[bar_idx - 1]),
            score=0,
            score_freshness=0,
            score_departure=0,
            score_base=0,
            score_trend=0,
            score_height=0,
        )
        self._score_zone(zone, df, bar_idx)
        return zone

    def _has_overlap(self, active_zones: list[Zone], new_zone: Zone, epsilon: float) -> bool:
        for existing in active_zones:
            if not existing.is_active:
                continue
            if existing.kind != new_zone.kind or existing.timeframe_min != new_zone.timeframe_min:
                continue
            if (
                abs(existing.top - new_zone.top) < self.tick_size * 0.5
                and abs(existing.bottom - new_zone.bottom) < self.tick_size * 0.5
            ):
                return True
            overlaps = (
                new_zone.bottom <= existing.top + epsilon
                and new_zone.top >= existing.bottom - epsilon
            )
            if overlaps:
                return True
        return False

    def _score_zone(self, zone: Zone, df: pd.DataFrame, bar_idx: int) -> None:
        """Compute all 5 score components and set them on the zone."""
        zone_height = zone.top - zone.bottom
        if zone_height <= 0:
            zone.score_departure = 0
        else:
            next_close = float(df.iloc[bar_idx]["close"])
            base_close = float(df.iloc[bar_idx - 1]["close"])
            base_high = float(df.iloc[bar_idx - 1]["high"])
            base_low = float(df.iloc[bar_idx - 1]["low"])
            zone_edge = base_high if zone.kind == "RBR" else base_low

            dep_body_bp = _to_basis_points(abs(next_close - base_close), zone_height)
            dep_ext_bp = _to_basis_points(abs(next_close - zone_edge), zone_height)
            zone.departure_body_bp = dep_body_bp
            zone.departure_ext_bp = dep_ext_bp

            if dep_body_bp >= 15000 and dep_ext_bp >= 5000:
                zone.score_departure = 2
            elif dep_body_bp >= 10000 and dep_ext_bp > 0:
                zone.score_departure = 1
            else:
                zone.score_departure = 0

        base_open = float(df.iloc[bar_idx - 1]["open"])
        base_close = float(df.iloc[bar_idx - 1]["close"])
        base_high = float(df.iloc[bar_idx - 1]["high"])
        base_low = float(df.iloc[bar_idx - 1]["low"])
        zone.base_body_bp = _to_basis_points(abs(base_close - base_open), max(base_high - base_low, 1e-9))
        if zone.base_body_bp <= 3500:
            zone.score_base = 2
        elif zone.base_body_bp <= 5000:
            zone.score_base = 1
        else:
            zone.score_base = 0

        ema_col = f"ema{self.ema_period}"
        if ema_col in df.columns:
            ema_at_base = float(df.iloc[bar_idx - 1][ema_col])
            ema_prev = float(df.iloc[bar_idx - 2][ema_col]) if bar_idx >= 2 else ema_at_base
            base_close_val = float(df.iloc[bar_idx - 1]["close"])
            if zone.kind == "RBR":
                trend_close_ok = base_close_val > ema_at_base
                trend_slope_ok = ema_at_base > ema_prev
            else:
                trend_close_ok = base_close_val < ema_at_base
                trend_slope_ok = ema_at_base < ema_prev
            zone.trend_close_ok = trend_close_ok
            zone.trend_slope_ok = trend_slope_ok
            if trend_close_ok and trend_slope_ok:
                zone.score_trend = 2
            elif trend_close_ok != trend_slope_ok:
                zone.score_trend = 1
            else:
                zone.score_trend = 0
        else:
            zone.score_trend = 0

        zone.zone_height_ticks = _to_tick_count(zone.top - zone.bottom, self.tick_size)
        total, components = score_continuation_zone(
            timeframe_min=zone.timeframe_min,
            touch_count=zone.touch_count,
            departure_body_to_height_bp=zone.departure_body_bp,
            departure_close_extension_to_height_bp=zone.departure_ext_bp,
            base_candle_count=1,
            max_base_body_ratio_bp=zone.base_body_bp,
            trend_close_side_ok=zone.trend_close_ok,
            trend_slope_ok=zone.trend_slope_ok,
            zone_height_ticks=zone.zone_height_ticks,
        )
        zone.score_freshness = components["freshness"]
        zone.score_departure = components["departure"]
        zone.score_base = components["base_quality"]
        zone.score_trend = components["trend_alignment"]
        zone.score_height = components["zone_height"]
        zone.score = total

    def _update_dynamic_score(self, zone: Zone) -> None:
        total, components = score_continuation_zone(
            timeframe_min=zone.timeframe_min,
            touch_count=zone.touch_count,
            departure_body_to_height_bp=zone.departure_body_bp,
            departure_close_extension_to_height_bp=zone.departure_ext_bp,
            base_candle_count=1,
            max_base_body_ratio_bp=zone.base_body_bp,
            trend_close_side_ok=zone.trend_close_ok,
            trend_slope_ok=zone.trend_slope_ok,
            zone_height_ticks=zone.zone_height_ticks,
        )
        zone.score_freshness = components["freshness"]
        zone.score = total

    def _enforce_active_zone_cap(self, active_zones: list[Zone], current_idx: int) -> list[Zone]:
        if len(active_zones) <= MAX_ACTIVE_ZONES:
            return active_zones

        ranked = sorted(active_zones, key=lambda zone: (self._display_opacity(zone, current_idx), zone.created_bar_idx))
        while len(ranked) > MAX_ACTIVE_ZONES:
            ranked[0].is_active = False
            ranked.pop(0)
        return ranked

    def _display_opacity(self, zone: Zone, current_idx: int) -> float:
        stage_opacity = 1.0 if zone.touch_count == 0 else 0.8 if zone.touch_count == 1 else 0.4
        age_bars = max(0, current_idx - zone.created_bar_idx)
        opacity_factor = (0.98**age_bars) * max(0.0, 1.0 - zone.touch_count * 0.20)
        effective = min(stage_opacity, opacity_factor)
        if zone.score < self.min_score:
            effective = min(effective, 0.10)
        return max(0.0, min(1.0, effective))


__all__ = ["ContinuationZoneDetector", "Zone", "score_continuation_zone"]
