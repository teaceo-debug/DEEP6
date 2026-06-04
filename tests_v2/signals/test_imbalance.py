from __future__ import annotations

from collections import deque

import pytest

from deep6v2.signals.imbalance import ImbalanceDetector
from deep6v2.types.bar import FootprintBar, SessionType
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId
from tests_v2.fixtures.loader import load_signal_fixture


def _bar_from_fixture(name: str) -> FootprintBar:
    data = load_signal_fixture(name)
    return FootprintBar.model_validate(data["bar"])


def _ctx(
    *,
    atr: float = 10.0,
    imbalance_history: list[dict[float, float]] | None = None,
    current_bar: FootprintBar | None = None,
) -> SessionContext:
    return SessionContext(
        atr=atr,
        cvd=0.0,
        vah=21500.0,
        val=21480.0,
        poc=21490.0,
        session_type=SessionType.RTH,
        session_open_bar_index=0,
        current_bar=current_bar,
        imbalance_history=deque(imbalance_history or [], maxlen=50),
    )


def _signal(results, signal_id: SignalId):
    return next(result for result in results if result.signal_id is signal_id)


def test_imb01_single_imbalance_bullish():
    bar = _bar_from_fixture("imb_01")
    detector = ImbalanceDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    signal = _signal(results, SignalId.IMB_01)
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.IMB_01
    assert signal.price == 21483.0
    assert signal.strength == pytest.approx((400 / 120) / 9.0)


def test_imb02_multiple_imbalance_across_three_bars():
    bar = _bar_from_fixture("imb_02")
    detector = ImbalanceDetector()
    ctx = _ctx(
        current_bar=bar,
        imbalance_history=[{21480.0: 3.5}, {21480.0: 4.2}],
    )

    results = detector.on_bar(bar, ctx)

    signal = _signal(results, SignalId.IMB_02)
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.IMB_02
    assert signal.price == 21480.0
    assert signal.strength == pytest.approx(3 / 5)


@pytest.mark.parametrize(
    ("name", "expected_strength"),
    [("imb_03_t1", pytest.approx(1 / 3)), ("imb_03", pytest.approx(2 / 3)), ("imb_03_t3", pytest.approx(1.0))],
)
def test_imb03_stacked_imbalance_tiers(name: str, expected_strength):
    if name == "imb_03_t1":
        base = _bar_from_fixture("imb_03")
        bar = base.model_copy(
            update={
                "bid_volumes": {
                    21488.0: 40,
                    21490.0: 50,
                    21490.25: 45,
                    21490.5: 40,
                    21490.75: 35,
                    21495.0: 120,
                    21500.0: 200,
                },
                "ask_volumes": {
                    21490.0: 200,
                    21490.25: 180,
                    21490.5: 190,
                    21490.75: 160,
                    21495.0: 350,
                    21500.0: 400,
                    21515.0: 160,
                },
            }
        )
    elif name == "imb_03_t3":
        bar = FootprintBar(
            open=21490.0,
            high=21492.0,
            low=21490.0,
            close=21491.75,
            delta=700,
            total_volume=4200,
            bid_volumes={
                21490.0: 50,
                21490.25: 45,
                21490.5: 40,
                21490.75: 35,
                21491.0: 30,
                21491.25: 28,
                21491.5: 25,
                21491.75: 60,
            },
            ask_volumes={
                21490.0: 180,
                21490.25: 170,
                21490.5: 165,
                21490.75: 160,
                21491.0: 150,
                21491.25: 145,
                21491.5: 140,
                21491.75: 70,
                21492.0: 50,
            },
            poc_price=21491.0,
            poc_volume=500,
            vah=21491.75,
            val=21490.25,
            cvd=700.0,
            bar_index=60,
            timestamp=bar_timestamp(),
            session_type=SessionType.RTH,
        )
    else:
        bar = _bar_from_fixture("imb_03")

    detector = ImbalanceDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    signal = _signal(results, SignalId.IMB_03)
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.IMB_03
    assert signal.strength == expected_strength


def test_imb04_reverse_imbalance_contested_level():
    bar = _bar_from_fixture("imb_04")
    detector = ImbalanceDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    signal = _signal(results, SignalId.IMB_04)
    assert signal.direction is Direction.NEUTRAL
    assert signal.flag_bit == SignalFlagBits.IMB_04
    assert signal.price == 21501.5
    assert signal.strength == pytest.approx(4 / 9)


def test_imb05_inverse_imbalance_in_red_bar():
    bar = _bar_from_fixture("imb_05")
    detector = ImbalanceDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    signal = _signal(results, SignalId.IMB_05)
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.IMB_05
    assert signal.price == 21500.0
    assert signal.strength == pytest.approx((350 / 80) / 6.0)


def test_imb06_oversized_imbalance():
    bar = _bar_from_fixture("imb_06")
    detector = ImbalanceDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    signal = _signal(results, SignalId.IMB_06)
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.IMB_06
    assert signal.price == 21490.0
    assert signal.strength == pytest.approx((500 / 40) / 15.0)


def test_imb07_consecutive_imbalance_two_bars():
    bar = _bar_from_fixture("imb_07")
    detector = ImbalanceDetector()
    ctx = _ctx(current_bar=bar, imbalance_history=[{21500.0: 4.0}])

    results = detector.on_bar(bar, ctx)

    signal = _signal(results, SignalId.IMB_07)
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.IMB_07
    assert signal.price == 21500.0
    assert signal.strength == pytest.approx(2 / 5)


def test_imb08_diagonal_imbalance():
    bar = _bar_from_fixture("imb_08")
    detector = ImbalanceDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    signal = _signal(results, SignalId.IMB_08)
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.IMB_08
    assert signal.price == 21502.25
    assert signal.strength == pytest.approx((300 / 70) / 9.0)


def test_imb09_reversal_imbalance():
    bar = _bar_from_fixture("imb_09")
    detector = ImbalanceDetector()
    ctx = _ctx(current_bar=bar, imbalance_history=[{21488.0: -3.5}])

    results = detector.on_bar(bar, ctx)

    signal = _signal(results, SignalId.IMB_09)
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.IMB_09
    assert signal.price == 21488.0
    assert signal.strength == pytest.approx(0.8)


def test_composite_imbalance_fixture_emits_multiple_signals():
    bar = _bar_from_fixture("composite_imbalance")
    detector = ImbalanceDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    signal_ids = {result.signal_id for result in results}
    assert {SignalId.IMB_01, SignalId.IMB_03, SignalId.IMB_06}.issubset(signal_ids)


def test_imbalance_history_records_current_bar_at_end():
    bar = _bar_from_fixture("imb_01")
    detector = ImbalanceDetector()
    ctx = _ctx(current_bar=bar, imbalance_history=[{21480.0: 3.1}])

    detector.on_bar(bar, ctx)

    assert ctx.imbalance_history[-1][21480.0] == pytest.approx(3.0)
    assert ctx.imbalance_history[-1][21483.0] == pytest.approx(400 / 120)
    assert ctx.imbalance_history[-1][21485.0] == pytest.approx(250 / 80)


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
        timestamp=bar_timestamp(),
        session_type=SessionType.RTH,
    )
    detector = ImbalanceDetector()
    ctx = _ctx(current_bar=bar)

    assert detector.on_bar(bar, ctx) == []
    assert list(ctx.imbalance_history) == []


def bar_timestamp():
    from datetime import UTC, datetime

    return datetime(2026, 5, 14, 14, 0, tzinfo=UTC)
