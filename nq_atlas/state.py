from __future__ import annotations

import time
from typing import Any, Optional

from nq_atlas.types import (
    BiasOutput,
    ChainSnapshot,
    FlowResult,
    GEXResult,
    NQLevels,
    VannaCharmResult,
)


class AtlasState:
    """Mutable shared state for the NQ ATLAS pipeline."""

    def __init__(self, refresh_interval_sec: int = 10, ai_refresh_sec: int = 60) -> None:
        self._refresh_interval = refresh_interval_sec
        self._ai_refresh = ai_refresh_sec
        self.chain: Optional[ChainSnapshot] = None
        self.spots: dict[str, float] = {}
        self.gex: Optional[GEXResult] = None
        self.vanna_charm: Optional[VannaCharmResult] = None
        self.flow: Optional[FlowResult] = None
        self.nq_levels: Optional[NQLevels] = None
        self.bias: Optional[BiasOutput] = None
        self.flashalpha: Optional[dict] = None
        self.last_chain_ts: Optional[float] = None
        self.last_ai_ts: Optional[float] = None
        self.last_fa_ts: Optional[float] = None
        self.started_at: float = time.monotonic()
        self.errors: list[dict[str, Any]] = []

    def degraded(self) -> bool:
        """True if any critical data is missing or stale."""
        if self.chain is None:
            return True
        if self.last_chain_ts is None:
            return True
        if time.time() - self.last_chain_ts > (self._refresh_interval * 2):
            return True
        if self.last_ai_ts is not None:
            if time.time() - self.last_ai_ts > (self._ai_refresh * 4):
                return True
        return False

    def snapshot_dict(self) -> dict[str, Any]:
        return {
            "spots": self.spots,
            "gex": self.gex.model_dump() if self.gex else None,
            "vanna_charm": self.vanna_charm.model_dump() if self.vanna_charm else None,
            "flow": self.flow.model_dump() if self.flow else None,
            "nq_levels": self.nq_levels.model_dump() if self.nq_levels else None,
            "bias": self.bias.model_dump(mode="json") if self.bias else None,
            "flashalpha": self.flashalpha,
            "last_chain_ts": self.last_chain_ts,
            "last_ai_ts": self.last_ai_ts,
            "last_fa_ts": self.last_fa_ts,
            "degraded": self.degraded(),
            "uptime_sec": int(time.monotonic() - self.started_at),
            "errors": self.errors[-5:],
        }

    def log_error(self, source: str, message: str) -> None:
        self.errors.append({"ts": time.time(), "source": source, "msg": message})
        if len(self.errors) > 20:
            self.errors = self.errors[-20:]


__all__ = ["AtlasState"]
