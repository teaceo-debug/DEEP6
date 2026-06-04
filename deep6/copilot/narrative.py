"""Narrative engine for the DEEP6 chart copilot."""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Callable
from datetime import datetime, time as dt_time
from typing import Any
from zoneinfo import ZoneInfo

from deep6.copilot.brain import CopilotBrain
from deep6.copilot.config import CopilotConfig
from deep6.copilot.context import ContextAggregator
from deep6.copilot.budget import TokenBudgetTracker
from deep6.copilot.types import ChartAnalysis, MarketContext
from deep6.copilot.vision import ScreenCapture
from deep6.copilot.vision_analysis import VisionAnalyzer

logger = logging.getLogger(__name__)

_CT = ZoneInfo("America/Chicago")


class NarrativeEngine:
    """Drive the continuous market-commentary loop."""

    DEFAULT_RTH_START = dt_time(hour=7, minute=30)
    DEFAULT_RTH_END = dt_time(hour=15, minute=0)
    DEFAULT_ESTIMATED_TOKENS = 4_000
    DEFAULT_CONTEXT_TIMEOUT_SEC = 10.0
    DEFAULT_SCREENSHOT_TIMEOUT_SEC = 10.0
    DEFAULT_VISION_TIMEOUT_SEC = 20.0
    DEFAULT_STREAM_CHUNK_TIMEOUT_SEC = 30.0
    DEFAULT_STOP_TIMEOUT_SEC = 5.0

    def __init__(
        self,
        config: CopilotConfig,
        aggregator: ContextAggregator,
        brain: CopilotBrain,
        screen_capture: ScreenCapture,
        vision_analyzer: VisionAnalyzer | None,
        budget_tracker: TokenBudgetTracker,
        *,
        rth_start: dt_time | None = None,
        rth_end: dt_time | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self.aggregator = aggregator
        self.brain = brain
        self.screen_capture = screen_capture
        self.vision_analyzer = vision_analyzer
        self.budget_tracker = budget_tracker
        self._rth_start = rth_start or self.DEFAULT_RTH_START
        self._rth_end = rth_end or self.DEFAULT_RTH_END
        self._now_provider = now_provider or (lambda: datetime.now(tz=_CT))
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._last_screenshot_b64: str | None = None
        self._last_screenshot_at: float = 0.0
        self._last_chart_analysis: ChartAnalysis | None = None
        self._chunk_callbacks: list[Callable[[str], Any]] = []
        self._complete_callbacks: list[Callable[[str], Any]] = []

    async def start(self) -> None:
        """Start the background narrative loop if needed."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._narrative_loop(), name="copilot-narrative-loop")

    async def stop(self) -> None:
        """Request shutdown and wait for the loop to exit."""
        self._stop_event.set()
        if self._task is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(self._task), timeout=self.DEFAULT_STOP_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        finally:
            self._task = None

    def on_narrative_chunk(self, callback: Callable[[str], None]) -> None:
        self._chunk_callbacks.append(callback)

    def on_narrative_complete(self, callback: Callable[[str], None]) -> None:
        self._complete_callbacks.append(callback)

    async def _narrative_loop(self) -> None:
        interval = max(0.01, float(self.config.narrative_interval_sec))
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                pass

            try:
                if not self._is_rth():
                    logger.debug("narrative.skip reason=outside_rth")
                    continue

                if not self.budget_tracker.can_make_call(self.DEFAULT_ESTIMATED_TOKENS):
                    logger.warning("narrative.skip reason=budget_exhausted")
                    continue

                context = await asyncio.wait_for(
                    self.aggregator.build_context(),
                    timeout=self.DEFAULT_CONTEXT_TIMEOUT_SEC,
                )
                context_str = self._format_context(context)
                screenshot_b64 = await self._maybe_refresh_screenshot()

                input_before = self.brain.total_input_tokens
                output_before = self.brain.total_output_tokens
                narrative = await self._stream_narrative(context_str, screenshot_b64)
                self.budget_tracker.record_usage(
                    self.brain.total_input_tokens - input_before,
                    self.brain.total_output_tokens - output_before,
                    call_type="narrative",
                )
                await self._emit_complete(narrative)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("narrative.loop_iteration_failed")

    def _is_rth(self) -> bool:
        now = self._now_provider().astimezone(_CT)
        current = now.time()
        return self._rth_start <= current <= self._rth_end

    def _format_context(self, ctx: MarketContext) -> str:
        return self.aggregator.format_for_llm(ctx)

    async def _maybe_refresh_screenshot(self) -> str | None:
        now = time.monotonic()
        screenshot_interval = max(0.0, float(self.config.screenshot_interval_sec))
        should_capture = (
            self._last_screenshot_b64 is None
            or screenshot_interval <= 0
            or now - self._last_screenshot_at >= screenshot_interval
        )
        if not should_capture:
            return self._last_screenshot_b64

        screenshot_b64 = await asyncio.wait_for(
            asyncio.to_thread(self.screen_capture.capture_as_base64),
            timeout=self.DEFAULT_SCREENSHOT_TIMEOUT_SEC,
        )
        if not screenshot_b64:
            return self._last_screenshot_b64

        self._last_screenshot_b64 = screenshot_b64
        self._last_screenshot_at = now

        if self.vision_analyzer is not None:
            try:
                self._last_chart_analysis = await asyncio.wait_for(
                    self.vision_analyzer.analyze_chart(screenshot_b64),
                    timeout=self.DEFAULT_VISION_TIMEOUT_SEC,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("narrative.vision_analysis_failed")

        return self._last_screenshot_b64

    async def _stream_narrative(self, context_str: str, screenshot_b64: str | None) -> str:
        parts: list[str] = []
        stream = self.brain.generate_narrative(context_str, screenshot_b64)
        iterator = stream.__aiter__()

        while True:
            try:
                chunk = await asyncio.wait_for(anext(iterator), timeout=self.DEFAULT_STREAM_CHUNK_TIMEOUT_SEC)
            except StopAsyncIteration:
                break

            if not chunk:
                continue
            parts.append(chunk)
            await self._emit_chunks(chunk)

        return "".join(parts)

    async def _emit_chunks(self, chunk: str) -> None:
        for callback in self._chunk_callbacks:
            await self._invoke_callback(callback, chunk)

    async def _emit_complete(self, narrative: str) -> None:
        for callback in self._complete_callbacks:
            await self._invoke_callback(callback, narrative)

    async def _invoke_callback(self, callback: Callable[[str], Any], payload: str) -> None:
        try:
            result = callback(payload)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("narrative.callback_failed callback=%r", callback)
