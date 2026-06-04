from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta

import pytest

from deep6v2.config.signals import SignalConfig
from deep6v2.signals.delta import DeltaDetector
from deep6v2.types.bar import FootprintBar, SessionType
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId
from deep6v2.utils.math import least_squares_slope
from tests_v2.fixtures.loader import load_signal_fixture


def _bar_from_fixture(name: str) -> FootprintBar:
    data = load_signal_fixture(name)
    return FootprintBar.model_validate(data["bar"])


def _ctx(
    *,
    current_bar: FootprintBar | None = None,
    atr: float = 10.0,
    cvd: float = 0.0,
    vah: float = 21500.0,
    val: float = 21480.0,
    poc: float = 21490.0,
    bar_history: list[FootprintBar] | None = None,
    price_history: list[float] | None = None,
    cvd_history: list[float] | None = None,
    delta_history: list[int] | None = None,
) -> SessionContext:
    return SessionContext(
        atr=atr,
        cvd=cvd,
        vah=vah,
        val=val,
        poc=poc,
        session_type=SessionType.RTH,
        session_open_bar_index=0,
        current_bar=current_bar,
        bar_history=deque(bar_history or [], maxlen=50),
        price_history=deque(price_history or [], maxlen=50),
        cvd_history=deque(cvd_history or [], maxlen=50),
        delta_history=deque(delta_history or [], maxlen=50),
    )


def _prior_bar(current: FootprintBar, *, close: float, delta: int, cvd: float) -> FootprintBar:
    return FootprintBar(
        open=close,
        high=max(close, current.high),
        low=min(close, current.low),
        close=close,
        delta=delta,
        total_volume=max(current.total_volume - 200, 1),
        bid_volumes=current.bid_volumes,
        ask_volumes=current.ask_volumes,
        poc_price=current.poc_price,
        poc_volume=max(current.poc_volume - 50, 1),
        vah=current.vah,
        val=current.val,
        cvd=cvd,
        bar_index=current.bar_index - 1,
        timestamp=current.timestamp - timedelta(minutes=1),
        session_type=current.session_type,
    )


def _assert_signal(result, expected_signal: dict, expected_flag: int) -> None:
    assert result.signal_id is SignalId(expected_signal["signal_id"])
    assert result.direction is Direction[expected_signal["direction"]]
    assert expected_signal["strength_min"] <= result.strength <= expected_signal["strength_max"]
    assert result.flag_bit == expected_flag


def test_least_squares_slope_basic():
    assert least_squares_slope([1.0, 2.0, 3.0, 4.0]) == pytest.approx(1.0)
    assert least_squares_slope([4.0, 3.0, 2.0, 1.0]) == pytest.approx(-1.0)
    assert least_squares_slope([5.0]) == 0.0


def test_delt01_rise_drop():
    fixture = load_signal_fixture("delt_01")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = DeltaDetector(config=SignalConfig(big_delta_threshold=200))

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    signal = next(result for result in results if result.signal_id is SignalId.DELT_01)
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.DELT_01
    assert signal.price == bar.close
    assert signal.strength == pytest.approx(0.5)


def test_delt02_tail_delta():
    fixture = load_signal_fixture("delt_02")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = DeltaDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    signal = next(result for result in results if result.signal_id is SignalId.DELT_02)
    _assert_signal(signal, fixture["expected_signal"], SignalFlagBits.DELT_02)
    assert signal.price == bar.low


def test_delt03_delta_reversal():
    fixture = load_signal_fixture("delt_03")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = DeltaDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar, delta_history=[300]))

    signal = next(result for result in results if result.signal_id is SignalId.DELT_03)
    _assert_signal(signal, fixture["expected_signal"], SignalFlagBits.DELT_03)


def test_delt04_cvd_price_divergence():
    fixture = load_signal_fixture("delt_04")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = DeltaDetector()
    ctx = _ctx(
        current_bar=bar,
        price_history=fixture["context"]["price_history"],
        cvd_history=fixture["context"]["cvd_history"],
    )

    results = detector.on_bar(bar, ctx)

    signal = next(result for result in results if result.signal_id is SignalId.DELT_04)
    _assert_signal(signal, fixture["expected_signal"], SignalFlagBits.DELT_04)


