"""Wall feature extractor for the LightGBM classifier (T12).

Converts per-wall lifecycle data into a 15-feature vector suitable for
LightGBM classification. Features capture wall placement, modification
behavior, market context, and order book state at observation time.

Feature normalization uses z-score with Welford's online algorithm for
numerically stable running mean/variance over a configurable window.
"""
from __future__ import annotations

from collections import deque

import numpy as np

# ---------------------------------------------------------------------------
# FEATURE_NAMES -- ordered list of all 15 wall features
# ---------------------------------------------------------------------------
FEATURE_NAMES: list[str] = [
    "time_in_book",        # 1. seconds since first appearance
    "modification_count",  # 2. total modifications
    "cancellation_count",  # 3. times cancelled and reappeared
    "original_size",       # 4. size when first placed
    "max_size",            # 5. peak size observed
    "current_size",        # 6. current resting size
    "size_ratio",          # 7. max_size / average_wall_size (relative to market)
    "distance_from_mid",   # 8. ticks from current mid price
    "distance_from_bbo",   # 9. ticks from best bid/offer
    "spread_at_placement", # 10. spread when order was placed
    "book_imbalance",      # 11. (bid_vol - ask_vol) / (bid_vol + ask_vol) top 10
    "side",                # 12. 0 for bid, 1 for ask
    "refill_count",        # 13. iceberg refill counter
    "price_crossed",       # 14. 1 if price traded through this level, 0 otherwise
    "modification_rate",   # 15. modifications per second
]
assert len(FEATURE_NAMES) == 15, f"Expected 15 features, got {len(FEATURE_NAMES)}"

NUM_FEATURES = 15

# Feature indices for direct access
_IDX: dict[str, int] = {name: idx for idx, name in enumerate(FEATURE_NAMES)}


def get_feature_names() -> list[str]:
    """Return ordered list of feature names for column labeling."""
    return list(FEATURE_NAMES)


# ---------------------------------------------------------------------------
# RollingStats -- Welford's online algorithm for running mean/std
# ---------------------------------------------------------------------------
class RollingStats:
    """Maintain running mean and standard deviation over a sliding window.

    Uses a deque-based approach: stores the last ``window`` feature vectors
    and recomputes mean/std from the buffer. Trades O(window) recompute cost
    for exact statistics without numerical drift.

    Args:
        window: Number of recent observations to track. Default 1000.
    """

    def __init__(self, window: int = 1000) -> None:
        self._window = max(1, window)
        self._buffer: deque[np.ndarray] = deque(maxlen=self._window)
        self._mean: np.ndarray = np.zeros(NUM_FEATURES, dtype=np.float64)
        self._std: np.ndarray = np.ones(NUM_FEATURES, dtype=np.float64)
        self._dirty = True

    @property
    def count(self) -> int:
        """Number of observations currently in the window."""
        return len(self._buffer)

    def update(self, features: np.ndarray) -> None:
        """Add a feature vector (or batch) to the rolling window.

        Args:
            features: 1D array of shape (15,) or 2D array of shape (N, 15).
        """
        if features.ndim == 1:
            self._buffer.append(features.astype(np.float64, copy=True))
        elif features.ndim == 2:
            for row in features:
                self._buffer.append(row.astype(np.float64, copy=True))
        self._dirty = True

    def _recompute(self) -> None:
        """Recompute mean and std from the current buffer."""
        if len(self._buffer) < 2:
            self._mean = np.zeros(NUM_FEATURES, dtype=np.float64)
            self._std = np.ones(NUM_FEATURES, dtype=np.float64)
        else:
            stacked = np.stack(list(self._buffer), axis=0)
            self._mean = stacked.mean(axis=0)
            std = stacked.std(axis=0)
            # Clamp std to avoid division by zero -- features with no variance
            # get std=1.0 so z-score leaves them at (x - mean).
            std[std < 1e-9] = 1.0
            self._std = std
        self._dirty = False

    def normalize(self, features: np.ndarray) -> np.ndarray:
        """Apply z-score normalization: (x - mean) / std.

        If fewer than 2 observations in the window, returns features unchanged.

        Args:
            features: 1D (15,) or 2D (N, 15) array of raw features.

        Returns:
            Normalized array with the same shape and dtype float64.
        """
        if len(self._buffer) < 2:
            return features.astype(np.float64)
        if self._dirty:
            self._recompute()
        return (features.astype(np.float64) - self._mean) / self._std


