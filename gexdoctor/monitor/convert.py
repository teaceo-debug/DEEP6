from __future__ import annotations

import logging
from typing import Literal

log = logging.getLogger(__name__)

__all__ = [
    "compute_nq_qqq_factor",
    "compute_nq_ndx_basis",
    "qqq_to_nq",
    "ndx_to_nq",
    "normalize_level",
]

SymbolType = Literal["NQ", "QQQ", "NDX", "SPX"]


def compute_nq_qqq_factor(nq_spot: float, qqq_spot: float) -> float:
    """Returns NQ/QQQ price ratio. Used to convert QQQ levels to NQ.

    Formula: factor = nq_spot / qqq_spot
    Usage: nq_level = qqq_level * factor
    """
    if qqq_spot == 0.0 or qqq_spot is None:
        raise ValueError(f"qqq_spot must be non-zero, got {qqq_spot}")
    factor = nq_spot / qqq_spot
    log.debug("nq_qqq_factor=%.4f (NQ=%.2f, QQQ=%.2f)", factor, nq_spot, qqq_spot)
    return factor


def compute_nq_ndx_basis(nq_spot: float, ndx_spot: float) -> float:
    """Returns NQ - NDX basis (futures premium over cash index).

    Formula: basis = nq_spot - ndx_spot
    Usage: nq_level = ndx_level + basis
    """
    basis = nq_spot - ndx_spot
    log.debug("nq_ndx_basis=%.2f (NQ=%.2f, NDX=%.2f)", basis, nq_spot, ndx_spot)
    return basis


def qqq_to_nq(qqq_level: float, nq_qqq_factor: float) -> float:
    """Convert a QQQ price level to NQ equivalent."""
    result = round(qqq_level * nq_qqq_factor, 2)
    log.debug("qqq_to_nq: QQQ=%.2f -> NQ=%.2f (factor=%.4f)", qqq_level, result, nq_qqq_factor)
    return result


def ndx_to_nq(ndx_level: float, nq_ndx_basis: float) -> float:
    """Convert an NDX index level to NQ futures equivalent."""
    result = round(ndx_level + nq_ndx_basis, 2)
    log.debug("ndx_to_nq: NDX=%.2f -> NQ=%.2f (basis=%.2f)", ndx_level, result, nq_ndx_basis)
    return result


def normalize_level(
    level: float,
    symbol: SymbolType,
    nq_spot: float,
    qqq_spot: float | None = None,
    ndx_spot: float | None = None,
) -> float:
    """Normalize a price level to NQ futures price.

    Dispatch rules:
    - NQ: return as-is
    - QQQ: multiply by NQ/QQQ factor (requires qqq_spot)
    - NDX: add NQ-NDX basis (requires ndx_spot)
    - SPX: REJECTED — SPX is regime context only, not convertible to NQ price
    """
    if symbol == "NQ":
        return level
    if symbol == "SPX":
        raise ValueError(
            "SPX levels cannot be converted to NQ price — "
            "use SPX data for regime context only"
        )
    if symbol == "QQQ":
        if qqq_spot is None:
            raise ValueError("qqq_spot required for QQQ→NQ conversion")
        factor = compute_nq_qqq_factor(nq_spot, qqq_spot)
        return qqq_to_nq(level, factor)
    if symbol == "NDX":
        if ndx_spot is None:
            raise ValueError("ndx_spot required for NDX→NQ conversion")
        basis = compute_nq_ndx_basis(nq_spot, ndx_spot)
        return ndx_to_nq(level, basis)
    raise ValueError(f"Unknown symbol: {symbol!r}")
