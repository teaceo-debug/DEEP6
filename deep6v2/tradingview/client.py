"""TradingView MCP client wrapper — graceful degradation when TV not running."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChartState:
    """Snapshot of the current TradingView chart configuration."""

    symbol: str
    timeframe: str
    indicators: list[str]


class TradingViewClient:
    """Wrapper around TradingView MCP tools for programmatic access.

    All methods return ``None`` / ``False`` when TradingView Desktop is not
    connected, ensuring the rest of the system degrades gracefully.
    """

    def __init__(self) -> None:
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        """Attempt to connect to TradingView via MCP.

        Returns ``True`` on success, ``False`` if TradingView Desktop is not
        running or the CDP bridge is unreachable.
        """
        # In practice this would probe the CDP endpoint via tv_health_check.
        # For now, always returns False (graceful degradation).
        self._connected = False
        return False

    def get_chart_state(self) -> ChartState | None:
        """Current chart symbol, timeframe, and active indicators."""
        if not self._connected:
            return None
        return None  # pragma: no cover — real implementation via MCP

    def get_ohlcv(self, count: int = 100) -> list[dict] | None:
        """Fetch OHLCV bar data from the visible chart."""
        if not self._connected:
            return None
        return None  # pragma: no cover

    def get_study_values(self) -> dict | None:
        """Read current indicator values from the data window."""
        if not self._connected:
            return None
        return None  # pragma: no cover

    def capture_screenshot(self, filename: str | None = None) -> str | None:
        """Capture chart screenshot. Returns file path or ``None``."""
        if not self._connected:
            return None
        return None  # pragma: no cover

    def inject_pine_script(self, source: str) -> bool:
        """Inject Pine Script source into the TradingView editor."""
        if not self._connected:
            return False
        return False  # pragma: no cover


__all__ = ["ChartState", "TradingViewClient"]