# ---------------------------------------------------------------------------
# WallFeatureExtractor
# ---------------------------------------------------------------------------
class WallFeatureExtractor:
    """Extract 15-feature vectors from wall lifecycle data for LightGBM.

    Args:
        tick_size: Instrument tick size. Default 0.25 (NQ).
        normalize: Whether to apply z-score normalization via RollingStats.
        rolling_window: Window size for RollingStats. Default 1000.
    """

    def __init__(
        self,
        tick_size: float = 0.25,
        normalize: bool = True,
        rolling_window: int = 1000,
    ) -> None:
        self.tick_size = tick_size
        self._normalize = normalize
        self._stats = RollingStats(window=rolling_window)

    @property
    def stats(self) -> RollingStats:
        """Access the underlying RollingStats for external inspection."""
        return self._stats

    def extract(self, wall_data: dict, market_context: dict) -> np.ndarray:
        """Extract a single 15-feature vector from one wall observation.

        Args:
            wall_data: Per-wall lifecycle fields.
                Required keys: time_in_book, modification_count,
                cancellation_count, original_size, max_size, current_size,
                refill_count, price_crossed, side, first_seen_time.
                Optional: wall_price (for distance features; defaults to 0).
            market_context: Current market state.
                Required keys: mid_price, best_bid, best_ask, spread,
                avg_wall_size, bid_volumes (list, top 10), ask_volumes
                (list, top 10).

        Returns:
            1D numpy array of shape (15,) with dtype float64.
        """
        vec = np.zeros(NUM_FEATURES, dtype=np.float64)

        # -- Raw wall lifecycle fields --
        time_in_book = float(wall_data.get("time_in_book") or 0.0)
        time_in_book = max(1.0, time_in_book)  # floor at 1s to avoid div-by-zero

        vec[_IDX["time_in_book"]] = time_in_book
        vec[_IDX["modification_count"]] = float(wall_data.get("modification_count") or 0)
        vec[_IDX["cancellation_count"]] = float(wall_data.get("cancellation_count") or 0)
        vec[_IDX["original_size"]] = float(wall_data.get("original_size") or 0)
        vec[_IDX["max_size"]] = float(wall_data.get("max_size") or 0)
        vec[_IDX["current_size"]] = float(wall_data.get("current_size") or 0)

        # -- Derived: size_ratio --
        avg_wall_size = float(market_context.get("avg_wall_size") or 1)
        avg_wall_size = max(1.0, avg_wall_size)
        vec[_IDX["size_ratio"]] = vec[_IDX["max_size"]] / avg_wall_size

        # -- Distance features (in ticks) --
        wall_price = float(wall_data.get("wall_price") or 0.0)
        mid_price = float(market_context.get("mid_price") or 0.0)
        best_bid = float(market_context.get("best_bid") or 0.0)
        best_ask = float(market_context.get("best_ask") or 0.0)
        spread = float(market_context.get("spread") or 0.0)
        side_val = int(wall_data.get("side") or 0)  # 0=bid, 1=ask

        vec[_IDX["distance_from_mid"]] = abs(wall_price - mid_price) / self.tick_size
        # Use best_bid for bid walls, best_ask for ask walls
        bbo_ref = best_ask if side_val == 1 else best_bid
        vec[_IDX["distance_from_bbo"]] = abs(wall_price - bbo_ref) / self.tick_size
        vec[_IDX["spread_at_placement"]] = spread / self.tick_size

        # -- Book imbalance (top 10 levels) --
        bid_vols = market_context.get("bid_volumes") or []
        ask_vols = market_context.get("ask_volumes") or []
        bid_sum = float(sum(bid_vols[:10]))
        ask_sum = float(sum(ask_vols[:10]))
        total_vol = bid_sum + ask_sum
        vec[_IDX["book_imbalance"]] = (bid_sum - ask_sum) / max(1.0, total_vol)

        # -- Categorical / binary --
        vec[_IDX["side"]] = float(side_val)
        vec[_IDX["refill_count"]] = float(wall_data.get("refill_count") or 0)
        vec[_IDX["price_crossed"]] = 1.0 if wall_data.get("price_crossed") else 0.0

        # -- Rate feature --
        mod_count = vec[_IDX["modification_count"]]
        vec[_IDX["modification_rate"]] = mod_count / time_in_book

        # -- Normalize if enabled --
        if self._normalize:
            self._stats.update(vec)
            vec = self._stats.normalize(vec)

        return vec

    def extract_batch(
        self, walls: list[dict], market_context: dict
    ) -> np.ndarray:
        """Extract features for multiple walls in a single call.

        Args:
            walls: List of wall_data dicts (same schema as extract()).
            market_context: Shared market state for all walls in this snapshot.

        Returns:
            2D numpy array of shape (len(walls), 15) with dtype float64.
            Returns empty (0, 15) array if walls is empty.
        """
        if not walls:
            return np.zeros((0, NUM_FEATURES), dtype=np.float64)

        # Build raw feature matrix first (before normalization)
        raw_vectors: list[np.ndarray] = []
        saved_normalize = self._normalize
        self._normalize = False  # disable per-row normalize in extract()
        try:
            for wall in walls:
                raw_vectors.append(self.extract(wall, market_context))
        finally:
            self._normalize = saved_normalize

        batch = np.stack(raw_vectors, axis=0)  # (N, 15)

        if saved_normalize:
            self._stats.update(batch)
            batch = self.normalize_features(batch)

        return batch

    def normalize_features(self, features: np.ndarray) -> np.ndarray:
        """Apply z-score normalization using rolling statistics.

        Args:
            features: 1D (15,) or 2D (N, 15) raw feature array.

        Returns:
            Normalized array with same shape, dtype float64.
        """
        return self._stats.normalize(features)
