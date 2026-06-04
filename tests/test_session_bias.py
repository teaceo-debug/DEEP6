from __future__ import annotations

from datetime import datetime, timedelta, timezone

from deep6.bias_engine.models import BiasDirection, JudasStatus, PO3BiasState, PO3Phase
from deep6.engines.session_bias import ICTSessionDomain


def _state(**overrides: object) -> PO3BiasState:
    base = dict(
        bull_pts=0,
        bear_pts=0,
        direction=BiasDirection.NEUTRAL,
        phase=PO3Phase.DISTRIBUTION,
        above_midnight_open=None,
        above_weekly_open=None,
        in_discount=None,
        judas_status=JudasStatus.NONE,
        current_close=0.0,
        timestamp=datetime.now(tz=timezone.utc),
    )
    base.update(overrides)
    return PO3BiasState(**base)


def test_all_bullish_scores_plus_four() -> None:
    domain = ICTSessionDomain()

    result = domain.compute(
        _state(
            above_midnight_open=True,
            above_weekly_open=True,
            judas_status=JudasStatus.BULL_CONFIRMED,
            in_discount=True,
        )
    )

    assert result.domain == "ict"
    assert result.available is True
    assert result.score == 4
    assert result.max_range == 4
    assert result.stale is False


def test_all_bearish_scores_minus_four() -> None:
    domain = ICTSessionDomain()

    result = domain.compute(
        _state(
            above_midnight_open=False,
            above_weekly_open=False,
            judas_status=JudasStatus.BEAR_CONFIRMED,
            in_discount=False,
        )
    )

    assert result.score == -4
    assert result.max_range == 4


def test_partial_availability_reduces_max_range() -> None:
    domain = ICTSessionDomain()

    result = domain.compute(
        _state(
            above_midnight_open=True,
            above_weekly_open=None,
            judas_status=JudasStatus.NONE,
            in_discount=None,
        )
    )

    assert result.score == 1
    assert result.max_range == 2
    assert result.detail["weekly_open"]["available"] is False
    assert result.detail["premium_discount"]["available"] is False


def test_none_state_is_unavailable() -> None:
    domain = ICTSessionDomain()

    result = domain.compute(None)

    assert result.available is False
    assert result.score == 0
    assert result.max_range == 0
    assert result.stale is False


def test_stale_state_sets_stale_true() -> None:
    domain = ICTSessionDomain()

    result = domain.compute(
        _state(timestamp=datetime.now(tz=timezone.utc) - timedelta(seconds=61))
    )

    assert result.available is True
    assert result.stale is True


def test_weekly_open_component_can_score_bullishly() -> None:
    domain = ICTSessionDomain()

    result = domain.compute(_state(above_weekly_open=True))

    assert result.score == 1
    assert result.detail["weekly_open"]["score"] == 1


def test_bear_judas_component_scores_minus_one() -> None:
    domain = ICTSessionDomain()

    result = domain.compute(_state(judas_status=JudasStatus.BEAR_CONFIRMED))

    assert result.score == -1
    assert result.detail["judas"]["score"] == -1


def test_discount_zone_scores_plus_one() -> None:
    domain = ICTSessionDomain()

    result = domain.compute(_state(in_discount=True))

    assert result.score == 1
    assert result.detail["premium_discount"]["score"] == 1


def test_unconfirmed_judas_is_neutral_but_available() -> None:
    domain = ICTSessionDomain()

    result = domain.compute(_state(judas_status=JudasStatus.SWEPT_HI))

    assert result.score == 0
    assert result.max_range == 1
    assert result.detail["judas"]["available"] is True
    assert result.detail["judas"]["score"] == 0
