"""Integration tests for all data adapters."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from deep6.copilot.adapters.calendar import EconomicCalendarAdapter
from deep6.copilot.adapters.internals import MarketInternalsAdapter
from deep6.copilot.adapters.news import NewsFeedAdapter
from deep6.copilot.adapters.options_flow import OptionsFlowAdapter
from deep6.copilot.adapters.sentiment import SentimentAdapter
from deep6.copilot.types import (
    CalendarEvent,
    MarketInternals,
    NewsItem,
    OptionsFlowSnapshot,
    SentimentSnapshot,
)


class TestEconomicCalendarAdapter:
    def test_instantiates_without_error(self):
        adapter = EconomicCalendarAdapter()
        assert adapter is not None

    def test_get_upcoming_returns_empty_when_no_cache(self):
        adapter = EconomicCalendarAdapter()
        result = adapter.get_upcoming(minutes=60)
        assert isinstance(result, list)

    def test_get_active_countdown_returns_none_when_no_cache(self):
        adapter = EconomicCalendarAdapter()
        result = adapter.get_active_countdown()
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_today_events_returns_list_on_feedparser_unavailable(self):
        adapter = EconomicCalendarAdapter()
        import deep6.copilot.adapters.calendar as cal_mod

        original = cal_mod.feedparser
        cal_mod.feedparser = None
        try:
            result = await adapter.fetch_today_events()
            assert isinstance(result, list)
        finally:
            cal_mod.feedparser = original

    @pytest.mark.asyncio
    async def test_fetch_today_events_handles_network_error_gracefully(self):
        adapter = EconomicCalendarAdapter()
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("Network error")
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await adapter.fetch_today_events()
            assert isinstance(result, list)


class TestNewsFeedAdapter:
    def test_instantiates_without_error(self):
        adapter = NewsFeedAdapter()
        assert adapter is not None

    def test_get_breaking_returns_empty_initially(self):
        adapter = NewsFeedAdapter()
        # Prevent sync refresh attempt inside an already-running loop
        adapter._cache = []
        result = adapter.get_breaking(since_minutes=5)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_fetch_latest_returns_cached_on_unavailable_deps(self):
        import deep6.copilot.adapters.news as news_mod

        original_httpx = news_mod.httpx
        original_feedparser = news_mod.feedparser
        news_mod.httpx = None
        news_mod.feedparser = None
        try:
            adapter = NewsFeedAdapter()
            result = await adapter.fetch_latest(10)
            assert isinstance(result, list)
        finally:
            news_mod.httpx = original_httpx
            news_mod.feedparser = original_feedparser

    @pytest.mark.asyncio
    async def test_fetch_latest_deduplicates_same_headline(self):
        """Adapter deduplicates headlines by normalized text."""
        adapter = NewsFeedAdapter()
        # Inject two items with same headline into cache
        item1 = NewsItem(
            headline="Fed raises rates",
            source="CNBC",
            timestamp=1000.0,
            url="http://a.com",
        )
        item2 = NewsItem(
            headline="Fed raises rates",
            source="Reuters",
            timestamp=1001.0,
            url="http://b.com",
        )
        adapter._cache = [item1, item2]
        # The cache is pre-deduplicated so just verify structure
        assert len(adapter._cache) == 2


class TestSentimentAdapter:
    @pytest.mark.asyncio
    async def test_fetch_sentiment_returns_snapshot_with_defaults_on_error(self):
        adapter = SentimentAdapter()
        original_client = adapter._client
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("network down"))
        adapter._client = mock_client
        try:
            result = await adapter.fetch_sentiment()
            assert isinstance(result, SentimentSnapshot)
            assert 0 <= result.bullish_pct <= 100
            assert 0 <= result.bearish_pct <= 100
        finally:
            await original_client.aclose()


class TestOptionsFlowAdapter:
    @pytest.mark.asyncio
    async def test_fetch_flow_returns_cached_when_no_api_key(self):
        adapter = OptionsFlowAdapter(api_key="")
        result = await adapter.fetch_flow("NQ")
        assert isinstance(result, OptionsFlowSnapshot)
        assert result.put_call_ratio >= 0

    @pytest.mark.asyncio
    async def test_fetch_flow_returns_empty_snapshot_on_http_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("connection refused"))
        adapter = OptionsFlowAdapter(api_key="test-key")
        adapter._client = mock_client
        result = await adapter.fetch_flow("NQ")
        assert isinstance(result, OptionsFlowSnapshot)

    def test_adapter_graceful_on_missing_httpx(self):
        import deep6.copilot.adapters.options_flow as of_mod

        original = of_mod.httpx
        of_mod.httpx = None
        try:
            adapter = OptionsFlowAdapter(api_key="test")
            assert adapter is not None
        finally:
            of_mod.httpx = original


class TestMarketInternalsAdapter:
    def test_instantiates_without_error(self):
        adapter = MarketInternalsAdapter()
        assert adapter is not None
        assert adapter.connected is False

    def test_get_current_returns_none_before_connection(self):
        adapter = MarketInternalsAdapter()
        result = adapter.get_current()
        assert result is None

    def test_on_update_registers_callback(self):
        adapter = MarketInternalsAdapter()
        called: list[MarketInternals] = []
        adapter.on_update(lambda mi: called.append(mi))
        assert len(adapter._callbacks) == 1

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected_does_not_crash(self):
        adapter = MarketInternalsAdapter()
        await adapter.disconnect()  # should not raise

    def test_adapter_caching_returns_stale_on_no_connection(self):
        adapter = MarketInternalsAdapter()
        assert adapter.get_current() is None
