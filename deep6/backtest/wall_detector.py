"""Streaming wall detection and classification during MBO replay."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from deep6.ml.depth_radar.classifier import WallClassifier
from deep6.ml.depth_radar.wall_features import WallFeatureExtractor


_ALLOWED_CLASSES = {"GENUINE", "SPOOF", "ICEBERG", "STALE", "UNKNOWN"}
_ASK_CODES = {"A", "ASK", "ASK_SIDE"}
_BID_CODES = {"B", "BID", "BID_SIDE"}


@dataclass
class ClassifiedWall:
    price: float
    size: int
    side: str
    classification: str
    confidence: float
    heat: float
    persistence_sec: float
    refill_count: int
    features: list[float]
    detected_at: float


@dataclass
class WallState:
    price: float
    side: str
    creation_ts_ns: int
    last_update_ts_ns: int
    original_size: int
    max_size: int
    current_size: int
    modification_count: int = 0
    cancellation_count: int = 0
    refill_count: int = 0
    filled_volume: int = 0
    price_crossed: bool = False
    price_cross_ts_ns: int | None = None
    order_ids_seen: set[str] = field(default_factory=set)
    _below_refill_threshold: bool = field(default=False, init=False, repr=False)

    def update_size(self, new_size: int, ts_ns: int, refill_drop_ratio: float) -> None:
        size = max(int(new_size), 0)
        previous = self.current_size

        if size != previous:
            self.modification_count += 1
        if previous > 0 and size == 0:
            self.cancellation_count += 1

        reference_max = max(self.max_size, previous)
        refill_floor = max(0.0, reference_max * (1.0 - refill_drop_ratio))
        refill_recovery = max(refill_floor, reference_max * 0.5)
        if reference_max > 0:
            if size <= refill_floor:
                self._below_refill_threshold = True
            elif self._below_refill_threshold and size >= refill_recovery and size > previous:
                self.refill_count += 1
                self._below_refill_threshold = False

        self.current_size = size
        if size > self.max_size:
            self.max_size = size
            self._below_refill_threshold = False
        self.last_update_ts_ns = ts_ns

    def mark_fill(self, fill_size: int, new_size: int, ts_ns: int, refill_drop_ratio: float) -> None:
        self.filled_volume += max(int(fill_size), 0)
        self.update_size(new_size, ts_ns, refill_drop_ratio)

    def mark_price_cross(self, ts_ns: int) -> None:
        if not self.price_crossed:
            self.price_crossed = True
            self.price_cross_ts_ns = ts_ns


class WallDetector:
    def __init__(
        self,
        model_path: str = "deep6/models/depth_radar_classifier_4class.joblib",
        wall_min_size: int = 50,
        wall_stale_sec: float = 90.0,
        spoof_confidence_threshold: float = 0.5,
    ) -> None:
        self.model_path = str(Path(model_path))
        self.wall_min_size = int(wall_min_size)
        self.wall_stale_sec = float(wall_stale_sec)
        self.spoof_confidence_threshold = float(spoof_confidence_threshold)
        self.refill_drop_ratio = 0.70

        self.classifier = WallClassifier(model_path=self.model_path)
        self.feature_extractor = WallFeatureExtractor(tick_size=0.25, normalize=True)

        self._orders: dict[str, tuple[float, int, str]] = {}
        self._bid_levels: dict[float, int] = defaultdict(int)
        self._ask_levels: dict[float, int] = defaultdict(int)
        self._walls: dict[tuple[str, float], WallState] = {}

    def process_event(self, price: float, size: int, side: str, action: str, order_id: str, ts_ns: int) -> None:
        action_code = str(action or "").upper()
        side_code, wall_side = self._normalize_side(side)
        order_key = str(order_id)
        price_value = float(price)
        size_value = max(int(size), 0)
        ts_value = int(ts_ns)

        if action_code == "R":
            self._orders.clear()
            self._bid_levels.clear()
            self._ask_levels.clear()
            self._prune_stale(ts_value, force=True)
            return

        if side_code is None:
            self._prune_stale(ts_value)
            return

        self._apply_book_event(price_value, size_value, side_code, action_code, order_key)
        level_size = self._current_level_size(side_code, price_value)
        key = (wall_side, price_value)
        tracker = self._walls.get(key)

        if tracker is None and level_size >= self.wall_min_size and action_code == "A":
            tracker = WallState(
                price=price_value,
                side=wall_side,
                creation_ts_ns=ts_value,
                last_update_ts_ns=ts_value,
                original_size=level_size,
                max_size=level_size,
                current_size=level_size,
            )
            tracker.order_ids_seen.add(order_key)
            self._walls[key] = tracker
        elif tracker is not None:
            tracker.order_ids_seen.add(order_key)
            if action_code in {"T", "F"}:
                tracker.mark_fill(size_value, level_size, ts_value, self.refill_drop_ratio)
            else:
                tracker.update_size(level_size, ts_value, self.refill_drop_ratio)

        self._mark_crossed_walls(ts_value)
        self._prune_stale(ts_value)

    def get_active_walls(self) -> list[ClassifiedWall]:
        now_ns = max((wall.last_update_ts_ns for wall in self._walls.values()), default=0)
        self._prune_stale(now_ns)
        return self._classify_walls(now_ns)

    def get_walls_at_bar_close(self, bar_ts_ns: int) -> list[ClassifiedWall]:
        ts_ns = int(bar_ts_ns)
        self._prune_stale(ts_ns)
        return self._classify_walls(ts_ns)

    def _classify_walls(self, ts_ns: int) -> list[ClassifiedWall]:
        active_states = [wall for wall in self._walls.values() if wall.current_size > 0]
        if not active_states:
            return []

        market_context = self._build_market_context()
        wall_dicts = [self._wall_to_feature_dict(wall, ts_ns) for wall in active_states]
        feature_matrix = self.feature_extractor.extract_batch(wall_dicts, market_context)
        model_results = self._classify_feature_matrix(feature_matrix)

        classified: list[ClassifiedWall] = []
        for wall, feature_row, model_result in zip(active_states, feature_matrix, model_results, strict=False):
            label, confidence = model_result
            if confidence < self.spoof_confidence_threshold or label not in _ALLOWED_CLASSES:
                label, confidence = self._apply_rule_based(wall, ts_ns)

            persistence_sec = max(0.0, (ts_ns - wall.creation_ts_ns) / 1e9)
            heat = min(1.0, persistence_sec / max(self.wall_stale_sec, 1.0))
            classified.append(
                ClassifiedWall(
                    price=wall.price,
                    size=wall.current_size,
                    side=wall.side,
                    classification=label,
                    confidence=float(max(0.0, min(1.0, confidence))),
                    heat=float(max(0.0, min(1.0, heat))),
                    persistence_sec=persistence_sec,
                    refill_count=wall.refill_count,
                    features=feature_row.astype(float).tolist(),
                    detected_at=ts_ns / 1e9,
                )
            )
        return classified

    def _classify_feature_matrix(self, feature_matrix: np.ndarray) -> list[tuple[str, float]]:
        if feature_matrix.size == 0:
            return []

        classifier = self.classifier
        classify_with_probs = getattr(classifier, "classify_batch_with_probs", None)
        if callable(classify_with_probs):
            raw_results = classify_with_probs(feature_matrix)
            return [(str(label).upper(), float(confidence)) for label, confidence, _ in raw_results]

        classify_batch = getattr(classifier, "classify_batch", None)
        if callable(classify_batch):
            raw_results = classify_batch(feature_matrix)
            return [(str(label).upper(), float(confidence)) for label, confidence in raw_results]

        classify_one = getattr(classifier, "classify", None)
        if callable(classify_one):
            return [(str(label).upper(), float(confidence)) for label, confidence in (classify_one(row) for row in feature_matrix)]

        return [("UNKNOWN", 0.0) for _ in range(feature_matrix.shape[0])]

    def _apply_rule_based(self, wall_state: WallState, ts_ns: int | None = None) -> tuple[str, float]:
        now_ns = wall_state.last_update_ts_ns if ts_ns is None else int(ts_ns)
        spoof_score = self._compute_spoof_score(wall_state, now_ns)
        freshness_score = self._compute_freshness_score(wall_state, now_ns)

        if spoof_score >= 70.0:
            return "SPOOF", 0.0
        if freshness_score < 0.1:
            return "STALE", 0.0
        if wall_state.refill_count >= 2:
            return "ICEBERG", 0.8
        if wall_state.max_size >= self.wall_min_size:
            return "GENUINE", 0.9
        return "UNKNOWN", 0.5

    def _compute_spoof_score(self, wall_state: WallState, ts_ns: int) -> float:
        avg_wall_size = max(self._average_active_wall_size(), 1.0)
        ticks_from_bbo = self._ticks_from_bbo(wall_state)

        cancel_ratio = wall_state.cancellation_count / float(wall_state.cancellation_count + 1)
        cancellation_score = min(40.0, (cancel_ratio / 0.95) * 40.0)

        time_in_book_ms = max(0.0, (ts_ns - wall_state.creation_ts_ns) / 1e6)
        time_in_book_score = 0.0
        if wall_state.cancellation_count > 0:
            time_in_book_score = max(0.0, min(25.0, 25.0 * (1.0 - ((time_in_book_ms - 500.0) / 4500.0))))

        size_ratio = wall_state.max_size / avg_wall_size
        size_anomaly_score = max(0.0, min(20.0, ((size_ratio - 1.0) / 4.0) * 20.0))
        distance_score = min(10.0, (ticks_from_bbo / 10.0) * 10.0) if ticks_from_bbo > 0.0 else 0.0

        elapsed_seconds = max(1.0, (ts_ns - wall_state.creation_ts_ns) / 1e9)
        modification_rate = wall_state.modification_count / elapsed_seconds
        modification_score = min(5.0, (modification_rate / 10.0) * 5.0)
        return cancellation_score + time_in_book_score + size_anomaly_score + distance_score + modification_score

    def _compute_freshness_score(self, wall_state: WallState, ts_ns: int) -> float:
        minutes_since_update = max(0.0, (ts_ns - wall_state.last_update_ts_ns) / 60e9)
        time_decay = float(np.exp(-0.02 * minutes_since_update))

        price_cross_penalty = 1.0
        if wall_state.price_crossed and wall_state.price_cross_ts_ns is not None:
            seconds_since_cross = max(0.0, (ts_ns - wall_state.price_cross_ts_ns) / 1e9)
            price_cross_penalty = float(np.exp(-0.1 * seconds_since_cross))

        mod_penalty = float(np.exp(-0.05 * wall_state.modification_count))
        distance_penalty = 1.0 / (1.0 + 0.05 * self._ticks_from_bbo(wall_state))
        return max(0.0, min(1.0, time_decay * price_cross_penalty * mod_penalty * distance_penalty))

    def _build_market_context(self) -> dict[str, Any]:
        bid_prices = sorted(self._bid_levels.keys(), reverse=True)[:10]
        ask_prices = sorted(self._ask_levels.keys())[:10]
        bid_sizes = [int(self._bid_levels[p]) for p in bid_prices]
        ask_sizes = [int(self._ask_levels[p]) for p in ask_prices]
        best_bid = bid_prices[0] if bid_prices else 0.0
        best_ask = ask_prices[0] if ask_prices else 0.0
        mid_price = (best_bid + best_ask) / 2.0 if best_bid and best_ask else best_bid or best_ask
        return {
            "mid_price": mid_price,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": max(0.0, best_ask - best_bid) if best_bid and best_ask else 0.0,
            "avg_wall_size": self._average_active_wall_size(),
            "bid_volumes": bid_sizes,
            "ask_volumes": ask_sizes,
        }

    def _wall_to_feature_dict(self, wall_state: WallState, ts_ns: int) -> dict[str, Any]:
        return {
            "time_in_book": max(0.0, (ts_ns - wall_state.creation_ts_ns) / 1e9),
            "modification_count": wall_state.modification_count,
            "cancellation_count": wall_state.cancellation_count,
            "original_size": wall_state.original_size,
            "max_size": wall_state.max_size,
            "current_size": wall_state.current_size,
            "refill_count": wall_state.refill_count,
            "price_crossed": wall_state.price_crossed,
            "side": 0 if wall_state.side == "bid" else 1,
            "wall_price": wall_state.price,
            "first_seen_time": wall_state.creation_ts_ns / 1e9,
        }

    def _prune_stale(self, ts_ns: int, force: bool = False) -> None:
        if force:
            self._walls.clear()
            return

        cutoff_ns = int(self.wall_stale_sec * 1e9)
        stale_keys = [
            key for key, wall in self._walls.items()
            if ts_ns > 0 and (ts_ns - wall.last_update_ts_ns) >= cutoff_ns
        ]
        for key in stale_keys:
            self._walls.pop(key, None)

    def _mark_crossed_walls(self, ts_ns: int) -> None:
        best_bid = max(self._bid_levels.keys(), default=0.0)
        best_ask = min(self._ask_levels.keys(), default=0.0)
        for wall in self._walls.values():
            if wall.price_crossed:
                continue
            if wall.side == "bid" and best_bid > 0.0 and best_bid < wall.price:
                wall.mark_price_cross(ts_ns)
            elif wall.side == "ask" and best_ask > 0.0 and best_ask > wall.price:
                wall.mark_price_cross(ts_ns)

    def _apply_book_event(self, price: float, size: int, side_code: str, action: str, order_id: str) -> None:
        levels = self._bid_levels if side_code == "B" else self._ask_levels

        if action == "A":
            self._orders[order_id] = (price, size, side_code)
            levels[price] += size
            return

        if action == "M":
            previous = self._orders.get(order_id)
            if previous is not None:
                prev_price, prev_size, prev_side = previous
                prev_levels = self._bid_levels if prev_side == "B" else self._ask_levels
                prev_levels[prev_price] -= prev_size
                if prev_levels[prev_price] <= 0:
                    prev_levels.pop(prev_price, None)
            self._orders[order_id] = (price, size, side_code)
            levels[price] += size
            return

        if action == "C":
            previous = self._orders.pop(order_id, None)
            if previous is None:
                return
            prev_price, prev_size, prev_side = previous
            prev_levels = self._bid_levels if prev_side == "B" else self._ask_levels
            prev_levels[prev_price] -= prev_size
            if prev_levels[prev_price] <= 0:
                prev_levels.pop(prev_price, None)
            return

        if action in {"T", "F"}:
            previous = self._orders.get(order_id)
            if previous is None:
                return
            prev_price, prev_size, prev_side = previous
            prev_levels = self._bid_levels if prev_side == "B" else self._ask_levels
            new_size = prev_size - size
            if new_size <= 0:
                self._orders.pop(order_id, None)
                prev_levels[prev_price] -= prev_size
            else:
                self._orders[order_id] = (prev_price, new_size, prev_side)
                prev_levels[prev_price] -= size
            if prev_levels[prev_price] <= 0:
                prev_levels.pop(prev_price, None)

    def _current_level_size(self, side_code: str, price: float) -> int:
        levels = self._bid_levels if side_code == "B" else self._ask_levels
        return int(levels.get(price, 0))

    def _average_active_wall_size(self) -> float:
        sizes = [wall.max_size for wall in self._walls.values() if wall.current_size > 0]
        if not sizes:
            return float(max(self.wall_min_size, 1))
        return float(sum(sizes) / len(sizes))

    def _ticks_from_bbo(self, wall_state: WallState) -> float:
        tick_size = max(self.feature_extractor.tick_size, 1e-9)
        if wall_state.side == "bid":
            best_bid = max(self._bid_levels.keys(), default=wall_state.price)
            return abs(wall_state.price - best_bid) / tick_size
        best_ask = min(self._ask_levels.keys(), default=wall_state.price)
        return abs(wall_state.price - best_ask) / tick_size

    @staticmethod
    def _normalize_side(side: str) -> tuple[str | None, str]:
        normalized = str(side or "").upper()
        if normalized in _ASK_CODES:
            return "A", "ask"
        if normalized in _BID_CODES:
            return "B", "bid"
        return None, "unknown"
