"""DOMState: pre-allocated array.array for zero-allocation DOM callbacks.

Per D-13: DOM callbacks update pre-allocated arrays in-place (zero allocation per callback).
Per DATA-05: 40 bid + 40 ask levels pre-allocated covering NQ L2 depth.

Uses array.array typecode 'd' (C double / Python float, 8 bytes each) — confirmed correct
for NQ price and size values (prices can be large integers * 0.25; sizes are integers).
"""
import array
import time
from dataclasses import dataclass, field

LEVELS = 40  # 40 bid + 40 ask levels pre-allocated (D-13, DATA-05)


@dataclass
class DOMState:
    """Pre-allocated Level 2 order book state for NQ.

    All arrays are fixed-length (LEVELS=40). update() assigns in-place — never appends,
    never reallocates. Called up to 1,000 times/sec from DOM callbacks.
    """
    bid_prices: array.array = field(default_factory=lambda: array.array('d', [0.0] * LEVELS))
    bid_sizes:  array.array = field(default_factory=lambda: array.array('d', [0.0] * LEVELS))
    ask_prices: array.array = field(default_factory=lambda: array.array('d', [0.0] * LEVELS))
    ask_sizes:  array.array = field(default_factory=lambda: array.array('d', [0.0] * LEVELS))
    last_update: float = 0.0

    def update(
        self,
        bid_prices: list,
        bid_sizes: list,
        ask_prices: list,
        ask_sizes: list,
        ts: float | None = None,
    ) -> None:
        """In-place update — zero allocation per call. Called from DOM callback.

        Clips incoming data at LEVELS — excess levels beyond 40 are discarded.
        Levels not covered by incoming data retain their prior values.
        """
        n_bid = min(len(bid_prices), LEVELS)
        n_ask = min(len(ask_prices), LEVELS)
        for i in range(n_bid):
            self.bid_prices[i] = bid_prices[i]
            self.bid_sizes[i]  = bid_sizes[i]
        for i in range(n_ask):
            self.ask_prices[i] = ask_prices[i]
            self.ask_sizes[i]  = ask_sizes[i]
        for i in range(n_bid, LEVELS):
            self.bid_prices[i] = 0.0
            self.bid_sizes[i] = 0.0
        for i in range(n_ask, LEVELS):
            self.ask_prices[i] = 0.0
            self.ask_sizes[i] = 0.0
        self.last_update = ts if ts is not None else time.monotonic()

    def snapshot(self) -> tuple:
        """Return a copy of current DOM state for engine use.

        Called once per bar close, NOT per callback — allocation here is acceptable.
        Returns: (bid_prices, bid_sizes, ask_prices, ask_sizes) as plain lists.
        """
        return (
            list(self.bid_prices),
            list(self.bid_sizes),
            list(self.ask_prices),
            list(self.ask_sizes),
        )

    def best_bid(self) -> tuple[float, float]:
        """Return (price, size) of best bid (index 0)."""
        return (self.bid_prices[0], self.bid_sizes[0])

    def best_ask(self) -> tuple[float, float]:
        """Return (price, size) of best ask (index 0)."""
        return (self.ask_prices[0], self.ask_sizes[0])
