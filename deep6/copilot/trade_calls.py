"""Trade call monitoring engine for the DEEP6 copilot."""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from dataclasses import replace
from typing import Any

from deep6.copilot.budget import TokenBudgetTracker
from deep6.copilot.types import CalendarEvent, ChartAnalysis, MarketContext, TradeCall

logger = logging.getLogger(__name__)


class TradeCallEngine:
    """Polls score confluence and requests advisory trade calls on strong setups."""

    SCORE_THRESHOLD: int = 72
    COOLDOWN_SECONDS: int = 300
    POLL_INTERVAL_SECONDS: int = 5
    VALID_SETUP_TIERS: frozenset[str] = frozenset({"TYPE_A", "TYPE_B"})
    LOW_CONFIDENCE_WITHOUT_MAD: float = 25.0

    def __init__(
        self,
        config: Any,
        bridge_client: Any,
        aggregator: Any,
        brain: Any,
        screen_capture: Any,
        vision_analyzer: Any,
        budget_tracker: TokenBudgetTracker | None = None,
    ) -> None:
        self._config = config
        self._bridge_client = bridge_client
        self._aggregator = aggregator
        self._brain = brain
        self._screen_capture = screen_capture
        self._vision_analyzer = vision_analyzer
        self._budget = budget_tracker
        self._callbacks: list[Callable[[TradeCall], None]] = []
        self._monitor_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._last_trade_call_at = 0.0

    async def start(self) -> None:
        """Start the background monitoring loop."""
        if self._monitor_task is not None and not self._monitor_task.done():
            return
        self._stop_event.clear()
        self._monitor_task = asyncio.create_task(self._monitor_loop(), name="copilot_trade_calls")

    async def stop(self) -> None:
        """Stop the background monitoring loop."""
        self._stop_event.set()
        task = self._monitor_task
        self._monitor_task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def on_trade_call(self, callback: Callable[[TradeCall], None]) -> None:
        """Register a trade-call listener."""
        self._callbacks.append(callback)

    async def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._monitor_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("trade_calls.monitor_cycle_failed")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                continue

    async def _monitor_once(self) -> TradeCall | None:
        score = self._bridge_client.get_latest_score()
        if not self._should_trigger(score):
            return None

        screenshot_b64 = await self._capture_screenshot_b64()
        if not screenshot_b64:
            logger.debug("trade_calls.screenshot_unavailable")
            return None

        chart_analysis = await self._vision_analyzer.analyze_chart(screenshot_b64)
        context = await self._aggregator.build_context()
        if self._is_near_high_impact_event(context.calendar if context else (), minutes=5):
            logger.info("trade_calls.event_gate_blocked reason=high_impact_event_within_5min")
            return None

        context_str = self._build_trade_context(score, context, chart_analysis)

        if self._budget is not None and not self._budget.can_make_call(estimated_tokens=5000):
            logger.warning("Trade call skipped: budget exceeded")
            return None

        input_before = getattr(self._brain, "total_input_tokens", 0)
        output_before = getattr(self._brain, "total_output_tokens", 0)
        trade_call = await self._brain.generate_trade_call(context_str, screenshot_b64)
        if self._budget is not None:
            self._budget.record_usage(
                max(0, getattr(self._brain, "total_input_tokens", 0) - input_before),
                max(0, getattr(self._brain, "total_output_tokens", 0) - output_before),
                call_type="trade_call",
            )
        normalized_call = self._normalize_trade_call(trade_call, context, chart_analysis)

        self._last_trade_call_at = time.time()
        self._dispatch_trade_call(normalized_call)
        return normalized_call

    def _should_trigger(self, score: Any) -> bool:
        if score is None:
            return False
        total_score = float(self._get_value(score, "total_score", 0.0))
        tier = str(self._get_value(score, "tier", "")).upper()
        if total_score < self.SCORE_THRESHOLD:
            return False
        if tier and tier not in self.VALID_SETUP_TIERS:
            return False
        return self._cooldown_remaining() <= 0.0

    def _cooldown_remaining(self) -> float:
        if self._last_trade_call_at <= 0:
            return 0.0
        elapsed = time.time() - self._last_trade_call_at
        return max(0.0, self.COOLDOWN_SECONDS - elapsed)

    def _is_near_high_impact_event(self, calendar_events: tuple[CalendarEvent, ...], minutes: int = 5) -> bool:
        """Return True if a high-impact event is within N minutes."""
        now = datetime.now(timezone.utc)
        for event in (calendar_events or []):
            if getattr(event, "nq_relevance", 0) < 0.7:
                continue
            if str(getattr(event, "impact", "")).strip().lower() != "high":
                continue
            event_time_value = getattr(event, "time", "")
            if not event_time_value:
                continue
            try:
                for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
                    try:
                        event_time = datetime.strptime(event_time_value, fmt)
                        if event_time.tzinfo is None:
                            event_time = event_time.replace(tzinfo=timezone.utc)
                        delta_minutes = abs((event_time - now).total_seconds() / 60)
                        if delta_minutes <= minutes:
                            return True
                        break
                    except ValueError:
                        continue
            except Exception:
                continue
        return False

    async def _capture_screenshot_b64(self) -> str | None:
        capture_fn = getattr(self._screen_capture, "capture_as_base64", None)
        if callable(capture_fn):
            return await self._maybe_await(capture_fn())
        if callable(self._screen_capture):
            return await self._maybe_await(self._screen_capture())
        return None

    async def _maybe_await(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    def _build_trade_context(self, score: Any, context: MarketContext, chart_analysis: ChartAnalysis) -> str:
        base_context = self._aggregator.format_for_llm(context)
        total_score = float(self._get_value(score, "total_score", 0.0))
        tier = str(self._get_value(score, "tier", "UNKNOWN") or "UNKNOWN")
        direction = self._format_direction(self._get_value(score, "direction", 0))
        categories = self._as_list(self._get_value(score, "categories_firing", ()))

        lines = [
            base_context,
            "",
            "## Trade Call Trigger",
            f"Confluence Score: {total_score:.1f}/100",
            f"Setup Tier: {tier}",
            f"Directional Lean: {direction}",
            f"Threshold: >= {self.SCORE_THRESHOLD}",
        ]
        if categories:
            lines.append(f"Categories Firing: {', '.join(categories)}")

        lines.extend(["", "## Current Screenshot Analysis", f"Vision Confidence: {chart_analysis.confidence:.2f}"])
        if chart_analysis.price_action:
            lines.append(f"Price Action: {chart_analysis.price_action}")
        if chart_analysis.visual_patterns:
            lines.append(f"Visible Patterns: {', '.join(chart_analysis.visual_patterns)}")
        if chart_analysis.support_resistance:
            levels = ", ".join(f"{level:.2f}" for level in chart_analysis.support_resistance)
            lines.append(f"Non-MAD Support/Resistance: {levels}")

        lines.extend(["", "## MAD Levels"])
        if chart_analysis.mad_levels:
            for level in chart_analysis.mad_levels:
                lines.append(f"- {level.label or 'MAD'} @ {level.price:.2f} ({level.level_type or 'unknown'})")
        else:
            lines.append("- No MAD levels detected in the screenshot. Lower confidence and avoid aggressive calls.")

        lines.append("")
        lines.append("Return a concrete advisory trade plan only if the setup remains high-confidence.")
        return "\n".join(lines).strip()

    def _normalize_trade_call(
        self,
        trade_call: TradeCall,
        context: MarketContext,
        chart_analysis: ChartAnalysis,
    ) -> TradeCall:
        normalized = trade_call
        if not normalized.timestamp:
            normalized = replace(normalized, timestamp=time.time())
        if not normalized.signals:
            normalized = replace(normalized, signals=tuple(signal.name for signal in context.signals[:5] if signal.name))
        if chart_analysis.mad_levels and not normalized.mad_levels:
            normalized = replace(normalized, mad_levels=tuple(chart_analysis.mad_levels))
        if not chart_analysis.mad_levels:
            rationale = normalized.rationale.strip()
            note = "MAD levels were not detected in the screenshot, so confidence was capped."
            if note not in rationale:
                rationale = f"{rationale} {note}".strip()
            normalized = replace(
                normalized,
                confidence=min(normalized.confidence, self.LOW_CONFIDENCE_WITHOUT_MAD),
                rationale=rationale,
                mad_levels=tuple(chart_analysis.mad_levels),
            )
        return normalized

    def _dispatch_trade_call(self, trade_call: TradeCall) -> None:
        for callback in list(self._callbacks):
            try:
                result = callback(trade_call)
                if inspect.isawaitable(result):
                    task = asyncio.create_task(result)
                    task.add_done_callback(self._log_callback_error)
            except Exception:  # noqa: BLE001
                logger.exception("trade_calls.callback_failed")

    def _log_callback_error(self, task: asyncio.Task[Any]) -> None:
        try:
            task.result()
        except Exception:  # noqa: BLE001
            logger.exception("trade_calls.callback_task_failed")

    def _get_value(self, payload: Any, field: str, default: Any) -> Any:
        if isinstance(payload, dict):
            return payload.get(field, default)
        return getattr(payload, field, default)

    def _as_list(self, value: Any) -> list[str]:
        if isinstance(value, (list, tuple, set, frozenset)):
            return [str(item) for item in value]
        if value in (None, ""):
            return []
        return [str(value)]

    def _format_direction(self, value: Any) -> str:
        if isinstance(value, (int, float)):
            if value > 0:
                return "bullish"
            if value < 0:
                return "bearish"
            return "neutral"
        text = str(value).strip().lower()
        return text or "neutral"
