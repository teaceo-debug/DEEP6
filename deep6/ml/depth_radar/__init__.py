"""DepthRadar ML components."""

from __future__ import annotations

from typing import Any


__all__ = ["EpisodeLabeler", "MBOWallEngine"]


def __getattr__(name: str) -> Any:
    if name == "EpisodeLabeler":
        from deep6.ml.depth_radar.episode_labeler import EpisodeLabeler

        return EpisodeLabeler
    if name == "MBOWallEngine":
        from deep6.ml.depth_radar.mbo_wall_engine import MBOWallEngine

        return MBOWallEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
