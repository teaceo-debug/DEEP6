"""FlashAlpha client — pre-computed dealer-state analytics for QQQ/NQ."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from flashalpha import FlashAlpha

from nq_atlas.state import AtlasState

logger = logging.getLogger(__name__)


class FlashAlphaClient:
    """Wraps FlashAlpha SDK. SDK is synchronous — runs in executor."""

    def __init__(self, api_key: str, symbol: str = "QQQ") -> None:
        self._fa = FlashAlpha(api_key)
        self._symbol = symbol

    async def _run(self, fn, *args) -> Any:
        """Run sync SDK call in executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, fn, *args)

    async def get_all(self) -> dict[str, Any]:
        """Fetch all key endpoints in parallel. Returns consolidated dict."""
        sym = self._symbol
        try:
            summary, zero_dte, levels, vex, chex = await asyncio.gather(
                self._run(self._fa.exposure_summary, sym),
                self._run(self._fa.zero_dte, sym),
                self._run(self._fa.exposure_levels, sym),
                self._run(self._fa.vex, sym),
                self._run(self._fa.chex, sym),
            )
            return {
                "summary": summary,
                "zero_dte": zero_dte,
                "levels": levels,
                "vex": vex,
                "chex": chex,
                "symbol": sym,
                "ts": time.time(),
            }
        except Exception as e:
            logger.error("FlashAlpha get_all error: %s", e)
            raise

    async def poll_loop(self, state: AtlasState, interval: int) -> None:
        """Async loop: fetch FlashAlpha data every interval seconds."""
        while True:
            try:
                data = await self.get_all()
                state.flashalpha = data
                state.last_fa_ts = time.time()
                logger.info(
                    "FlashAlpha updated: regime=%s flip=%.2f net_gex=%.0fM",
                    data["summary"].get("regime", "?"),
                    data["summary"].get("gamma_flip", 0),
                    (data["summary"].get("exposures", {}).get("net_gex", 0) or 0) / 1e6,
                )
            except Exception as e:
                logger.error("FlashAlpha poll_loop error: %s", e)
                state.log_error("flashalpha", str(e))
            await asyncio.sleep(interval)


__all__ = ["FlashAlphaClient"]
