from __future__ import annotations

from deep6v2.signals.dom.detectors.cvd import CVDDetector
from deep6v2.types.signal import Direction, SignalId


def test_cvd_accumulates_buys_into_running_sum() -> None:
    detector = CVDDetector()

    for _ in range(10):
        assert detector.update_trade(volume=20, is_aggressive_buy=True) == []

    assert detector.current_cvd == 200.0
    assert detector.cvd_history == (20.0, 40.0, 60.0, 80.0, 100.0, 120.0, 140.0, 160.0, 180.0, 200.0)


def test_zero_cross_bullish_emits_delta_signal() -> None:
    detector = CVDDetector()
    detector._cvd = -150.0

    events = detector.update_trade(volume=200, is_aggressive_buy=True)

    assert events
    assert events[0].signal_id is SignalId.DELT_01
    assert events[0].direction is Direction.BULLISH
    assert events[0].metadata["event_type"] == "zero_cross_bullish"
    assert detector.current_cvd == 50.0


def test_zero_cross_bearish_emits_delta_signal() -> None:
    detector = CVDDetector()
    detector._cvd = 150.0

    events = detector.update_trade(volume=200, is_aggressive_buy=False)

    assert events
    assert events[0].signal_id is SignalId.DELT_01
    assert events[0].direction is Direction.BEARISH
    assert events[0].metadata["event_type"] == "zero_cross_bearish"
    assert detector.current_cvd == -50.0


def test_small_fluctuations_around_zero_do_not_emit_events() -> None:
    detector = CVDDetector()

    assert detector.update_trade(volume=20, is_aggressive_buy=True) == []
    assert detector.update_trade(volume=15, is_aggressive_buy=False) == []
    assert detector.update_trade(volume=10, is_aggressive_buy=True) == []
    assert detector.update_trade(volume=18, is_aggressive_buy=False) == []

    assert detector.current_cvd == -3.0


def test_reset_clears_cvd_without_emitting_event() -> None:
    detector = CVDDetector()
    detector.update_trade(volume=40, is_aggressive_buy=True)
    detector.reset()

    assert detector.current_cvd == 0.0
    assert detector.cvd_history == ()
    assert detector.update_trade(volume=10, is_aggressive_buy=False) == []
    assert detector.current_cvd == -10.0


def test_acceleration_emits_delta_signal_on_rapid_same_direction_flow() -> None:
    detector = CVDDetector(acceleration_threshold=50.0)

    assert detector.update_trade(volume=10, is_aggressive_buy=True) == []
    assert detector.update_trade(volume=20, is_aggressive_buy=True) == []

    events = detector.update_trade(volume=30, is_aggressive_buy=True)

    assert events
    assert events[0].signal_id is SignalId.DELT_01
    assert events[0].direction is Direction.BULLISH
    assert events[0].metadata["event_type"] == "acceleration_bullish"
    assert detector.current_cvd == 60.0
