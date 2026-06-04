"""Causal 44-feature extractor for DepthRadar V4 wall episodes."""
from __future__ import annotations

from collections import deque
from statistics import mean
from typing import Any, Iterable

import numpy as np


# A1. current_size — resting size visible right now; primary size state.
# A2. original_size — initial displayed size; anchors depletion / spoof context.
# A3. max_size_so_far — peak displayed size observed causally so far; captures growth.
# A4. age_seconds — age up to observation time; separates fresh vs established walls.
# A5. side — 0 bid / 1 ask; preserves directional asymmetry in the book.
# A6. modifications_so_far — cumulative size changes so far; measures activity.
# A7. refills_so_far — cumulative refill events so far; reserve/iceberg evidence.
# A8. size_vs_original — current/original ratio; depletion or persistence proxy.
# B1. mod_rate_2s — short-horizon modification intensity; pull/defense urgency.
# B2. mod_rate_10s — medium-horizon modification intensity; steadier behavior profile.
# B3. cancel_reappear_count — times wall vanished then returned; suspicious/sticky behavior.
# B4. size_volatility_10s — size instability over last 10s; spoofing or active defense.
# B5. refill_elasticity — refill/depletion recovery ratio; reserve depth quality.
# B6. pull_approach_flag — pull >50% on near-price approach; spoof-like tell.
# B7. repricing_count — number of price migrations so far; migratory behavior proxy.
# B8. time_at_current_size — staleness of present size; passive vs twitchy liquidity.
# C1. prominence_zscore — wall size vs nearby same-side levels; local salience.
# C2. same_side_depth_behind — support depth behind wall; reinforcement strength.
# C3. same_side_depth_ahead — same-side depth toward mid; queue competition ahead.
# C4. opposite_depth_mirror — opposing liquidity at mirrored distance; balance context.
# C5. cluster_density — count of nearby large neighbors; wall cluster / shelf density.
# C6. depth_slope — local depth gradient around the wall; ladder shape information.
# C7. vacuum_behind — empty support behind wall; fragile backing condition.
# C8. ladder_correlation — neighborhood coordination vs prior snapshot; synthetic behavior cue.
# D1. distance_from_mid — ticks from wall to mid; immediacy of interaction.
# D2. distance_from_bbo — ticks from wall to same-side BBO; front-queue vs back-book.
# D3. spread_ticks — current inside spread width; regime / execution friction proxy.
# D4. book_imbalance_top10 — top-10 bid/ask imbalance; directional pressure context.
# D5. session_phase — coarse intraday phase bucket; open/lunch/close behavior shifts.
# D6. minutes_since_open — continuous intraday clock from RTH open.
# D7. realized_vol_2m — 2-minute realized vol in ticks; current movement regime.
# D8. range_expansion_flag — current short-term range vs recent baseline; expansion regime.
# E1. cumulative_delta — running aggressive buy-sell volume since session open.
# E2. delta_2s — very recent aggressive flow impulse.
# E3. delta_10s — slightly slower aggressive flow backdrop.
# E4. approach_speed — mid-price movement toward wall in ticks/sec.
# E5. consecutive_aggressor — one-sided trade streak length; attack persistence.
# E6. sweep_flag — fast multi-level consumption flag; violent attack signature.
# F1. absorbed_volume — cumulative aggressive volume absorbed at/near wall.
# F2. absorption_ratio — absorbed volume divided by current size; defense efficiency.
# F3. tests_count — number of touch/test events seen so far.
# F4. recovery_after_test — did size recover after most recent test; resilience cue.
# F5. time_since_last_test — recency of prior test; live attack cadence.
# F6. attack_intensity — aggressive volume per second on approach/attack window.
CAUSAL_FEATURE_NAMES: list[str] = [
    "current_size",
    "original_size",
    "max_size_so_far",
    "age_seconds",
    "side",
    "modifications_so_far",
    "refills_so_far",
    "size_vs_original",
    "mod_rate_2s",
    "mod_rate_10s",
    "cancel_reappear_count",
    "size_volatility_10s",
    "refill_elasticity",
    "pull_approach_flag",
    "repricing_count",
    "time_at_current_size",
    "prominence_zscore",
    "same_side_depth_behind",
    "same_side_depth_ahead",
    "opposite_depth_mirror",
    "cluster_density",
    "depth_slope",
    "vacuum_behind",
    "ladder_correlation",
    "distance_from_mid",
    "distance_from_bbo",
    "spread_ticks",
    "book_imbalance_top10",
    "session_phase",
    "minutes_since_open",
    "realized_vol_2m",
    "range_expansion_flag",
    "cumulative_delta",
    "delta_2s",
    "delta_10s",
    "approach_speed",
    "consecutive_aggressor",
    "sweep_flag",
    "absorbed_volume",
    "absorption_ratio",
    "tests_count",
    "recovery_after_test",
    "time_since_last_test",
    "attack_intensity",
]
assert len(CAUSAL_FEATURE_NAMES) == 44, f"Expected 44 features, got {len(CAUSAL_FEATURE_NAMES)}"

