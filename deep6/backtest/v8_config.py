"""V8-specific optimization configuration for the backtest discovery loop."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from deep6.backtest.param_bounds import PARAM_BOUNDS, ParamBound

V8_PARENT0_PATH = Path("data/backtests/v8_parent0.json")

V8_DEFAULTS: dict[str, Any] = {
    "BiasLongThreshold": 0.60,
    "BiasShortThreshold": -0.60,
    "MinArrowConfluence": 4,
    "MinExhaustionStrength": 0.60,
    "MaxSignalsPerSession": 15,
    "BiasLookback": 3,
    "ShowClassicAbsorption": 0,
    "ShowPassiveAbsorption": 0,
    "ShowStoppingVolume": 0,
    "ShowEffortVsResult": 0,
    "ShowZeroPrint": 0,
    "ShowExhaustionPrint": 1,
    "ShowThinPrint": 0,
    "ShowFatPrint": 0,
    "ShowFadingMomentum": 0,
    "ShowBidAskFade": 1,
}

V8_PARAM_BOUNDS: dict[str, tuple[float, float]] = {
    "BiasLongThreshold": (0.40, 0.85),
    "BiasShortThreshold": (-0.85, -0.40),
    "MinArrowConfluence": (1, 7),
    "MinExhaustionStrength": (0.30, 0.90),
    "MaxSignalsPerSession": (5, 30),
    "BiasLookback": (1, 10),
    "ShowClassicAbsorption": (0, 1),
    "ShowPassiveAbsorption": (0, 1),
    "ShowStoppingVolume": (0, 1),
    "ShowEffortVsResult": (0, 1),
    "ShowZeroPrint": (0, 1),
    "ShowExhaustionPrint": (0, 1),
    "ShowThinPrint": (0, 1),
    "ShowFatPrint": (0, 1),
    "ShowFadingMomentum": (0, 1),
    "ShowBidAskFade": (0, 1),
}

V8_CONVERGENCE = {
    "patience": 20,
    "max_iterations": 200,
    "max_hours": 4,
}

_V8_DESCRIPTIONS: dict[str, str] = {
    "BiasLongThreshold": "Bias score threshold required to render LONG state",
    "BiasShortThreshold": "Bias score threshold required to render SHORT state",
    "MinArrowConfluence": "Minimum category count before raw arrows render",
    "MinExhaustionStrength": "Minimum exhaustion strength required to render marker",
    "MaxSignalsPerSession": "Cap on rendered V8 signals per session",
    "BiasLookback": "Rendered-signal lookback window for bias box scoring",
    "ShowClassicAbsorption": "Binary toggle for ABS-01 marker visibility",
    "ShowPassiveAbsorption": "Binary toggle for ABS-02 marker visibility",
    "ShowStoppingVolume": "Binary toggle for ABS-03 marker visibility",
    "ShowEffortVsResult": "Binary toggle for ABS-04 marker visibility",
    "ShowZeroPrint": "Binary toggle for EXH-01 marker visibility",
    "ShowExhaustionPrint": "Binary toggle for EXH-02 marker visibility",
    "ShowThinPrint": "Binary toggle for EXH-03 marker visibility",
    "ShowFatPrint": "Binary toggle for EXH-04 marker visibility",
    "ShowFadingMomentum": "Binary toggle for EXH-05 marker visibility",
    "ShowBidAskFade": "Binary toggle for EXH-06 marker visibility",
}


def _bound_dtype(name: str) -> type:
    if name.startswith("Show") or name in {
        "MinArrowConfluence",
        "MaxSignalsPerSession",
        "BiasLookback",
    }:
        return int
    return float


def _build_v8_param_specs() -> dict[str, ParamBound]:
    specs: dict[str, ParamBound] = {}
    for name, (min_val, max_val) in V8_PARAM_BOUNDS.items():
        dtype = _bound_dtype(name)
        default = V8_DEFAULTS[name]
        specs[name] = ParamBound(
            name=name,
            min_val=min_val,
            max_val=max_val,
            default=default,
            dtype=dtype,
            description=_V8_DESCRIPTIONS[name],
        )
    return specs


V8_PARAM_SPECS: dict[str, ParamBound] = _build_v8_param_specs()
V8_PARAM_REGISTRY: dict[str, ParamBound] = {**PARAM_BOUNDS, **V8_PARAM_SPECS}


def get_v8_param_registry() -> dict[str, ParamBound]:
    """Return shared backtest bounds plus V8-specific bounds."""
    return dict(V8_PARAM_REGISTRY)


def get_v8_bounds(name: str | None = None) -> ParamBound | dict[str, ParamBound]:
    """Return one V8 bound or the full V8-specific registry."""
    if name is None:
        return dict(V8_PARAM_SPECS)
    if name not in V8_PARAM_SPECS:
        raise KeyError(f"Unknown V8 parameter: {name}")
    return V8_PARAM_SPECS[name]


def _normalize_value(name: str, value: Any) -> int | float:
    bound = V8_PARAM_SPECS[name]
    if bound.dtype is int:
        return int(round(float(value)))
    return float(value)


def validate_v8_params(params: Mapping[str, Any]) -> list[str]:
    """Validate a flat V8 parameter payload against local bounds."""
    errors: list[str] = []
    for name, bound in V8_PARAM_SPECS.items():
        if name not in params:
            continue
        value = _normalize_value(name, params[name])
        if value < bound.min_val or value > bound.max_val:
            errors.append(
                f"{name} {value} outside bounds [{bound.min_val}, {bound.max_val}]"
            )
    return errors


def clamp_v8_params(params: Mapping[str, Any]) -> dict[str, Any]:
    """Clamp a flat V8 parameter payload into the valid search space."""
    clamped = copy.deepcopy(dict(params))
    for name, bound in V8_PARAM_SPECS.items():
        if name not in clamped:
            continue
        value = _normalize_value(name, clamped[name])
        value = max(bound.min_val, min(bound.max_val, value))
        clamped[name] = int(value) if bound.dtype is int else float(value)
    return clamped


def load_v8_parent0(path: str | Path = V8_PARENT0_PATH) -> dict[str, Any]:
    """Load the parent-0 baseline snapshot used to seed V8 optimization."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def convergence_reached(
    plateau_iterations: int,
    total_iterations: int,
    elapsed_hours: float,
    config: Mapping[str, int] = V8_CONVERGENCE,
) -> bool:
    """Evaluate early-stop conditions without mutating the loop."""
    return bool(
        plateau_iterations > config["patience"]
        or total_iterations >= config["max_iterations"]
        or elapsed_hours >= config["max_hours"]
    )


__all__ = [
    "V8_CONVERGENCE",
    "V8_DEFAULTS",
    "V8_PARAM_BOUNDS",
    "V8_PARAM_REGISTRY",
    "V8_PARAM_SPECS",
    "V8_PARENT0_PATH",
    "clamp_v8_params",
    "convergence_reached",
    "get_v8_bounds",
    "get_v8_param_registry",
    "load_v8_parent0",
    "validate_v8_params",
]
