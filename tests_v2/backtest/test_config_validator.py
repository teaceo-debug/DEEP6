from __future__ import annotations

from deep6.backtest.config_validator import ValidationResult, suggest_fix, validate
from deep6.backtest.strategy_config import BracketExit, LevelExit, LevelTarget, StrategyConfig, TimeExit, TimingFilter


def test_validate_accepts_valid_config():
    config = StrategyConfig(bracket_exit=BracketExit(stop_ticks=20, target_ticks=40, rr_ratio=2.0))

    result = validate(config)

    assert result == ValidationResult(valid=True, errors=[], warnings=[])


def test_validate_rejects_target_ticks_below_stop_ticks_when_rr_ratio_above_one():
    config = StrategyConfig(bracket_exit=BracketExit(stop_ticks=50, target_ticks=20, rr_ratio=2.0))

    result = validate(config)

    assert not result.valid
    assert any("target_ticks" in error for error in result.errors)


def test_validate_rejects_missing_exit_strategy():
    config = StrategyConfig(bracket_exit=None, level_exit=None)

    result = validate(config)

    assert not result.valid
    assert any("at least one exit" in error.lower() for error in result.errors)


def test_validate_propagates_bounds_errors_from_param_bounds():
    config = StrategyConfig(bracket_exit=BracketExit(stop_ticks=999, target_ticks=40, rr_ratio=2.0))

    result = validate(config)

    assert not result.valid
    assert any("outside bounds" in error for error in result.errors)


def test_suggest_fix_returns_expected_hints():
    hints = suggest_fix(
        [
            "target_ticks (20) must be > stop_ticks (50) when rr_ratio=2.0 > 1.0",
            "stop_ticks 999 outside bounds [5, 100]",
            "Must have at least one exit: bracket_exit or level_exit",
        ]
    )

    assert hints["target_ticks"].startswith("Set target_ticks = stop_ticks * rr_ratio")
    assert hints["stop_ticks"] == "Set stop_ticks within bounds [5, 100]"
    assert hints["exit"].startswith("Add bracket_exit")


def test_validate_emits_expected_warnings():
    config = StrategyConfig(
        level_target=LevelTarget.VPOC,
        timing_filter=TimingFilter.MIDDAY_BLOCK_EXCLUDED,
        bracket_exit=BracketExit(stop_ticks=20, target_ticks=40, rr_ratio=2.0),
        level_exit=LevelExit(exit_at_next_zone=False, trail_to_zone_boundary=True),
        time_exit=TimeExit(max_bars_in_trade=30, session_end_flatten=True),
    )

    result = validate(config)

    assert result.valid
    assert any("MIDDAY_BLOCK_EXCLUDED" in warning for warning in result.warnings)
    assert any("VPOC" in warning for warning in result.warnings)
