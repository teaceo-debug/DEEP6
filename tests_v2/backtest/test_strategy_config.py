from __future__ import annotations

import pytest

from deep6.backtest.strategy_config import (
    ApproachDirection,
    BracketExit,
    ConfirmationSignal,
    LevelTarget,
    StrategyConfig,
    TimeExit,
    TimingFilter,
)


def test_strategy_config_roundtrip_and_hash_stable():
    config = StrategyConfig(
        level_target=LevelTarget.LVN,
        approach_direction=ApproachDirection.EITHER,
        timing_filter=TimingFilter.ANY,
        confirmation_signals=[ConfirmationSignal(signal_id="ABS_01", threshold=0.75, operator="gt")],
        bracket_exit=BracketExit(stop_ticks=20, target_ticks=40, rr_ratio=2.0),
        time_exit=TimeExit(max_bars_in_trade=30, session_end_flatten=True),
    )

    encoded = config.model_dump_json()
    decoded = StrategyConfig.model_validate_json(encoded)

    assert decoded == config
    assert config.config_hash() == decoded.config_hash()


def test_strategy_config_hash_changes_when_config_changes():
    hvn = StrategyConfig(level_target=LevelTarget.HVN)
    lvn = StrategyConfig(level_target=LevelTarget.LVN)

    assert hvn.config_hash() == StrategyConfig(level_target=LevelTarget.HVN).config_hash()
    assert hvn.config_hash() != lvn.config_hash()


def test_strategy_config_is_frozen():
    config = StrategyConfig(level_target=LevelTarget.LVN)

    with pytest.raises((AttributeError, TypeError, ValueError, Exception)):
        config.level_target = LevelTarget.HVN
