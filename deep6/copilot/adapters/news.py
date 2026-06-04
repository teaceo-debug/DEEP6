"""News feed adapter for headline aggregation and scoring."""

from __future__ import annotations

import asyncio
import calendar as _calendar
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Iterable

try:
    import feedparser  # type: ignore
except Exception:  # pragma: no cover - optional dependency at import time
    feedparser = None  # type: ignore

try:
    import httpx  # type: ignore
except Exception:  # pragma: no cover - optional dependency at import time
    httpx = None  # type: ignore

from deep6.copilot.types import NewsItem

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _FeedSource:
    name: str
    url: str


class NewsFeedAdapter:
    """Aggregate, dedupe, and score RSS headlines."""

    POLL_INTERVAL_SECONDS = 120

    _DEFAULT_SOURCES: tuple[_FeedSource, ...] = (
        _FeedSource("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
        _FeedSource("MarketWatch", "https://feeds.marketwatch.com/marketwatch/topstories/"),
        _FeedSource("Yahoo Finance", "https://feeds.finance.yahoo.com/rss/2.0/headline"),
    )

    _HIGH_RELEVANCE_THRESHOLD = 0.8

    _RELEVANCE_RULES: tuple[tuple[tuple[str, ...], float], ...] = (
        (("fed", "fomc", "rate", "inflation"), 0.9),
        (("tech", "nasdaq", "qqq", "semiconductor", "ai"), 0.8),
        (("earnings",), 0.6),
    )

    def __init__(self, sources: Iterable[tuple[str, str]] | None = None) -> None:
        self._sources = tuple(_FeedSource(name, url) for name, url in (sources or ((s.name, s.url) for s in self._DEFAULT_SOURCES)))
        self._cache: list[NewsItem] = []
        self._last_fetch_at: datetime | None = None

    async def fetch_latest(self, limit: int = 20) -> list[NewsItem]:
        """Fetch the latest RSS headlines, dedupe, score, and cache them."""

        if httpx is None or feedparser is None:
            logger.warning("news feed dependencies unavailable; returning cached results")
            return self._cache[:limit]

        if self._is_cache_fresh() and self._cache:
            return self._cache[:limit]

        items: list[NewsItem] = []
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            tasks = [self._fetch_source(client, source) for source in self._sources]
            for result in await asyncio.gather(*tasks, return_exceptions=True):
                if isinstance(result, Exception):
                    logger.warning("news source fetch failed: %s", result)
                    continue
                items.extend(result)

        deduped = self._dedupe_and_sort(items)
        self._cache = deduped
        self._last_fetch_at = datetime.now(tz=UTC)
        return deduped[:limit]

    def get_breaking(self, since_minutes: int = 5) -> list[NewsItem]:
        """Return the highest relevance recent items from the cache."""

        if not self._cache and self._can_run_sync_refresh():
            asyncio.run(self.fetch_latest())
        elif not self._is_cache_fresh() and self._can_run_sync_refresh():
            asyncio.run(self.fetch_latest())

        cutoff = datetime.now(tz=UTC) - timedelta(minutes=since_minutes)
        breaking: list[NewsItem] = []
        for item in self._cache:
            item_time = self._parse_iso_timestamp(item.timestamp)
            if item_time is None or item_time < cutoff:
                continue
            score = self._relevance_score(item.headline, item.source)
            if score >= self._HIGH_RELEVANCE_THRESHOLD:
                breaking.append(item)
        return breaking

    async def _fetch_source(self, client: "httpx.AsyncClient", source: _FeedSource) -> list[NewsItem]:
        try:
            response = await client.get(source.url)
            response.raise_for_status()
        except Exception as exc:
            logger.warning("news source request failed (%s): %s", source.name, exc)
            return []

        parsed = feedparser.parse(response.content)
        entries = getattr(parsed, "entries", []) or []
        items: list[NewsItem] = []
        for entry in entries:
            headline = self._clean_text(getattr(entry, "title", ""))
            if not headline:
                continue
            url = self._clean_text(getattr(entry, "link", ""))
            timestamp = self._entry_timestamp(entry)
            items.append(NewsItem(headline=headline, source=source.name, timestamp=timestamp, url=url))
        return items

    def _dedupe_and_sort(self, items: Iterable[NewsItem]) -> list[NewsItem]:
        seen: set[str] = set()
        deduped: list[NewsItem] = []
        for item in items:
            key = self._normalize_headline(item.headline)
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        deduped.sort(key=self._sort_key, reverse=True)
        return deduped

    def _sort_key(self, item: NewsItem) -> datetime:
        parsed = self._parse_iso_timestamp(item.timestamp)
        return parsed if parsed is not None else datetime.now(tz=UTC)

    def _entry_timestamp(self, entry: object) -> float:
        for attr in ("published_parsed", "updated_parsed", "created_parsed"):
            parsed = getattr(entry, attr, None)
            if parsed:
                try:
                    return float(_calendar.timegm(parsed))
                except Exception:
                    continue

        for attr in ("published", "updated", "created"):
            value = getattr(entry, attr, "")
            dt = self._parse_date(value)
            if dt is not None:
                return dt.timestamp()

        return datetime.now(tz=UTC).timestamp()

    def _parse_date(self, value: object) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value.astimezone(UTC)
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except Exception:
            return None

    def _parse_iso_timestamp(self, value: float | int | str) -> datetime | None:
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value), tz=UTC)
            except Exception:
                return None
        return self._parse_date(value)

    def _relevance_score(self, headline: str, source: str) -> float:
        text = f"{headline} {source}".lower()
        for keywords, score in self._RELEVANCE_RULES:
            if any(keyword in text for keyword in keywords):
                return score
        return 0.3

    def _normalize_headline(self, headline: str) -> str:
        normalized = re.sub(r"[^a-z0-9\s]+", "", headline.lower())
        return re.sub(r"\s+", " ", normalized).strip()

    def _clean_text(self, value: object) -> str:
        if not value:
            return ""
        text = str(value).strip()
        text = re.sub(r"\s+", " ", text)
        return text

    def _is_cache_fresh(self) -> bool:
        if self._last_fetch_at is None:
            return False
        return (datetime.now(tz=UTC) - self._last_fetch_at).total_seconds() < self.POLL_INTERVAL_SECONDS

    def _can_run_sync_refresh(self) -> bool:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return True
        return False


__all__ = ["NewsFeedAdapter"]
