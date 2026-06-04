"""Lightweight OHLCV bar builder for intermarket tick data.

Accumulates ticks into time-based OHLCV bars without any L2/DOM/delta
complexity.  Used by IntermarketFeed to build bars for each subscribed
symbol (ES, YM, RTY, etc.).

Bar boundaries are determined by a configurable interval in seconds.
The first tick after a boundary opens a new bar; subsequent ticks
extend OHLCV until the next boundary is crossed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class OHLCVBar:
    """Completed OHLCV bar for a single symbol."""

    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    bar_start_ts: float  # unix timestamp of bar open boundary
    bar_end_ts: float  # unix timestamp of bar close boundary
    tick_count: int


class OHLCVAccumulator:
    """Accumulates ticks into fixed-interval OHLCV bars.

    Parameters
    ----------
    symbol : str
        Instrument symbol (e.g. "ES", "YM").
    interval_sec : int
        Bar duration in seconds (default 60).
    """

    def __init__(self, symbol: str, interval_sec: int = 60) -> None:
        self.symbol = symbol
        self.interval_sec = interval_sec
        self._reset()

    # -- internal state management ------------------------------------------

    def _reset(self) -> None:
        self._open: float = 0.0
        self._high: float = 0.0
        self._low: float = 0.0
        self._close: float = 0.0
        self._volume: float = 0.0
        self._tick_count: int = 0
        self._bar_start: Optional[float] = None

    def _snap_boundary(self, timestamp: float) -> float:
        """Snap *timestamp* down to its interval boundary."""
        return (timestamp // self.interval_sec) * self.interval_sec

    def _build_bar(self) -> OHLCVBar:
        assert self._bar_start is not None
        return OHLCVBar(
            symbol=self.symbol,
            open=self._open,
            high=self._high,
            low=self._low,
            close=self._close,
            volume=self._volume,
            bar_start_ts=self._bar_start,
            bar_end_ts=self._bar_start + self.interval_sec,
            tick_count=self._tick_count,
        )

    def _apply_tick(self, price: float, volume: float) -> None:
        if self._tick_count == 0:
            self._open = price
            self._high = price
            self._low = price
        else:
            if price > self._high:
                self._high = price
            if price < self._low:
                self._low = price
        self._close = price
        self._volume += volume
        self._tick_count += 1

    # -- public API ---------------------------------------------------------

    def feed_tick(
        self, price: float, volume: float, timestamp: float
    ) -> Optional[OHLCVBar]:
        """Feed a single tick.

        Returns a completed ``OHLCVBar`` when *timestamp* crosses the
        current bar's interval boundary.  Otherwise returns ``None``.
        """
        tick_boundary = self._snap_boundary(timestamp)

        # First tick ever — open a fresh bar.
        if self._bar_start is None:
            self._bar_start = tick_boundary
            self._apply_tick(price, volume)
            return None

        # Tick belongs to the current bar.
        if tick_boundary == self._bar_start:
            self._apply_tick(price, volume)
            return None

        # Tick crosses into a new interval — close the current bar first.
        completed = self._build_bar()
        self._reset()
        self._bar_start = tick_boundary
        self._apply_tick(price, volume)
        return completed

    def flush(self) -> Optional[OHLCVBar]:
        """Force-close the current bar (e.g. at market close).

        Returns ``None`` if no ticks have been accumulated.
        """
        if self._bar_start is None or self._tick_count == 0:
            return None
        bar = self._build_bar()
        self._reset()
        return bar

    @property
    def current_bar_start(self) -> Optional[float]:
        """Start timestamp of the currently-accumulating bar."""
        return self._bar_start


__all__ = ["OHLCVBar", "OHLCVAccumulator"]
