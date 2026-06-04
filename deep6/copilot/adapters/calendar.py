"""Economic calendar adapter with event countdown support."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Sequence

try:
    import feedparser  # type: ignore
except Exception:
    feedparser = None  # type: ignore

try:
    import httpx  # type: ignore
except Exception:
    httpx = None  # type: ignore

from deep6.copilot.types import CalendarEvent

logger = logging.getLogger(__name__)

# NQ-relevance mapping: keyword -> relevance score
_RELEVANCE_MAP: dict[str, float] = {
    "fomc": 1.0, "federal reserve": 1.0, "fed rate": 1.0, "fed decision": 1.0,
    "cpi": 0.9, "consumer price": 0.9,
    "ppi": 0.9, "producer price": 0.9,
    "nonfarm": 0.9, "non-farm": 0.9, "nfp": 0.9, "payroll": 0.9,
    "gdp": 0.9, "gross domestic": 0.9,
    "fed speak": 0.7, "powell": 0.7, "waller": 0.7, "williams": 0.7,
    "bostic": 0.7, "daly": 0.7, "goolsbee": 0.7, "barkin": 0.7,
    "pmi": 0.5, "ism": 0.5, "manufacturing": 0.5,
    "jobless": 0.6, "unemployment": 0.6, "claims": 0.6,
    "retail sales": 0.7, "housing": 0.4, "consumer confidence": 0.5,
}


def _score_relevance(name: str) -> float:
    lower = name.lower()
    best = 0.3  # default
    for keyword, score in _RELEVANCE_MAP.items():
        if keyword in lower:
            best = max(best, score)
    return best


class EconomicCalendarAdapter:
    """Fetches economic calendar events and provides countdown support."""

    POLL_INTERVAL_SECONDS = 300  # 5 minutes

    _CALENDAR_FEEDS: tuple[str, ...] = (
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^IXIC&region=US&lang=en-US",
    )

    def __init__(self) -> None:
        self._cache: list[CalendarEvent] = []
        self._last_fetch: float = 0.0
        self._task: asyncio.Task[None] | None = None

    async def fetch_today_events(self) -> list[CalendarEvent]:
        """Fetch economic events. Returns cached data on failure."""
        now = datetime.now(UTC).timestamp()
        if self._cache and (now - self._last_fetch) < self.POLL_INTERVAL_SECONDS:
            return list(self._cache)

        events: list[CalendarEvent] = []
        try:
            if feedparser is None:
                logger.warning("feedparser not installed; returning cached events")
                return list(self._cache) if self._cache else []

            for url in self._CALENDAR_FEEDS:
                try:
                    if httpx is not None:
                        async with httpx.AsyncClient(timeout=10.0) as client:
                            resp = await client.get(url)
                            feed = feedparser.parse(resp.content)
                    else:
                        feed = feedparser.parse(url)

                    for entry in feed.get("entries", []):
                        title = entry.get("title", "")
                        pub = entry.get("published", "")
                        events.append(CalendarEvent(
                            name=title,
                            time=pub,
                            impact="high" if _score_relevance(title) >= 0.8 else "medium",
                            nq_relevance=_score_relevance(title),
                        ))
                except Exception:
                    logger.warning("Failed to fetch calendar feed: %s", url, exc_info=True)

            if events:
                self._cache = events
                self._last_fetch = now
        except Exception:
            logger.warning("Calendar fetch failed, returning cached", exc_info=True)

        return list(self._cache) if self._cache else []

    def get_upcoming(self, minutes: int = 60) -> list[CalendarEvent]:
        """Filter cached events to those within the next N minutes."""
        if not self._cache:
            return []
        now = datetime.now(UTC)
        cutoff = now + timedelta(minutes=minutes)
        results: list[CalendarEvent] = []
        for event in self._cache:
            try:
                # Try parsing various time formats
                for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
                    try:
                        event_time = datetime.strptime(event.time, fmt)
                        if event_time.tzinfo is None:
                            event_time = event_time.replace(tzinfo=UTC)
                        if now <= event_time <= cutoff:
                            results.append(event)
                        break
                    except ValueError:
                        continue
            except Exception:
                continue
        return results

    def get_active_countdown(self) -> str | None:
        """Return countdown string for nearest high-impact event, e.g. 'FOMC in 22 min'."""
        upcoming = self.get_upcoming(minutes=120)
        high_impact = [e for e in upcoming if e.nq_relevance >= 0.7]
        if not high_impact:
            return None

        now = datetime.now(UTC)
        best_event: CalendarEvent | None = None
        best_minutes: float = float("inf")

        for event in high_impact:
            for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
                try:
                    event_time = datetime.strptime(event.time, fmt)
                    if event_time.tzinfo is None:
                        event_time = event_time.replace(tzinfo=UTC)
                    delta = (event_time - now).total_seconds() / 60
                    if 0 < delta < best_minutes:
                        best_minutes = delta
                        best_event = event
                    break
                except ValueError:
                    continue

        if best_event is None:
            return None
        return f"{best_event.name} in {int(best_minutes)} min"

    async def start_polling(self) -> None:
        """Start background polling loop."""
        async def _loop() -> None:
            while True:
                await self.fetch_today_events()
                await asyncio.sleep(self.POLL_INTERVAL_SECONDS)
        self._task = asyncio.create_task(_loop())

    async def stop(self) -> None:
        """Stop background polling."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
