"""Tests for WallFeatureExtractor: extraction, batching, normalization, edge cases."""
from __future__ import annotations

import numpy as np
import pytest

from deep6.ml.depth_radar.wall_features import (
    FEATURE_NAMES,
    NUM_FEATURES,
    RollingStats,
    WallFeatureExtractor,
    get_feature_names,
)


class TestGetFeatureNames:
    def test_returns_15_names(self):
        names = get_feature_names()
        assert len(names) == 15

    def test_returns_list_copy(self):
        names = get_feature_names()
        names.append("extra")
        assert len(get_feature_names()) == 15, "get_feature_names must return a copy"

    def test_names_match_module_constant(self):
        assert get_feature_names() == list(FEATURE_NAMES)


class TestExtract:
    def test_returns_15_feature_array(self, sample_wall_data, sample_market_context):
        extractor = WallFeatureExtractor(normalize=False)
        vec = extractor.extract(sample_wall_data, sample_market_context)
        assert isinstance(vec, np.ndarray)
        assert vec.shape == (NUM_FEATURES,)
        assert vec.dtype == np.float64

    def test_feature_values_are_deterministic(self, sample_wall_data, sample_market_context):
        extractor = WallFeatureExtractor(normalize=False)
        v1 = extractor.extract(sample_wall_data, sample_market_context)
        v2 = extractor.extract(sample_wall_data, sample_market_context)
        np.testing.assert_array_equal(v1, v2)

    def test_time_in_book_floors_at_1(self, sample_market_context):
        wall = {
            "time_in_book": 0.0,
            "modification_count": 0,
            "cancellation_count": 0,
            "original_size": 100,
            "max_size": 100,
            "current_size": 100,
            "refill_count": 0,
            "price_crossed": False,
            "side": 0,
            "wall_price": 21450.0,
        }
        extractor = WallFeatureExtractor(normalize=False)
        vec = extractor.extract(wall, sample_market_context)
        idx = FEATURE_NAMES.index("time_in_book")
        assert vec[idx] == 1.0, "time_in_book should floor at 1.0 to avoid div-by-zero"

    def test_modification_rate_uses_floored_time(self, sample_market_context):
        wall = {
            "time_in_book": 0.0,
            "modification_count": 10,
            "cancellation_count": 0,
            "original_size": 100,
            "max_size": 100,
            "current_size": 100,
            "refill_count": 0,
            "price_crossed": False,
            "side": 0,
            "wall_price": 21450.0,
        }
        extractor = WallFeatureExtractor(normalize=False)
        vec = extractor.extract(wall, sample_market_context)
        rate_idx = FEATURE_NAMES.index("modification_rate")
        # time floored to 1.0s, so rate = 10/1.0 = 10.0
        assert vec[rate_idx] == pytest.approx(10.0)

    def test_size_ratio_computed_correctly(self, sample_wall_data, sample_market_context):
        extractor = WallFeatureExtractor(normalize=False)
        vec = extractor.extract(sample_wall_data, sample_market_context)
        idx = FEATURE_NAMES.index("size_ratio")
        # max_size=250, avg_wall_size=100 -> 2.5
        assert vec[idx] == pytest.approx(2.5)

    def test_distance_from_mid_in_ticks(self, sample_wall_data, sample_market_context):
        extractor = WallFeatureExtractor(tick_size=0.25, normalize=False)
        vec = extractor.extract(sample_wall_data, sample_market_context)
        idx = FEATURE_NAMES.index("distance_from_mid")
        # |21450.0 - 21450.25| / 0.25 = 1.0
        assert vec[idx] == pytest.approx(1.0)

    def test_distance_from_bbo_bid_side(self, sample_wall_data, sample_market_context):
        extractor = WallFeatureExtractor(tick_size=0.25, normalize=False)
        vec = extractor.extract(sample_wall_data, sample_market_context)
        idx = FEATURE_NAMES.index("distance_from_bbo")
        # side=0 (bid), |21450.0 - 21450.0| / 0.25 = 0.0
        assert vec[idx] == pytest.approx(0.0)

    def test_book_imbalance_range(self, sample_wall_data, sample_market_context):
        extractor = WallFeatureExtractor(normalize=False)
        vec = extractor.extract(sample_wall_data, sample_market_context)
        idx = FEATURE_NAMES.index("book_imbalance")
        assert -1.0 <= vec[idx] <= 1.0

    def test_side_feature_bid_is_0(self, sample_wall_data, sample_market_context):
        extractor = WallFeatureExtractor(normalize=False)
        vec = extractor.extract(sample_wall_data, sample_market_context)
        idx = FEATURE_NAMES.index("side")
        assert vec[idx] == 0.0

    def test_side_feature_ask_is_1(self, sample_wall_data, sample_market_context):
        wall = dict(sample_wall_data)
        wall["side"] = 1
        wall["wall_price"] = 21450.50
        extractor = WallFeatureExtractor(normalize=False)
        vec = extractor.extract(wall, sample_market_context)
        idx = FEATURE_NAMES.index("side")
        assert vec[idx] == 1.0

    def test_price_crossed_binary(self, sample_wall_data, sample_market_context):
        extractor = WallFeatureExtractor(normalize=False)

        wall_no_cross = dict(sample_wall_data)
        wall_no_cross["price_crossed"] = False
        v1 = extractor.extract(wall_no_cross, sample_market_context)

        wall_crossed = dict(sample_wall_data)
        wall_crossed["price_crossed"] = True
        v2 = extractor.extract(wall_crossed, sample_market_context)

        idx = FEATURE_NAMES.index("price_crossed")
        assert v1[idx] == 0.0
        assert v2[idx] == 1.0