NUM_CAUSAL_FEATURES = 44
_IDX: dict[str, int] = {name: idx for idx, name in enumerate(CAUSAL_FEATURE_NAMES)}


def get_causal_feature_names() -> list[str]:
    """Return the ordered feature name list for column labeling."""

    return list(CAUSAL_FEATURE_NAMES)


class RollingStats:
    """Exact sliding-window mean/std for causal z-score normalization."""

    def __init__(self, window: int = 1000) -> None:
        self._window = max(1, int(window))
        self._buffer: deque[np.ndarray] = deque(maxlen=self._window)
        self._mean = np.zeros(NUM_CAUSAL_FEATURES, dtype=np.float64)
        self._std = np.ones(NUM_CAUSAL_FEATURES, dtype=np.float64)
        self._dirty = True

    def update(self, features: np.ndarray) -> None:
        if features.ndim == 1:
            self._buffer.append(features.astype(np.float64, copy=True))
        elif features.ndim == 2:
            for row in features:
                self._buffer.append(row.astype(np.float64, copy=True))
        self._dirty = True

    def normalize(self, features: np.ndarray) -> np.ndarray:
        if len(self._buffer) < 2:
            return features.astype(np.float64)
        if self._dirty:
            self._recompute()
        return (features.astype(np.float64) - self._mean) / self._std

    def _recompute(self) -> None:
        if len(self._buffer) < 2:
            self._mean = np.zeros(NUM_CAUSAL_FEATURES, dtype=np.float64)
            self._std = np.ones(NUM_CAUSAL_FEATURES, dtype=np.float64)
            self._dirty = False
            return
        stacked = np.stack(list(self._buffer), axis=0)
        self._mean = stacked.mean(axis=0)
        std = stacked.std(axis=0)
        std[std < 1e-9] = 1.0
        self._std = std
        self._dirty = False


