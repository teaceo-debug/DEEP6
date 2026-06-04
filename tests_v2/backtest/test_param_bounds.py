from __future__ import annotations

from deep6.backtest.param_bounds import ParamBound, clamp_config, get_bounds, validate_config
from deep6.backtest.strategy_config import BracketExit, StrategyConfig, TimeExit


def test_validate_config_returns_empty_list_for_valid_config():
    config = StrategyConfig(
        bracket_exit=BracketExit(stop_ticks=20, target_ticks=40, rr_ratio=2.0),
        time_exit=TimeExit(max_bars_in_trade=30, session_end_flatten=True),
    )

    assert validate_config(config) == []


def test_validate_config_returns_error_for_out_of_bounds_stop_ticks():
    config = StrategyConfig(
        bracket_exit=BracketExit(stop_ticks=999, target_ticks=40, rr_ratio=2.0),
        time_exit=TimeExit(max_bars_in_trade=30, session_end_flatten=True),
    )

    errors = validate_config(config)

    assert errors
    assert any("stop_ticks" in error for error in errors)


def test_clamp_config_clamps_stop_ticks_to_upper_bound():
    config = StrategyConfig(
        bracket_exit=BracketExit(stop_ticks=999, target_ticks=40, rr_ratio=2.0),
        time_exit=TimeExit(max_bars_in_trade=30, session_end_flatten=True),
    )

    clamped = clamp_config(config)

    assert clamped.bracket_exit.stop_ticks == 100
    assert clamped.bracket_exit.target_ticks == 40
    assert clamped.bracket_exit.rr_ratio == 2.0


def test_get_bounds_returns_expected_param_bound():
    bound = get_bounds("stop_ticks")

    assert bound == ParamBound(
        name="stop_ticks",
        min_val=5,
        max_val=100,
        default=20,
        dtype=int,
        description="Stop loss in ticks",
    )
