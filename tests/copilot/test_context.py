from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from deep6.copilot.context import ContextAggregator
from deep6.copilot.types import (
    CalendarEvent,
    ChartAnalysis,
    MADLevel,
    MarketInternals,
    NewsItem,
    OptionsFlowSnapshot,
    SentimentSnapshot,
    UnusualTrade,
)


class FakeBridgeClient:
    def __init__(self) -> None:
        now = datetime.now(tz=UTC).timestamp()
        self.latest_context = {
            "bar": {
                "ts": now,
                "open": 21000.0,
                "high": 21020.0,
                "low": 20990.0,
                "close": 21010.0,
                "bar_range": 18.0,
            },
            "price": {
                "current": 21010.0,
                "open": 21000.0,
                "high": 21020.0,
                "low": 20990.0,
                "atr": 24.5,
                "session_change_pct": 0.8,
            },
            "score": {
                "timestamp": now,
                "total_score": 82.0,
                "tier": "TYPE_A",
                "direction": 1,
                "categories_firing": ["absorption", "delta", "auction"],
            },
            "signal": {
                "timestamp": now,
                "narrative": "ABSORBED @ MAD support",
                "direction": 1,
                "categories_firing": ["absorption", "delta"],
            },
        }


class FakeCalendarAdapter:
    POLL_INTERVAL_SECONDS = 300

    async def fetch_today_events(self) -> list[CalendarEvent]:
        event_time = (datetime.now(tz=UTC) + timedelta(minutes=45)).strftime("%Y-%m-%d %H:%M:%S")
        return [CalendarEvent(name="FOMC Minutes", time=event_time, impact="high", nq_relevance=1.0)]


class FakeNewsAdapter:
    POLL_INTERVAL_SECONDS = 120

    async def fetch_latest(self, limit: int = 20) -> list[NewsItem]:
        now = datetime.now(tz=UTC).timestamp()
        return [
            NewsItem(headline="Fed official flags inflation risk", source="CNBC", timestamp=now, nq_relevance_score=0.9),
            NewsItem(headline="AI rally lifts Nasdaq futures", source="MarketWatch", timestamp=now - 60, nq_relevance_score=0.85),
        ][:limit]


class FakeSentimentAdapter:
    async def fetch_sentiment(self) -> SentimentSnapshot:
        return SentimentSnapshot(bullish_pct=63.0, bearish_pct=37.0, volume=123, trending_topics=("nq", "ai", "fed"), timestamp=datetime.now(tz=UTC).timestamp())


class FakeInternalsAdapter:
    def get_current(self) -> MarketInternals:
        return MarketInternals(tick_value=650, tick_direction="bullish", add_value=1200, add_direction="bullish", vold_value=1.9, vold_ratio=1.9, timestamp=datetime.now(tz=UTC).timestamp())


class FakeOptionsFlowAdapter:
    async def fetch_flow(self) -> OptionsFlowSnapshot:
        trade = UnusualTrade(strike=21000, expiry="2026-05-15", trade_type="call", premium=250000, volume=400, oi_ratio=2.5, sentiment="bullish")
        return OptionsFlowSnapshot(unusual_trades=[trade], net_premium=125000.0, put_call_ratio=0.72, largest_trade=trade, timestamp=datetime.now(tz=UTC).timestamp())


class FakeVisionProvider:
    def get_latest_analysis(self) -> ChartAnalysis:
        return ChartAnalysis(
            mad_levels=(
                MADLevel(price=20980.0, label="MAD Support", level_type="support"),
                MADLevel(price=21035.0, label="MAD Resistance", level_type="resistance"),
            ),
            price_action="Holding above support",
            visual_patterns=("coil", "higher low"),
            confidence=0.91,
            raw_analysis="Vision snapshot",
        )


class FakeGexAdapter:
    staleness_seconds = 300
    _levels = type(
        "Levels",
        (),
        {
            "call_wall": 21100.0,
            "put_wall": 20900.0,
            "gamma_flip": 21020.0,
            "hvl": 21050.0,
            "regime": type("Regime", (), {"name": "POSITIVE_DAMPENING"})(),
            "timestamp": datetime.now(tz=UTC).timestamp(),
            "stale": False,
        },
    )()

    def get_levels(self):
        return self._levels


class FakeKronosAdapter:
    inference_interval = 5

    async def get_bias(self):
        return type("Bias", (), {"direction": 1, "confidence": 74.0, "timestamp": datetime.now(tz=UTC).timestamp()})()


@pytest.mark.asyncio
async def test_build_context_collects_available_sources() -> None:
    aggregator = ContextAggregator(
        bridge_client=FakeBridgeClient(),
        calendar_adapter=FakeCalendarAdapter(),
        news_adapter=FakeNewsAdapter(),
        sentiment_adapter=FakeSentimentAdapter(),
        internals_adapter=FakeInternalsAdapter(),
        options_flow_adapter=FakeOptionsFlowAdapter(),
        gex_adapter=FakeGexAdapter(),
        kronos_adapter=FakeKronosAdapter(),
        chart_analysis_provider=FakeVisionProvider(),
    )

    context = await aggregator.build_context()

    assert context.price is not None
    assert context.price.current == 21010.0
    assert context.gex is not None
    assert context.gex.regime == "positive_dampening"
    assert context.kronos_bias is not None
    assert context.kronos_bias.direction == "bullish"
    assert len(context.signals) == 3
    assert len(aggregator._history) == 1

    prompt = aggregator.format_for_llm(context)
    assert "## Current Market State" in prompt
    assert "## MAD Levels" in prompt
    assert "Confluence Score: 82.0/100 (TYPE_A setup)" in prompt
    assert "FOMC Minutes" in prompt


@pytest.mark.asyncio
async def test_build_context_gracefully_degrades_on_source_failure() -> None:
    class BrokenNewsAdapter:
        POLL_INTERVAL_SECONDS = 120

        async def fetch_latest(self, limit: int = 20):
            raise RuntimeError("feed down")

    aggregator = ContextAggregator(
        bridge_client=FakeBridgeClient(),
        news_adapter=BrokenNewsAdapter(),
        internals_adapter=FakeInternalsAdapter(),
    )

    context = await aggregator.build_context()
    prompt = aggregator.format_for_llm(context)

    news_status = next(status for status in context.source_statuses if status.source_name == "news")
    assert news_status.is_stale is True
    assert news_status.error == "feed down"
    assert "[UNAVAILABLE: news - feed down]" in prompt
    assert context.internals is not None


@pytest.mark.asyncio
async def test_format_for_llm_stays_under_budget_with_history() -> None:
    aggregator = ContextAggregator(
        bridge_client=FakeBridgeClient(),
        chart_analysis_provider=FakeVisionProvider(),
        token_budget=400,
    )

    for _ in range(6):
        await aggregator.build_context()

    prompt = aggregator.format_for_llm()

    assert len(aggregator._history) == 5
    assert len(prompt) <= 1600
    assert "## Recent Context History" in prompt
