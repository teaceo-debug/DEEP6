from __future__ import annotations

from pathlib import Path

from deep6.backtest.wall_detector import WallDetector


MODEL_PATH = "deep6/models/depth_radar_classifier_4class.joblib"


class LowConfidenceClassifier:
    def __init__(self, model_path: str | None = None) -> None:
        self.model_path = model_path

    def classify_batch_with_probs(self, features):
        return [("GENUINE", 0.2, {"GENUINE": 0.2, "SPOOF": 0.2, "ICEBERG": 0.3, "STALE": 0.3}) for _ in range(features.shape[0])]


def _build_detector(monkeypatch) -> WallDetector:
    monkeypatch.setattr("deep6.backtest.wall_detector.WallClassifier", LowConfidenceClassifier)
    return WallDetector(model_path=MODEL_PATH)


def test_wall_creation(monkeypatch):
    detector = _build_detector(monkeypatch)

    detector.process_event(price=20000.0, size=80, side="B", action="A", order_id="o1", ts_ns=1_000_000_000)
    walls = detector.get_active_walls()

    assert len(walls) == 1
    wall = walls[0]
    assert wall.price == 20000.0
    assert wall.size == 80
    assert wall.side == "bid"
    assert wall.classification == "GENUINE"
    assert wall.confidence == 0.9
    assert len(wall.features) == 15


def test_refill_detection(monkeypatch):
    detector = _build_detector(monkeypatch)
    base_ts = 1_000_000_000

    detector.process_event(price=20000.0, size=100, side="B", action="A", order_id="o1", ts_ns=base_ts)
    detector.process_event(price=20000.0, size=20, side="B", action="M", order_id="o1", ts_ns=base_ts + 1_000_000_000)
    detector.process_event(price=20000.0, size=90, side="B", action="M", order_id="o1", ts_ns=base_ts + 2_000_000_000)

    state = detector._walls[("bid", 20000.0)]
    assert state.refill_count == 1
    assert state.current_size == 90


def test_cancellation_tracking(monkeypatch):
    detector = _build_detector(monkeypatch)
    base_ts = 1_000_000_000

    detector.process_event(price=20000.0, size=75, side="A", action="A", order_id="o2", ts_ns=base_ts)
    detector.process_event(price=20000.0, size=75, side="A", action="C", order_id="o2", ts_ns=base_ts + 1_000_000_000)

    state = detector._walls[("ask", 20000.0)]
    assert state.cancellation_count == 1
    assert state.current_size == 0


def test_model_loads_correctly():
    detector = WallDetector(model_path=MODEL_PATH)

    assert detector.classifier is not None
    assert detector.classifier.mode == "multiclass"
    assert detector.classifier.class_names == ["GENUINE", "SPOOF", "ICEBERG", "STALE"]
    assert Path(MODEL_PATH).exists()


def test_rule_fallback_when_model_confidence_is_low(monkeypatch):
    detector = _build_detector(monkeypatch)
    base_ts = 1_000_000_000

    detector.process_event(price=20000.0, size=100, side="B", action="A", order_id="o1", ts_ns=base_ts)
    detector.process_event(price=20000.0, size=20, side="B", action="M", order_id="o1", ts_ns=base_ts + 1_000_000_000)
    detector.process_event(price=20000.0, size=90, side="B", action="M", order_id="o1", ts_ns=base_ts + 2_000_000_000)
    detector.process_event(price=20000.0, size=20, side="B", action="M", order_id="o1", ts_ns=base_ts + 3_000_000_000)
    detector.process_event(price=20000.0, size=90, side="B", action="M", order_id="o1", ts_ns=base_ts + 4_000_000_000)

    walls = detector.get_active_walls()
    assert len(walls) == 1
    assert walls[0].classification == "ICEBERG"
    assert walls[0].confidence == 0.8
    assert walls[0].refill_count == 2


def test_stale_wall_pruning(monkeypatch):
    detector = _build_detector(monkeypatch)
    base_ts = 1_000_000_000

    detector.process_event(price=20000.0, size=60, side="B", action="A", order_id="o1", ts_ns=base_ts)
    walls = detector.get_walls_at_bar_close(base_ts + 91_000_000_000)

    assert walls == []
    assert detector._walls == {}
