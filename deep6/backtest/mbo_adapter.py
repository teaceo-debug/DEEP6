"""MBOAdapter — Databento MBO → live feed callback shape.

Phase 13-01 core. Replays historical Market-by-Order events through the
same ``on_tick(price, size, aggressor)`` / ``on_dom(bid_levels, ask_levels)``
callbacks that ``deep6/data/rithmic.py`` drives in live mode. The DEEP6
signal pipeline (absorption/exhaustion/delta/auction/POC/trap/volpat/
slingshot…) is therefore totally oblivious to whether it's processing a
live Rithmic feed or a Databento replay — the single biggest win of
this phase.

Architecture:

    Databento MBO events ──▶ MBOAdapter.run()
                             │
                             ├─ clock.advance(event.ts_event / 1e9)
                             │
                             ├─ dispatch by action:
                             │    'T'/'F' → on_tick(price, size, aggressor)
                             │    'A'     → book.add    → on_dom(...)
                             │    'C'     → book.cancel → on_dom(...)
                             │    'M'     → book.mod    → on_dom(...)
                             │    'R'     → book.clear  → on_dom([], [])
                             │
                             └─ book state: order_book.OrderBook (C-backed)

Databento MBO schema reference:
    action: single-char — T (trade), F (fill, treated as trade), A (add),
            C (cancel), M (modify), R (clear/reset)
    side:   single-char — A (ask-side order — when this is a trade,
            buyer lifted the ask → BUY aggressor); B (bid-side —
            seller hit the bid → SELL aggressor); N (none).
            Phase 13-01 FOOTGUN 2 — inverting this flips every delta.
    price:  fixed-point int, divide by 1e9 for dollar value
    size:   integer

Symbol roll: Databento continuous symbols (e.g. NQ.c.0) emit a new
``instrument_id`` on contract roll. We detect the change and clear the
book + reset the state so the new contract starts fresh.
"""
from __future__ import annotations

import array
from typing import Any, AsyncIterator, Awaitable, Callable, Iterable, Literal, Protocol

import structlog

from deep6.backtest.clock import EventClock
from deep6.state.dom import DOMState, LEVELS

log = structlog.get_logger(__name__)

# Callback signatures — MUST match deep6/data/rithmic.py exactly.
TickCB = Callable[[float, int, Literal["BUY", "SELL"]], Awaitable[None]]
DomCB = Callable[
    [list[tuple[float, int]], list[tuple[float, int]]], Awaitable[None]
]

# Databento price scaling — MBO prices are fixed-point int / 1e9.
DATABENTO_PRICE_SCALE = 1e9


class FeedAdapter(Protocol):
    """A feed that pushes ticks/DOM updates through the live callback shape.

    Mirrors the shape already expected by ``SharedState.wire_callbacks()``.
    Live ``rithmic.py`` is the reference implementation; ``MBOAdapter`` is
    the replay implementation.
    """

    async def run(self, on_tick: TickCB, on_dom: DomCB) -> None: ...


def _book_to_domstate(book: Any) -> DOMState:
    """Convert a bmoscon ``OrderBook`` snapshot into ``DOMState``.

    Rules (LOCKED for phase 13; equivalence-tested):
      - ``DOMState.bid_prices[0]`` = best bid (highest price).
        ``order_book.OrderBook.bids`` iterates in descending order by
        price so we can consume directly.
      - ``DOMState.ask_prices[0]`` = best ask (lowest price).
      - Up to LEVELS (40) levels per side; beyond-range truncated with a
        debug log (Phase 13-01 FOOTGUN 1 mitigation).
      - Price/size are stored as ``float`` in ``array.array('d')``.

    No allocation outside the DOMState construction; the bmoscon book is
    read-only here.
    """
    dom = DOMState()
    bids = book.bids
    asks = book.asks

    bid_keys = list(bids.keys())
    ask_keys = list(asks.keys())

    n_bid = min(len(bid_keys), LEVELS)
    n_ask = min(len(ask_keys), LEVELS)

    for i in range(n_bid):
        price = bid_keys[i]
        dom.bid_prices[i] = float(price)
        dom.bid_sizes[i] = float(bids[price])
    for i in range(n_ask):
        price = ask_keys[i]
        dom.ask_prices[i] = float(price)
        dom.ask_sizes[i] = float(asks[price])

    dropped = max(0, len(bid_keys) - LEVELS) + max(0, len(ask_keys) - LEVELS)
    if dropped:
        log.debug("mbo.dom.truncated", dropped_levels=dropped, kept=LEVELS)
    return dom


