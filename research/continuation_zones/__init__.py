"""Continuation zones research package."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "CACHE_PATH",
    "END_DATE",
    "RTH_END",
    "RTH_START",
    "SCHEMA",
    "START_DATE",
    "STYPE_IN",
    "SYMBOL",
    "apply_rth_filter",
    "build_ohlcv",
    "get_nq_5m",
    "get_nq_15m",
    "load_1m_bars",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    data_loader = import_module(".data_loader", __name__)
    return getattr(data_loader, name)
