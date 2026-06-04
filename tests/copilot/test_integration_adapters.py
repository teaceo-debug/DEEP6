"""Integration tests for copilot data adapters.

Tests real adapter logic with mocked external services (HTTP, TCP, feeds).
No real network calls are made.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deep6.copilot.adapters.calendar import EconomicCalendarAdapter
from deep6.copilot.adapters.news import NewsFeedAdapter
from deep6.copilot.adapters.options_flow import OptionsFlowAdapter
from deep6.copilot.types import SentimentSnapshot


# ---------------------------------------------------------------------------
# Calendar adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calendar_adapter_offline():
    """Calendar adapter returns [] when feed fetch raises ConnectionError."""
    adapter = EconomicCalendarAdapter()

    mock_feed = MagicMock()
    mock_feed.get.return_value = []  # no entries

    with patch("deep6.copilot.adapters.calendar.httpx") as mock_httpx, \
         patch("deep6.copilot.adapters.calendar.feedparser") as mock_fp:
        # Simulate network failure
        client_cm = AsyncMock()
        client_cm.get = AsyncMock(side_effect=ConnectionError("offline"))
        mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=client_cm)
        mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

        events = await adapter.fetch_today_events()

    assert isinstance(events, list)
    # Empty cache + failed fetch → empty list
    assert events == []


# ---------------------------------------------------------------------------
# News adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_news_adapter_deduplication():
    """News adapter deduplicates identical headlines from mock feed."""
    adapter = NewsFeedAdapter(sources=[("TestFeed", "https://test.example.com/rss")])

    # Build a mock httpx response whose .content feedparser can parse
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.content = b"<rss></rss>"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    # feedparser returns duplicate entries
    duplicate_entry = MagicMock()
    duplicate_entry.title = "Fed Holds Rates Steady"
    duplicate_entry.link = "https://example.com/article"
    duplicate_entry.published_parsed = None
    duplicate_entry.updated_parsed = None
    duplicate_entry.created_parsed = None
    duplicate_entry.published = ""
    duplicate_entry.updated = ""
    duplicate_entry.created = ""

    mock_parsed = MagicMock()
    mock_parsed.entries = [duplicate_entry, duplicate_entry, duplicate_entry]

    with patch("deep6.copilot.adapters.news.httpx") as mock_httpx, \
         patch("deep6.copilot.adapters.news.feedparser") as mock_fp:
        mock_httpx.AsyncClient.return_value = mock_client
        mock_fp.parse.return_value = mock_parsed

        items = await adapter.fetch_latest()

    # Three identical headlines → only 1 after dedup
    assert len(items) == 1
    assert items[0].headline == "Fed Holds Rates Steady"


# ---------------------------------------------------------------------------
# Sentiment adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sentiment_snapshot_combined():
    """Sentiment adapter combines StockTwits + Reddit into coherent percentages."""
    from deep6.copilot.adapters.sentiment import SentimentAdapter

    # Mock StockTwits response with bullish messages
    stocktwits_payload = {
        "messages": [
            {"entities": {"sentiment": {"basic": "Bullish"}}},
            {"entities": {"sentiment": {"basic": "Bullish"}}},
            {"entities": {"sentiment": {"basic": "Bearish"}}},
        ]
    }

    # Mock Reddit response with mixed sentiment
    reddit_payload = {
        "data": {
            "children": [
                {"data": {"title": "NQ to the moon! Bull run confirmed"}},
                {"data": {"title": "Market crash incoming sell everything"}},
            ]
        }
    }

    call_count = 0

    async def mock_get(url: str, **kwargs):
        nonlocal call_count
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()

        if "stocktwits" in url:
            resp.json.return_value = stocktwits_payload
        elif "reddit" in url:
            resp.json.return_value = reddit_payload
        else:
            resp.json.return_value = {}
        call_count += 1
        return resp

    adapter = SentimentAdapter()
    adapter._client = MagicMock()
    adapter._client.get = mock_get
    adapter._client.aclose = AsyncMock()

    snapshot = await adapter.fetch_sentiment(symbols=("NQ",))

    assert isinstance(snapshot, SentimentSnapshot)
    assert snapshot.bullish_pct + snapshot.bearish_pct == pytest.approx(100.0, abs=0.1)
    assert snapshot.volume > 0
    await adapter.aclose()


# ---------------------------------------------------------------------------
# Options flow adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_options_flow_missing_key():
    """Options flow adapter returns empty snapshot when no API key is set."""
    with patch.dict("os.environ", {}, clear=False):
        # Ensure no API key env vars are set
        import os
        orig_massive = os.environ.pop("MASSIVE_API_KEY", None)
        orig_flash = os.environ.pop("FLASHALPHA_API_KEY", None)

        try:
            adapter = OptionsFlowAdapter(api_key="")
            async with adapter:
                snapshot = await adapter.fetch_flow("NQ")

            # Should return a default snapshot, not raise
            assert snapshot is not None
            assert snapshot.unusual_trades == []
            assert snapshot.net_premium == 0.0
        finally:
            if orig_massive is not None:
                os.environ["MASSIVE_API_KEY"] = orig_massive
            if orig_flash is not None:
                os.environ["FLASHALPHA_API_KEY"] = orig_flash


# ---------------------------------------------------------------------------
# Market Internals adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_internals_bridge_offline():
    """MarketInternals adapter handles DataBridge offline without hanging."""
    from deep6.copilot.adapters.internals import MarketInternalsAdapter

    adapter = MarketInternalsAdapter()

    # Connect to a port that's not listening — should not hang
    # We use a very short timeout by patching the backoff constants
    with patch("deep6.copilot.adapters.internals._BACKOFF_INITIAL", 0.01), \
         patch("deep6.copilot.adapters.internals._BACKOFF_MAX", 0.02):

        await adapter.connect("127.0.0.1", 19999)
        # Let it attempt one connection cycle
        await asyncio.sleep(0.05)
        await adapter.disconnect()

    # Should not crash; current snapshot is None (never connected)
    assert adapter.get_current() is None
    assert adapter.connected is False