def _dom_levels(book: Any) -> tuple[list[tuple[float, int]], list[tuple[float, int]]]:
    """Extract top-N bid/ask levels from a bmoscon ``OrderBook``.

    Matches the DomCB signature: ``(bid_levels, ask_levels)`` where each
    element is ``(price, size)``. Ordering:
      bid_levels[0] — best (highest price)
      ask_levels[0] — best (lowest price)
    """
    bids = book.bids
    asks = book.asks
    bid_keys = list(bids.keys())[:LEVELS]
    ask_keys = list(asks.keys())[:LEVELS]
    bid_levels = [(float(p), int(bids[p])) for p in bid_keys]
    ask_levels = [(float(p), int(asks[p])) for p in ask_keys]
    return bid_levels, ask_levels


def _aggressor_from_side(side: str) -> Literal["BUY", "SELL"]:
    """Map a Databento MBO ``side`` char to DEEP6 aggressor string.

    Databento MBO ``side`` semantics (Phase 13-01 FOOTGUN 2):
      'A' → ask-side order; when this is a trade, the aggressor lifted
            the ask — BUY aggressor.
      'B' → bid-side order; aggressor hit the bid — SELL aggressor.
      'N' → none (shouldn't appear on trades) → default to BUY.

    Inverting this flips every delta signal; the unit test in
    ``tests/backtest/test_mbo_adapter.py::test_adapter_dispatches_trade_to_on_tick``
    pins the mapping.
    """
    if side == "A":
        return "BUY"
    if side == "B":
        return "SELL"
    # Defensive: 'N' / anything else — log once so we notice if data drifts.
    log.debug("mbo.side.unknown", side=side, default="BUY")
    return "BUY"


