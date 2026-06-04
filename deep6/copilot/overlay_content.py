"""Bridge between copilot engines and overlay display.

Routes formatted content from NarrativeEngine and TradeCallEngine
into CopilotOverlay update methods.  Manages narrative rotation,
trade call auto-expiry, and periodic source status refresh.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import TYPE_CHECKING, Any

from .types import CalendarEvent, DataSourceStatus, TradeCall

if TYPE_CHECKING:
    from .adapters.calendar import EconomicCalendarAdapter
    from .freshness import FreshnessTracker
    from .narrative import NarrativeEngine
    from .overlay import CopilotOverlay
    from .trade_calls import TradeCallEngine

logger = logging.getLogger(__name__)

_MAX_NARRATIVE_HISTORY = 3
_STATUS_REFRESH_SEC = 5.0
_TRADE_CALL_EXPIRY_SEC = 600  # 10 minutes
_UPCOMING_EVENTS_MINUTES = 120
_DEFAULT_NARRATIVE_MAX_CHARS = 300


class OverlayContentRenderer:
    """Format and route engine outputs to the CopilotOverlay.

    Subscribes to NarrativeEngine completion callbacks and
    TradeCallEngine trade-call callbacks, formatting content
    before passing it to the overlay's thread-safe update methods.

    Parameters
    ----------
    overlay:
        CopilotOverlay instance whose ``update_*`` methods receive content.
    narrative_engine:
        NarrativeEngine that fires ``on_narrative_complete`` callbacks.
    trade_engine:
        TradeCallEngine that fires ``on_trade_call`` callbacks.
    freshness_tracker:
        FreshnessTracker for periodic source-health polling.
    calendar_adapter:
        EconomicCalendarAdapter for upcoming event countdowns.
        May be *None* if calendar data is unavailable.
    """

    def __init__(
        self,
        overlay: CopilotOverlay,
        narrative_engine: NarrativeEngine,
        trade_engine: TradeCallEngine,
        freshness_tracker: FreshnessTracker,
        calendar_adapter: EconomicCalendarAdapter | None = None,
    ) -> None:
        self._overlay = overlay
        self._narrative_engine = narrative_engine
        self._trade_engine = trade_engine
        self._freshness = freshness_tracker
        self._calendar = calendar_adapter

        self._narrative_history: deque[str] = deque(maxlen=_MAX_NARRATIVE_HISTORY)
        self._status_task: asyncio.Task[None] | None = None
        self._clear_task: asyncio.Task[None] | None = None
        self._running = False

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Register callbacks and start the periodic status refresh."""
        if self._running:
            return
        self._running = True
        self._narrative_engine.on_narrative_complete(self._on_narrative_complete)
        self._trade_engine.on_trade_call(self._on_trade_call)
        self._status_task = asyncio.create_task(
            self._status_refresh_loop(), name="overlay-status-refresh",
        )
        logger.info("OverlayContentRenderer started")

    async def stop(self) -> None:
        """Cancel background tasks.  Does not unregister callbacks."""
        self._running = False
        for task in (self._status_task, self._clear_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._status_task = None
        self._clear_task = None
        logger.info("OverlayContentRenderer stopped")

    # ── Callbacks ────────────────────────────────────────────────────────

    def _on_narrative_complete(self, text: str) -> None:
        """Handle a completed narrative from the engine."""
        formatted = self._format_narrative(text)
        self._narrative_history.append(formatted)
        self._overlay.update_narrative(formatted)

    def _on_trade_call(self, call: TradeCall) -> None:
        """Handle a new trade call from the engine."""
        self._overlay.update_trade_call(call)

        # Cancel any pending auto-clear before scheduling a new one
        if self._clear_task is not None and not self._clear_task.done():
            self._clear_task.cancel()

        try:
            loop = asyncio.get_running_loop()
            self._clear_task = loop.create_task(
                self._auto_clear_trade_call(_TRADE_CALL_EXPIRY_SEC),
                name="overlay-trade-clear",
            )
        except RuntimeError:
            # No running loop — skip auto-clear (e.g. in sync test context)
            pass

    # ── Formatting ───────────────────────────────────────────────────────

    @staticmethod
    def _format_narrative(text: str, max_chars: int = _DEFAULT_NARRATIVE_MAX_CHARS) -> str:
        """Truncate narrative at a sentence boundary within *max_chars*."""
        if len(text) <= max_chars:
            return text

        truncated = text[:max_chars]
        # Find last sentence-ending punctuation
        for sep in (". ", "! ", "? "):
            idx = truncated.rfind(sep)
            if idx >= 0:
                return truncated[: idx + 1]

        # Fall back to last space to avoid mid-word cut
        space_idx = truncated.rfind(" ")
        if space_idx > 0:
            return truncated[:space_idx] + "..."
        return truncated + "..."

    @staticmethod
    def _format_trade_call_display(call: TradeCall) -> str:
        """Format a trade call into a compact display string.

        Example output::

            LONG @ 18,445 | Stop: 18,430 | Target: 18,490 | Conf: 85%
            MAD R1 (18,450)
        """
        line1 = (
            f"{call.direction.upper()} @ {call.entry:,.0f}"
            f" | Stop: {call.stop:,.0f}"
            f" | Target: {call.target:,.0f}"
            f" | Conf: {call.confidence:.0f}%"
        )
        parts = [line1]
        if call.mad_levels:
            first = call.mad_levels[0]
            label = first.label or "MAD"
            parts.append(f"{label} ({first.price:,.0f})")
        return "\n".join(parts)

    # ── Background loops ─────────────────────────────────────────────────

    async def _status_refresh_loop(self) -> None:
        """Poll freshness and calendar every few seconds."""
        while self._running:
            try:
                statuses = self._freshness.get_status_all()
                self._overlay.update_source_status(statuses)

                if self._calendar is not None:
                    events = self._calendar.get_upcoming(_UPCOMING_EVENTS_MINUTES)
                    self._overlay.update_countdowns(events)
            except Exception:
                logger.exception("overlay_content.status_refresh_failed")

            try:
                await asyncio.sleep(_STATUS_REFRESH_SEC)
            except asyncio.CancelledError:
                break

    async def _auto_clear_trade_call(self, delay_sec: int = _TRADE_CALL_EXPIRY_SEC) -> None:
        """Clear the trade call from the overlay after *delay_sec*."""
        try:
            await asyncio.sleep(delay_sec)
            self._overlay.update_trade_call(None)
        except asyncio.CancelledError:
            pass