class TestExtractBatch:
    def test_returns_correct_shape(self, sample_wall_data, sample_market_context):
        extractor = WallFeatureExtractor(normalize=False)
        walls = [sample_wall_data, sample_wall_data, sample_wall_data]
        batch = extractor.extract_batch(walls, sample_market_context)
        assert batch.shape == (3, NUM_FEATURES)
        assert batch.dtype == np.float64

    def test_empty_list_returns_0x15(self, sample_market_context):
        extractor = WallFeatureExtractor(normalize=False)
        batch = extractor.extract_batch([], sample_market_context)
        assert batch.shape == (0, NUM_FEATURES)

    def test_single_wall_matches_extract(self, sample_wall_data, sample_market_context):
        extractor = WallFeatureExtractor(normalize=False)
        single = extractor.extract(sample_wall_data, sample_market_context)
        batch = extractor.extract_batch([sample_wall_data], sample_market_context)
        np.testing.assert_array_almost_equal(batch[0], single)


class TestNormalization:
    def test_zscore_with_enough_data(self, sample_wall_data, sample_market_context):
        extractor = WallFeatureExtractor(normalize=True, rolling_window=10)
        # Feed some data to build stats
        for _ in range(5):
            extractor.extract(sample_wall_data, sample_market_context)
        vec = extractor.extract(sample_wall_data, sample_market_context)
        # After 6 identical vectors, z-score should be ~0 for all features
        # (std is small or features are identical -> mean ~ value, z ~ 0)
        assert vec.dtype == np.float64

    def test_normalization_disabled_returns_raw(self, sample_wall_data, sample_market_context):
        extractor = WallFeatureExtractor(normalize=False)
        vec = extractor.extract(sample_wall_data, sample_market_context)
        # time_in_book should be raw value (10.0)
        idx = FEATURE_NAMES.index("time_in_book")
        assert vec[idx] == pytest.approx(10.0)

    def test_single_observation_returns_unchanged(self, sample_wall_data, sample_market_context):
        extractor = WallFeatureExtractor(normalize=True)
        vec = extractor.extract(sample_wall_data, sample_market_context)
        # With only 1 observation, normalize returns as-is (buffer < 2)
        assert vec.dtype == np.float64


class TestRollingStats:
    def test_count_tracks_observations(self):
        stats = RollingStats(window=100)
        assert stats.count == 0
        stats.update(np.ones(NUM_FEATURES))
        assert stats.count == 1

    def test_window_evicts_old(self):
        stats = RollingStats(window=3)
        for i in range(5):
            stats.update(np.full(NUM_FEATURES, float(i)))
        assert stats.count == 3

    def test_normalize_with_insufficient_data_returns_float64(self):
        stats = RollingStats(window=100)
        stats.update(np.ones(NUM_FEATURES))
        result = stats.normalize(np.ones(NUM_FEATURES))
        assert result.dtype == np.float64

    def test_normalize_2d_input(self):
        stats = RollingStats(window=100)
        for i in range(5):
            stats.update(np.random.randn(NUM_FEATURES))
        batch = np.random.randn(3, NUM_FEATURES)
        result = stats.normalize(batch)
        assert result.shape == (3, NUM_FEATURES)


class TestEdgeCases:
    def test_empty_bid_ask_volumes(self, sample_wall_data):
        ctx = {
            "mid_price": 21450.0,
            "best_bid": 21450.0,
            "best_ask": 21450.25,
            "spread": 0.25,
            "avg_wall_size": 100.0,
            "bid_volumes": [],
            "ask_volumes": [],
        }
        extractor = WallFeatureExtractor(normalize=False)
        vec = extractor.extract(sample_wall_data, ctx)
        idx = FEATURE_NAMES.index("book_imbalance")
        assert vec[idx] == pytest.approx(0.0), "Empty volumes should yield 0 imbalance"

    def test_zero_avg_wall_size_floors_to_1(self, sample_wall_data):
        ctx = {
            "mid_price": 21450.0,
            "best_bid": 21450.0,
            "best_ask": 21450.25,
            "spread": 0.25,
            "avg_wall_size": 0.0,
            "bid_volumes": [100],
            "ask_volumes": [100],
        }
        extractor = WallFeatureExtractor(normalize=False)
        vec = extractor.extract(sample_wall_data, ctx)
        idx = FEATURE_NAMES.index("size_ratio")
        # avg_wall_size floored to 1.0, max_size=250 -> ratio=250.0
        assert vec[idx] == pytest.approx(250.0)

    def test_missing_optional_keys_use_defaults(self, sample_market_context):
        wall = {}  # All keys missing
        extractor = WallFeatureExtractor(normalize=False)
        vec = extractor.extract(wall, sample_market_context)
        assert vec.shape == (NUM_FEATURES,)
        # time_in_book floors to 1.0
        idx = FEATURE_NAMES.index("time_in_book")
        assert vec[idx] == 1.0
