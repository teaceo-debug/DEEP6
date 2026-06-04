"""Tests for WallClassifier: initialization, classify, save/load, label mapping."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from deep6.ml.depth_radar.wall_features import NUM_FEATURES

# Import classifier module -- lightgbm may or may not be available
from deep6.ml.depth_radar.classifier import (
    WallClassifier,
    _BINARY_CLASS_NAMES,
    _MULTICLASS_CLASS_NAMES,
)


class TestInit:
    def test_init_without_model(self):
        clf = WallClassifier()
        assert clf.model is None
        assert clf.mode == "binary"
        assert len(clf.feature_names) == NUM_FEATURES
        assert clf.threshold == 0.5

    def test_init_with_nonexistent_model_raises(self):
        with pytest.raises((FileNotFoundError, RuntimeError)):
            WallClassifier(model_path="/nonexistent/model.joblib")

    def test_class_names_default_binary(self):
        clf = WallClassifier()
        assert clf.class_names == list(_BINARY_CLASS_NAMES)

    def test_training_metrics_empty(self):
        clf = WallClassifier()
        assert clf.training_metrics == {}


class TestClassifyWithoutModel:
    def test_classify_no_model_raises(self):
        clf = WallClassifier()
        features = np.random.randn(NUM_FEATURES)
        with pytest.raises(RuntimeError, match="(No classifier model|lightgbm is not installed)"):
            clf.classify(features)

    def test_classify_batch_no_model_raises(self):
        clf = WallClassifier()
        features = np.random.randn(3, NUM_FEATURES)
        with pytest.raises(RuntimeError, match="(No classifier model|lightgbm is not installed)"):
            clf.classify_batch(features)


class TestFeatureValidation:
    def test_wrong_feature_count_raises(self):
        clf = WallClassifier()
        with pytest.raises(ValueError, match="Expected 15 features"):
            clf._coerce_feature_matrix(np.zeros(10))

    def test_correct_feature_count_reshapes(self):
        clf = WallClassifier()
        result = clf._coerce_feature_matrix(np.zeros(NUM_FEATURES))
        assert result.shape == (1, NUM_FEATURES)

    def test_2d_input_passes(self):
        clf = WallClassifier()
        result = clf._coerce_feature_matrix(np.zeros((5, NUM_FEATURES)))
        assert result.shape == (5, NUM_FEATURES)

    def test_2d_wrong_width_raises(self):
        clf = WallClassifier()
        with pytest.raises(ValueError, match="Expected feature matrix"):
            clf._coerce_feature_matrix(np.zeros((5, 10)))


class TestBinaryLabelMapping:
    def test_binary_class_names(self):
        assert _BINARY_CLASS_NAMES == ["NOT_SPOOF", "SPOOF"]

    def test_binary_label_ids(self):
        # In binary mode: 0 = NOT_SPOOF, 1 = SPOOF
        assert _BINARY_CLASS_NAMES[0] == "NOT_SPOOF"
        assert _BINARY_CLASS_NAMES[1] == "SPOOF"


class TestMulticlassLabelMapping:
    def test_multiclass_class_names(self):
        assert _MULTICLASS_CLASS_NAMES == ["GENUINE", "SPOOF", "ICEBERG", "STALE"]

    def test_multiclass_label_count(self):
        assert len(_MULTICLASS_CLASS_NAMES) == 4

    def test_multiclass_ids_are_sequential(self):
        from deep6.ml.depth_radar.classifier import _MULTICLASS_LABEL_TO_ID
        for idx, name in enumerate(_MULTICLASS_CLASS_NAMES):
            assert _MULTICLASS_LABEL_TO_ID[name] == idx


class TestSaveLoadRoundTrip:
    """Test model save/load when lightgbm is available."""

    def test_save_requires_model(self):
        clf = WallClassifier()
        with pytest.raises(RuntimeError, match="(No classifier model|lightgbm is not installed)"):
            clf.save("/tmp/test_model.joblib")

    def test_round_trip_with_mock_model(self):
        lgb = pytest.importorskip("lightgbm")

        # Create a minimal training dataset to get a real booster
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
        clf.mode = "binary"
        clf.training_metrics = {"f1": 0.85}

        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "model.joblib")
            clf.save(path)

            clf2 = WallClassifier()
            clf2.load(path)
            assert clf2.model is not None
            assert clf2.mode == "binary"
            assert clf2.training_metrics["f1"] == pytest.approx(0.85)

            # Verify classify works with loaded model
            features = rng.standard_normal(NUM_FEATURES)
            label, confidence = clf2.classify(features)
            assert label in ("NOT_SPOOF", "SPOOF")
            assert isinstance(confidence, float)


class TestHelperMethods:
    def test_encode_side_bid(self):
        assert WallClassifier._encode_side("bid") == 0
        assert WallClassifier._encode_side("Bid") == 0
        assert WallClassifier._encode_side(0) == 0

    def test_encode_side_ask(self):
        assert WallClassifier._encode_side("ask") == 1
        assert WallClassifier._encode_side("Ask") == 1
        assert WallClassifier._encode_side(1) == 1

    def test_encode_side_default(self):
        assert WallClassifier._encode_side(None) == 0
        assert WallClassifier._encode_side("invalid") == 0

    def test_as_bool_variations(self):
        assert WallClassifier._as_bool(True) is True
        assert WallClassifier._as_bool(False) is False
        assert WallClassifier._as_bool("true") is True
        assert WallClassifier._as_bool("1") is True
        assert WallClassifier._as_bool("yes") is True
        assert WallClassifier._as_bool("no") is False
        assert WallClassifier._as_bool("") is False

    def test_coerce_levels_list(self):
        assert WallClassifier._coerce_levels([1.0, 2.0, 3.0]) == [1.0, 2.0, 3.0]

    def test_coerce_levels_none(self):
        assert WallClassifier._coerce_levels(None) == []

    def test_coerce_levels_json_string(self):
        assert WallClassifier._coerce_levels("[1, 2, 3]") == [1.0, 2.0, 3.0]

    def test_coerce_levels_numpy(self):
        arr = np.array([10.0, 20.0])
        assert WallClassifier._coerce_levels(arr) == [10.0, 20.0]
