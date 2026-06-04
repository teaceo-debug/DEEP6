from __future__ import annotations

import pytest

from deep6.engines.bias_contracts import BiasState
from deep6.engines.bias_hysteresis import BiasHysteresisFSM


def test_initial_state_is_neutral() -> None:
    fsm = BiasHysteresisFSM()

    assert fsm.state is BiasState.NEUTRAL
    assert fsm.current_state is BiasState.NEUTRAL
    assert fsm.previous_state is None
    assert fsm.bars_in_state == 0


def test_target_state_maps_score_without_hysteresis() -> None:
    fsm = BiasHysteresisFSM()

    assert fsm._target_state(7) is BiasState.STRONG_BULL
    assert fsm._target_state(3) is BiasState.LEAN_BULL
    assert fsm._target_state(0) is BiasState.NEUTRAL
    assert fsm._target_state(-3) is BiasState.LEAN_BEAR
    assert fsm._target_state(-7) is BiasState.STRONG_BEAR


def test_enters_strong_bull_at_enter_threshold() -> None:
    fsm = BiasHysteresisFSM()

    assert fsm.update(7) is BiasState.STRONG_BULL


def test_does_not_enter_strong_bull_below_threshold() -> None:
    fsm = BiasHysteresisFSM()

    assert fsm.update(6) is BiasState.LEAN_BULL


def test_stays_strong_bull_above_degrade_threshold() -> None:
    fsm = BiasHysteresisFSM()

    fsm.update(7)

    assert fsm.update(5) is BiasState.STRONG_BULL
    assert fsm.bars_in_state == 2


def test_leaves_strong_bull_below_degrade_threshold() -> None:
    fsm = BiasHysteresisFSM()

    fsm.update(7)

    assert fsm.update(3) is BiasState.NEUTRAL
    assert fsm.previous_state is BiasState.STRONG_BULL
    assert fsm.bars_in_state == 1


def test_enters_and_holds_lean_bull_until_degrade_threshold_breaks() -> None:
    fsm = BiasHysteresisFSM()

    assert fsm.update(3) is BiasState.LEAN_BULL
    assert fsm.update(1) is BiasState.LEAN_BULL
    assert fsm.update(0) is BiasState.NEUTRAL


def test_neutral_when_score_is_zero() -> None:
    fsm = BiasHysteresisFSM()

    assert fsm.update(0) is BiasState.NEUTRAL
    assert fsm.bars_in_state == 1


def test_enters_strong_bear_at_enter_threshold() -> None:
    fsm = BiasHysteresisFSM()

    assert fsm.update(-7) is BiasState.STRONG_BEAR


def test_stays_strong_bear_above_degrade_threshold_magnitude() -> None:
    fsm = BiasHysteresisFSM()

    fsm.update(-7)

    assert fsm.update(-5) is BiasState.STRONG_BEAR


def test_leaves_strong_bear_below_degrade_threshold_magnitude() -> None:
    fsm = BiasHysteresisFSM()

    fsm.update(-7)

    assert fsm.update(-3) is BiasState.NEUTRAL
    assert fsm.previous_state is BiasState.STRONG_BEAR


def test_enters_and_holds_lean_bear_until_degrade_threshold_breaks() -> None:
    fsm = BiasHysteresisFSM()

    assert fsm.update(-3) is BiasState.LEAN_BEAR
    assert fsm.update(-1) is BiasState.LEAN_BEAR
    assert fsm.update(0) is BiasState.NEUTRAL


def test_emergency_flip_bypasses_hysteresis() -> None:
    fsm = BiasHysteresisFSM()

    fsm.update(7)

    assert fsm.update(-3) is BiasState.LEAN_BEAR


def test_sequence_matches_expected_hysteresis_path() -> None:
    fsm = BiasHysteresisFSM()

    scores = [3, 5, 7, 5, 3, 1, -1, -3]

    assert [fsm.update(score) for score in scores] == [
        BiasState.LEAN_BULL,
        BiasState.LEAN_BULL,
        BiasState.STRONG_BULL,
        BiasState.STRONG_BULL,
        BiasState.NEUTRAL,
        BiasState.NEUTRAL,
        BiasState.NEUTRAL,
        BiasState.LEAN_BEAR,
    ]


def test_rejects_scores_outside_supported_range() -> None:
    fsm = BiasHysteresisFSM()

    # Max score with 5 domains is ±15; values beyond that should raise
    with pytest.raises(ValueError):
        fsm.update(16)


def test_rejects_non_integer_scores() -> None:
    fsm = BiasHysteresisFSM()

    with pytest.raises(TypeError):
        fsm.update(1.5)  # type: ignore[arg-type]
