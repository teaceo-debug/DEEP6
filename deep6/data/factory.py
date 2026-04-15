"""Feed factory — dispatch by ``config.data_source``.

Phase 14 (D-07): choose Databento Live or Rithmic market data at startup
without touching the downstream bar-builder / signal pipeline.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deep6.config import Config


def create_feed(source: str, config: "Config") -> Any:
    """Return the live feed adapter selected by ``source``.

    Args:
        source: One of ``"databento"`` or ``"rithmic"``.
        config: DEEP6 Config.

    Returns:
        For ``databento``: a ``DatabentoLiveFeed`` instance with ``.start(state)``.
        For ``rithmic``: a coroutine returning a connected ``RithmicClient``.
        ``__main__.py`` dispatches on the returned type.
    """
    if source == "databento":
        from deep6.data.databento_live import DatabentoLiveFeed

        # Phase 14 (D-01): prefer GLBX.MDP3-scoped key; fall back to primary.
        key = config.databento_live_key()
        if not key:
            raise RuntimeError(
                "DATABENTO_API_KEY_GLBX (or DATABENTO_API_KEY) must be set "
                "for source=databento"
            )
        return DatabentoLiveFeed(api_key=key)
    if source == "rithmic":
        from deep6.data.rithmic import connect_rithmic

        return connect_rithmic(config)
    raise ValueError(f"Unknown data source: {source}")
