"""SessionManager — top-level copilot startup/shutdown orchestrator.

Coordinates component lifecycle:
  1. Load persisted state from disk
  2. Connect bridge_client (TCP + WS)
  3. Initialize adapters (calendar, news, sentiment, internals, options_flow)
  4. Start brain (narrative engine) and context aggregator
  5. Start overlay
  6. RTH watchdog: auto-pause outside 7:30 AM - 3:00 PM CT

Called from ``__main__.py`` via ``asyncio.run(session.run_until_shutdown())``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import time
from pathlib import Path
from typing import Any

from zoneinfo import ZoneInfo

from deep6.copilot.bridge_client import CopilotBridgeClient
from deep6.copilot.brain import CopilotBrain
from deep6.copilot.config import CopilotConfig
from deep6.copilot.context import ContextAggregator
from deep6.copilot.freshness import FreshnessTracker
from deep6.copilot.narrative import NarrativeEngine
from deep6.copilot.overlay import CopilotOverlay
from deep6.copilot.overlay_content import OverlayContentRenderer
from deep6.copilot.budget import TokenBudgetTracker
from deep6.copilot.trade_calls import TradeCallEngine
from deep6.copilot.vision import ScreenCapture
from deep6.copilot.vision_analysis import VisionAnalyzer

logger = logging.getLogger(__name__)

_CT = ZoneInfo("America/Chicago")

# RTH boundaries in Central Time (hours, minutes)
_RTH_OPEN_HOUR, _RTH_OPEN_MIN = 7, 30
_RTH_CLOSE_HOUR, _RTH_CLOSE_MIN = 15, 0

# How often the RTH watchdog checks (seconds)
_RTH_CHECK_INTERVAL = 60.0

# Startup timeout per component (seconds)
_COMPONENT_TIMEOUT = 10.0

# Default state file name
_DEFAULT_STATE_FILE = ".copilot_state.json"


def _is_rth_now() -> bool:
    """Return True if current time is within NQ RTH (7:30-15:00 CT)."""
    from datetime import datetime

    now = datetime.now(tz=_CT)
    open_minutes = _RTH_OPEN_HOUR * 60 + _RTH_OPEN_MIN
    close_minutes = _RTH_CLOSE_HOUR * 60 + _RTH_CLOSE_MIN
    current_minutes = now.hour * 60 + now.minute
    weekday = now.weekday()
    if weekday >= 5:  # Saturday=5, Sunday=6
        return False
    return open_minutes <= current_minutes < close_minutes


def _seconds_until_rth_open() -> float:
    """Return seconds until next RTH open. Returns 0 if already in RTH."""
    from datetime import datetime, timedelta

    now = datetime.now(tz=_CT)
    if _is_rth_now():
        return 0.0

    # Next open: today if before open, else next weekday
    target = now.replace(
        hour=_RTH_OPEN_HOUR, minute=_RTH_OPEN_MIN, second=0, microsecond=0,
    )
    if target <= now:
        target += timedelta(days=1)
    # Skip weekends
    while target.weekday() >= 5:
        target += timedelta(days=1)
    return max(0.0, (target - now).total_seconds())


class SessionManager:
    """Top-level copilot coordinator.

    Parameters
    ----------
    config:
        CopilotConfig instance (from env or explicit).
    state_path:
        Path to the JSON state file. Defaults to ``.copilot_state.json``
        in the current directory.
    """

    def __init__(
        self,
        config: CopilotConfig,
        *,
        state_path: Path | str | None = None,
        override_rth: bool = False,
    ) -> None:
        self._config = config
        self._override_rth = override_rth
        self._state_path = Path(state_path) if state_path else Path(_DEFAULT_STATE_FILE)

        # Core components
        self._bridge_client = CopilotBridgeClient(config)
        self._overlay = CopilotOverlay(config)
        self._budget = TokenBudgetTracker(token_budget_per_hour=config.token_budget_per_hour)
        self._freshness = FreshnessTracker()
        self._brain = CopilotBrain(config)
        self._screen_capture = ScreenCapture(config)
        self._vision_analyzer = VisionAnalyzer(config, budget_tracker=self._budget)
        self._aggregator = ContextAggregator(config=config, bridge_client=self._bridge_client)
        self._narrative_engine: NarrativeEngine | None = None
        self._trade_engine: TradeCallEngine | None = None
        self._overlay_content: OverlayContentRenderer | None = None

        # Adapter stubs (populated by start or externally)
        self._adapters: dict[str, Any] = {}
        self._calendar: Any | None = None
        self._news: Any | None = None
        self._sentiment: Any | None = None
        self._internals: Any | None = None
        self._options_flow: Any | None = None

        # Lifecycle state
        self._started = False
        self._paused = False
        self._shutdown_event: asyncio.Event | None = None
        self._rth_task: asyncio.Task[None] | None = None
        self._session_stats: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def bridge_client(self) -> CopilotBridgeClient:
        return self._bridge_client

    @property
    def context(self) -> ContextAggregator:
        return self._aggregator

    @property
    def overlay(self) -> CopilotOverlay:
        return self._overlay

    @property
    def budget(self) -> TokenBudgetTracker:
        return self._budget

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def is_paused(self) -> bool:
        return self._paused

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start all components in order. Non-critical failures are logged."""
        if self._started:
            logger.warning("session.already_started")
            return

        logger.info("session.starting")

        # 1. Load persisted state
        state = self.load_state()
        self._session_stats = state.get("session_stats", {})

        # 2. Connect bridge client (TCP + WS)
        await self._start_component("bridge_client", self._bridge_client.connect())

        # 3. Initialize adapters
        await self._init_adapters()

        self._aggregator = ContextAggregator(
            config=self._config,
            bridge_client=self._bridge_client,
            calendar_adapter=self._calendar,
            news_adapter=self._news,
            sentiment_adapter=self._sentiment,
            internals_adapter=self._internals,
            options_flow_adapter=self._options_flow,
        )
        self._narrative_engine = NarrativeEngine(
            config=self._config,
            aggregator=self._aggregator,
            brain=self._brain,
            screen_capture=self._screen_capture,
            vision_analyzer=self._vision_analyzer,
            budget_tracker=self._budget,
        )
        self._trade_engine = TradeCallEngine(
            config=self._config,
            bridge_client=self._bridge_client,
            aggregator=self._aggregator,
            brain=self._brain,
            screen_capture=self._screen_capture,
            vision_analyzer=self._vision_analyzer,
            budget_tracker=self._budget,
        )
        self._overlay_content = OverlayContentRenderer(
            overlay=self._overlay,
            narrative_engine=self._narrative_engine,
            trade_engine=self._trade_engine,
            freshness_tracker=self._freshness,
            calendar_adapter=self._calendar,
        )

        await self._start_component("narrative_engine", self._narrative_engine.start())
        await self._start_component("trade_engine", self._trade_engine.start())

        # 4. Start overlay (runs on its own thread)
        try:
            self._overlay.start()
        except Exception:
            logger.warning("session.overlay_start_failed", exc_info=True)

        if self._overlay_content is not None:
            await self._start_component("overlay_content", self._overlay_content.start())

        # 5. RTH watchdog
        self._rth_task = asyncio.create_task(
            self._rth_watchdog(), name="rth_watchdog",
        )

        self._started = True
        self._session_stats["last_start"] = time.time()
        self._session_stats["start_count"] = self._session_stats.get("start_count", 0) + 1

        status = self.get_status()
        logger.info(
            "session.started bridge_tcp=%s bridge_ws=%s overlay=running adapters=%d",
            status.get("bridge_tcp", "unknown"),
            status.get("bridge_ws", "unknown"),
            len(self._adapters),
        )

    async def stop(self) -> None:
        """Shutdown in reverse order: watchdog → overlay → bridge → save state."""
        if not self._started:
            return

        logger.info("session.stopping")

        # Cancel RTH watchdog
        if self._rth_task is not None and not self._rth_task.done():
            self._rth_task.cancel()
            try:
                await self._rth_task
            except (asyncio.CancelledError, Exception):
                pass
            self._rth_task = None

        # Stop overlay
        if self._overlay_content is not None:
            try:
                await asyncio.wait_for(self._overlay_content.stop(), timeout=_COMPONENT_TIMEOUT)
            except (asyncio.TimeoutError, Exception):
                logger.warning("session.overlay_content_stop_failed", exc_info=True)
            finally:
                self._overlay_content = None

        if self._trade_engine is not None:
            try:
                await asyncio.wait_for(self._trade_engine.stop(), timeout=_COMPONENT_TIMEOUT)
            except (asyncio.TimeoutError, Exception):
                logger.warning("session.trade_engine_stop_failed", exc_info=True)
            finally:
                self._trade_engine = None

        if self._narrative_engine is not None:
            try:
                await asyncio.wait_for(self._narrative_engine.stop(), timeout=_COMPONENT_TIMEOUT)
            except (asyncio.TimeoutError, Exception):
                logger.warning("session.narrative_engine_stop_failed", exc_info=True)
            finally:
                self._narrative_engine = None

        try:
            self._overlay.stop()
        except Exception:
            logger.warning("session.overlay_stop_failed", exc_info=True)

        await self._stop_adapters()

        # Disconnect bridge
        try:
            await asyncio.wait_for(
                self._bridge_client.disconnect(), timeout=_COMPONENT_TIMEOUT,
            )
        except (asyncio.TimeoutError, Exception):
            logger.warning("session.bridge_disconnect_failed", exc_info=True)

        # Persist state
        self._session_stats["last_stop"] = time.time()
        self.save_state()

        self._started = False
        self._paused = False
        logger.info("session.stopped")

    async def run_until_shutdown(self) -> None:
        """Main entry point: start, wait for OS signal, then stop."""
        self._shutdown_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        # Register OS signal handlers (Unix-style; Windows may not support all)
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._signal_shutdown)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler for SIGTERM
                pass

        await self.start()

        try:
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def save_state(self) -> None:
        """Write session state to disk."""
        payload = {
            "session_stats": self._session_stats,
            "last_run": time.time(),
        }
        try:
            self._state_path.write_text(
                json.dumps(payload, indent=2, default=str), encoding="utf-8",
            )
            logger.debug("session.state_saved path=%s", self._state_path)
        except OSError:
            logger.warning("session.state_save_failed path=%s", self._state_path, exc_info=True)

    def load_state(self) -> dict[str, Any]:
        """Load persisted state or return defaults."""
        if not self._state_path.exists():
            return {"session_stats": {}}
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"session_stats": {}}
            return data
        except (OSError, json.JSONDecodeError):
            logger.warning("session.state_load_failed path=%s", self._state_path, exc_info=True)
            return {"session_stats": {}}

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return current component health."""
        return {
            "started": self._started,
            "paused": self._paused,
            "bridge_tcp": "connected" if self._bridge_client.is_tcp_connected else "disconnected",
            "bridge_ws": "connected" if self._bridge_client.is_ws_connected else "disconnected",
            "adapters": list(self._adapters.keys()),
            "session_stats": dict(self._session_stats),
        }

    # ------------------------------------------------------------------
    # RTH watchdog
    # ------------------------------------------------------------------

    async def _rth_watchdog(self) -> None:
        """Periodically check RTH and pause/resume accordingly."""
        while True:
            try:
                if self._override_rth or _is_rth_now():
                    if self._paused:
                        logger.info("session.rth_open — resuming copilot")
                        self._paused = False
                        self._overlay.set_connected(True)
                else:
                    if not self._paused and self._started:
                        logger.info("session.rth_closed — pausing copilot")
                        self._paused = True
                        self._overlay.set_connected(False)

                    # Sleep until next RTH open (capped to avoid huge sleeps)
                    wait = min(_seconds_until_rth_open(), 3600.0)
                    if wait > _RTH_CHECK_INTERVAL:
                        await asyncio.sleep(wait)
                        continue

                await asyncio.sleep(_RTH_CHECK_INTERVAL)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("session.rth_watchdog_error", exc_info=True)
                await asyncio.sleep(_RTH_CHECK_INTERVAL)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _init_adapters(self) -> None:
        """Wire adapters that are enabled in config."""
        self._adapters.clear()
        self._calendar = None
        self._news = None
        self._sentiment = None
        self._internals = None
        self._options_flow = None

        if self._config.calendar_enabled:
            self._calendar = self._build_adapter(
                "calendar",
                "deep6.copilot.adapters.calendar",
                "EconomicCalendarAdapter",
            )
        if self._config.news_enabled:
            self._news = self._build_adapter(
                "news",
                "deep6.copilot.adapters.news",
                "NewsFeedAdapter",
            )
        if self._config.sentiment_enabled:
            self._sentiment = self._build_adapter(
                "sentiment",
                "deep6.copilot.adapters.sentiment",
                "SentimentAdapter",
            )
        if self._config.internals_enabled:
            self._internals = self._build_adapter(
                "internals",
                "deep6.copilot.adapters.internals",
                "MarketInternalsAdapter",
            )
            if self._internals is not None and hasattr(self._internals, "connect"):
                await self._start_component(
                    "internals_adapter",
                    self._internals.connect(self._config.data_bridge_host, self._config.data_bridge_port),
                )
        if self._config.options_flow_enabled:
            self._options_flow = self._build_adapter(
                "options_flow",
                "deep6.copilot.adapters.options_flow",
                "OptionsFlowAdapter",
            )

    def _build_adapter(self, name: str, module_name: str, class_name: str) -> Any | None:
        try:
            module = __import__(module_name, fromlist=[class_name])
            adapter_cls = getattr(module, class_name)
            adapter = adapter_cls()
        except Exception:
            logger.warning("session.adapter_init_failed name=%s", name, exc_info=True)
            return None

        self._adapters[name] = adapter
        logger.debug("session.adapter_enabled name=%s", name)
        return adapter

    async def _stop_adapters(self) -> None:
        for name, adapter in list(self._adapters.items()):
            try:
                disconnect = getattr(adapter, "disconnect", None)
                if callable(disconnect):
                    result = disconnect()
                    if asyncio.iscoroutine(result):
                        await asyncio.wait_for(result, timeout=_COMPONENT_TIMEOUT)

                stop = getattr(adapter, "stop", None)
                if callable(stop):
                    result = stop()
                    if asyncio.iscoroutine(result):
                        await asyncio.wait_for(result, timeout=_COMPONENT_TIMEOUT)

                aclose = getattr(adapter, "aclose", None)
                if callable(aclose):
                    result = aclose()
                    if asyncio.iscoroutine(result):
                        await asyncio.wait_for(result, timeout=_COMPONENT_TIMEOUT)
            except (asyncio.TimeoutError, Exception):
                logger.warning("session.adapter_stop_failed name=%s", name, exc_info=True)

        self._adapters.clear()
        self._calendar = None
        self._news = None
        self._sentiment = None
        self._internals = None
        self._options_flow = None

    async def _start_component(self, name: str, coro: Any) -> None:
        """Await a component's startup coroutine with timeout + error tolerance."""
        try:
            await asyncio.wait_for(coro, timeout=_COMPONENT_TIMEOUT)
            logger.debug("session.component_started name=%s", name)
        except asyncio.TimeoutError:
            logger.warning("session.component_timeout name=%s timeout=%s", name, _COMPONENT_TIMEOUT)
        except Exception:
            logger.warning("session.component_failed name=%s", name, exc_info=True)

    def _signal_shutdown(self) -> None:
        """Called by OS signal handler to trigger graceful shutdown."""
        logger.info("session.shutdown_signal_received")
        if self._shutdown_event is not None:
            self._shutdown_event.set()


__all__ = ["SessionManager"]