class MBOAdapter:
    """FeedAdapter replaying Databento MBO events through live callbacks.

    Instantiate with an ``EventClock`` (which the adapter will tick forward
    on each event) and a pre-built Databento iterator (``event_source`` —
    either a live Databento stream or an in-memory iterable for tests).

    Usage:
        clock = EventClock()
        adapter = MBOAdapter(
            dataset="GLBX.MDP3",
            symbol="NQ.c.0",
            start="2026-04-09T13:30",
            end="2026-04-09T20:00",
            clock=clock,
            tick_size=0.25,
            event_source=my_iter,  # or None to open Databento client
        )
        await adapter.run(on_tick, on_dom)

    Testability note: ``event_source`` is injectable — tests pass in a
    synthetic iterator so no network call is made. In production,
    ``event_source=None`` triggers ``_open_stream()`` which pulls from
    Databento historical range (TODO: wire once live Databento
    integration is proven in phase 14 parity harness).
    """

    def __init__(
        self,
        dataset: str,
        symbol: str,
        start: str,
        end: str,
        clock: EventClock,
        tick_size: float = 0.25,
        event_source: Iterable[Any] | AsyncIterator[Any] | None = None,
        max_depth: int = LEVELS,
    ) -> None:
        # Imported lazily so tests that don't use Databento don't pay the
        # module import cost (databento pulls numpy+pandas transitively).
        from order_book import OrderBook

        self.dataset = dataset
        self.symbol = symbol
        self.start = start
        self.end = end
        self._clock = clock
        self.tick_size = tick_size
        self._event_source = event_source
        self._book = OrderBook(max_depth=max_depth)
        self._current_instrument_id: int | None = None

    def _open_stream(self) -> Iterable[Any]:
        """Open a Databento historical MBO range (production path).

        Returns a record iterator over ``(dataset, symbol, start, end)``
        with schema='mbo'. Raises at call time if DATABENTO_API_KEY is
        missing. In tests, ``event_source`` is injected and this method
        is never invoked.
        """
        import os

        import databento as db

        api_key = os.environ.get("DATABENTO_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "DATABENTO_API_KEY not set — required for MBOAdapter live stream"
            )
        client = db.Historical(key=api_key)
        data = client.timeseries.get_range(
            dataset=self.dataset,
            schema="mbo",
            stype_in="continuous",
            symbols=[self.symbol],
            start=self.start,
            end=self.end,
        )
        return data

    async def run(self, on_tick: TickCB, on_dom: DomCB) -> None:
        """Replay the full event stream through the two callbacks.

        Contract with live path (``deep6/data/rithmic.py``):
          - ``on_tick(price: float, size: int, aggressor: 'BUY'|'SELL')``
          - ``on_dom(bid_levels, ask_levels)`` with list[(price, size)]
            top-N sorted (best at index 0)

        On each event we:
          1. Advance ``self._clock`` to ``event.ts_event / 1e9`` (seconds).
          2. Detect symbol roll: if ``instrument_id`` changes, clear the
             book and reset state before dispatch.
          3. Dispatch by ``action`` (see module docstring for table).
          4. For book-mutating actions, emit a DOM snapshot (top-N
             levels) via ``on_dom``.
          5. For trade/fill actions, emit via ``on_tick``.

        Errors while processing a single event are logged and swallowed —
        one bad event should not kill the whole replay.
        """
        src = self._event_source if self._event_source is not None else self._open_stream()

        # Handle both sync and async iterators
        if hasattr(src, "__aiter__"):
            async for ev in src:  # type: ignore[union-attr]
                await self._dispatch(ev, on_tick, on_dom)
        else:
            for ev in src:
                await self._dispatch(ev, on_tick, on_dom)

    async def _dispatch(
        self, ev: Any, on_tick: TickCB, on_dom: DomCB
    ) -> None:
        """Process a single MBO event — advance clock then dispatch."""
        # Advance replay clock to event time (ns → s).
        ts_s = float(ev.ts_event) / 1e9
        self._clock.advance(ts_s)

        # Detect contract roll — reset book state on instrument_id change.
        inst_id = getattr(ev, "instrument_id", None)
        if self._current_instrument_id is None:
            self._current_instrument_id = inst_id
        elif inst_id is not None and inst_id != self._current_instrument_id:
            log.info(
                "mbo.symbol_roll",
                old_instrument_id=self._current_instrument_id,
                new_instrument_id=inst_id,
                ts=ts_s,
            )
            self._reset_book()
            self._current_instrument_id = inst_id
            # Emit an empty DOM so downstream state knows the book reset.
            await on_dom([], [])

        action = ev.action
        # Databento action may be bytes (b'T') or str ('T') depending on
        # source; normalize to a 1-char str.
        if isinstance(action, (bytes, bytearray)):
            action = action.decode("ascii")
        if isinstance(action, int):
            action = chr(action)

        side = getattr(ev, "side", "N")
        if isinstance(side, (bytes, bytearray)):
            side = side.decode("ascii")
        if isinstance(side, int):
            side = chr(side)

        price = float(ev.price) / DATABENTO_PRICE_SCALE
        size = int(ev.size)

        try:
            if action in ("T", "F"):
                # Trade or fill — emit tick. Aggressor per Databento MBO
                # side semantics (FOOTGUN 2).
                aggressor = _aggressor_from_side(side)
                await on_tick(price, size, aggressor)
            elif action == "A":
                # Add — apply to book, emit DOM.
                self._apply_add(side, price, size)
                bids, asks = _dom_levels(self._book)
                await on_dom(bids, asks)
            elif action == "C":
                # Cancel — remove from book (set to 0 / del), emit DOM.
                self._apply_cancel(side, price, size)
                bids, asks = _dom_levels(self._book)
                await on_dom(bids, asks)
            elif action == "M":
                # Modify — overwrite the size at that price, emit DOM.
                self._apply_modify(side, price, size)
                bids, asks = _dom_levels(self._book)
                await on_dom(bids, asks)
            elif action == "R":
                # Reset/clear — wipe book, emit empty DOM.
                self._reset_book()
                await on_dom([], [])
            else:
                # Unknown action — log and skip.
                log.debug("mbo.action.unknown", action=action)
        except Exception:
            log.exception(
                "mbo.dispatch_failed",
                action=action,
                side=side,
                price=price,
                size=size,
            )

    # ------------------------------------------------------------------
    # Book mutation helpers — small, single-responsibility, easy to test.
    # The Databento MBO schema gives us orders (add/cancel/modify) per
    # individual order; the bmoscon OrderBook we keep is an aggregated
    # price-level view. We model each add/cancel/modify as an incremental
    # size update at the price level, which preserves top-of-book
    # correctness for our DOM-consumer signals (E2/E3/E4).
    # ------------------------------------------------------------------

    def _side_dict(self, side: str):
        if side == "A":
            return self._book.asks
        return self._book.bids  # default bid for 'B' or anything else

    def _reset_book(self) -> None:
        """Wipe all price levels. bmoscon.OrderBook has no clear() method,
        so we iterate the sorted-dict sides and delete each key."""
        for price in list(self._book.bids.keys()):
            del self._book.bids[price]
        for price in list(self._book.asks.keys()):
            del self._book.asks[price]

    def _apply_add(self, side: str, price: float, size: int) -> None:
        book_side = self._side_dict(side)
        existing = int(book_side[price]) if price in book_side else 0
        book_side[price] = existing + size

    def _apply_cancel(self, side: str, price: float, size: int) -> None:
        book_side = self._side_dict(side)
        if price not in book_side:
            return
        existing = int(book_side[price])
        new_size = existing - size
        if new_size <= 0:
            del book_side[price]
        else:
            book_side[price] = new_size

    def _apply_modify(self, side: str, price: float, size: int) -> None:
        book_side = self._side_dict(side)
        if size <= 0:
            if price in book_side:
                del book_side[price]
        else:
            book_side[price] = size
