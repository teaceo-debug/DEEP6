from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
import sys

from deep6v2.types.dom import DOMLevel, DOMSnapshot
from deep6v2.types.dom_intelligence import DetectorTier, ReplaySafety
from deep6v2.types.signal import SignalId


def _load_detector_class() -> type:
    module_path = Path(__file__).resolve().parents[2] / "deep6v2" / "signals" / "dom" / "detectors" / "pull_replace.py"
    spec = importlib.util.spec_from_file_location("test_pull_replace_detector", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.PullReplaceTrapDetector


PullReplaceTrapDetector = _load_detector_class()

BASE_TIME = datetime(2026, 5, 27, 14, 30, tzinfo=UTC)


def _snapshot(step: int, *, bid_levels: list[tuple[float, int]], ask_levels: list[tuple[float, int]] | None = None) -> DOMSnapshot:
    asks = ask_levels or [(20000.75, 120), (20001.0, 110)]
    return DOMSnapshot(
        timestamp=BASE_TIME + timedelta(milliseconds=step),
        bids=[DOMLevel(price=price, volume=volume) for price, volume in bid_levels],
        asks=[DOMLevel(price=price, volume=volume) for price, volume in asks],
    )


def test_repeated_pull_replace_emits_heuristic_event_on_second_confirmation() -> None:
    detector = PullReplaceTrapDetector(cancel_threshold=50, price_range=0.5, look_ahead=2, confirmation_threshold=2)

    assert detector.on_depth(_snapshot(0, bid_levels=[(20000.25, 10), (20000.0, 300), (19999.75, 80)])) == []
    assert detector.on_depth(_snapshot(1, bid_levels=[(20000.25, 280), (20000.0, 10), (19999.75, 80)])) == []
    assert detector.on_depth(_snapshot(2, bid_levels=[(20000.25, 20), (20000.0, 320), (19999.75, 80)])) == []

    events = detector.on_depth(_snapshot(3, bid_levels=[(20000.25, 290), (20000.0, 20), (19999.75, 80)]))

    assert len(events) == 1
    event = events[0]
    assert event.signal_id is SignalId.REGIME_CHANGE
    assert event.tier is DetectorTier.HEURISTIC
    assert event.replay_safety is ReplaySafety.REPLAY_DEGRADED
    assert event.price == 20000.25
    assert event.metadata["repeat_count"] == 2
    assert event.metadata["pull_price"] == 20000.0
    assert event.metadata["replacement_price"] == 20000.25


def test_pull_without_nearby_replacement_stays_silent() -> None:
    detector = PullReplaceTrapDetector(cancel_threshold=50, price_range=0.5, look_ahead=2, confirmation_threshold=2)

    detector.on_depth(_snapshot(0, bid_levels=[(20000.25, 10), (20000.0, 300), (19999.75, 80)]))
    events = detector.on_depth(_snapshot(1, bid_levels=[(20000.25, 30), (20000.0, 10), (19999.75, 80)]))

    assert events == []


def test_single_pull_replace_without_repetition_stays_silent() -> None:
    detector = PullReplaceTrapDetector(cancel_threshold=50, price_range=0.5, look_ahead=2, confirmation_threshold=2)

    detector.on_depth(_snapshot(0, bid_levels=[(20000.25, 10), (20000.0, 300), (19999.75, 80)]))
    events = detector.on_depth(_snapshot(1, bid_levels=[(20000.25, 280), (20000.0, 10), (19999.75, 80)]))

    assert events == []


def test_event_metadata_includes_pull_ratio_and_replacement_speed() -> None:
    detector = PullReplaceTrapDetector(cancel_threshold=50, price_range=0.5, look_ahead=2, confirmation_threshold=2)

    detector.on_depth(_snapshot(0, bid_levels=[(20000.25, 10), (20000.0, 300), (19999.75, 80)]))
    detector.on_depth(_snapshot(1, bid_levels=[(20000.25, 280), (20000.0, 10), (19999.75, 80)]))
    detector.on_depth(_snapshot(2, bid_levels=[(20000.25, 20), (20000.0, 320), (19999.75, 80)]))
    events = detector.on_depth(_snapshot(3, bid_levels=[(20000.25, 290), (20000.0, 20), (19999.75, 80)]))

    metadata = events[0].metadata
    assert metadata["pull_ratio"] == 270 / 300
    assert metadata["replacement_speed"] == 1
