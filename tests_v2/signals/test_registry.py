from __future__ import annotations

from collections import deque
from datetime import UTC, datetime

from deep6v2.signals.registry import DetectorRegistry
from deep6v2.types.bar import FootprintBar, SessionType
from deep6v2.types.dom import DOMSnapshot
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult
from tests_v2.fixtures.loader import load_signal_fixture


class BrokenDetector:
    def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]:
        raise RuntimeError("boom")


class WorkingDetector:
    def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]:
        return [
            SignalResult(
                signal_id=SignalId.ENG_02,
                direction=Direction.BULLISH,
                strength=0.9,
                detail="ok",
                price=bar.close,
                flag_bit=SignalFlagBits.ENG_02,
            )
        ]


def _bar(name: str) -> FootprintBar:
    return FootprintBar.model_validate(load_signal_fixture(name)["bar"])


def _ctx(name: str, bar: FootprintBar) -> SessionContext:
    data = load_signal_fixture(name)["context"]
    return SessionContext(
        atr=data["atr"],
        cvd=data["cvd"],
        vah=data["vah"],
        val=data["val"],
        poc=data["poc"],
        session_type=SessionType(data["session_type"]),
        session_open_bar_index=data["session_open_bar_index"],
        current_bar=bar,
        vol_history=deque([900, 1000, 1100], maxlen=50),
    )


def _snapshot(name: str) -> DOMSnapshot:
    data = load_signal_fixture(name)["context"]["dom_snapshot"]
    return DOMSnapshot.model_validate({"timestamp": timestamp().isoformat(), **data})


def test_evaluate_bar_runs_all_detectors_and_collects_results():
    registry = DetectorRegistry.create_default()
    bar = _bar("eng_04").model_copy(update={"close": 21508.0})
    ctx = _ctx("eng_04", bar)
    ctx.poc = 21508.0
    snapshot = DOMSnapshot.model_validate(
        {
            "timestamp": timestamp().isoformat(),
            "bids": [
                {"price": 21500.0, "volume": 50},
                {"price": 21499.75, "volume": 400},
                {"price": 21499.50, "volume": 350},
                {"price": 21499.25, "volume": 300},
                {"price": 21499.0, "volume": 250},
            ],
            "asks": [
                {"price": 21500.25, "volume": 20},
                {"price": 21500.50, "volume": 20},
                {"price": 21500.75, "volume": 20},
                {"price": 21501.0, "volume": 20},
                {"price": 21501.25, "volume": 20},
            ],
        }
    )

    registry.on_depth(snapshot)
    results = registry.evaluate_bar(bar, ctx)

    signal_ids = {result.signal_id for result in results}
    assert SignalId.ENG_02 in signal_ids
    assert SignalId.ENG_04 in signal_ids
    assert SignalId.ENG_06 in signal_ids
    assert SignalId.ENG_05 in signal_ids


def test_exception_isolation_keeps_other_detectors_running():
    bar = _bar("eng_02")
    ctx = _ctx("eng_02", bar)
    registry = DetectorRegistry(detectors=[BrokenDetector(), WorkingDetector()])

    results = registry.evaluate_bar(bar, ctx)

    assert len(results) == 1
    assert results[0].signal_id is SignalId.ENG_02


def test_cross_detector_wiring_absorption_to_iceberg_notification():
    registry = DetectorRegistry.create_default()
    bar = FootprintBar(
        open=21502.0,
        high=21508.0,
        low=21500.0,
        close=21506.0,
        delta=-100,
        total_volume=2000,
        bid_volumes={21500.0: 800, 21500.25: 150, 21501.0: 100},
        ask_volumes={21504.0: 200, 21505.0: 250, 21506.0: 150},
        poc_price=21500.0,
        poc_volume=900,
        vah=21506.0,
        val=21500.5,
        cvd=50.0,
        bar_index=10,
        timestamp=timestamp(),
        session_type=SessionType.RTH,
    )
    ctx = SessionContext(
        atr=10.0,
        cvd=50.0,
        vah=21506.0,
        val=21500.5,
        poc=21503.0,
        session_type=SessionType.RTH,
        session_open_bar_index=0,
        current_bar=bar,
        vol_history=deque([1000, 1100, 1200], maxlen=50),
    )
    snapshot = DOMSnapshot.model_validate(
        {
            "timestamp": timestamp().isoformat(),
            "bids": [
                {"price": 21500.0, "volume": 50},
                {"price": 21499.75, "volume": 100},
                {"price": 21499.5, "volume": 90},
                {"price": 21499.25, "volume": 80},
                {"price": 21499.0, "volume": 70},
            ],
            "asks": [
                {"price": 21500.25, "volume": 40},
                {"price": 21500.5, "volume": 35},
                {"price": 21500.75, "volume": 30},
                {"price": 21501.0, "volume": 25},
                {"price": 21501.25, "volume": 20},
            ],
        }
    )

    registry.on_depth(snapshot)
    results = registry.evaluate_bar(bar, ctx)

    signal_ids = {result.signal_id for result in results}
    assert SignalId.ABS_01 in signal_ids
    assert SignalId.ENG_04 in signal_ids
    iceberg = next(result for result in results if result.signal_id is SignalId.ENG_04)
    assert iceberg.direction is Direction.BULLISH


def test_empty_bar_returns_empty_results():
    bar = FootprintBar(
        open=21490.0,
        high=21490.0,
        low=21490.0,
        close=21490.0,
        delta=0,
        total_volume=0,
        bid_volumes={},
        ask_volumes={},
        poc_price=21490.0,
        poc_volume=0,
        vah=21490.0,
        val=21490.0,
        cvd=0.0,
        bar_index=0,
        timestamp=timestamp(),
        session_type=SessionType.RTH,
    )
    ctx = SessionContext(
        atr=10.0,
        cvd=0.0,
        vah=21510.0,
        val=21470.0,
        poc=21520.0,
        session_type=SessionType.RTH,
        session_open_bar_index=0,
        current_bar=bar,
    )
    registry = DetectorRegistry.create_default()

    assert registry.evaluate_bar(bar, ctx) == []


def timestamp() -> datetime:
    return datetime(2026, 5, 14, 14, 0, tzinfo=UTC)
