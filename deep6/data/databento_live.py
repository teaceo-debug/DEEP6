"""Databento Live MBO feed adapter for DEEP6 live pipeline.

Subscribes to CME MDP 3.0 MBO stream via ``databento.Live`` and reconstructs
the same ``DOMState`` + ``FootprintBar`` pipeline that ``rithmic.py`` drives.
This eliminates data drift between backtest (Historical MBO) and live —
the schema is identical.

Per phase 14 decisions:
- D-01..D-04: databento SDK, dataset ``GLBX.MDP3``, schema ``mbo``, symbol ``NQ.c.0``.
- D-09..D-11: maintain per-order book, aggregate to top-40 DOM levels, batch
  DOM snapshots every 10ms (``_BATCH_INTERVAL_S``) to bound signal-engine load.
- D-12..D-14: trade (action='T') events feed ``FootprintBar.add_trade`` via
  each ``BarBuilder.on_trade`` (which already enforces RTH + freeze gates).
- D-15..D-17: RTH filtering happens inside ``BarBuilder.on_trade``; DOM updates
  are applied unconditionally because the DOM is a passive snapshot consumed
  only on bar-close (outside-RTH ticks are harmless there).
- D-18..D-20: on disconnect mark ``FreezeGuard`` FROZEN; on resume restore
  CONNECTED and log gap duration for post-session review.
- D-21..D-22: callbacks run on the databento background thread; we push every
  event into an ``asyncio.Queue`` through ``loop.call_soon_threadsafe`` and
  drain in the main event loop. DOM snapshots are emitted at most once per
  10 ms batch window.
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

try:
    import databento as db
except ImportError:  # pragma: no cover — databento is an installed dep
    db = None  # type: ignore[assignment]

from deep6.state.connection import ConnectionState

if TYPE_CHECKING:
    from deep6.state.shared import SharedState


log = structlog.get_logger()

# Default DOM snapshot batch window (D-22).
_BATCH_INTERVAL_S: float = 0.010  # 10 ms

# MBO action codes (CME / Databento). Strings after chr() of single-byte field.
_ACTION_ADD = "A"
_ACTION_MODIFY = "M"
_ACTION_CANCEL = "C"
_ACTION_TRADE = "T"
_ACTION_FILL = "F"      # fill — not emitted as standalone trade in MBO
_ACTION_CLEAR = "R"     # book reset

# MBO side codes. 'A' = ask, 'B' = bid, 'N' = none (e.g. trade with no side).
_SIDE_ASK = "A"
_SIDE_BID = "B"


@dataclass
class _OrderBookState:
    """Per-side price-level aggregate book reconstructed from MBO events.

    Not a full order-by-order book — we only track aggregated size per price
    level, which is what DOMState consumes. Per-order bookkeeping is avoided
    because Databento's MBO aggregator output already delivers consistent
    add/modify/cancel deltas keyed by ``order_id``.
    """

    # order_id -> (price, size, side)
    orders: dict[int, tuple[float, int, str]] = field(default_factory=dict)
    # price -> aggregated size (bids)
    bid_levels: dict[float, int] = field(default_factory=lambda: defaultdict(int))
    # price -> aggregated size (asks)
    ask_levels: dict[float, int] = field(default_factory=lambda: defaultdict(int))

    def clear(self) -> None:
        self.orders.clear()
        self.bid_levels.clear()
        self.ask_levels.clear()

    def apply(self, order_id: int, price: float, size: int, side: str, action: str) -> None:
        """Apply one MBO event to the internal order + level book.

        Silent no-op for events that don't carry a real price/side (e.g.
        trade-prints where side='N'). Those are handled by the trade path.
        """
        if side not in (_SIDE_BID, _SIDE_ASK):
            return

        levels = self.bid_levels if side == _SIDE_BID else self.ask_levels

        if action == _ACTION_ADD:
            self.orders[order_id] = (price, size, side)
            levels[price] += size
        elif action == _ACTION_MODIFY:
            prev = self.orders.get(order_id)
            if prev is not None:
                prev_price, prev_size, prev_side = prev
                prev_levels = self.bid_levels if prev_side == _SIDE_BID else self.ask_levels
                prev_levels[prev_price] -= prev_size
                if prev_levels[prev_price] <= 0:
                    prev_levels.pop(prev_price, None)
            self.orders[order_id] = (price, size, side)
            levels[price] += size
        elif action == _ACTION_CANCEL:
            prev = self.orders.pop(order_id, None)
            if prev is not None:
                prev_price, prev_size, prev_side = prev
                prev_levels = self.bid_levels if prev_side == _SIDE_BID else self.ask_levels
                prev_levels[prev_price] -= prev_size
                if prev_levels[prev_price] <= 0:
                    prev_levels.pop(prev_price, None)
        elif action == _ACTION_TRADE or action == _ACTION_FILL:
            # A fill reduces resting size at the resting side's price level.
            prev = self.orders.get(order_id)
            if prev is not None:
                prev_price, prev_size, prev_side = prev
                new_size = prev_size - size
                prev_levels = self.bid_levels if prev_side == _SIDE_BID else self.ask_levels
                if new_size <= 0:
                    self.orders.pop(order_id, None)
                    prev_levels[prev_price] -= prev_size
                else:
                    self.orders[order_id] = (prev_price, new_size, prev_side)
                    prev_levels[prev_price] -= size
                if prev_levels[prev_price] <= 0:
                    prev_levels.pop(prev_price, None)

    def top_levels(self, n: int = 40) -> tuple[list[float], list[int], list[float], list[int]]:
        """Return top-n bid/ask levels sorted best-first.

        Bids: highest price first. Asks: lowest price first.
        """
        bid_prices = sorted(self.bid_levels.keys(), reverse=True)[:n]
        ask_prices = sorted(self.ask_levels.keys())[:n]
        bid_sizes = [self.bid_levels[p] for p in bid_prices]
        ask_sizes = [self.ask_levels[p] for p in ask_prices]
        return bid_prices, bid_sizes, ask_prices, ask_sizes


class DatabentoLiveFeed:
    """Live Databento MBO feed — drives DOMState + FootprintBar accumulation.

    Usage::

        feed = DatabentoLiveFeed(api_key=config.databento_api_key)
        await feed.start(state)

    ``start()`` runs forever (subscribes, processes events, batches DOM
    snapshots at 10 ms). Cancel the surrounding task on shutdown.
    """

    def __init__(
        self,
        api_key: str,
        dataset: str = "GLBX.MDP3",
        symbol: str = "NQ.c.0",
        schema: str = "mbo",
        batch_interval_s: float = _BATCH_INTERVAL_S,
    ) -> None:
        if db is None:  # pragma: no cover
            raise RuntimeError("databento package not installed")
        self.api_key = api_key
        self.dataset = dataset
        self.symbol = symbol
        self.schema = schema
        self.batch_interval_s = batch_interval_s

        self._book = _OrderBookState()
        self._client: Any = None
        self._queue: asyncio.Queue | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._dom_dirty: bool = False
        self._disconnect_ts: float | None = None

    # ------------------------------------------------------------------ API
    async def start(self, state: "SharedState") -> None:
        """Subscribe and run the live feed until the task is cancelled."""
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=100_000)
        # Stash the state so disconnect/reconnect callbacks (SDK signature
        # does not pass state) can reach the FreezeGuard.
        self._state_ref = state

        self._client = db.Live(key=self.api_key)
        self._client.subscribe(
            dataset=self.dataset,
            schema=self.schema,
            symbols=[self.symbol],
            stype_in="continuous",
        )
        self._client.add_callback(record_callback=self._on_record)
        # Databento Live exposes disconnect callbacks in SDK >=0.50. If not
        # present (older SDK), we rely on the stream-end signal to surface
        # reconnects.
        add_dc = getattr(self._client, "add_disconnect_callback", None)
        if callable(add_dc):
            add_dc(self._on_disconnect)
        add_rc = getattr(self._client, "add_reconnect_callback", None)
        if callable(add_rc):
            add_rc(self._on_reconnect)

        self._client.start()

        log.info(
            "databento_live.subscribed",
            dataset=self.dataset,
            schema=self.schema,
            symbol=self.symbol,
        )

        # Drive the batched DOM emitter in parallel with the event drainer.
        drain_task = asyncio.create_task(self._drain(state), name="databento_live_drain")
        batch_task = asyncio.create_task(self._dom_batcher(state), name="databento_live_dom_batch")
        try:
            await asyncio.gather(drain_task, batch_task)
        except asyncio.CancelledError:
            drain_task.cancel()
            batch_task.cancel()
            stop = getattr(self._client, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception:  # noqa: BLE001
                    pass
            raise

    # ------------------------------------------------------------ callbacks
    def _on_record(self, record: Any) -> None:
        """Databento background-thread callback. Push onto asyncio queue."""
        if self._loop is None or self._queue is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, record)
        except asyncio.QueueFull:
            log.warning("databento_live.queue_full")
        except RuntimeError:
            # Loop closed during shutdown — drop.
            pass

    def _on_disconnect(self, *_: Any, **__: Any) -> None:  # pragma: no cover — wired by SDK
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._handle_disconnect)

    def _on_reconnect(self, *_: Any, **__: Any) -> None:  # pragma: no cover — wired by SDK
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._handle_reconnect)

    # --------------------------------------------------------- async drain
    async def _drain(self, state: "SharedState") -> None:
        assert self._queue is not None
        while True:
            record = await self._queue.get()
            try:
                self._process_record(state, record)
            except Exception:  # noqa: BLE001
                log.exception("databento_live.process_failed")

    def _process_record(self, state: "SharedState", record: Any) -> None:
        """Route one MBO record to book reconstruction or trade accumulation."""
        action = getattr(record, "action", None)
        if action is None:
            return
        # Databento stores action as a one-byte int in native records; the
        # Python SDK surfaces either a str or an int. Normalise to a single
        # char string for comparison.
        if isinstance(action, (bytes, bytearray)):
            action = action.decode("ascii", errors="replace")
        elif isinstance(action, int):
            action = chr(action)
        action = str(action)

        side_raw = getattr(record, "side", "N")
        if isinstance(side_raw, (bytes, bytearray)):
            side = side_raw.decode("ascii", errors="replace")
        elif isinstance(side_raw, int):
            side = chr(side_raw)
        else:
            side = str(side_raw)

        order_id = int(getattr(record, "order_id", 0) or 0)
        size = int(getattr(record, "size", 0) or 0)
        raw_price = getattr(record, "price", 0) or 0
        # Databento native MBO prices are int64 in 1e-9 units; the high-level
        # Python record objects typically expose them already scaled as float.
        if isinstance(raw_price, int):
            price = raw_price / 1e9
        else:
            price = float(raw_price)

        ts_ns = int(getattr(record, "ts_event", 0) or 0)
        ts = ts_ns / 1e9 if ts_ns else time.time()

        # Book reset — clear everything.
        if action == _ACTION_CLEAR:
            self._book.clear()
            self._dom_dirty = True
            return

        # Trade path. action='T' events accumulate into the live FootprintBars
        # via each BarBuilder.on_trade(), which already enforces RTH gating
        # (D-15..D-17) and FreezeGuard (D-17).
        if action == _ACTION_TRADE:
            # Trade 'side' semantics in Databento MBO: side='A' means an ask
            # order was consumed → the aggressor was the buyer (hit the ask).
            # side='B' means a bid was consumed → the aggressor was the
            # seller (hit the bid). Matches databento_feed.py mapping.
            if side == _SIDE_ASK:
                aggressor = 1  # BUY / ask-aggressor
            elif side == _SIDE_BID:
                aggressor = 2  # SELL / bid-aggressor
            else:
                aggressor = 0
            if aggressor != 0 and size > 0:
                for builder in getattr(state, "bar_builders", []) or []:
                    # on_trade is O(1); internally gates RTH + freeze.
                    builder.on_trade(price, size, aggressor)
            # A trade also decrements the resting order size — apply to book.
            self._book.apply(order_id, price, size, side, action)
            self._dom_dirty = True
            return

        if action in (_ACTION_ADD, _ACTION_MODIFY, _ACTION_CANCEL, _ACTION_FILL):
            self._book.apply(order_id, price, size, side, action)
            self._dom_dirty = True

    # ---------------------------------------------------- DOM batch emitter
    async def _dom_batcher(self, state: "SharedState") -> None:
        """Emit a DOMState snapshot every batch interval if the book changed.

        Per D-22: batching keeps signal-engine load bounded during high-burst
        opens where MBO callbacks can exceed 10,000/sec.
        """
        while True:
            await asyncio.sleep(self.batch_interval_s)
            if not self._dom_dirty:
                continue
            self._dom_dirty = False
            bid_prices, bid_sizes, ask_prices, ask_sizes = self._book.top_levels(40)
            try:
                state.dom.update(
                    bid_prices, bid_sizes, ask_prices, ask_sizes, ts=time.time()
                )
            except Exception:  # noqa: BLE001
                log.exception("databento_live.dom_update_failed")

    # ---------------------------------------------- connection state hooks
    def _handle_disconnect(self) -> None:
        self._disconnect_ts = time.time()
        # FreezeGuard: enter FROZEN (D-19). No new orders; bar builders
        # already observe freeze_guard.is_frozen and skip accumulation.
        if self._state_has_freeze_guard():
            # Reuse on_disconnect which already logs with ts (matches D-20).
            self._current_state.freeze_guard.on_disconnect(self._disconnect_ts)  # type: ignore[union-attr]
        log.warning("databento_live.disconnected", ts=self._disconnect_ts)

    def _handle_reconnect(self) -> None:
        gap = None
        if self._disconnect_ts is not None:
            gap = time.time() - self._disconnect_ts
        # Restore CONNECTED. Databento Live's own WebSocket auto-reconnect
        # guarantees the MBO stream has resumed, so we do not need the
        # Rithmic-style position reconciliation path here.
        if self._state_has_freeze_guard():
            self._current_state.freeze_guard._state = ConnectionState.CONNECTED  # type: ignore[union-attr]
        log.info("databento_live.reconnected", gap_seconds=gap)
        self._disconnect_ts = None

    # The connect/reconnect callbacks are scheduled onto the event loop via
    # call_soon_threadsafe and expected to access state through the same
    # SharedState handed to ``start()``. We stash it on start() so the
    # callbacks don't need to plumb it through the SDK signature.
    @property
    def _current_state(self) -> "SharedState | None":
        return getattr(self, "_state_ref", None)

    def _state_has_freeze_guard(self) -> bool:
        s = self._current_state
        return s is not None and hasattr(s, "freeze_guard")
