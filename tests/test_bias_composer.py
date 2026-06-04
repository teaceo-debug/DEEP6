from __future__ import annotations

import pytest

from deep6.engines.bias_composer import BiasComposer
from deep6.engines.bias_contracts import BiasState, DomainScore


def _domain(
    domain: str,
    score: int,
    *,
    available: bool = True,
    stale: bool = False,
    max_range: int = 3,
) -> DomainScore:
    return DomainScore(
        domain=domain,
        score=score,
        max_range=max_range,
        available=available,
        stale=stale,
        detail={},
    )


@pytest.fixture
def composer() -> BiasComposer:
    return BiasComposer()


def test_compose_sums_active_domains_and_clamps(composer: BiasComposer) -> None:
    result = composer.compose(
        ict=_domain("ict", 4, max_range=4),
        macro=_domain("macro", 3),
        flow=_domain("flow", 2, max_range=2),
        kronos=_domain("kronos", 3),
    )

    assert result.total_score == 9
    assert result.ict_score == 4
    assert result.macro_score == 3
    assert result.flow_score == 2
    assert result.kronos_score == 3
    assert result.confidence == 1.0


def test_stale_domain_is_excluded_from_sum(composer: BiasComposer) -> None:
    result = composer.compose(
        ict=_domain("ict", 4, stale=True, max_range=4),
        macro=_domain("macro", 2),
        flow=_domain("flow", 1, max_range=2),
        kronos=_domain("kronos", 2),
    )

    assert result.total_score == 5
    assert result.ict_score == 0
    assert result.confidence == pytest.approx((5 / 9.0) * 0.9)


def test_unavailable_domain_is_excluded_from_sum(composer: BiasComposer) -> None:
    result = composer.compose(
        ict=_domain("ict", 4, available=False, max_range=4),
        macro=_domain("macro", 2),
        flow=_domain("flow", 1, max_range=2),
        kronos=_domain("kronos", 0),
    )

    assert result.total_score == 3
    assert result.ict_score == 0


def test_heavy_disagreement_halves_confidence(composer: BiasComposer) -> None:
    result = composer.compose(
        ict=_domain("ict", 4, max_range=4),
        macro=_domain("macro", -3),
        flow=_domain("flow", 1, max_range=2),
        kronos=_domain("kronos", 0),
    )

    assert result.total_score == 2
    assert result.confidence == pytest.approx((2 / 9.0) * 0.5)


def test_single_active_domain_gets_domain_penalty(composer: BiasComposer) -> None:
    result = composer.compose(
        ict=_domain("ict", 4, available=False, max_range=4),
        macro=_domain("macro", 3),
        flow=_domain("flow", 0, available=False, max_range=2),
        kronos=_domain("kronos", 0, available=False),
    )

    assert result.total_score == 3
    assert result.confidence == pytest.approx((3 / 9.0) * 0.5)


def test_multiple_stale_domains_stack_penalties(composer: BiasComposer) -> None:
    result = composer.compose(
        ict=_domain("ict", 4, stale=True, max_range=4),
        macro=_domain("macro", 2, stale=True),
        flow=_domain("flow", 2, max_range=2),
        kronos=_domain("kronos", 1),
    )

    assert result.total_score == 3
    assert result.confidence == pytest.approx((3 / 9.0) * 0.9 * 0.9)


def test_setup_quality_counts_agreement_and_flags(composer: BiasComposer) -> None:
    result = composer.compose(
        ict=_domain("ict", 2, max_range=4),
        macro=_domain("macro", 2),
        flow=_domain("flow", 1, max_range=2),
        kronos=_domain("kronos", 1),
        session_quality=True,
        proximity_bonus=True,
        flow_clean=True,
        rvol_bonus=True,
    )

    assert result.setup_quality == 5


def test_setup_quality_no_agreement_when_scores_mixed(composer: BiasComposer) -> None:
    result = composer.compose(
        ict=_domain("ict", 2, max_range=4),
        macro=_domain("macro", -1),
        flow=_domain("flow", 0, max_range=2),
        kronos=_domain("kronos", 0),
        session_quality=True,
    )

    assert result.setup_quality == 1


def test_component_returns_placeholder_state_before_fsm(composer: BiasComposer) -> None:
    result = composer.compose(
        ict=_domain("ict", 1, max_range=4),
        macro=_domain("macro", 1),
        flow=_domain("flow", 0, max_range=2),
        kronos=_domain("kronos", 0),
    )

    assert result.bias_state is BiasState.NEUTRAL
    assert result.reason == "Pending hysteresis and kill switch"
