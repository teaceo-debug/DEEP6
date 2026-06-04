from __future__ import annotations

from nq_atlas.types import GEXResult, NQLevels


def map_qqq_to_nq(qqq_level: float, qqq_spot: float, nq_spot: float) -> float:
    """Convert a QQQ price level to an NQ-equivalent level."""
    if qqq_spot <= 0:
        raise ValueError(f"qqq_spot must be positive, got {qqq_spot}")
    return qqq_level / qqq_spot * nq_spot


def map_chain_levels(gex: GEXResult, qqq_spot: float, nq_spot: float) -> NQLevels:
    """Convert all GEX levels from QQQ to NQ points."""

    def _convert(level: float | None) -> float | None:
        if level is None:
            return None
        return map_qqq_to_nq(level, qqq_spot, nq_spot)

    return NQLevels(
        gex_flip=_convert(gex.flip_level),
        call_wall=_convert(gex.call_wall),
        put_wall=_convert(gex.put_wall),
        support=_convert(gex.put_wall),
        resistance=_convert(gex.call_wall),
    )


__all__ = ["map_chain_levels", "map_qqq_to_nq"]
