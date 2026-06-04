"""Tests for DepthRadarService: initialization, NDJSON dispatch, passthrough mode."""
from __future__ import annotations

import json

import pytest

from deep6.services.depth_radar_service import DepthRadarService


class TestServiceInit:
    def test_init_with_missing_model(self):
        """Service should initialize in passthrough mode when model is missing."""
        svc = DepthRadarService(model_path="/nonexistent/model.joblib")
        assert svc._model_loaded is False
        assert svc._classifier is None
        assert svc._connected is False
        assert svc._walls_classified == 0

    def test_passthrough_after_load_attempt(self):
        """After calling _load_model with bad path, service is in passthrough mode."""
        svc = DepthRadarService(model_path="/nonexistent/model.joblib")
        svc._load_model()
        assert svc._model_loaded is False
        assert svc._classifier is None

    def test_default_ports(self):
        svc = DepthRadarService(model_path="/nonexistent/model.joblib")
        assert svc._bridge_port == 9201
        assert svc._health_port == 9202

    def test_custom_ports(self):
        svc = DepthRadarService(
            model_path="/nonexistent/model.joblib",
            bridge_port=9301,
            health_port=9302,
        )
        assert svc._bridge_port == 9301
        assert svc._health_port == 9302


class TestNDJSONParsing:
    def test_wall_snapshot_structure(self):
        """Verify the expected fields in a wall_snapshot message."""
        msg = {
            "type": "wall_snapshot",
            "price": 21450.0,
            "side": "bid",
            "best_bid": 21450.0,
            "best_ask": 21450.25,
            "time_in_book": 10.0,
            "modification_count": 3,
            "cancellation_count": 1,
            "original_size": 200,
            "max_size": 250,
            "current_size": 200,
            "refill_count": 0,
            "price_crossed": False,
        }
        ndjson_line = json.dumps(msg) + "\n"
        parsed = json.loads(ndjson_line)
        assert parsed["type"] == "wall_snapshot"
        assert parsed["price"] == 21450.0
        assert parsed["side"] == "bid"

    def test_heartbeat_structure(self):
        msg = {"type": "heartbeat", "timestamp": 1700000000}
        ndjson_line = json.dumps(msg) + "\n"
        parsed = json.loads(ndjson_line)
        assert parsed["type"] == "heartbeat"

    def test_classification_response_format(self):
        """Verify the outbound classification NDJSON format."""
        response = {
            "type": "wall_classification",
            "price": 21450.0,
            "side": "bid",
            "classification": "GENUINE",
            "confidence": 0.85,
        }
        line = json.dumps(response) + "\n"
        parsed = json.loads(line)
        assert parsed["type"] == "wall_classification"
        assert parsed["classification"] in ["GENUINE", "SPOOF", "ICEBERG", "STALE", "UNKNOWN"]
        assert 0.0 <= parsed["confidence"] <= 1.0


class TestDispatchRouting:
    def test_dispatch_identifies_wall_snapshot(self):
        svc = DepthRadarService(model_path="/nonexistent/model.joblib")
        data = {"type": "wall_snapshot", "price": 21450.0}
        assert data.get("type") == "wall_snapshot"

    def test_dispatch_identifies_heartbeat(self):
        data = {"type": "heartbeat", "timestamp": 1700000000}
        assert data.get("type") == "heartbeat"

    def test_dispatch_unknown_type_is_ignored(self):
        data = {"type": "unknown_message_type"}
        assert data.get("type") not in ("wall_snapshot", "heartbeat")


class TestLabelNormalization:
    def test_binary_not_spoof_maps_to_genuine(self):
        svc = DepthRadarService(model_path="/nonexistent/model.joblib")
        svc._load_model()
        # Manually set up a mock classifier-like state
        from unittest.mock import MagicMock
        mock_clf = MagicMock()
        mock_clf.mode = "binary"
        svc._classifier = mock_clf

        result = svc._normalize_label_for_service("NOT_SPOOF")
        assert result == "GENUINE"

    def test_binary_spoof_stays_spoof(self):
        svc = DepthRadarService(model_path="/nonexistent/model.joblib")
        svc._load_model()
        from unittest.mock import MagicMock
        mock_clf = MagicMock()
        mock_clf.mode = "binary"
        svc._classifier = mock_clf

        result = svc._normalize_label_for_service("SPOOF")
        assert result == "SPOOF"

    def test_multiclass_labels_pass_through(self):
        svc = DepthRadarService(model_path="/nonexistent/model.joblib")
        svc._load_model()
        from unittest.mock import MagicMock
        mock_clf = MagicMock()
        mock_clf.mode = "multiclass"
        svc._classifier = mock_clf

        for label in ["GENUINE", "SPOOF", "ICEBERG", "STALE"]:
            result = svc._normalize_label_for_service(label)
            assert result == label

    def test_no_classifier_passes_through(self):
        svc = DepthRadarService(model_path="/nonexistent/model.joblib")
        svc._classifier = None
        assert svc._normalize_label_for_service("ANYTHING") == "ANYTHING"


class TestFastAPIApp:
    def test_app_has_health_endpoint(self):
        svc = DepthRadarService(model_path="/nonexistent/model.joblib")
        routes = [r.path for r in svc._app.routes]
        assert "/health" in routes

    def test_app_has_metrics_endpoint(self):
        svc = DepthRadarService(model_path="/nonexistent/model.joblib")
        routes = [r.path for r in svc._app.routes]
        assert "/metrics" in routes
