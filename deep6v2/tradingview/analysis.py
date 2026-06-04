"""Visual analysis integration — screenshot on significant signals."""

from __future__ import annotations

from deep6v2.tradingview.client import TradingViewClient
from deep6v2.types.scoring import ScorerResult, SignalTier


class VisualAnalysis:
    """Captures TradingView screenshots for high-tier signals and trade reports."""

    def __init__(self, client: TradingViewClient | None = None) -> None:
        self._client = client or TradingViewClient()

    def on_score(self, result: ScorerResult) -> str | None:
        """Capture screenshot on Type A or B signals. Returns path or ``None``."""
        if result.tier not in (SignalTier.TYPE_A, SignalTier.TYPE_B):
            return None
        if not self._client.is_connected:
            return None
        return self._client.capture_screenshot(f"signal_{result.tier.value}")

    def generate_trade_report(self, session_id: str) -> list[str]:
        """Capture multi-timeframe screenshots for trade review."""
        if not self._client.is_connected:
            return []
        screenshots: list[str] = []
        for tf in ["1", "5", "15", "60"]:
            path = self._client.capture_screenshot(f"report_{session_id}_{tf}m")
            if path:
                screenshots.append(path)
        return screenshots


__all__ = ["VisualAnalysis"]