def test_delt05_cvd_zero_flip():
    fixture = load_signal_fixture("delt_05")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = DeltaDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar, cvd_history=[50.0]))

    signal = next(result for result in results if result.signal_id is SignalId.DELT_05)
    _assert_signal(signal, fixture["expected_signal"], SignalFlagBits.DELT_05)


def test_delt06_delta_trap():
    fixture = load_signal_fixture("delt_06")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = DeltaDetector()
    prior_bar = _prior_bar(bar, close=21520.0, delta=600, cvd=600.0)

    results = detector.on_bar(bar, _ctx(current_bar=bar, bar_history=[prior_bar]))

    signal = next(result for result in results if result.signal_id is SignalId.DELT_06)
    _assert_signal(signal, fixture["expected_signal"], SignalFlagBits.DELT_06)


def test_delt07_delta_sweep():
    fixture = load_signal_fixture("delt_07")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = DeltaDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    signal = next(result for result in results if result.signal_id is SignalId.DELT_07)
    _assert_signal(signal, fixture["expected_signal"], SignalFlagBits.DELT_07)


def test_delt08_slingshot():
    fixture = load_signal_fixture("delt_08")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = DeltaDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar, delta_history=[-5]))

    signal = next(result for result in results if result.signal_id is SignalId.DELT_08)
    _assert_signal(signal, fixture["expected_signal"], SignalFlagBits.DELT_08)


def test_delt09_session_delta_extreme():
    fixture = load_signal_fixture("delt_09")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = DeltaDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar, cvd_history=[100.0, 400.0, 750.0, 1100.0]))

    signal = next(result for result in results if result.signal_id is SignalId.DELT_09)
    _assert_signal(signal, fixture["expected_signal"], SignalFlagBits.DELT_09)


def test_delt10_cvd_polyfit_divergence():
    fixture = load_signal_fixture("delt_10")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = DeltaDetector()
    ctx = _ctx(
        current_bar=bar,
        price_history=fixture["context"]["price_history"],
        cvd_history=fixture["context"]["cvd_history"],
    )

    results = detector.on_bar(bar, ctx)

    signal = next(result for result in results if result.signal_id is SignalId.DELT_10)
    _assert_signal(signal, fixture["expected_signal"], SignalFlagBits.DELT_10)


def test_delt11_delta_velocity():
    fixture = load_signal_fixture("delt_11")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = DeltaDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar, delta_history=[200]))

    signal = next(result for result in results if result.signal_id is SignalId.DELT_11)
    _assert_signal(signal, fixture["expected_signal"], SignalFlagBits.DELT_11)


def test_composite_delta_signals():
    fixture = load_signal_fixture("composite_delta")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = DeltaDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar, delta_history=[10, -15, 20, -5, 25]))

    result_by_id = {result.signal_id: result for result in results}
    assert set(result_by_id) == {SignalId.DELT_01, SignalId.DELT_08, SignalId.DELT_11}
    for expected in fixture["expected_signals"]:
        signal = result_by_id[SignalId(expected["signal_id"])]
        assert signal.signal_id is SignalId(expected["signal_id"])
        assert signal.direction is Direction[expected["direction"]]
        assert signal.flag_bit == getattr(SignalFlagBits, expected["signal_id"])
        assert 0.0 <= signal.strength <= 1.0


@pytest.mark.parametrize(
    ("fixture_name", "signal_id"),
    [
        ("delt_03", SignalId.DELT_03),
        ("delt_04", SignalId.DELT_04),
        ("delt_05", SignalId.DELT_05),
        ("delt_06", SignalId.DELT_06),
        ("delt_08", SignalId.DELT_08),
        ("delt_09", SignalId.DELT_09),
        ("delt_10", SignalId.DELT_10),
        ("delt_11", SignalId.DELT_11),
    ],
)
def test_no_signal_when_insufficient_history(fixture_name: str, signal_id: SignalId):
    bar = _bar_from_fixture(fixture_name)
    detector = DeltaDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    assert all(result.signal_id is not signal_id for result in results)


def test_no_signal_empty_bar():
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
        timestamp=datetime(2026, 5, 14, 14, 0, tzinfo=UTC),
        session_type=SessionType.RTH,
    )
    detector = DeltaDetector()

    assert detector.on_bar(bar, _ctx(current_bar=bar)) == []
