"""Rolling market-context aggregator for the DEEP6 copilot."""

from __future__ import annotations

import asyncio
import inspect
import math
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from deep6.copilot.config import CopilotConfig
from deep6.copilot.types import (
    CalendarEvent,
    ChartAnalysis,
    DataSourceStatus,
    GEXSummary,
    KronosBias,
    MADLevel,
    MarketContext,
    MarketInternals,
    NewsItem,
    OptionsFlowSnapshot,
    PriceSnapshot,
    SentimentSnapshot,
    SignalSummary,
)

_ET = ZoneInfo("America/New_York")
_DEFAULT_TOKEN_BUDGET = 8000
_DEFAULT_SIGNAL_INTERVAL = 15.0
_DEFAULT_BRIDGE_INTERVAL = 5.0
_DEFAULT_GEX_INTERVAL = 300.0
_DEFAULT_KRONOS_INTERVAL = 75.0
_DEFAULT_VISION_INTERVAL = 30.0


@dataclass(slots=True)
class _SourceSnapshot:
    name: str
    value: Any
    last_update: float
    stale: bool
    error: str | None = None


class ContextAggregator:
    """Collects the latest market data and formats it for the LLM."""

    def __init__(
        self,
        *,
        config: CopilotConfig | None = None,
        bridge_client: Any | None = None,
        calendar_adapter: Any | None = None,
        news_adapter: Any | None = None,
        sentiment_adapter: Any | None = None,
        internals_adapter: Any | None = None,
        options_flow_adapter: Any | None = None,
        gex_adapter: Any | None = None,
        kronos_adapter: Any | None = None,
        chart_analysis_provider: Any | None = None,
        history_size: int = 5,
        token_budget: int = _DEFAULT_TOKEN_BUDGET,
    ) -> None:
        self.config = config or CopilotConfig.from_env()
        self.bridge_client = bridge_client
        self.calendar_adapter = calendar_adapter
        self.news_adapter = news_adapter
        self.sentiment_adapter = sentiment_adapter
        self.internals_adapter = internals_adapter
        self.options_flow_adapter = options_flow_adapter
        self.gex_adapter = gex_adapter
        self.kronos_adapter = kronos_adapter
        self.chart_analysis_provider = chart_analysis_provider
        self.token_budget = token_budget
        self._history: deque[MarketContext] = deque(maxlen=history_size)
        self._history_timestamps: deque[float] = deque(maxlen=history_size)
        self._source_cache: dict[str, Any] = {}
        self._source_errors: dict[str, str | None] = {}
        self._source_last_seen: dict[str, float] = {}
        self._latest_chart_analysis: ChartAnalysis | None = None
        self._latest_score: dict[str, Any] = {}
        self._latest_signal_event: dict[str, Any] = {}

    async def build_context(self) -> MarketContext:
        """Collect one snapshot from every available source."""
        now = time.time()
        tasks = [
            self._collect_bridge(now),
            self._collect_chart_analysis(now),
            self._collect_calendar(now),
            self._collect_news(now),
            self._collect_sentiment(now),
            self._collect_internals(now),
            self._collect_options_flow(now),
            self._collect_gex(now),
            self._collect_kronos(now),
        ]
        results = await asyncio.gather(*tasks)
        snapshots = {result.name: result for result in results}

        bridge_data = snapshots["bridge"].value or {}
        context = MarketContext(
            signals=tuple(bridge_data.get("signals", ())),
            gex=snapshots["gex"].value,
            kronos_bias=snapshots["kronos"].value,
            internals=snapshots["internals"].value,
            calendar=tuple(snapshots["calendar"].value or ()),
            news=tuple(snapshots["news"].value or ()),
            sentiment=snapshots["sentiment"].value,
            options_flow=snapshots["options_flow"].value,
            price=bridge_data.get("price"),
            source_statuses=tuple(
                DataSourceStatus(
                    source_name=snapshot.name,
                    last_update=snapshot.last_update,
                    is_stale=snapshot.stale,
                    error=snapshot.error,
                )
                for snapshot in snapshots.values()
            ),
        )
        self._history.append(context)
        self._history_timestamps.append(now)
        return context

    def format_for_llm(self, context: MarketContext | None = None) -> str:
        """Render the latest market context into a bounded prompt string."""
        if context is None:
            if not self._history:
                context = MarketContext()
                created_at = time.time()
            else:
                context = self._history[-1]
                created_at = self._history_timestamps[-1]
        else:
            created_at = self._history_timestamps[-1] if self._history_timestamps else time.time()

        lines = self._build_prompt_lines(context, created_at, history_mode="full")
        prompt = "\n".join(lines).strip()
        if self._estimate_tokens(prompt) <= self.token_budget:
            return prompt

        lines = self._build_prompt_lines(context, created_at, history_mode="compact")
        prompt = "\n".join(lines).strip()
        if self._estimate_tokens(prompt) <= self.token_budget:
            return prompt

        lines = self._build_prompt_lines(context, created_at, history_mode="minimal")
        prompt = "\n".join(lines).strip()
        if self._estimate_tokens(prompt) <= self.token_budget:
            return prompt

        trimmed = prompt[: self.token_budget * 4]
        return trimmed.rsplit("\n", 1)[0].strip()

    async def _collect_bridge(self, now: float) -> _SourceSnapshot:
        if self.bridge_client is None:
            return self._missing_source("bridge")

        async def _fetch() -> dict[str, Any]:
            latest = await self._maybe_call(
                self.bridge_client,
                "get_latest_context",
                "get_snapshot",
                "get_latest",
            )
            payload = latest if isinstance(latest, dict) else {}
            payload = {
                **(self._coerce_mapping(getattr(self.bridge_client, "latest_context", None))),
                **payload,
            }
            bar = payload.get("bar") or self._coerce_mapping(getattr(self.bridge_client, "latest_bar", None))
            score = payload.get("score") or self._coerce_mapping(getattr(self.bridge_client, "latest_score", None))
            signal = payload.get("signal") or self._coerce_mapping(getattr(self.bridge_client, "latest_signal", None))
            signals = self._extract_signal_summaries(payload, score, signal, now)
            price = self._extract_price_snapshot(payload, bar)
            if score:
                self._latest_score = score
            if signal:
                self._latest_signal_event = signal
            return {
                "signals": signals,
                "price": price,
                "score": score,
                "signal": signal,
                "bar": bar,
                "timestamp": self._best_timestamp(payload, bar, score, signal, fallback=now),
            }

        return await self._capture_source(
            "bridge",
            _fetch,
            now,
            interval=self._bridge_interval(),
            stale_checker=lambda value, age, _interval: age > self._bridge_interval() * 2 or value.get("price") is None,
        )

    async def _collect_chart_analysis(self, now: float) -> _SourceSnapshot:
        if self.chart_analysis_provider is None:
            return self._missing_source("chart_analysis")

        async def _fetch() -> ChartAnalysis | None:
            value = await self._maybe_call(
                self.chart_analysis_provider,
                "get_latest_analysis",
                "get_current_analysis",
                "analyze_latest",
            )
            if value is None:
                value = getattr(self.chart_analysis_provider, "latest_analysis", None)
            return self._coerce_chart_analysis(value)

        snapshot = await self._capture_source(
            "chart_analysis",
            _fetch,
            now,
            interval=self._poll_interval(self.chart_analysis_provider, _DEFAULT_VISION_INTERVAL),
            stale_checker=lambda value, age, interval: value is None or age > interval * 2,
        )
        self._latest_chart_analysis = snapshot.value
        return snapshot

    async def _collect_calendar(self, now: float) -> _SourceSnapshot:
        if self.calendar_adapter is None:
            return self._missing_source("calendar")

        async def _fetch() -> tuple[CalendarEvent, ...]:
            events = await self._maybe_call(self.calendar_adapter, "fetch_today_events", "get_events")
            return tuple(event for event in (events or []) if isinstance(event, CalendarEvent))

        return await self._capture_source(
            "calendar",
            _fetch,
            now,
            interval=self._poll_interval(self.calendar_adapter, 300.0),
            stale_checker=lambda _value, age, interval: age > interval * 2,
        )

    async def _collect_news(self, now: float) -> _SourceSnapshot:
        if self.news_adapter is None:
            return self._missing_source("news")

        async def _fetch() -> tuple[NewsItem, ...]:
            items = await self._maybe_call(self.news_adapter, "fetch_latest", "get_latest")
            normalized = [item for item in (items or []) if isinstance(item, NewsItem)]
            normalized.sort(key=lambda item: (item.nq_relevance_score, item.timestamp), reverse=True)
            return tuple(normalized)

        return await self._capture_source(
            "news",
            _fetch,
            now,
            interval=self._poll_interval(self.news_adapter, 120.0),
            stale_checker=lambda _value, age, interval: age > interval * 2,
        )

    async def _collect_sentiment(self, now: float) -> _SourceSnapshot:
        if self.sentiment_adapter is None:
            return self._missing_source("sentiment")

        async def _fetch() -> SentimentSnapshot | None:
            value = await self._maybe_call(self.sentiment_adapter, "fetch_sentiment", "get_sentiment")
            return value if isinstance(value, SentimentSnapshot) else None

        return await self._capture_source(
            "sentiment",
            _fetch,
            now,
            interval=self._poll_interval(self.sentiment_adapter, 300.0),
            stale_checker=lambda value, age, interval: value is None or age > interval * 2,
        )

    async def _collect_internals(self, now: float) -> _SourceSnapshot:
        if self.internals_adapter is None:
            return self._missing_source("internals")

        async def _fetch() -> MarketInternals | None:
            value = await self._maybe_call(self.internals_adapter, "get_current", "current")
            return value if isinstance(value, MarketInternals) else None

        return await self._capture_source(
            "internals",
            _fetch,
            now,
            interval=self._poll_interval(self.internals_adapter, 5.0),
            stale_checker=lambda value, age, interval: value is None or age > interval * 2,
        )

    async def _collect_options_flow(self, now: float) -> _SourceSnapshot:
        if self.options_flow_adapter is None:
            return self._missing_source("options_flow")

        async def _fetch() -> OptionsFlowSnapshot | None:
            value = await self._maybe_call(self.options_flow_adapter, "fetch_flow", "get_flow")
            return value if isinstance(value, OptionsFlowSnapshot) else None

        return await self._capture_source(
            "options_flow",
            _fetch,
            now,
            interval=self._poll_interval(self.options_flow_adapter, 180.0),
            stale_checker=lambda value, age, interval: value is None or age > interval * 2,
        )

    async def _collect_gex(self, now: float) -> _SourceSnapshot:
        if self.gex_adapter is None:
            return self._missing_source("gex")

        async def _fetch() -> GEXSummary | None:
            value = await self._maybe_call(self.gex_adapter, "get_levels", "fetch_and_compute", "get_summary", "get_latest_gex")
            if value is None:
                value = getattr(self.gex_adapter, "_levels", None)
            return self._coerce_gex_summary(value)

        return await self._capture_source(
            "gex",
            _fetch,
            now,
            interval=self._poll_interval(self.gex_adapter, _DEFAULT_GEX_INTERVAL, fallback_attr="staleness_seconds"),
            stale_checker=self._gex_stale,
        )

    async def _collect_kronos(self, now: float) -> _SourceSnapshot:
        if self.kronos_adapter is None:
            return self._missing_source("kronos")

        async def _fetch() -> KronosBias | None:
            value = await self._maybe_call(self.kronos_adapter, "get_bias", "process", "get_latest_bias", "get_latest_kronos")
            if value is None:
                value = getattr(self.kronos_adapter, "_last_bias", None)
            return self._coerce_kronos_bias(value)

        return await self._capture_source(
            "kronos",
            _fetch,
            now,
            interval=self._poll_interval(self.kronos_adapter, _DEFAULT_KRONOS_INTERVAL, fallback_attr="inference_interval"),
            stale_checker=lambda value, age, interval: value is None or age > interval * 2,
        )

    async def _capture_source(
        self,
        name: str,
        fetcher: Callable[[], Awaitable[Any]] | Callable[[], Any],
        now: float,
        *,
        interval: float,
        stale_checker: Callable[[Any, float, float], bool],
    ) -> _SourceSnapshot:
        try:
            value = fetcher()
            if inspect.isawaitable(value):
                value = await value
            last_update = self._best_timestamp(value, fallback=now)
            self._source_cache[name] = value
            self._source_last_seen[name] = last_update
            self._source_errors[name] = None
            age = max(0.0, now - last_update)
            return _SourceSnapshot(name, value, last_update, stale_checker(value, age, interval))
        except Exception as exc:  # noqa: BLE001
            cached = self._source_cache.get(name)
            last_seen = self._source_last_seen.get(name, 0.0)
            self._source_errors[name] = str(exc)
            age = max(0.0, now - last_seen) if last_seen > 0 else float("inf")
            stale = True
            if cached is not None and last_seen > 0:
                stale = stale_checker(cached, age, interval) or True
            return _SourceSnapshot(name, cached, last_seen, stale, error=str(exc))

    def _missing_source(self, name: str) -> _SourceSnapshot:
        return _SourceSnapshot(name, None, self._source_last_seen.get(name, 0.0), True, error="adapter unavailable")

    async def _maybe_call(self, target: Any, *method_names: str) -> Any:
        for method_name in method_names:
            method = getattr(target, method_name, None)
            if method is None:
                continue
            if callable(method):
                try:
                    if method_name == "fetch_and_compute":
                        arg = self._latest_known_price(default=0.0) / 40.0 if self._latest_known_price(default=0.0) > 0 else 0.0
                        result = method(arg)
                    else:
                        result = method()
                except TypeError:
                    continue
                if inspect.isawaitable(result):
                    return await result
                return result
            return method
        return None

    def _poll_interval(self, adapter: Any, default: float, fallback_attr: str | None = None) -> float:
        for attr in ("POLL_INTERVAL_SECONDS", "poll_interval_seconds", fallback_attr):
            if not attr:
                continue
            value = getattr(adapter, attr, None)
            if isinstance(value, (int, float)) and value > 0:
                return float(value)
        return float(default)

    def _bridge_interval(self) -> float:
        return min(float(self.config.narrative_interval_sec), _DEFAULT_BRIDGE_INTERVAL)

    def _coerce_mapping(self, value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    def _extract_signal_summaries(
        self,
        payload: dict[str, Any],
        score: dict[str, Any],
        signal: dict[str, Any],
        now: float,
    ) -> tuple[SignalSummary, ...]:
        explicit = payload.get("signals")
        if isinstance(explicit, (list, tuple)):
            converted = [self._coerce_signal_summary(item, now) for item in explicit]
            return tuple(item for item in converted if item is not None)

        names = score.get("categories_firing") or signal.get("categories_firing") or []
        if not names and signal.get("narrative"):
            names = [signal["narrative"]]
        direction = self._normalize_direction(score.get("direction", signal.get("direction")))
        strength = float(score.get("total_score") or signal.get("total_score") or 0.0)
        timestamp = self._best_timestamp(score, signal, fallback=now)
        summaries: list[SignalSummary] = []
        for name in names:
            text = str(name).strip()
            if not text:
                continue
            summaries.append(
                SignalSummary(
                    name=text,
                    direction=self._direction_label(direction),
                    strength=strength,
                    category=text,
                    timestamp=timestamp,
                )
            )
        return tuple(summaries)

    def _coerce_signal_summary(self, value: Any, now: float) -> SignalSummary | None:
        if isinstance(value, SignalSummary):
            return value
        mapping = self._coerce_mapping(value)
        if not mapping:
            return None
        name = str(mapping.get("name") or mapping.get("category") or mapping.get("label") or "").strip()
        if not name:
            return None
        return SignalSummary(
            name=name,
            direction=self._direction_label(self._normalize_direction(mapping.get("direction"))),
            strength=float(mapping.get("strength") or mapping.get("total_score") or 0.0),
            category=str(mapping.get("category") or name),
            timestamp=self._best_timestamp(mapping, fallback=now),
        )

    def _extract_price_snapshot(self, payload: dict[str, Any], bar: dict[str, Any]) -> PriceSnapshot | None:
        source = payload.get("price")
        if isinstance(source, PriceSnapshot):
            return source
        source_map = self._coerce_mapping(source)
        bar_map = self._coerce_mapping(bar)
        current = self._to_float(source_map.get("current", bar_map.get("close")))
        open_ = self._to_float(source_map.get("open", bar_map.get("open")))
        high = self._to_float(source_map.get("high", bar_map.get("high")))
        low = self._to_float(source_map.get("low", bar_map.get("low")))
        if current == open_ == high == low == 0.0:
            return None
        atr = self._to_float(source_map.get("atr") or payload.get("atr") or bar_map.get("bar_range"))
        if atr <= 0.0 and high > low:
            atr = high - low
        session_change_pct = self._to_float(
            source_map.get("session_change_pct")
            or payload.get("session_change_pct")
            or self._percent_change(current, open_)
        )
        return PriceSnapshot(
            current=current,
            open=open_,
            high=high,
            low=low,
            atr=atr,
            session_change_pct=session_change_pct,
        )

    def _coerce_chart_analysis(self, value: Any) -> ChartAnalysis | None:
        if isinstance(value, ChartAnalysis):
            return value
        mapping = self._coerce_mapping(value)
        if not mapping:
            return None
        mad_levels: list[MADLevel] = []
        for item in mapping.get("mad_levels", []):
            if isinstance(item, MADLevel):
                mad_levels.append(item)
            elif isinstance(item, dict):
                mad_levels.append(
                    MADLevel(
                        price=self._to_float(item.get("price")),
                        label=str(item.get("label") or ""),
                        level_type=str(item.get("level_type") or item.get("type") or ""),
                    )
                )
        return ChartAnalysis(
            mad_levels=tuple(mad_levels),
            price_action=str(mapping.get("price_action") or ""),
            visual_patterns=tuple(str(x) for x in mapping.get("visual_patterns", ()) if str(x)),
            support_resistance=tuple(float(x) for x in mapping.get("support_resistance", ()) if isinstance(x, (int, float))),
            confidence=self._to_float(mapping.get("confidence")),
            raw_analysis=str(mapping.get("raw_analysis") or ""),
        )

    def _coerce_gex_summary(self, value: Any) -> GEXSummary | None:
        if isinstance(value, GEXSummary):
            return value
        if value is None:
            return None
        regime = getattr(value, "regime", None)
        regime_text = getattr(regime, "name", regime) or "unknown"
        return GEXSummary(
            call_wall=self._to_float(getattr(value, "call_wall", None)),
            put_wall=self._to_float(getattr(value, "put_wall", None)),
            gamma_flip=self._to_float(getattr(value, "gamma_flip", None)),
            hvl=self._to_float(getattr(value, "hvl", None)),
            regime=str(regime_text).lower(),
        )

    def _coerce_kronos_bias(self, value: Any) -> KronosBias | None:
        if isinstance(value, KronosBias):
            return value
        if value is None:
            return None
        raw_direction = getattr(value, "direction", None)
        if isinstance(raw_direction, str):
            direction = raw_direction.lower()
        else:
            direction = self._direction_label(self._normalize_direction(raw_direction)).lower()
        return KronosBias(
            direction=direction,
            confidence=self._to_float(getattr(value, "confidence", None)),
        )

    def _gex_stale(self, value: Any, age: float, interval: float) -> bool:
        if value is None:
            return True
        if bool(getattr(value, "stale", False)):
            return True
        return age > interval * 2

    def _build_prompt_lines(self, context: MarketContext, created_at: float, *, history_mode: str) -> list[str]:
        dt_label = datetime.fromtimestamp(created_at, tz=_ET).strftime("%Y-%m-%d %I:%M:%S %p")
        lines: list[str] = [
            f"## Current Market State (NQ, {dt_label} ET)",
            self._format_current_market_state(context),
            "",
            "## MAD Levels (from last vision scan)",
            *self._format_mad_levels(),
            "",
            "## Signal Engine (44-signal synthesis)",
            *self._format_signal_engine(context),
            "",
            "## GEX Regime",
            *self._format_gex(context),
            "",
            "## Kronos E10 Bias",
            *self._format_kronos(context),
            "",
            "## Market Internals",
            *self._format_internals(context),
            "",
            "## Economic Calendar",
            *self._format_calendar(context),
            "",
            "## News (last 15 min)",
            *self._format_news(context),
            "",
            "## Options Flow",
            *self._format_options_flow(context),
            "",
            "## Social Sentiment",
            *self._format_sentiment(context),
        ]
        history_lines = self._format_history(history_mode)
        if history_lines:
            lines.extend(["", "## Recent Context History", *history_lines])
        return lines

    def _format_current_market_state(self, context: MarketContext) -> str:
        if context.price is None:
            return self._unavailable_line("bridge")
        return (
            f"Price: {context.price.current:.2f} | ATR(14): {context.price.atr:.2f} | "
            f"Session: {context.price.session_change_pct:+.2f}%"
        )

    def _format_mad_levels(self) -> list[str]:
        analysis = self._latest_chart_analysis
        if analysis is None or not analysis.mad_levels:
            return [self._unavailable_line("chart_analysis")]
        lines: list[str] = []
        for level in analysis.mad_levels[:6]:
            suffix = f" ({level.level_type})" if level.level_type else ""
            label = f" - {level.label}" if level.label else ""
            lines.append(f"- {level.price:.2f}{suffix}{label}")
        if analysis.visual_patterns:
            lines.append(f"Patterns: {', '.join(analysis.visual_patterns[:4])}")
        if analysis.price_action:
            lines.append(f"Price action: {analysis.price_action}")
        return lines

    def _format_signal_engine(self, context: MarketContext) -> list[str]:
        score = self._latest_score
        if not score and not context.signals:
            return [self._unavailable_line("bridge")]
        total_score = self._to_float(score.get("total_score"))
        tier = str(score.get("tier") or "QUIET")
        lines = [f"Confluence Score: {total_score:.1f}/100 ({tier} setup)"]
        active_signals = [signal.name for signal in context.signals[:8] if signal.name]
        if not active_signals and score.get("categories_firing"):
            active_signals = [str(name) for name in score.get("categories_firing", [])[:8]]
        lines.append(
            f"Active signals: {', '.join(active_signals) if active_signals else 'none'}"
        )
        return lines

    def _format_gex(self, context: MarketContext) -> list[str]:
        if context.gex is None:
            return [self._unavailable_line("gex")]
        return [
            f"Call wall: {context.gex.call_wall:.2f} | Put wall: {context.gex.put_wall:.2f} | Gamma flip: {context.gex.gamma_flip:.2f}",
            f"Regime: {context.gex.regime}",
        ]

    def _format_kronos(self, context: MarketContext) -> list[str]:
        if context.kronos_bias is None:
            return [self._unavailable_line("kronos")]
        return [
            f"Direction: {context.kronos_bias.direction} | Confidence: {context.kronos_bias.confidence:.1f}%"
        ]

    def _format_internals(self, context: MarketContext) -> list[str]:
        if context.internals is None:
            return [self._unavailable_line("internals")]
        return [
            (
                f"TICK: {context.internals.tick_value:.0f} | "
                f"ADD: {context.internals.add_value:.0f} | "
                f"VOLD: {context.internals.vold_value:.2f}"
            )
        ]

    def _format_calendar(self, context: MarketContext) -> list[str]:
        status = self._status_by_name(context, "calendar")
        if not context.calendar:
            return [self._unavailable_from_status("calendar", status)]
        next_event = self._next_calendar_event(context.calendar)
        if next_event is None:
            return ["No high-relevance event inside the next 2 hours."]
        countdown = self._calendar_countdown(next_event)
        return [f"{next_event.name} ({next_event.impact}) {countdown}"]

    def _format_news(self, context: MarketContext) -> list[str]:
        status = self._status_by_name(context, "news")
        recent = [item for item in context.news if self._is_within_minutes(item.timestamp, 15)]
        if not recent:
            return [self._unavailable_from_status("news", status)]
        lines = []
        for item in recent[:3]:
            lines.append(f"- {item.headline} ({item.source})")
        return lines

    def _format_options_flow(self, context: MarketContext) -> list[str]:
        if context.options_flow is None:
            return [self._unavailable_line("options_flow")]
        snapshot = context.options_flow
        lines = [
            f"Net premium: {snapshot.net_premium:+,.0f} | Put/Call ratio: {snapshot.put_call_ratio:.2f}",
        ]
        trades = snapshot.unusual_trades[:3]
        if not trades:
            lines.append("No unusual trades detected.")
            return lines
        for trade in trades:
            lines.append(
                f"- {trade.sentiment} {trade.trade_type} {trade.strike:.0f} {trade.expiry} premium=${trade.premium:,.0f} vol={trade.volume}"
            )
        return lines

    def _format_sentiment(self, context: MarketContext) -> list[str]:
        if context.sentiment is None:
            return [self._unavailable_line("sentiment")]
        topics = ", ".join(context.sentiment.trending_topics[:3]) or "none"
        return [
            f"Bull: {context.sentiment.bullish_pct:.1f}% | Bear: {context.sentiment.bearish_pct:.1f}% | Topics: {topics}"
        ]

    def _format_history(self, mode: str) -> list[str]:
        if len(self._history) <= 1:
            return []
        entries = list(zip(self._history_timestamps, self._history))[:-1]
        if mode == "minimal":
            entries = entries[-1:]
        elif mode == "compact":
            entries = entries[-2:]
        history_lines: list[str] = []
        for idx, (ts, snapshot) in enumerate(entries, start=1):
            dt_label = datetime.fromtimestamp(ts, tz=_ET).strftime("%I:%M %p")
            price = f"{snapshot.price.current:.2f}" if snapshot.price else "n/a"
            score = self._to_float(self._latest_score.get("total_score")) if idx == len(entries) else 0.0
            signal_count = len(snapshot.signals)
            if mode == "full":
                history_lines.append(
                    f"- {dt_label}: price {price}, signals={signal_count}, gex={snapshot.gex.regime if snapshot.gex else 'n/a'}, score~{score:.1f}"
                )
            else:
                history_lines.append(f"- {dt_label}: price {price}, signals={signal_count}")
        return history_lines

    def _status_by_name(self, context: MarketContext, name: str) -> DataSourceStatus | None:
        for status in context.source_statuses:
            if status.source_name == name:
                return status
        return None

    def _unavailable_line(self, source: str) -> str:
        status = self._status_from_cache(source)
        return self._unavailable_from_status(source, status)

    def _unavailable_from_status(self, source: str, status: DataSourceStatus | None) -> str:
        if status is None or status.last_update <= 0:
            reason = status.error if status and status.error else "no data"
            return f"[UNAVAILABLE: {source} - {reason}]"
        age = self._human_age(max(0.0, time.time() - status.last_update))
        reason = status.error or f"last seen {age} ago"
        return f"[UNAVAILABLE: {source} - {reason}]"

    def _status_from_cache(self, source: str) -> DataSourceStatus | None:
        if source not in self._source_last_seen and source not in self._source_errors:
            return None
        return DataSourceStatus(
            source_name=source,
            last_update=self._source_last_seen.get(source, 0.0),
            is_stale=True,
            error=self._source_errors.get(source),
        )

    def _next_calendar_event(self, events: tuple[CalendarEvent, ...]) -> CalendarEvent | None:
        now = time.time()
        candidates: list[tuple[float, CalendarEvent]] = []
        for event in events:
            event_ts = self._parse_datetime(event.time)
            if event_ts is None:
                continue
            delta = event_ts - now
            if 0 <= delta <= 7200:
                candidates.append((delta, event))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _calendar_countdown(self, event: CalendarEvent) -> str:
        event_ts = self._parse_datetime(event.time)
        if event_ts is None:
            return "time unknown"
        delta = max(0, int(event_ts - time.time()))
        minutes = delta // 60
        return f"in {minutes}m"

    def _parse_datetime(self, value: str) -> float | None:
        for fmt in (
            "%a, %d %b %Y %H:%M:%S %z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                dt = datetime.strptime(value, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                return dt.timestamp()
            except ValueError:
                continue
        return None

    def _is_within_minutes(self, timestamp: float, minutes: int) -> bool:
        if timestamp <= 0:
            return False
        return (time.time() - timestamp) <= (minutes * 60)

    def _best_timestamp(self, *values: Any, fallback: float = 0.0) -> float:
        for value in values:
            if value is None:
                continue
            for key in ("timestamp", "ts", "last_update", "_last_fetch", "_last_fetch_at"):
                candidate = getattr(value, key, None)
                if candidate is None and isinstance(value, dict):
                    candidate = value.get(key)
                if candidate is None:
                    continue
                if hasattr(candidate, "timestamp"):
                    try:
                        return float(candidate.timestamp())
                    except Exception:
                        continue
                try:
                    number = float(candidate)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(number) and number > 0:
                    return number
        return fallback

    def _estimate_tokens(self, text: str) -> int:
        return math.ceil(len(text) / 4)

    def _human_age(self, seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        if seconds < 3600:
            return f"{int(seconds // 60)}m"
        return f"{int(seconds // 3600)}h"

    def _latest_known_price(self, default: float = 0.0) -> float:
        if not self._history:
            return default
        latest = self._history[-1].price
        if latest is None:
            return default
        return latest.current

    def _normalize_direction(self, value: Any) -> int:
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"1", "long", "bull", "bullish", "up"}:
                return 1
            if text in {"-1", "short", "bear", "bearish", "down"}:
                return -1
            return 0
        try:
            number = int(value)
        except (TypeError, ValueError):
            return 0
        return 1 if number > 0 else -1 if number < 0 else 0

    def _direction_label(self, value: int) -> str:
        if value > 0:
            return "bullish"
        if value < 0:
            return "bearish"
        return "neutral"

    def _to_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _percent_change(self, current: float, baseline: float) -> float:
        if baseline == 0.0:
            return 0.0
        return ((current - baseline) / baseline) * 100.0


__all__ = ["ContextAggregator"]
