from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from deep6v2.types.dom import DOMLevel, DOMSnapshot
from deep6v2.types.dom_intelligence import DetectorTier, ReplaySafety
from deep6v2.types.signal import Direction, SignalId


_MODULE_PATH = Path(__file__).resolve().parents[2] / "deep6v2" / "signals" / "dom" / "detectors" / "imbalance.py"
_SPEC = spec_from_file_location("deep6v2.signals.dom.detectors.imbalance", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

LiquidityThinnessDetector = _MODULE.LiquidityThinnessDetector
OrderBookImbalanceDetector = _MODULE.OrderBookImbalanceDetector


def _snapshot(*, bids: list[int], asks: list[int], base_price: float = 20000.0) -> DOMSnapshot:
    return DOMSnapshot(
        timestamp=datetime(2026, 5, 27, 14, 30, tzinfo=UTC),
        bids=[DOMLevel(price=base_price - (idx * 0.25), volume=volume) for idx, volume in enumerate(bids)],
        asks=[DOMLevel(price=base_price + 0.25 + (idx * 0.25), volume=volume) for idx, volume in enumerate(asks)],
    )


def test_order_book_imbalance_fires_long_on_bid_dominance() -> None:
    detector = OrderBookImbalanceDetector()
    snapshot = _snapshot(bids=[60, 60, 60, 60, 60], asks=[20, 20, 20, 20, 20])

    events = detector.on_depth(snapshot)

    assert len(events) == 1
    event = events[0]
    assert event.signal_id is SignalId.IMB_01
    assert event.detector_id == "dom.imbalance.v1"
    assert event.direction is Direction.BULLISH
    assert event.tier is DetectorTier.MECHANICAL
    assert event.replay_safety is ReplaySafety.REPLAY_SAFE
    assert event.metadata["bid_volume"] == 300
    assert event.metadata["ask_volume"] == 100
    assert event.metadata["imbalance_ratio"] == 3.0


def test_order_book_imbalance_stays_silent_on_balanced_book() -> None:
    detector = OrderBookImbalanceDetector()
    snapshot = _snapshot(bids=[40, 40, 40, 40, 40], asks=[38, 38, 38, 38, 38])

    assert detector.on_depth(snapshot) == []


def test_order_book_imbalance_fires_short_on_ask_dominance() -> None:
    detector = OrderBookImbalanceDetector()
    snapshot = _snapshot(bids=[20, 20, 20, 20, 20], asks=[60, 60, 60, 60, 60])

    events = detector.on_depth(snapshot)

    assert len(events) == 1
    assert events[0].direction is Direction.BEARISH
    assert events[0].price == 20000.25


def test_liquidity_thinness_fires_on_globally_thin_book() -> None:
    detector = LiquidityThinnessDetector()
    snapshot = _snapshot(bids=[10, 10, 10, 10, 10], asks=[8, 8, 8, 8, 8])

    events = detector.on_depth(snapshot)

    assert len(events) == 1
    event = events[0]
    assert event.signal_id is SignalId.IMB_02
    assert event.detector_id == "dom.thinness.v1"
    assert event.metadata["total_volume"] == 90
    assert event.metadata["condition"] == "global_thinness"


def test_liquidity_thinness_stays_silent_on_normal_depth() -> None:
    detector = LiquidityThinnessDetector()
    snapshot = _snapshot(bids=[60, 70, 80, 90, 100], asks=[65, 75, 85, 95, 105])

    assert detector.on_depth(snapshot) == []


def test_liquidity_thinness_detects_asymmetric_bid_thinness_as_bearish() -> None:
    detector = LiquidityThinnessDetector()
    snapshot = _snapshot(bids=[4, 4, 4, 4, 4], asks=[30, 30, 30, 30, 30])

    events = detector.on_depth(snapshot)

    assert len(events) == 1
    event = events[0]
    assert event.direction is Direction.BEARISH
    assert event.metadata["bid_volume"] == 20
    assert event.metadata["ask_volume"] == 150
    assert event.metadata["condition"] == "asymmetric_thinness"


def test_liquidity_thinness_detects_asymmetric_ask_thinness_as_bullish() -> None:
    detector = LiquidityThinnessDetector()
    snapshot = _snapshot(bids=[30, 30, 30, 30, 30], asks=[4, 4, 4, 4, 4])

    events = detector.on_depth(snapshot)

    assert len(events) == 1
    assert events[0].direction is Direction.BULLISH
