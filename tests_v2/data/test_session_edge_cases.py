from __future__ import annotations

from datetime import date, datetime, timezone

from deep6v2.clock import EventClock
from deep6v2.data.session_edge_cases import (
    CMEHaltDetector,
    ContractRollDetector,
    ET,
    HaltState,
    get_session_end,
    is_half_day,
    is_market_holiday,
    is_weekend,
    should_trade,
)


def test_cme_halt_confirms_after_35_seconds_and_tick_resets() -> None:
    detector = CMEHaltDetector(silence_threshold_s=30.0)

    detector.on_tick(100.0)

    assert detector.check(135.0) is HaltState.CONFIRMED_HALT
    assert detector.state is HaltState.CONFIRMED_HALT

    detector.on_tick(136.0)

    assert detector.state is HaltState.NORMAL
    assert detector.check(140.0) is HaltState.NORMAL


def test_contract_roll_week_is_true_around_second_thursday_in_march_2026() -> None:
    assert ContractRollDetector.is_roll_week(datetime(2026, 3, 10, 12, 0, tzinfo=ET)) is True
    assert ContractRollDetector.is_roll_week(datetime(2026, 3, 12, 12, 0, tzinfo=ET)) is True
    assert ContractRollDetector.is_roll_week(datetime(2026, 3, 13, 12, 0, tzinfo=ET)) is True
    assert ContractRollDetector.is_roll_week(datetime(2026, 3, 9, 12, 0, tzinfo=ET)) is False
    assert ContractRollDetector.is_roll_week(datetime(2026, 3, 16, 12, 0, tzinfo=ET)) is False


def test_front_month_symbol_uses_next_quarterly_expiry() -> None:
    assert ContractRollDetector.front_month_symbol(datetime(2026, 1, 20, 12, 0, tzinfo=ET)) == "NQH26"
    assert ContractRollDetector.front_month_symbol(datetime(2026, 4, 1, 12, 0, tzinfo=ET)) == "NQM26"


def test_market_holiday_detection() -> None:
    assert is_market_holiday(date(2026, 1, 1)) is True
    assert is_market_holiday(date(2026, 1, 2)) is False


def test_half_day_detection() -> None:
    assert is_half_day(date(2026, 11, 27)) is True


def test_get_session_end_handles_normal_and_half_days() -> None:
    assert get_session_end(date(2026, 5, 13)) == "16:00"
    assert get_session_end(date(2026, 11, 27)) == "13:00"


def test_is_weekend_flags_saturday_but_not_monday() -> None:
    assert is_weekend(date(2026, 5, 16)) is True
    assert is_weekend(date(2026, 5, 18)) is False


def test_should_trade_blocks_weekend_and_holiday() -> None:
    assert should_trade(datetime(2026, 5, 16, 10, 0, tzinfo=ET)) == (False, "weekend")
    assert should_trade(datetime(2026, 1, 1, 10, 0, tzinfo=ET)) == (False, "market_holiday")
    assert should_trade(datetime(2026, 5, 13, 10, 0, tzinfo=ET)) == (True, "ok")


def test_dst_keeps_930_et_correct_in_march_and_november() -> None:
    march_open_utc = datetime(2026, 3, 10, 13, 30, tzinfo=timezone.utc)
    november_open_utc = datetime(2026, 11, 10, 14, 30, tzinfo=timezone.utc)

    march_clock = EventClock()
    march_clock.advance(march_open_utc)
    assert march_clock.now().astimezone(ET).hour == 9
    assert march_clock.now().astimezone(ET).minute == 30
    assert march_clock.is_rth() is True
    assert march_clock.session_bar_index() == 0

    november_clock = EventClock()
    november_clock.advance(november_open_utc)
    assert november_clock.now().astimezone(ET).hour == 9
    assert november_clock.now().astimezone(ET).minute == 30
    assert november_clock.is_rth() is True
    assert november_clock.session_bar_index() == 0
