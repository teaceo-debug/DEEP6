"""Integration tests: end-to-end pipeline, classifier format, v1 integrity."""
from __future__ import annotations

import subprocess

import numpy as np
import pytest

from deep6.ml.depth_radar.wall_features import (
    FEATURE_NAMES,
    NUM_FEATURES,
    WallFeatureExtractor,
)
from deep6.ml.depth_radar.classifier import WallClassifier


class TestFeatureExtractionPipeline:
    """Test 1: Synthetic wall data -> extract features -> verify 15 features."""

    def test_synthetic_bid_wall_full_pipeline(self):
        """Create synthetic bid wall, extract features, verify values."""
        extractor = WallFeatureExtractor(tick_size=0.25, normalize=False)

        wall_data = {
            "time_in_book": 30.0,
            "modification_count": 5,
            "cancellation_count": 2,
            "original_size": 150,
            "max_size": 200,
            "current_size": 180,
            "refill_count": 1,
            "price_crossed": False,
            "side": 0,
            "wall_price": 21450.0,
        }
        market_context = {
            "mid_price": 21450.50,
            "best_bid": 21450.0,
            "best_ask": 21451.0,
            "spread": 1.0,
            "avg_wall_size": 100.0,
            "bid_volumes": [100, 80, 60, 50, 40, 30, 20, 10, 5, 3],
            "ask_volumes": [90, 70, 55, 45, 35, 25, 15, 8, 4, 2],
        }

        features = extractor.extract(wall_data, market_context)

        # Shape and type
        assert features.shape == (NUM_FEATURES,)
        assert features.dtype == np.float64

        # Verify specific feature values
        idx = {name: i for i, name in enumerate(FEATURE_NAMES)}

        assert features[idx["time_in_book"]] == pytest.approx(30.0)
        assert features[idx["modification_count"]] == pytest.approx(5.0)
        assert features[idx["cancellation_count"]] == pytest.approx(2.0)
        assert features[idx["original_size"]] == pytest.approx(150.0)
        assert features[idx["max_size"]] == pytest.approx(200.0)
        assert features[idx["current_size"]] == pytest.approx(180.0)
        assert features[idx["size_ratio"]] == pytest.approx(2.0)  # 200/100
        assert features[idx["distance_from_mid"]] == pytest.approx(2.0)  # |21450-21450.5|/0.25
        assert features[idx["distance_from_bbo"]] == pytest.approx(0.0)  # bid at best_bid
        assert features[idx["spread_at_placement"]] == pytest.approx(4.0)  # 1.0/0.25
        assert features[idx["side"]] == pytest.approx(0.0)
        assert features[idx["refill_count"]] == pytest.approx(1.0)
        assert features[idx["price_crossed"]] == pytest.approx(0.0)
        assert features[idx["modification_rate"]] == pytest.approx(5.0 / 30.0)

        # Book imbalance: bid_sum=398, ask_sum=349, (398-349)/747
        bid_sum = sum([100, 80, 60, 50, 40, 30, 20, 10, 5, 3])
        ask_sum = sum([90, 70, 55, 45, 35, 25, 15, 8, 4, 2])
        expected_imbalance = (bid_sum - ask_sum) / (bid_sum + ask_sum)
        assert features[idx["book_imbalance"]] == pytest.approx(expected_imbalance, abs=1e-6)

    def test_synthetic_ask_wall_pipeline(self):
        """Verify ask-side wall uses best_ask for BBO distance."""
        extractor = WallFeatureExtractor(tick_size=0.25, normalize=False)

        wall_data = {
            "time_in_book": 5.0,
            "modification_count": 0,
            "cancellation_count": 0,
            "original_size": 300,
            "max_size": 300,
            "current_size": 300,
            "refill_count": 0,
            "price_crossed": False,
            "side": 1,
            "wall_price": 21455.0,
        }
        market_context = {
            "mid_price": 21452.50,
            "best_bid": 21452.25,
            "best_ask": 21452.75,
            "spread": 0.50,
            "avg_wall_size": 100.0,
            "bid_volumes": [100] * 10,
            "ask_volumes": [100] * 10,
        }

        features = extractor.extract(wall_data, market_context)
        idx = {name: i for i, name in enumerate(FEATURE_NAMES)}

        # distance_from_bbo for ask side: |21455 - 21452.75| / 0.25 = 9.0
        assert features[idx["distance_from_bbo"]] == pytest.approx(9.0)
        assert features[idx["side"]] == pytest.approx(1.0)

    def test_batch_pipeline_consistency(self):
        """Batch extraction should match individual extractions."""
        extractor = WallFeatureExtractor(tick_size=0.25, normalize=False)

        walls = [
            {
                "time_in_book": float(i * 10 + 5),
                "modification_count": i,
                "cancellation_count": 0,
                "original_size": 100 + i * 50,
                "max_size": 100 + i * 50,
                "current_size": 100 + i * 50,
                "refill_count": 0,
                "price_crossed": False,
                "side": i % 2,
                "wall_price": 21450.0 + i * 0.25,
            }
            for i in range(5)
        ]
        market_context = {
            "mid_price": 21451.0,
            "best_bid": 21450.75,
            "best_ask": 21451.25,
            "spread": 0.50,
            "avg_wall_size": 100.0,
            "bid_volumes": [80] * 10,
            "ask_volumes": [80] * 10,
        }

        batch = extractor.extract_batch(walls, market_context)
        assert batch.shape == (5, NUM_FEATURES)

        # Each row individually
        for i, wall in enumerate(walls):
            single_extractor = WallFeatureExtractor(tick_size=0.25, normalize=False)
            single = single_extractor.extract(wall, market_context)
            np.testing.assert_array_almost_equal(batch[i], single, decimal=10)


