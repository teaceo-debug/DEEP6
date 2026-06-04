from __future__ import annotations

from collections import deque

from deep6v2.signals.auction import AuctionDetector
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
    vol_history: list[int] | None = None,
    current_bar: FootprintBar | None = None,
) -> SessionContext:
    return SessionContext(
        atr=atr,
        cvd=0.0,
        vah=21520.0,
        val=21480.0,
        poc=21500.0,
        session_type=SessionType.RTH,
        session_open_bar_index=0,
        current_bar=current_bar,
        vol_history=deque(vol_history or [], maxlen=50),
    )


def _assert_fixture_signal(name: str, expected_id: SignalId, expected_direction: Direction) -> None:
    fixture = load_signal_fixture(name)
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = AuctionDetector()

    results = detector.on_bar(bar, _ctx(atr=fixture["context"]["atr"], current_bar=bar))

    signal = next(result for result in results if result.signal_id is expected_id)
    expected = fixture["expected_signal"]
    assert signal.direction is expected_direction
    assert expected["strength_min"] <= signal.strength <= expected["strength_max"]


def test_auct01_high_unfinished_bullish():
    bar = _bar_from_fixture("auct_01")
    detector = AuctionDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    signal = next(result for result in results if result.signal_id is SignalId.AUCT_01 and result.price == bar.high)
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.AUCT_01
    assert 0.25 <= signal.strength <= 0.45
    assert "Unfinished auction at high" in signal.detail


def test_auct01_low_unfinished_bearish():
    bar = FootprintBar(
        open=21500.0,
        high=21508.0,
        low=21495.0,
        close=21504.0,
        delta=120,
        total_volume=1800,
        bid_volumes={21495.0: 2, 21498.0: 140, 21500.0: 220, 21504.0: 200},
        ask_volumes={21498.0: 160, 21500.0: 240, 21504.0: 280, 21508.0: 120},
        poc_price=21504.0,
        poc_volume=480,
        vah=21504.0,
        val=21498.0,
        cvd=120.0,
        bar_index=12,
        timestamp=bar_timestamp(),
        session_type=SessionType.RTH,
    )
    detector = AuctionDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    signal = next(result for result in results if result.signal_id is SignalId.AUCT_01 and result.price == bar.low)
    assert signal.direction is Direction.BEARISH
    assert signal.flag_bit == SignalFlagBits.AUCT_01
    assert 0.25 <= signal.strength <= 0.45
    assert "Unfinished auction at low" in signal.detail


def test_auct02_finished_auction_bearish():
    _assert_fixture_signal("auct_02", SignalId.AUCT_02, Direction.BEARISH)


def test_auct03_poor_high_bearish():
    _assert_fixture_signal("auct_03", SignalId.AUCT_03, Direction.BEARISH)


def test_auct04_volume_void_bullish():
    bar = _bar_from_fixture("auct_04")
    detector = AuctionDetector()

    results = detector.on_bar(bar, _ctx(current_bar=bar))

    signal = next(result for result in results if result.signal_id is SignalId.AUCT_04)
    assert signal.direction is Direction.BULLISH
    assert signal.flag_bit == SignalFlagBits.AUCT_04
    assert 0.30 <= signal.strength <= 0.50
    assert "Volume void across 2 levels" in signal.detail


def test_auct05_market_sweep_bearish():
    _assert_fixture_signal("auct_05", SignalId.AUCT_05, Direction.BEARISH)


def test_composite_auction_fixture_emits_expected_signals():
    fixture = load_signal_fixture("composite_auction")
    bar = FootprintBar.model_validate(fixture["bar"])
    detector = AuctionDetector()

    results = detector.on_bar(bar, _ctx(atr=fixture["context"]["atr"], current_bar=bar))

    ids = {result.signal_id for result in results}
    assert SignalId.AUCT_01 in ids
    assert SignalId.AUCT_02 in ids
    assert SignalId.AUCT_05 in ids


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
    detector = AuctionDetector()

    assert detector.on_bar(bar, _ctx(current_bar=bar)) == []


def bar_timestamp():
    from datetime import UTC, datetime

    return datetime(2026, 5, 14, 14, 0, tzinfo=UTC)
