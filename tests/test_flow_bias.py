from __future__ import annotations

from datetime import datetime

from deep6.engines.flow_bias import ET, IntradayFlowDomain


def _et(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, 12, hour, minute, tzinfo=ET)


def test_all_bullish_inputs_clamp_to_plus_two() -> None:
    domain = IntradayFlowDomain()

    score = domain.compute(
        tick_value=1_000,
        cvd_slope=75.0,
        price=20_105.0,
        vwap=20_100.0,
        now_et=_et(10, 0),
    )

    assert score.domain == "flow"
    assert score.score == 2
    assert score.max_range == 2
    assert score.available is True
    assert score.stale is False
    assert score.detail["raw_score"] == 3


def test_all_bearish_inputs_clamp_to_minus_two() -> None:
    domain = IntradayFlowDomain()

    score = domain.compute(
        tick_value=-1_100,
        cvd_slope=-90.0,
        price=20_090.0,
        vwap=20_100.0,
        now_et=_et(11, 15),
    )

    assert score.score == -2
    assert score.detail["raw_score"] == -3


def test_returns_stale_zero_outside_rth() -> None:
    domain = IntradayFlowDomain()

    score = domain.compute(
        tick_value=900,
        cvd_slope=60.0,
        price=20_105.0,
        vwap=20_100.0,
        now_et=_et(8, 45),
    )

    assert score.score == 0
    assert score.available is False
    assert score.stale is True
    assert score.detail == {"reason": "outside RTH"}


def test_vwap_none_skips_vwap_component() -> None:
    domain = IntradayFlowDomain()

    score = domain.compute(
        tick_value=900,
        cvd_slope=60.0,
        price=20_105.0,
        vwap=None,
        now_et=_et(10, 30),
    )

    assert score.score == 2
    assert score.detail["vwap_component"] == 0
    assert score.detail["raw_score"] == 2


def test_tick_none_skips_tick_component() -> None:
    domain = IntradayFlowDomain()

    score = domain.compute(
        tick_value=None,
        cvd_slope=-75.0,
        price=20_090.0,
        vwap=20_100.0,
        now_et=_et(13, 5),
    )

    assert score.score == -2
    assert score.detail["tick_component"] == 0
    assert score.detail["raw_score"] == -2


def test_cvd_threshold_is_strict() -> None:
    domain = IntradayFlowDomain()

    score = domain.compute(
        tick_value=None,
        cvd_slope=50.0,
        price=20_105.0,
        vwap=20_100.0,
        now_et=_et(14, 0),
    )

    assert score.detail["cvd_component"] == 0
    assert score.score == 1


def test_tick_threshold_is_strict() -> None:
    domain = IntradayFlowDomain()

    score = domain.compute(
        tick_value=800,
        cvd_slope=60.0,
        price=20_100.0,
        vwap=20_100.0,
        now_et=_et(14, 30),
    )

    assert score.detail["tick_component"] == 0
    assert score.detail["vwap_component"] == 0
    assert score.score == 1


def test_rth_start_is_inclusive_and_end_is_exclusive() -> None:
    domain = IntradayFlowDomain()

    assert domain._is_rth(_et(9, 30)) is True
    assert domain._is_rth(_et(16, 0)) is False


def test_naive_now_is_treated_as_eastern_time() -> None:
    domain = IntradayFlowDomain()
    naive = datetime(2026, 5, 12, 10, 0)

    score = domain.compute(
        tick_value=900,
        cvd_slope=None,
        price=None,
        vwap=None,
        now_et=naive,
    )

    assert score.score == 1
    assert score.stale is False


def test_no_inputs_inside_rth_returns_unavailable_but_not_stale() -> None:
    domain = IntradayFlowDomain()

    score = domain.compute(
        tick_value=None,
        cvd_slope=None,
        price=None,
        vwap=None,
        now_et=_et(10, 0),
    )

    assert score.score == 0
    assert score.available is False
    assert score.stale is False
    assert score.detail["raw_score"] == 0