class TestClassifierFormat:
    """Test 2: Verify classify() returns (label, confidence) with correct types."""

    def test_classify_return_types_with_lightgbm(self):
        lgb = pytest.importorskip("lightgbm")

        rng = np.random.default_rng(42)
        X = rng.standard_normal((100, NUM_FEATURES))
        y = (rng.random(100) > 0.5).astype(np.int8)

        train_set = lgb.Dataset(X, label=y)
        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "num_leaves": 4,
            "verbose": -1,
        }
        booster = lgb.train(params, train_set, num_boost_round=5)

        clf = WallClassifier()
        clf.model = booster

        features = rng.standard_normal(NUM_FEATURES)
        result = clf.classify(features)

        assert isinstance(result, tuple)
        assert len(result) == 2
        label, confidence = result
        assert isinstance(label, str)
        assert isinstance(confidence, float)
        assert label in ("NOT_SPOOF", "SPOOF")
        assert 0.0 <= confidence <= 1.0

    def test_classify_batch_return_types_with_lightgbm(self):
        lgb = pytest.importorskip("lightgbm")

        rng = np.random.default_rng(42)
        X = rng.standard_normal((100, NUM_FEATURES))
        y = (rng.random(100) > 0.5).astype(np.int8)

        train_set = lgb.Dataset(X, label=y)
        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "num_leaves": 4,
            "verbose": -1,
        }
        booster = lgb.train(params, train_set, num_boost_round=5)

        clf = WallClassifier()
        clf.model = booster

        batch_features = rng.standard_normal((5, NUM_FEATURES))
        results = clf.classify_batch(batch_features)

        assert isinstance(results, list)
        assert len(results) == 5
        for label, confidence in results:
            assert isinstance(label, str)
            assert isinstance(confidence, float)
            assert label in ("NOT_SPOOF", "SPOOF")

    def test_classify_without_model_raises_runtime_error(self):
        clf = WallClassifier()
        features = np.random.randn(NUM_FEATURES)
        with pytest.raises(RuntimeError):
            clf.classify(features)


class TestV1Integrity:
    """Test 3: Verify v1 DEEP6DepthRadar.cs has not been modified."""

    def test_v1_file_unmodified(self):
        """git diff HEAD should show no changes to v1 indicator."""
        result = subprocess.run(
            ["git", "diff", "HEAD", "--", "ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs"],
            capture_output=True,
            text=True,
            cwd=r"C:\Users\Tea\DEEP6",
        )
        assert result.returncode == 0, f"git diff failed: {result.stderr}"
        assert result.stdout.strip() == "", (
            "v1 DEEP6DepthRadar.cs has been modified! "
            "Phase B must not touch v1 files.\n"
            f"Diff output:\n{result.stdout[:500]}"
        )
