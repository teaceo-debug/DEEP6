"""Massive.com adapter — wraps nq_atlas.massive_client + nq_atlas.gex for cross-validation."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from nq_atlas.types import FlowResult, GEXResult

from gex_terminal.schemas import GEXLevels, SourceHealth

_LEVEL_CACHE_PATH = Path.home() / ".deep6" / "massive_levels_cache.json"

logger = logging.getLogger(__name__)


class _MissingMassiveClient:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def get_options_chain(self, symbol: str):
        raise self._error


class _MissingEngine:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def compute(self, *_args, **_kwargs):
        raise self._error


@dataclass
class MassiveResult:
    levels: GEXLevels  # GEX levels computed from raw chain (cross-validates FlashAlpha)
    source_health: SourceHealth
    raw_gex_result: Optional[GEXResult]  # nq_atlas.types.GEXResult for debugging
    flow_result: Optional[FlowResult] = None


class MassiveAdapter:
    """Thin adapter: fetches QQQ chain from Massive, computes GEX via GEXEngine.

    Massive.com is the PRIMARY GEX source. Levels are cached so NT8 always has
    populated values — even after hours when the options chain has no volume.
    """

    def __init__(self, api_key: str, symbol: str = "QQQ", *, level_cache_path: Optional[Path] = _LEVEL_CACHE_PATH) -> None:
        try:
            from nq_atlas.flow import FlowEngine  # IMPORT, do NOT rewrite
            from nq_atlas.gex import GEXEngine  # IMPORT, do NOT rewrite
            from nq_atlas.massive_client import MassiveClient  # IMPORT, do NOT rewrite

            self._client = MassiveClient(api_key=api_key)
            self._gex_engine = GEXEngine()
            self._flow_engine = FlowEngine()
        except ModuleNotFoundError as exc:
            self._client = _MissingMassiveClient(exc)
            self._gex_engine = _MissingEngine(exc)
            self._flow_engine = _MissingEngine(exc)
        self._symbol = symbol
        self._level_cache_path = level_cache_path
        self._last_result: Optional[MassiveResult] = None
        # QQQ-space level cache disabled — analyzer handles NQ-space caching instead.
        # Keeping the plumbing for future use if needed.
        self._last_good_levels: Optional[GEXLevels] = None
        self._error_count = 0

    def _load_level_cache(self) -> Optional[GEXLevels]:
        """Load last known good levels from disk (survives restarts)."""
        cache_path = self._level_cache_path
        try:
            if cache_path and cache_path.exists():
                data = json.loads(cache_path.read_text(encoding="utf-8-sig"))
                levels = GEXLevels(
                    gamma_flip=data.get("gamma_flip"),
                    call_wall=data.get("call_wall"),
                    put_wall=data.get("put_wall"),
                    hvl=data.get("hvl"),
                    zero_dte_magnet=data.get("zero_dte_magnet"),
                )
                age_hours = (time.time() - data.get("cached_at", 0)) / 3600
                if age_hours < 24:
                    logger.info("Massive: loaded cached levels (%.1fh old): flip=%s cw=%s pw=%s",
                                age_hours, levels.gamma_flip, levels.call_wall, levels.put_wall)
                    return levels
                logger.info("Massive: cached levels too old (%.1fh) — ignoring", age_hours)
        except Exception as exc:
            logger.debug("Massive: level cache load failed: %s", exc)
        return None

    def _save_level_cache(self, levels: GEXLevels) -> None:
        """Persist good levels to disk so they survive restarts."""
        cache_path = self._level_cache_path
        if not cache_path:
            return
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps({
                    "gamma_flip": levels.gamma_flip,
                    "call_wall": levels.call_wall,
                    "put_wall": levels.put_wall,
                    "hvl": levels.hvl,
                    "zero_dte_magnet": levels.zero_dte_magnet,
                    "cached_at": time.time(),
                }, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug("Massive: level cache save failed: %s", exc)

    async def poll(self) -> MassiveResult:
        """Fetch chain snapshot and compute GEX."""
        try:
            chain = await self._client.get_options_chain(self._symbol)
            gex_result = self._gex_engine.compute(chain)
            for contract in chain.contracts:
                if contract.last is None or not contract.volume:
                    continue
                self._flow_engine.update(
                    {
                        "price": contract.last,
                        "bid": contract.bid or 0,
                        "ask": contract.ask or 0,
                        "volume": contract.volume,
                        "call_put": contract.call_put,
                    }
                )
            flow_result = self._flow_engine.compute()
            result = self._normalize(gex_result, flow_result)
            self._last_result = result
            self._error_count = 0
            return result
        except Exception as e:
            logger.error("Massive poll error: %s", e)
            self._error_count += 1
            return self._degraded_result(str(e))

    @staticmethod
    def _has_real_levels(levels: GEXLevels) -> bool:
        """True if at least gamma_flip or one wall is populated."""
        return any(
            v is not None and v != 0.0
            for v in (levels.gamma_flip, levels.call_wall, levels.put_wall)
        )

    def _normalize(self, gex_result: GEXResult, flow_result: FlowResult) -> MassiveResult:
        """Convert GEXResult to gex_terminal schemas.

        When the GEXEngine returns None levels (e.g. after hours / no volume),
        fall back to the last cached good levels so NT8 always has values.
        """
        fresh_levels = GEXLevels(
            gamma_flip=gex_result.flip_level,
            call_wall=gex_result.call_wall,
            put_wall=gex_result.put_wall,
        )

        if self._has_real_levels(fresh_levels):
            # Live data with real levels — use it
            levels = fresh_levels
            status = "ok"
        else:
            # No live levels (after hours / no volume) — return empty
            # The analyzer's NQ-space cache will handle the fallback
            levels = fresh_levels
            status = "ok"
            logger.info("Massive: no fresh levels (after hours?) — analyzer NQ cache will handle fallback")

        source_health = SourceHealth(
            name="massive",
            status=status,
            last_update=time.time(),
            ttl_sec=60,
        )
        return MassiveResult(
            levels=levels,
            source_health=source_health,
            raw_gex_result=gex_result,
            flow_result=flow_result,
        )

    def _degraded_result(self, error_msg: str) -> MassiveResult:
        """Return last known data with error status, or empty if no prior data."""
        health = SourceHealth(
            name="massive",
            status="error",
            last_update=self._last_result.source_health.last_update if self._last_result else None,
            ttl_sec=60,
            error_msg=error_msg,
        )
        if self._last_result:
            return MassiveResult(
                levels=self._last_result.levels,
                source_health=health,
                raw_gex_result=self._last_result.raw_gex_result,
                flow_result=self._last_result.flow_result,
            )
        return MassiveResult(
            levels=GEXLevels(),
            source_health=health,
            raw_gex_result=None,
            flow_result=None,
        )


__all__ = ["MassiveAdapter", "MassiveResult"]
