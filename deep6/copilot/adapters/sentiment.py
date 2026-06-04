"""Social sentiment adapter for free public sources."""

from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

import httpx

from deep6.copilot.types import SentimentSnapshot

logger = logging.getLogger(__name__)

_BULL_WORDS = ("bull", "long", "buy", "calls", "moon")
_BEAR_WORDS = ("bear", "short", "sell", "puts", "crash")
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "have",
    "will",
    "about",
    "just",
    "your",
    "are",
    "was",
    "you",
    "but",
    "not",
    "all",
    "out",
    "into",
    "what",
    "when",
    "who",
    "why",
    "how",
    "now",
    "still",
    "after",
    "before",
}


@dataclass(slots=True)
class _SourceTotals:
    bullish: int = 0
    bearish: int = 0
    volume: int = 0
    topics: Counter[str] | None = None

    def __post_init__(self) -> None:
        if self.topics is None:
            self.topics = Counter()


class SentimentAdapter:
    """Aggregate public social sentiment from StockTwits and Reddit."""

    def __init__(
        self,
        polling_interval_seconds: int = 300,
        timeout_seconds: float = 10.0,
        user_agent: str = "DEEP6-SentimentAdapter/1.0",
    ) -> None:
        self._polling_interval_seconds = polling_interval_seconds
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=min(5.0, timeout_seconds)),
            headers={"User-Agent": user_agent},
        )
        self._cache: SentimentSnapshot | None = None
        self._stocktwits_backoff_until: dict[str, datetime] = {}
        self._stocktwits_backoff_attempts: dict[str, int] = {}

    async def __aenter__(self) -> "SentimentAdapter":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_sentiment(self, symbols: Iterable[str] | None = None) -> SentimentSnapshot:
        symbols = tuple(symbols or ("NQ", "QQQ", "NDX"))
        now = datetime.now(timezone.utc)
        totals = _SourceTotals()

        stocktwits_totals = await self._fetch_stocktwits(symbols, now)
        totals.bullish += stocktwits_totals.bullish
        totals.bearish += stocktwits_totals.bearish
        totals.volume += stocktwits_totals.volume
        totals.topics.update(stocktwits_totals.topics or {})

        reddit_totals = await self._fetch_reddit(now)
        totals.bullish += reddit_totals.bullish
        totals.bearish += reddit_totals.bearish
        totals.volume += reddit_totals.volume
        totals.topics.update(reddit_totals.topics or {})

        if totals.volume <= 0 and self._cache is not None:
            return self._cache

        bullish_pct, bearish_pct = self._percentages(totals.bullish, totals.bearish)
        trending_topics = tuple(topic for topic, _ in totals.topics.most_common(5))

        snapshot = SentimentSnapshot(
            timestamp=now.timestamp(),
            bullish_pct=bullish_pct,
            bearish_pct=bearish_pct,
            volume=totals.volume,
            trending_topics=trending_topics,
        )
        self._cache = snapshot
        return snapshot

    async def run_forever(self, symbols: Iterable[str] | None = None, callback=None) -> None:
        symbols = tuple(symbols or ("NQ", "QQQ", "NDX"))
        while True:
            snapshot = await self.fetch_sentiment(symbols)
            if callback is not None:
                result = callback(snapshot)
                if asyncio.iscoroutine(result):
                    await result
            await asyncio.sleep(self._polling_interval_seconds)

    async def _fetch_stocktwits(self, symbols: tuple[str, ...], now: datetime) -> _SourceTotals:
        totals = _SourceTotals()
        for symbol in symbols:
            if self._stocktwits_backoff_until.get(symbol, datetime.min.replace(tzinfo=timezone.utc)) > now:
                if self._cache is not None:
                    logger.debug("StockTwits backoff active for %s; using cache", symbol)
                continue

            url = f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
            try:
                response = await self._client.get(url)
                if response.status_code == 429:
                    self._register_stocktwits_backoff(symbol, now)
                    logger.warning("StockTwits rate limit for %s", symbol)
                    continue
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                logger.debug("StockTwits fetch failed for %s: %s", symbol, exc)
                continue

            messages = payload.get("messages", []) if isinstance(payload, dict) else []
            for message in messages:
                if not isinstance(message, dict):
                    continue
                totals.volume += 1
                sentiment = (
                    message.get("entities", {})
                    if isinstance(message.get("entities"), dict)
                    else {}
                )
                basic = ""
                if isinstance(sentiment, dict):
                    sentiment_obj = sentiment.get("sentiment", {})
                    if isinstance(sentiment_obj, dict):
                        basic = str(sentiment_obj.get("basic", "")).lower()
                if basic.startswith("bull"):
                    totals.bullish += 1
                elif basic.startswith("bear"):
                    totals.bearish += 1
                totals.topics[symbol.lower()] += 1

        return totals

    async def _fetch_reddit(self, now: datetime) -> _SourceTotals:
        totals = _SourceTotals()
        url = "https://www.reddit.com/r/wallstreetbets/hot.json?limit=25"
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.debug("Reddit fetch failed: %s", exc)
            return totals

        children = []
        if isinstance(payload, dict):
            data = payload.get("data", {})
            if isinstance(data, dict):
                children = data.get("children", []) or []

        for child in children:
            if not isinstance(child, dict):
                continue
            data = child.get("data", {})
            if not isinstance(data, dict):
                continue
            title = str(data.get("title", ""))
            if not title:
                continue
            totals.volume += 1
            bullish, bearish, topics = self._classify_text(title)
            totals.bullish += bullish
            totals.bearish += bearish
            totals.topics.update(topics)

        return totals

    def _classify_text(self, text: str) -> tuple[int, int, Counter[str]]:
        lowered = text.lower()
        bullish = sum(lowered.count(word) for word in _BULL_WORDS)
        bearish = sum(lowered.count(word) for word in _BEAR_WORDS)
        tokens = Counter(token for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]{1,}", lowered) if token not in _STOPWORDS)
        return bullish, bearish, tokens

    def _register_stocktwits_backoff(self, symbol: str, now: datetime) -> None:
        attempts = self._stocktwits_backoff_attempts.get(symbol, 0) + 1
        self._stocktwits_backoff_attempts[symbol] = attempts
        delay_seconds = min(300, 15 * (2 ** (attempts - 1)))
        self._stocktwits_backoff_until[symbol] = now + timedelta(seconds=delay_seconds)

    @staticmethod
    def _percentages(bullish: int, bearish: int) -> tuple[float, float]:
        total = bullish + bearish
        if total <= 0:
            return 50.0, 50.0
        bullish_pct = round((bullish / total) * 100.0, 2)
        bearish_pct = round((bearish / total) * 100.0, 2)
        return bullish_pct, bearish_pct