class CausalFeatureExtractor:
    """Extract 44 strictly causal DepthRadar wall features."""

    def __init__(
        self,
        tick_size: float = 0.25,
        normalize: bool = False,
        rolling_window: int = 1000,
    ) -> None:
        self.tick_size = float(tick_size)
        self._normalize = bool(normalize)
        self._stats = RollingStats(window=rolling_window)

    @property
    def stats(self) -> RollingStats:
        return self._stats

    def extract(
        self,
        wall_data: dict,
        market_context: dict,
        flow_context: dict,
        attack_context: dict,
    ) -> np.ndarray:
        vec = np.zeros(NUM_CAUSAL_FEATURES, dtype=np.float64)

        current_size = self._as_float(wall_data.get("current_size"))
        original_size = max(self._as_float(wall_data.get("original_size")), 1.0)
        max_size_so_far = self._as_float(wall_data.get("max_size_so_far"), default=current_size)
        age_seconds = max(self._as_float(wall_data.get("age_seconds")), 0.0)
        side = self._encode_side(wall_data.get("side"))
        modifications_so_far = self._as_float(wall_data.get("modifications_so_far"))
        refills_so_far = self._as_float(wall_data.get("refills_so_far"))

        # Block A — wall snapshot.
        vec[_IDX["current_size"]] = current_size
        vec[_IDX["original_size"]] = original_size
        vec[_IDX["max_size_so_far"]] = max(max_size_so_far, current_size)
        vec[_IDX["age_seconds"]] = age_seconds
        vec[_IDX["side"]] = float(side)
        vec[_IDX["modifications_so_far"]] = modifications_so_far
        vec[_IDX["refills_so_far"]] = refills_so_far
        vec[_IDX["size_vs_original"]] = current_size / original_size

        modification_times = self._as_float_list(wall_data.get("modification_times"))
        recent_sizes = self._as_float_list(wall_data.get("recent_sizes"))
        refill_ratios = self._as_float_list(wall_data.get("refill_ratios"))

        # Block B — behavior trajectory.
        vec[_IDX["mod_rate_2s"]] = self._count_recent(modification_times, 2.0)
        vec[_IDX["mod_rate_10s"]] = self._count_recent(modification_times, 10.0)
        vec[_IDX["cancel_reappear_count"]] = self._as_float(wall_data.get("cancel_reappear_count"))
        vec[_IDX["size_volatility_10s"]] = float(np.std(recent_sizes)) if len(recent_sizes) >= 2 else 0.0
        vec[_IDX["refill_elasticity"]] = float(mean(refill_ratios)) if refill_ratios else 0.0
        vec[_IDX["pull_approach_flag"]] = 1.0 if wall_data.get("pull_approach_flag") else 0.0
        vec[_IDX["repricing_count"]] = self._as_float(wall_data.get("repricing_count"))
        vec[_IDX["time_at_current_size"]] = max(self._as_float(wall_data.get("time_at_current_size")), 0.0)

        wall_price = self._as_float(wall_data.get("wall_price"))
        best_bid = self._as_float(market_context.get("best_bid"))
        best_ask = self._as_float(market_context.get("best_ask"))
        mid_price = self._as_float(market_context.get("mid_price"), default=(best_bid + best_ask) / 2.0)
        spread_ticks = max((best_ask - best_bid) / max(self.tick_size, 1e-9), 0.0)
        same_side_levels = self._as_pairs(market_context.get("same_side_levels"))
        opposite_side_levels = self._as_pairs(market_context.get("opposite_side_levels"))
        prior_same_side_levels = self._as_pairs(market_context.get("prior_same_side_levels"))

        # Block C — local depth geometry.
        neighborhood = self._neighborhood_sizes(same_side_levels, wall_price, 5)
        neighborhood_mean = float(np.mean(neighborhood)) if neighborhood else 0.0
        neighborhood_std = float(np.std(neighborhood)) if len(neighborhood) >= 2 else 0.0
        vec[_IDX["prominence_zscore"]] = (
            (current_size - neighborhood_mean) / neighborhood_std if neighborhood_std > 1e-9 else 0.0
        )
        vec[_IDX["same_side_depth_behind"]] = self._depth_sum(same_side_levels, wall_price, side, 1, 3, toward_mid=False)
        vec[_IDX["same_side_depth_ahead"]] = self._depth_sum(same_side_levels, wall_price, side, 1, 3, toward_mid=True)
        vec[_IDX["opposite_depth_mirror"]] = self._mirror_depth(opposite_side_levels, wall_price, mid_price)
        vec[_IDX["cluster_density"]] = self._cluster_density(same_side_levels, wall_price, current_size)
        vec[_IDX["depth_slope"]] = self._depth_slope(same_side_levels, wall_price)
        vec[_IDX["vacuum_behind"]] = 1.0 if self._has_vacuum(same_side_levels, wall_price, side) else 0.0
        vec[_IDX["ladder_correlation"]] = self._ladder_correlation(same_side_levels, prior_same_side_levels, wall_price)

        bid_volumes = self._as_float_list(market_context.get("bid_volumes"))
        ask_volumes = self._as_float_list(market_context.get("ask_volumes"))
        price_returns_2m = self._as_float_list(market_context.get("price_returns_2m"))
        recent_ranges = self._as_float_list(market_context.get("recent_ranges"))

        # Block D — market context.
        vec[_IDX["distance_from_mid"]] = abs(wall_price - mid_price) / max(self.tick_size, 1e-9)
        same_side_bbo = best_ask if side == 1 else best_bid
        vec[_IDX["distance_from_bbo"]] = abs(wall_price - same_side_bbo) / max(self.tick_size, 1e-9)
        vec[_IDX["spread_ticks"]] = spread_ticks
        top10_bid = float(sum(bid_volumes[:10]))
        top10_ask = float(sum(ask_volumes[:10]))
        total_top10 = top10_bid + top10_ask
        vec[_IDX["book_imbalance_top10"]] = (top10_bid - top10_ask) / total_top10 if total_top10 > 0 else 0.0
        vec[_IDX["session_phase"]] = self._as_float(market_context.get("session_phase"))
        vec[_IDX["minutes_since_open"]] = self._as_float(market_context.get("minutes_since_open"))
        vec[_IDX["realized_vol_2m"]] = float(np.std(price_returns_2m)) if len(price_returns_2m) >= 2 else 0.0
        current_range = self._as_float(market_context.get("current_range"))
        baseline_range = float(mean(recent_ranges[-10:])) if recent_ranges else 0.0
        vec[_IDX["range_expansion_flag"]] = 1.0 if baseline_range > 0 and current_range > (1.5 * baseline_range) else 0.0

        # Block E — flow context.
        vec[_IDX["cumulative_delta"]] = self._as_float(flow_context.get("cumulative_delta"))
        vec[_IDX["delta_2s"]] = self._as_float(flow_context.get("delta_2s"))
        vec[_IDX["delta_10s"]] = self._as_float(flow_context.get("delta_10s"))
        vec[_IDX["approach_speed"]] = self._as_float(flow_context.get("approach_speed"))
        vec[_IDX["consecutive_aggressor"]] = self._as_float(flow_context.get("consecutive_aggressor"))
        vec[_IDX["sweep_flag"]] = 1.0 if flow_context.get("sweep_flag") else 0.0

        # Block F — attack / defense state.
        vec[_IDX["absorbed_volume"]] = self._as_float(attack_context.get("absorbed_volume"))
        vec[_IDX["absorption_ratio"]] = vec[_IDX["absorbed_volume"]] / max(current_size, 1.0)
        vec[_IDX["tests_count"]] = self._as_float(attack_context.get("tests_count"))
        vec[_IDX["recovery_after_test"]] = 1.0 if attack_context.get("recovery_after_test") else 0.0
        vec[_IDX["time_since_last_test"]] = max(self._as_float(attack_context.get("time_since_last_test")), 0.0)
        vec[_IDX["attack_intensity"]] = self._as_float(attack_context.get("attack_intensity"))

        if self._normalize:
            self._stats.update(vec)
            vec = self._stats.normalize(vec)

        return vec

    def extract_batch(
        self,
        walls: list[dict],
        market_context: dict,
        flow_context: dict,
        attack_context: dict | list[dict],
    ) -> np.ndarray:
        if not walls:
            return np.zeros((0, NUM_CAUSAL_FEATURES), dtype=np.float64)
        raw_vectors: list[np.ndarray] = []
        saved_normalize = self._normalize
        self._normalize = False
        try:
            for idx, wall in enumerate(walls):
                current_attack_context = (
                    attack_context[idx] if isinstance(attack_context, list) else attack_context
                )
                raw_vectors.append(self.extract(wall, market_context, flow_context, current_attack_context))
        finally:
            self._normalize = saved_normalize
        batch = np.stack(raw_vectors, axis=0)
        if saved_normalize:
            self._stats.update(batch)
            batch = self._stats.normalize(batch)
        return batch

    def normalize_features(self, features: np.ndarray) -> np.ndarray:
        return self._stats.normalize(features)

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return float(default)
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def _as_float_list(value: Any) -> list[float]:
        if value is None:
            return []
        if isinstance(value, np.ndarray):
            return [float(item) for item in value.tolist()]
        if isinstance(value, (list, tuple, deque)):
            return [float(item) for item in value]
        return []

    @staticmethod
    def _as_pairs(value: Any) -> list[tuple[float, float]]:
        if value is None:
            return []
        pairs: list[tuple[float, float]] = []
        for item in value:
            try:
                price, size = item
                pairs.append((float(price), float(size)))
            except (TypeError, ValueError):
                continue
        return pairs

    @staticmethod
    def _encode_side(value: Any) -> int:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"ask", "a", "1"}:
                return 1
            if lowered in {"bid", "b", "0"}:
                return 0
        try:
            return 1 if int(value) == 1 else 0
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _count_recent(times_ago_seconds: Iterable[float], window: float) -> float:
        return float(sum(1 for delta in times_ago_seconds if 0.0 <= float(delta) <= window))

    def _neighborhood_sizes(self, levels: list[tuple[float, float]], wall_price: float, radius_ticks: int) -> list[float]:
        result: list[float] = []
        for price, size in levels:
            tick_distance = abs(price - wall_price) / max(self.tick_size, 1e-9)
            if tick_distance <= radius_ticks:
                result.append(size)
        return result

    def _depth_sum(
        self,
        levels: list[tuple[float, float]],
        wall_price: float,
        side: int,
        start_ticks: int,
        end_ticks: int,
        toward_mid: bool,
    ) -> float:
        total = 0.0
        direction = 1 if side == 0 else -1
        if toward_mid:
            direction *= -1
        targets = {
            round(wall_price + (direction * step * self.tick_size), 10)
            for step in range(start_ticks, end_ticks + 1)
        }
        for price, size in levels:
            if round(price, 10) in targets:
                total += size
        return total

    def _mirror_depth(self, opposite_levels: list[tuple[float, float]], wall_price: float, mid_price: float) -> float:
        distance = wall_price - mid_price
        mirror_price = round(mid_price - distance, 10)
        for price, size in opposite_levels:
            if round(price, 10) == mirror_price:
                return size
        return 0.0

    def _cluster_density(self, levels: list[tuple[float, float]], wall_price: float, current_size: float) -> float:
        threshold = current_size * 0.5
        count = 0
        for price, size in levels:
            tick_distance = abs(price - wall_price) / max(self.tick_size, 1e-9)
            if tick_distance <= 3 and size >= threshold:
                count += 1
        return float(count)

    def _depth_slope(self, levels: list[tuple[float, float]], wall_price: float) -> float:
        x: list[float] = []
        y: list[float] = []
        for price, size in levels:
            offset = (price - wall_price) / max(self.tick_size, 1e-9)
            if abs(offset) <= 5:
                x.append(offset)
                y.append(size)
        if len(x) < 2:
            return 0.0
        slope, _ = np.polyfit(np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64), 1)
        return float(slope)

    def _has_vacuum(self, levels: list[tuple[float, float]], wall_price: float, side: int) -> bool:
        direction = -1 if side == 0 else 1
        targets = {
            round(wall_price + (direction * step * self.tick_size), 10)
            for step in range(1, 4)
        }
        size_map = {round(price, 10): size for price, size in levels}
        return any(size_map.get(target, 0.0) <= 0.0 for target in targets)

    def _ladder_correlation(
        self,
        levels: list[tuple[float, float]],
        prior_levels: list[tuple[float, float]],
        wall_price: float,
    ) -> float:
        current_map = {round(price, 10): size for price, size in levels}
        prior_map = {round(price, 10): size for price, size in prior_levels}
        keys = [round(wall_price + (step * self.tick_size), 10) for step in range(-3, 4)]
        current = np.asarray([float(current_map.get(key, 0.0)) for key in keys], dtype=np.float64)
        prior = np.asarray([float(prior_map.get(key, 0.0)) for key in keys], dtype=np.float64)
        delta = current - prior
        if np.allclose(current.std(), 0.0) or np.allclose(delta.std(), 0.0):
            return 0.0
        return float(np.corrcoef(current, delta)[0, 1])


__all__ = [
    "CAUSAL_FEATURE_NAMES",
    "CausalFeatureExtractor",
    "NUM_CAUSAL_FEATURES",
    "RollingStats",
    "get_causal_feature_names",
]
