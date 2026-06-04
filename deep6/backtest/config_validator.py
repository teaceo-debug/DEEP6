from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from deep6.backtest.param_bounds import validate_config as bounds_validate
from deep6.backtest.strategy_config import LevelTarget, StrategyConfig, TimingFilter


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate(config: StrategyConfig) -> ValidationResult:
    """Full semantic validation of a StrategyConfig."""
    errors: list[str] = []
    warnings: list[str] = []

    bound_errors = bounds_validate(config)
    errors.extend(bound_errors)

    if config.bracket_exit is not None:
        be = config.bracket_exit
        if be.rr_ratio > 1.0 and be.target_ticks <= be.stop_ticks:
            errors.append(
                f"target_ticks ({be.target_ticks}) must be > stop_ticks ({be.stop_ticks}) when rr_ratio={be.rr_ratio} > 1.0"
            )
        if be.stop_ticks == be.target_ticks:
            warnings.append(
                f"stop_ticks == target_ticks ({be.stop_ticks}): R:R will always be 1.0, which fails the >1.5 fitness threshold"
            )

    has_exit = (config.bracket_exit is not None) or (config.level_exit is not None)
    if not has_exit:
        errors.append("Must have at least one exit: bracket_exit or level_exit")

    if config.timing_filter == TimingFilter.MIDDAY_BLOCK_EXCLUDED:
        warnings.append("TimingFilter.MIDDAY_BLOCK_EXCLUDED excludes 10:30-13:00 ET — verify sufficient trade opportunities remain")

    if config.level_target == LevelTarget.VPOC:
        warnings.append("LevelTarget.VPOC targets a single price level — may produce <30 trades, triggering rejection")

    if config.level_exit is not None and config.level_exit.trail_to_zone_boundary and config.bracket_exit is None:
        warnings.append("LevelExit.trail_to_zone_boundary without BracketExit stop: no hard downside protection")

    if config.time_exit.max_bars_in_trade <= 0:
        errors.append(f"time_exit.max_bars_in_trade must be > 0, got {config.time_exit.max_bars_in_trade}")

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


def suggest_fix(errors: list[str]) -> dict[str, Any]:
    """For each error, suggest the nearest valid value."""
    suggestions: dict[str, Any] = {}
    for error in errors:
        if "target_ticks" in error and "stop_ticks" in error:
            suggestions["target_ticks"] = "Set target_ticks = stop_ticks * rr_ratio (e.g., stop=20, rr=2.0 → target=40)"
        elif "outside bounds" in error:
            param = error.split()[0]
            bounds_str = error.split("[")[1].rstrip("]") if "[" in error else ""
            suggestions[param] = f"Set {param} within bounds [{bounds_str}]"
        elif "exit" in error.lower():
            suggestions["exit"] = "Add bracket_exit: {stop_ticks: 20, target_ticks: 40, rr_ratio: 2.0}"
        elif "time_exit.max_bars_in_trade" in error:
            suggestions["max_bars_in_trade"] = "Set max_bars_in_trade to a positive integer within bounds [5, 60]"
    return suggestions


__all__ = ["ValidationResult", "validate", "suggest_fix"]
