"""FootprintBar: core data structure for bid/ask volume per price level.

This is the central type of the DEEP6 system. Every signal engine in Phases 2-5
operates on FootprintBar objects. Correctness here gates the entire project.

Per DATA-03: accumulates bid/ask volume per price level using defaultdict[int, FootprintLevel].
Per ARCH-04: BarHistory is the deque that feeds the Phase 3 correlation matrix.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

# NQ instrument constants — sourced from Config in production
TICK_SIZE: float = 0.25


def price_to_tick(price: float) -> int:
    """Convert float price to integer tick index.

    NQ example: 21000.0 / 0.25 = 84000
    Using round() to avoid floating-point precision issues (e.g., 20999.75 → 83999).
    """
    return round(price / TICK_SIZE)


def tick_to_price(tick: int) -> float:
    """Convert integer tick index to float price.

    NQ example: 84000 * 0.25 = 21000.0
    """
    return tick * TICK_SIZE


@dataclass
class FootprintLevel:
    """Bid and ask volume at a single price level (one tick width).

    bid_vol: sell aggressor volume (aggressor=2 — trade hits the bid)
    ask_vol: buy aggressor volume  (aggressor=1 — trade hits the ask)
    """
    bid_vol: int = 0
    ask_vol: int = 0


@dataclass
class FootprintBar:
    """One completed (or in-progress) footprint bar.

    During accumulation: levels is a defaultdict — no pre-sizing needed.
    After finalize():    bar_delta, poc_price, bar_range, cvd are computed.

    levels key: integer price-in-ticks (price_to_tick(price)) — no float key precision issues.
    """
    timestamp: float = 0.0
    open:  float = 0.0
    high:  float = 0.0
    low:   float = float('inf')
    close: float = 0.0
    levels: dict = field(default_factory=lambda: defaultdict(FootprintLevel))
    total_vol: int = 0

    # Derived fields — set by finalize()
    bar_delta: int = 0       # sum(ask_vol - bid_vol) across all levels
    cvd: int = 0             # cumulative volume delta — set from prior bar's cvd
    poc_price: float = 0.0   # price with highest total volume
    bar_range: float = 0.0   # high - low in points

    def add_trade(self, price: float, size: int, aggressor: int) -> None:
        """Accumulate one trade tick into the current bar.

        aggressor: 1=BUY (ask-side aggressor), 2=SELL (bid-side aggressor)
        Uses integer tick key to avoid float dict key precision issues.

        Per T-02-01: only called after aggressor_verification_gate passes (Plan 01).
        aggressor=0 (UNSPECIFIED) never reaches add_trade.
        """
        tick = price_to_tick(price)
        level = self.levels[tick]
        if aggressor == 1:    # BUY — trade hit the ask
            level.ask_vol += size
        elif aggressor == 2:  # SELL — trade hit the bid
            level.bid_vol += size
        # Update OHLC
        if self.open == 0.0:
            self.open = price
        self.high = max(self.high, price)
        self.low  = min(self.low, price)
        self.close = price
        self.total_vol += size

    def finalize(self, prior_cvd: int = 0) -> "FootprintBar":
        """Compute derived fields. Must be called exactly once at bar close.

        Args:
            prior_cvd: CVD from the previous closed bar — carried forward for session CVD.

        Returns self for chaining.
        """
        if self.levels:
            self.bar_delta = sum(
                lv.ask_vol - lv.bid_vol for lv in self.levels.values()
            )
            self.poc_price = tick_to_price(
                max(
                    self.levels.keys(),
                    key=lambda t: self.levels[t].ask_vol + self.levels[t].bid_vol,
                )
            )
        # Empty bar: set low=0.0 so bar_range is 0.0 (not inf - 0)
        if self.high == 0.0:
            self.low = 0.0
        self.bar_range = self.high - self.low if self.high > 0.0 else 0.0
        self.cvd = prior_cvd + self.bar_delta
        return self


# BarHistory: ring buffer of closed FootprintBar objects.
# maxlen=200 covers 200 bars of history (200min = ~3.3hr for 1-min bars).
# This is the data structure that feeds ARCH-04 correlation matrix in Phase 3.
# Usage: history = BarHistory()  — returns a new deque[FootprintBar] each call.
def BarHistory() -> deque:  # type: ignore[return-value]
    """Factory: create a new ring buffer for closed FootprintBar objects.

    Per ARCH-04: this deque feeds the Phase 3 Pearson correlation matrix.
    maxlen=200 prevents unbounded growth (T-02-02).
    """
    return deque(maxlen=200)
