from __future__ import annotations

from deep6v2.config.scoring import ScoringConfig
from deep6v2.scoring.hysteresis import (
    BiasState,
    HysteresisFSM,
    get_ib_multiplier,
    is_initial_balance,
    is_midday_blocked,
)
from deep6v2.types.signal import Direction


def test_two_bullish_bars_stay_transitioning() -> None:
    fsm = HysteresisFSM()

    assert fsm.update(Direction.BULLISH) is BiasState.TRANSITIONING
    assert fsm.update(Direction.BULLISH) is BiasState.TRANSITIONING
    assert fsm.state is BiasState.TRANSITIONING
    assert fsm.direction is Direction.BULLISH


def test_disagreement_after_partial_run_resets_to_neutral() -> None:
    fsm = HysteresisFSM()

    fsm.update(Direction.BULLISH)
    fsm.update(Direction.BULLISH)

    assert fsm.update(Direction.BEARISH) is BiasState.NEUTRAL
    assert fsm.state is BiasState.NEUTRAL
    assert fsm.direction is Direction.NEUTRAL


def test_three_bullish_bars_confirm_bullish_bias() -> None:
    fsm = HysteresisFSM()

    fsm.update(Direction.BULLISH)
    fsm.update(Direction.BULLISH)

    assert fsm.update(Direction.BULLISH) is BiasState.BULLISH_CONFIRMED
    assert fsm.direction is Direction.BULLISH


def test_three_bearish_bars_confirm_bearish_bias() -> None:
    fsm = HysteresisFSM()

    fsm.update(Direction.BEARISH)
    fsm.update(Direction.BEARISH)

    assert fsm.update(Direction.BEARISH) is BiasState.BEARISH_CONFIRMED
    assert fsm.direction is Direction.BEARISH


def test_neutral_direction_does_not_reset_or_advance_partial_run() -> None:
    fsm = HysteresisFSM()

    fsm.update(Direction.BULLISH)
    assert fsm.update(Direction.NEUTRAL) is BiasState.TRANSITIONING
    assert fsm.update(Direction.BULLISH) is BiasState.TRANSITIONING
    assert fsm.update(Direction.BULLISH) is BiasState.BULLISH_CONFIRMED


def test_confirmed_state_decays_after_five_neutral_bars() -> None:
    fsm = HysteresisFSM()

    fsm.update(Direction.BULLISH)
    fsm.update(Direction.BULLISH)
    assert fsm.update(Direction.BULLISH) is BiasState.BULLISH_CONFIRMED

    for _ in range(4):
        assert fsm.update(Direction.NEUTRAL) is BiasState.BULLISH_CONFIRMED

    assert fsm.update(Direction.NEUTRAL) is BiasState.NEUTRAL
    assert fsm.direction is Direction.NEUTRAL


def test_confirmed_state_resets_immediately_on_opposite_direction() -> None:
    fsm = HysteresisFSM()

    fsm.update(Direction.BEARISH)
    fsm.update(Direction.BEARISH)
    assert fsm.update(Direction.BEARISH) is BiasState.BEARISH_CONFIRMED

    assert fsm.update(Direction.BULLISH) is BiasState.NEUTRAL


def test_midday_block_boundaries() -> None:
    assert is_midday_blocked(59) is False
    assert is_midday_blocked(60) is True
    assert is_midday_blocked(120) is True
    assert is_midday_blocked(210) is True
    assert is_midday_blocked(211) is False


def test_midday_block_uses_config_override() -> None:
    config = ScoringConfig(midday_block_start_bar=10, midday_block_end_bar=12)

    assert is_midday_blocked(9, config) is False
    assert is_midday_blocked(10, config) is True
    assert is_midday_blocked(12, config) is True
    assert is_midday_blocked(13, config) is False


def test_initial_balance_boundaries() -> None:
    assert is_initial_balance(0) is True
    assert is_initial_balance(59) is True
    assert is_initial_balance(60) is False


def test_ib_multiplier_boundaries() -> None:
    assert get_ib_multiplier(30) == 1.15
    assert get_ib_multiplier(70) == 1.0
