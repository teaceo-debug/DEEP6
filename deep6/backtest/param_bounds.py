from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParamBound:
    name: str
    min_val: float
    max_val: float
    default: float
    dtype: type  # int or float
    description: str


PARAM_BOUNDS: dict[str, ParamBound] = {
    # Entry params
    "level_approach_ticks": ParamBound("level_approach_ticks", 2, 20, 5, int, "Max ticks from level to trigger entry"),
    "confirmation_threshold": ParamBound("confirmation_threshold", 0.3, 0.9, 0.6, float, "Signal strength threshold for confirmation"),
    "multi_level_distance_ticks": ParamBound("multi_level_distance_ticks", 2, 50, 10, int, "Max ticks between levels for confluence"),
    # Exit params
    "stop_ticks": ParamBound("stop_ticks", 5, 100, 20, int, "Stop loss in ticks"),
    "target_ticks": ParamBound("target_ticks", 5, 200, 40, int, "Take profit in ticks"),
    "max_bars_in_trade": ParamBound("max_bars_in_trade", 5, 60, 30, int, "Max bars before time exit"),
    "rr_ratio": ParamBound("rr_ratio", 0.5, 5.0, 2.0, float, "Reward to risk ratio"),
    # Volume Profile params
    "lvn_threshold": ParamBound("lvn_threshold", 0.10, 0.50, 0.30, float, "Volume fraction below which a bin is LVN"),
    "hvn_threshold": ParamBound("hvn_threshold", 1.20, 3.00, 1.70, float, "Volume fraction above which a bin is HVN"),
    "zone_decay_rate": ParamBound("zone_decay_rate", 0.005, 0.10, 0.02, float, "Zone score decay per bar"),
    "min_zone_ticks": ParamBound("min_zone_ticks", 1, 10, 2, int, "Minimum zone width in ticks"),
    "max_zones": ParamBound("max_zones", 5, 100, 50, int, "Maximum number of active zones"),
    # Depth Radar params
    "wall_min_size": ParamBound("wall_min_size", 20, 200, 50, int, "Minimum order size to classify as wall"),
    "wall_stale_sec": ParamBound("wall_stale_sec", 30, 300, 90, float, "Seconds before wall is pruned as stale"),
    "spoof_confidence_threshold": ParamBound("spoof_confidence_threshold", 0.3, 0.9, 0.5, float, "Model confidence below which rule-based fallback applies"),
    "glow_threshold": ParamBound("glow_threshold", 50, 500, 100, int, "Size threshold for visual glow effect"),
}


def _get_child(container: Any, name: str) -> Any:
    if isinstance(container, dict):
        return container.get(name)
    return getattr(container, name, None)


def _set_child(container: Any, name: str, value: Any) -> None:
    if isinstance(container, dict):
        container[name] = value
    else:
        setattr(container, name, value)


def _clamp_value(value: Any, bound: ParamBound) -> Any:
    clamped = max(bound.min_val, min(bound.max_val, value))
    if bound.dtype is int:
        return int(clamped)
    return float(clamped)


def _maybe_check_value(errors: list[str], param: str, value: Any) -> None:
    bound = PARAM_BOUNDS[param]
    if value is None:
        return
    if value < bound.min_val or value > bound.max_val:
        errors.append(f"{param} {value} outside bounds [{bound.min_val}, {bound.max_val}]")


def validate_config(config: Any) -> list[str]:
    """Validate a StrategyConfig-style object against parameter bounds."""
    errors: list[str] = []

    bracket_exit = _get_child(config, "bracket_exit")
    if bracket_exit is not None:
        for param in ("stop_ticks", "target_ticks", "rr_ratio"):
            if hasattr(bracket_exit, param) or isinstance(bracket_exit, dict) and param in bracket_exit:
                _maybe_check_value(errors, param, _get_child(bracket_exit, param))

    time_exit = _get_child(config, "time_exit")
    if time_exit is not None:
        if hasattr(time_exit, "max_bars_in_trade") or isinstance(time_exit, dict) and "max_bars_in_trade" in time_exit:
            _maybe_check_value(errors, "max_bars_in_trade", _get_child(time_exit, "max_bars_in_trade"))

    for param in ("multi_level_distance_ticks", "lvn_threshold", "hvn_threshold", "zone_decay_rate", "min_zone_ticks", "max_zones", "wall_min_size", "wall_stale_sec", "spoof_confidence_threshold", "glow_threshold"):
        if hasattr(config, param) or isinstance(config, dict) and param in config:
            _maybe_check_value(errors, param, _get_child(config, param))

    return errors


def clamp_config(config: Any) -> Any:
    """Clamp all out-of-bounds parameters to their nearest valid value."""
    data = copy.deepcopy(config.model_dump() if hasattr(config, "model_dump") else config)

    bracket_exit = data.get("bracket_exit") if isinstance(data, dict) else None
    if isinstance(bracket_exit, dict):
        for param in ("stop_ticks", "target_ticks", "rr_ratio"):
            if param in bracket_exit:
                bracket_exit[param] = _clamp_value(bracket_exit[param], PARAM_BOUNDS[param])

    time_exit = data.get("time_exit") if isinstance(data, dict) else None
    if isinstance(time_exit, dict) and "max_bars_in_trade" in time_exit:
        time_exit["max_bars_in_trade"] = _clamp_value(time_exit["max_bars_in_trade"], PARAM_BOUNDS["max_bars_in_trade"])

    for param in ("multi_level_distance_ticks", "lvn_threshold", "hvn_threshold", "zone_decay_rate", "min_zone_ticks", "max_zones", "wall_min_size", "wall_stale_sec", "spoof_confidence_threshold", "glow_threshold"):
        if param in data:
            data[param] = _clamp_value(data[param], PARAM_BOUNDS[param])

    return type(config).model_validate(data) if hasattr(type(config), "model_validate") else data


def get_bounds(param_name: str) -> ParamBound:
    """Get bounds for a specific parameter."""
    if param_name not in PARAM_BOUNDS:
        raise KeyError(f"Unknown parameter: {param_name}")
    return PARAM_BOUNDS[param_name]


__all__ = ["ParamBound", "PARAM_BOUNDS", "validate_config", "clamp_config", "get_bounds"]
