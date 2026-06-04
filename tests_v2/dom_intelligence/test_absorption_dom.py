from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deep6v2.signals.dom.detectors.absorption import AbsorptionDOMDetector
from deep6v2.types.dom import DOMLevel, DOMSnapshot
from deep6v2.types.dom_intelligence import DetectorTier, ReplaySafety
from deep6v2.types.signal import Direction, SignalId


BASE_TIME = datetime(2026, 5, 27, 14, 30, tzinfo=UTC)


def _snapshot(
    *,
    bid_wall: int,
    ask_wall: int = 120,
    best_bid: float = 21000.0,
    best_ask: float = 21000.25,
    offset_seconds: int,
) -> DOMSnapshot:
    bids = [DOMLevel(price=best_bid, volume=bid_wall)]
    asks = [DOMLevel(price=best_ask, volume=ask_wall)]
    return DOMSnapshot(
        timestamp=BASE_TIME + timedelta(seconds=offset_seconds),
        bids=bids,
        asks=asks,
    )


def test_single_snapshot_never_fires() -> None:
    detector = AbsorptionDOMDetector()

    events = detector.on_depth(_snapshot(bid_wall=320, offset_seconds=0))

    assert events == []


def test_fires_on_three_consecutive_bid_wall_absorptions() -> None:
    detector = AbsorptionDOMDetector(wall_threshold=200, aggression_threshold=50, absorption_count=3)

    detector.on_depth(_snapshot(bid_wall=380, offset_seconds=0))
    assert detector.on_depth(_snapshot(bid_wall=320, offset_seconds=1)) == []
    assert detector.on_depth(_snapshot(bid_wall=260, offset_seconds=2)) == []
    events = detector.on_depth(_snapshot(bid_wall=200, offset_seconds=3))

    assert len(events) == 1
    event = events[0]
    assert event.signal_id is SignalId.ABS_01
    assert event.direction is Direction.BULLISH
    assert event.tier is DetectorTier.MECHANICAL
    assert event.replay_safety is ReplaySafety.REPLAY_SAFE
    assert event.price == 21000.0
    assert event.confidence == 1.0
    assert event.detector_id == "dom.absorption.v1"
    assert event.metadata["hit_count"] == 3
    assert event.metadata["aggressive_flow"] == 60
    assert event.dom_state_snapshot is not None


def test_direction_maps_ask_wall_absorption_to_bearish() -> None:
    detector = AbsorptionDOMDetector(wall_threshold=200, aggression_threshold=50, absorption_count=3)

    detector.on_depth(_snapshot(bid_wall=120, ask_wall=380, best_bid=21000.0, best_ask=21000.25, offset_seconds=0))
    detector.on_depth(_snapshot(bid_wall=120, ask_wall=320, best_bid=21000.0, best_ask=21000.25, offset_seconds=1))
    detector.on_depth(_snapshot(bid_wall=120, ask_wall=260, best_bid=21000.0, best_ask=21000.25, offset_seconds=2))
    events = detector.on_depth(_snapshot(bid_wall=120, ask_wall=200, best_bid=21000.0, best_ask=21000.25, offset_seconds=3))

    assert len(events) == 1
    assert events[0].direction is Direction.BEARISH
    assert events[0].price == 21000.25


def test_silent_on_normal_displacement_when_wall_breaks() -> None:
    detector = AbsorptionDOMDetector(wall_threshold=200, aggression_threshold=50, absorption_count=3)

    detector.on_depth(_snapshot(bid_wall=340, offset_seconds=0))
    detector.on_depth(_snapshot(bid_wall=280, offset_seconds=1))
    events = detector.on_depth(_snapshot(bid_wall=150, best_bid=20999.75, offset_seconds=2))

    assert events == []


def test_silent_below_aggression_threshold() -> None:
    detector = AbsorptionDOMDetector(wall_threshold=200, aggression_threshold=50, absorption_count=3)

    detector.on_depth(_snapshot(bid_wall=350, offset_seconds=0))
    detector.on_depth(_snapshot(bid_wall=320, offset_seconds=1))
    detector.on_depth(_snapshot(bid_wall=300, offset_seconds=2))
    events = detector.on_depth(_snapshot(bid_wall=280, offset_seconds=3))

    assert events == []


def test_reset_clears_hit_count_carryover() -> None:
    detector = AbsorptionDOMDetector(wall_threshold=200, aggression_threshold=50, absorption_count=3)

    detector.on_depth(_snapshot(bid_wall=350, offset_seconds=0))
    detector.on_depth(_snapshot(bid_wall=290, offset_seconds=1))
    detector.on_depth(_snapshot(bid_wall=235, offset_seconds=2))
    detector.reset()

    assert detector.on_depth(_snapshot(bid_wall=350, offset_seconds=10)) == []
    assert detector.on_depth(_snapshot(bid_wall=290, offset_seconds=11)) == []
