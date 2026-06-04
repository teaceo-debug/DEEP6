from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
import sys

from deep6v2.types.dom import DOMLevel, DOMSnapshot
from deep6v2.types.signal import Direction, SignalId


def _load_detector_class() -> type:
    module_path = Path(__file__).resolve().parents[2] / "deep6v2" / "signals" / "dom" / "detectors" / "sweep_reload.py"
    spec = importlib.util.spec_from_file_location("test_sweep_reload_detector", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.SweepReloadDetector


SweepReloadDetector = _load_detector_class()


def _snapshot(
    step: int,
    *,
    bid_volume: int,
    ask_volume: int,
    extra_bids: list[DOMLevel] | None = None,
    extra_asks: list[DOMLevel] | None = None,
) -> DOMSnapshot:
    base_time = datetime(2026, 5, 27, 14, 30, tzinfo=UTC)
    return DOMSnapshot(
        timestamp=base_time + timedelta(milliseconds=step),
        bids=[DOMLevel(price=21000.0, volume=bid_volume), *(extra_bids or [])],
        asks=[DOMLevel(price=21000.25, volume=ask_volume), *(extra_asks or [])],
    )


def test_positive_sweep_then_reload_emits_abs02_only_on_reload() -> None:
    detector = SweepReloadDetector()

    assert detector.on_depth(_snapshot(0, bid_volume=300, ask_volume=220)) == []
    assert detector.on_depth(_snapshot(1, bid_volume=15, ask_volume=220)) == []

    events = detector.on_depth(_snapshot(2, bid_volume=200, ask_volume=220))

    assert len(events) == 1
    event = events[0]
    assert event.signal_id is SignalId.ABS_02
    assert event.direction is Direction.BULLISH
    assert event.price == 21000.0
    assert event.metadata["state_path"] == ["NORMAL", "SWEPT", "RELOADED"]
    assert event.metadata["swept_volume"] == 15
    assert event.metadata["reloaded_volume"] == 200


def test_sweep_without_reload_stays_silent() -> None:
    detector = SweepReloadDetector()

    detector.on_depth(_snapshot(0, bid_volume=300, ask_volume=220))
    detector.on_depth(_snapshot(1, bid_volume=10, ask_volume=220))

    assert detector.on_depth(_snapshot(2, bid_volume=18, ask_volume=220)) == []
    assert detector.on_depth(_snapshot(3, bid_volume=12, ask_volume=220)) == []


def test_reload_without_prior_sweep_does_not_emit() -> None:
    detector = SweepReloadDetector()

    assert detector.on_depth(_snapshot(0, bid_volume=120, ask_volume=120)) == []
    assert detector.on_depth(_snapshot(1, bid_volume=240, ask_volume=240)) == []


def test_swept_level_times_out_when_reload_window_is_missed() -> None:
    detector = SweepReloadDetector(max_reload_snapshots=3)

    detector.on_depth(_snapshot(0, bid_volume=300, ask_volume=220))
    detector.on_depth(_snapshot(1, bid_volume=15, ask_volume=220))
    detector.on_depth(_snapshot(2, bid_volume=12, ask_volume=220))
    detector.on_depth(_snapshot(3, bid_volume=10, ask_volume=220))
    detector.on_depth(_snapshot(4, bid_volume=14, ask_volume=220))

    assert detector.on_depth(_snapshot(5, bid_volume=250, ask_volume=220)) == []


def test_ask_sweep_reload_maps_to_short_direction() -> None:
    detector = SweepReloadDetector()

    detector.on_depth(_snapshot(0, bid_volume=220, ask_volume=300))
    detector.on_depth(_snapshot(1, bid_volume=220, ask_volume=15))

    events = detector.on_depth(_snapshot(2, bid_volume=220, ask_volume=200))

    assert len(events) == 1
    event = events[0]
    assert event.signal_id is SignalId.ABS_02
    assert event.direction is Direction.BEARISH
    assert event.price == 21000.25
    assert event.metadata["side"] == "ask"


def test_bid_and_ask_levels_can_emit_separate_events_in_same_snapshot() -> None:
    detector = SweepReloadDetector()

    detector.on_depth(_snapshot(0, bid_volume=300, ask_volume=300))
    detector.on_depth(_snapshot(1, bid_volume=15, ask_volume=10))

    events = detector.on_depth(_snapshot(2, bid_volume=220, ask_volume=210))

    assert len(events) == 2
    by_side = {event.metadata["side"]: event for event in events}
    assert set(by_side) == {"bid", "ask"}
    assert by_side["bid"].direction is Direction.BULLISH
    assert by_side["ask"].direction is Direction.BEARISH
