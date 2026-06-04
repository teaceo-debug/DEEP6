"""Async news sentiment + economic calendar engine.

Primary source: Finnhub API (single key covers news + calendar).
Fallback: Alpha Vantage NEWS_SENTIMENT for QQQ/NDX.

Environment variables:
    FINNHUB_API_KEY   — Required. Free tier: 60 calls/min.
    ALPHAVANTAGE_KEY  — Optional fallback.

Usage:
    async with NewsEngine() as engine:
        news, events = await engine.fetch_all()
        conf_mult = compute_macro_confidence_multiplier(events)
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiohttp

from deep6.bias_engine.models import MacroEvent, NewsItem

_FINNHUB = "https://finnhub.io/api/v1"
_AV      = "https://www.alphavantage.co/query"

# Events whose names trigger HIGH impact classification
_HIGH_IMPACT = {
    "FOMC", "Federal Reserve", "Fed", "CPI", "Consumer Price",
    "NFP", "Nonfarm", "Payroll", "PPI", "Producer Price",
    "GDP", "PCE", "Personal Consumption", "Unemployment",
    "Jobless", "ISM", "Retail Sales",
}

# NQ proxy symbols — QQQ is the best single proxy for Nasdaq-100
_NQ_PROXIES = ["QQQ", "NDX"]


class NewsEngine:
    """Async context manager for news + sentiment + macro calendar."""

    def __init__(self) -> None:
        self._fh_key = os.getenv("FINNHUB_API_KEY", "")
        self._av_key = os.getenv("ALPHAVANTAGE_KEY", "")
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "NewsEngine":
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._session:
            await self._session.close()

    # ──────────────────────────────────────────────────────────────────
    # News + Sentiment
    # ──────────────────────────────────────────────────────────────────

    async def get_news_sentiment(self) -> list[NewsItem]:
        """Fetch last 6h of news for NQ proxies, scored by Finnhub sentiment."""
        if not self._fh_key:
            return await self._av_news_sentiment() if self._av_key else []

        now = datetime.now(tz=timezone.utc)
        start = now - timedelta(hours=6)
        items: list[NewsItem] = []

        # Fetch sentiment score first (single call per symbol)
        sentiment_cache: dict[str, float] = {}
        for sym in _NQ_PROXIES[:1]:  # QQQ only — avoids rate limit
            sentiment_cache[sym] = await self._fh_sentiment_score(sym)

        # Fetch recent headlines
        for sym in _NQ_PROXIES[:1]:
            try:
                params = {
                    "symbol": sym,
                    "from": start.strftime("%Y-%m-%d"),
                    "to": now.strftime("%Y-%m-%d"),
                    "token": self._fh_key,
                }
                async with self._session.get(f"{_FINNHUB}/company-news", params=params) as r:
                    if r.status != 200:
                        continue
                    articles = await r.json()

                score = sentiment_cache.get(sym, 0.0)
                for art in articles[:6]:
                    headline = art.get("headline", "").strip()
                    if not headline:
                        continue
                    items.append(NewsItem(
                        headline=headline,
                        source=art.get("source", "finnhub"),
                        sentiment=score,
                        sentiment_label=_score_label(score),
                        published_at=datetime.fromtimestamp(
                            art.get("datetime", now.timestamp()), tz=timezone.utc
                        ),
                        url=art.get("url", ""),
                    ))
            except Exception:
                continue

        # Deduplicate by headline
        seen: set[str] = set()
        unique: list[NewsItem] = []
        for item in items:
            key = item.headline[:60]
            if key not in seen:
                seen.add(key)
                unique.append(item)

        return unique[:10]

    async def _fh_sentiment_score(self, symbol: str) -> float:
        """Return Finnhub news sentiment as -1.0..+1.0 for symbol."""
        try:
            params = {"symbol": symbol, "token": self._fh_key}
            async with self._session.get(f"{_FINNHUB}/news-sentiment", params=params) as r:
                if r.status != 200:
                    return 0.0
                data = await r.json()
                sent = data.get("sentiment", {})
                bull = float(sent.get("bullishPercent", 0.5))
                bear = float(sent.get("bearishPercent", 0.5))
                return bull - bear   # -1.0 to +1.0
        except Exception:
            return 0.0

    async def _av_news_sentiment(self) -> list[NewsItem]:
        """Alpha Vantage NEWS_SENTIMENT fallback for QQQ."""
        try:
            params = {
                "function": "NEWS_SENTIMENT",
                "tickers": "QQQ",
                "limit": "10",
                "sort": "LATEST",
                "apikey": self._av_key,
            }
            async with self._session.get(_AV, params=params) as r:
                if r.status != 200:
                    return []
                data = await r.json()

            items: list[NewsItem] = []
            for art in data.get("feed", [])[:8]:
                raw_score = float(art.get("overall_sentiment_score", 0))
                label = art.get("overall_sentiment_label", "Neutral").lower()
                try:
                    pub = datetime.strptime(
                        art.get("time_published", ""), "%Y%m%dT%H%M%S"
                    ).replace(tzinfo=timezone.utc)
                except Exception:
                    pub = datetime.now(tz=timezone.utc)
                items.append(NewsItem(
                    headline=art.get("title", "")[:120],
                    source=art.get("source", "alphavantage"),
                    sentiment=raw_score,
                    sentiment_label=label,
                    published_at=pub,
                    url=art.get("url", ""),
                ))
            return items
        except Exception:
            return []

    # ──────────────────────────────────────────────────────────────────
    # Economic Calendar
    # ──────────────────────────────────────────────────────────────────

    async def get_macro_events(self, lookahead_hours: int = 24) -> list[MacroEvent]:
        """Fetch upcoming economic events via Finnhub calendar."""
        if not self._fh_key:
            return []

        now = datetime.now(tz=timezone.utc)
        end = now + timedelta(hours=lookahead_hours)

        try:
            params = {
                "from": now.strftime("%Y-%m-%d"),
                "to": end.strftime("%Y-%m-%d"),
                "token": self._fh_key,
            }
            async with self._session.get(f"{_FINNHUB}/calendar/economic", params=params) as r:
                if r.status != 200:
                    return []
                data = await r.json()
        except Exception:
            return []

        events: list[MacroEvent] = []
        for ev in data.get("economicCalendar", []):
            name = ev.get("event", "").strip()
            if not name:
                continue
            impact = _classify_impact(name, ev.get("impact", ""))

            try:
                rel_time_str = ev.get("time", "")
                rel_time = datetime.fromisoformat(rel_time_str)
                if rel_time.tzinfo is None:
                    rel_time = rel_time.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            minutes_until = int((rel_time - now).total_seconds() / 60)
            if minutes_until < -120:  # Skip events more than 2h in the past
                continue

            events.append(MacroEvent(
                name=name,
                release_time=rel_time,
                impact=impact,
                country=ev.get("country", "US"),
                forecast=ev.get("estimate") or None,
                previous=ev.get("prev") or None,
                actual=ev.get("actual") or None,
                minutes_until=minutes_until,
            ))

        events.sort(key=lambda e: e.release_time)
        return events

    # ──────────────────────────────────────────────────────────────────
    # Combined fetch
    # ──────────────────────────────────────────────────────────────────

    async def fetch_all(self) -> tuple[list[NewsItem], list[MacroEvent]]:
        """Fetch news and macro events concurrently. Returns (news, events)."""
        news, events = await asyncio.gather(
            self.get_news_sentiment(),
            self.get_macro_events(),
            return_exceptions=True,
        )
        if isinstance(news, Exception):
            news = []
        if isinstance(events, Exception):
            events = []
        return news, events  # type: ignore[return-value]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def compute_macro_confidence_multiplier(events: list[MacroEvent]) -> float:
    """Return confidence multiplier based on upcoming HIGH-impact events.

    1.0  — no high-impact events nearby
    0.5  — HIGH event within 30 minutes
    0.3  — active release window (±5 minutes)
    """
    for ev in events:
        if ev.impact != "HIGH" or ev.minutes_until is None:
            continue
        if abs(ev.minutes_until) <= 5:
            return 0.3
        if 0 <= ev.minutes_until <= 30:
            return 0.5
    return 1.0


def aggregate_news_score(items: list[NewsItem]) -> float:
    """Return mean sentiment of items as a -100..+100 score."""
    if not items:
        return 0.0
    avg = sum(n.sentiment for n in items) / len(items)
    return round(avg * 100.0, 1)


def _score_label(score: float) -> str:
    if score > 0.1:
        return "positive"
    if score < -0.1:
        return "negative"
    return "neutral"


def _classify_impact(name: str, finnhub_impact: str) -> str:
    name_up = name.upper()
    for kw in _HIGH_IMPACT:
        if kw.upper() in name_up:
            return "HIGH"
    if finnhub_impact in ("high", "HIGH", "3"):
        return "HIGH"
    if finnhub_impact in ("medium", "MEDIUM", "2"):
        return "MEDIUM"
    return "LOW"
