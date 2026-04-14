"""ReplaySession — orchestrator for backtest replay.

Phase 13-01 T-13-01-10. Wires together the four core pieces:

    EventClock  ──▶  SharedState.clock
        │
        │     bar-close events
        ▼
    MBOAdapter ──▶  on_tick / on_dom ──▶ DOMState + BarAccumulator
                                                       │
                                                       ▼
                                            DOM-signal engines (E2/E3/E4)
                                                       │
                                                       ▼
                                            DuckDBResultStore.record_bar

Replay differs from live in one key way: we cannot use ``BarBuilder.run()``
because it ``asyncio.sleep``s to real wall-clock bar boundaries. Replay
must advance bar boundaries with event time. ``ReplaySession`` owns a
lightweight, event-driven accumulator that mirrors ``BarBuilder.on_trade``
semantics and closes a bar the first time an incoming tick's timestamp
exceeds the next boundary.

The ReplaySession is intentionally self-contained: tests construct one
with a synthetic ``event_source`` and assert on the DuckDB outputs
directly. Production callers (phase 14 sweep harness) supply a
Databento-backed adapter.
"""
from __future__ import annotations

import uuid
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable, Literal

import structlog

from deep6.backtest.clock import EventClock
from deep6.backtest.config import BacktestConfig
from deep6.backtest.mbo_adapter import MBOAdapter
from deep6.backtest.result_store import DuckDBResultStore
from deep6.engines.counter_spoof import CounterSpoofEngine
from deep6.engines.iceberg import IcebergEngine
from deep6.engines.trespass import TrespassEngine
from deep6.state.dom import DOMState
from deep6.state.footprint import FootprintBar

log = structlog.get_logger(__name__)


# Signal bit positions for DOM-dependent engines — only used to pack a
# compact signal_flags mask into DuckDB. Real live code uses
# deep6.signals.flags.SignalFlags; we keep the constants local so
# ReplaySession doesn't need to know which IMB/DELT/AUCT positions are
# currently assigned.
_BIT_E2_TRESPASS = 1 << 12      # co-located with IMB_SINGLE — illustrative
_BIT_E3_COUNTER_SPOOF = 1 << 37  # TRAP region
_BIT_E4_ICEBERG = 1 << 38        # TRAP region


class ReplaySession(AbstractAsyncContextManager["ReplaySession"]):
    """Drive a full Databento MBO replay through DEEP6 signal engines.

    Usage:
        cfg = BacktestConfig(dataset="GLBX.MDP3", symbol="NQ.c.0",
                             start=..., end=...)
        async with ReplaySession(cfg, state, event_source=ev_iter) as s:
            await s.run()

    If ``event_source`` is None, MBOAdapter opens a live Databento
    historical range (requires ``DATABENTO_API_KEY``).
    """

    def __init__(
        self,
        config: BacktestConfig,
        state: Any,   # SharedState — typed as Any to avoid circular import surface
        event_source: Iterable[Any] | None = None,
        bar_close_hook: Callable[[str, FootprintBar, dict], Awaitable[None]] | None = None,
    ) -> None:
        self.config = config
        self.state = state
        self.run_id = str(uuid.uuid4())

        # Inject the replay clock. WallClock default is overwritten for the
        # lifetime of the session — callers are expected to either spawn a
        # fresh SharedState per replay or restore state.clock = WallClock()
        # post-run if they reuse a state object.
        self._clock = EventClock()
        state.clock = self._clock

        self._adapter = MBOAdapter(
            dataset=config.dataset,
            symbol=config.symbol,
            start=config.start.isoformat(),
            end=config.end.isoformat(),
            clock=self._clock,
            tick_size=config.tick_size,
            event_source=event_source,
        )

        self._store = DuckDBResultStore(config.duckdb_path)

        # DOM-dependent engines — instantiated fresh per session so their
        # internal history is isolated from prior runs.
        self._trespass = TrespassEngine()
        self._counter_spoof = CounterSpoofEngine()
        self._iceberg = IcebergEngine()

        # Per-timeframe bar accumulators (seconds).
        self._tf_seconds: dict[str, int] = {"1m": 60, "5m": 300}
        self._tf_seconds = {tf: self._tf_seconds[tf] for tf in config.tf_list if tf in self._tf_seconds}
        self._current_bars: dict[str, FootprintBar] = {tf: FootprintBar() for tf in self._tf_seconds}
        self._next_boundary: dict[str, float] = {tf: 0.0 for tf in self._tf_seconds}
        self._prior_cvd: dict[str, int] = {tf: 0 for tf in self._tf_seconds}

        self._bar_close_hook = bar_close_hook
        self._bars_written = 0
        self._dom_signal_fires = 0   # tracked for integration assertions

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "ReplaySession":
        self._store.__enter__()
        self._store.record_run(
            run_id=self.run_id,
            symbol=self.config.symbol,
            dataset=self.config.dataset,
            config_json=self.config.model_dump(mode="json"),
            git_sha=self.config.git_sha,
            start_ts=self.config.start,
            end_ts=self.config.end,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._store.flush()
        self._store.__exit__(exc_type, exc, tb)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Pull every MBO event through the pipeline. Returns on stream exhaust."""
        await self._adapter.run(on_tick=self._on_tick, on_dom=self._on_dom)
        # Finalize any bars still in progress (stream ended mid-bar).
        for tf in list(self._current_bars.keys()):
            if self._current_bars[tf].total_vol > 0:
                await self._close_bar(tf, ts_now=self._clock.now())

    @property
    def bars_written(self) -> int:
        return self._bars_written

    @property
    def dom_signal_fires(self) -> int:
        return self._dom_signal_fires

    # ------------------------------------------------------------------
    # Callbacks (shape: live-compatible)
    # ------------------------------------------------------------------

    async def _on_tick(
        self,
        price: float,
        size: int,
        aggressor: Literal["BUY", "SELL"],
    ) -> None:
        ts_now = self._clock.now()
        # Close any bars whose boundary is now in the past.
        for tf in self._tf_seconds:
            await self._maybe_close_bar(tf, ts_now)
        aggr_int = 1 if aggressor == "BUY" else 2
        for tf in self._tf_seconds:
            self._current_bars[tf].add_trade(price, size, aggr_int)

    async def _on_dom(
        self,
        bid_levels: list[tuple[float, int]],
        ask_levels: list[tuple[float, int]],
    ) -> None:
        # Update the shared DOMState in-place — same contract as live dom_feed.
        bid_prices = [p for p, _ in bid_levels]
        bid_sizes = [s for _, s in bid_levels]
        ask_prices = [p for p, _ in ask_levels]
        ask_sizes = [s for _, s in ask_levels]
        self.state.dom.update(
            bid_prices, bid_sizes, ask_prices, ask_sizes,
            ts=self._clock.monotonic(),
        )

    # ------------------------------------------------------------------
    # Bar lifecycle
    # ------------------------------------------------------------------

    async def _maybe_close_bar(self, tf: str, ts_now: float) -> None:
        """Close the current bar if ts_now has crossed its boundary."""
        period = self._tf_seconds[tf]
        boundary = self._next_boundary[tf]
        if boundary == 0.0:
            # First event — seed boundary at the next period multiple.
            self._next_boundary[tf] = (int(ts_now // period) + 1) * period
            return
        while ts_now >= boundary:
            await self._close_bar(tf, ts_now=boundary)
            boundary = boundary + period
        self._next_boundary[tf] = boundary

    async def _close_bar(self, tf: str, ts_now: float) -> None:
        bar = self._current_bars[tf]
        bar.timestamp = ts_now
        bar.finalize(self._prior_cvd[tf])
        self._prior_cvd[tf] = bar.cvd

        signal_flags, tier, direction, score = self._run_dom_engines(bar)
        bar_ts = datetime.fromtimestamp(ts_now, tz=timezone.utc)
        self._store.record_bar(
            run_id=self.run_id,
            bar_ts=bar_ts,
            tf=tf,
            ohlcv=(
                bar.open, bar.high, bar.low, bar.close, bar.total_vol,
            ),
            signal_flags=signal_flags,
            score=score,
            tier=tier,
            direction=direction,
            bar_key=self._bars_written,
        )
        self._bars_written += 1

        if self._bar_close_hook is not None:
            try:
                await self._bar_close_hook(
                    tf, bar, {"signal_flags": signal_flags, "score": score},
                )
            except Exception:
                log.exception("replay.bar_close_hook_failed", tf=tf)

        # Reset bar accumulator.
        self._current_bars[tf] = FootprintBar()

    # ------------------------------------------------------------------
    # Engine plumbing
    # ------------------------------------------------------------------

    def _run_dom_engines(
        self, bar: FootprintBar
    ) -> tuple[int, str, str, float]:
        """Run the three DOM-dependent engines against the current DOMState.

        Returns a (signal_flags, tier, direction, score) tuple suitable for
        ``DuckDBResultStore.record_bar``. Engine failures degrade to a
        no-signal row — never kill the replay.
        """
        dom: DOMState = self.state.dom
        dom_snapshot = dom.snapshot()
        flags = 0
        score = 0.0
        direction_int = 0

        # E2 Trespass — queue imbalance.
        try:
            t = self._trespass.process(dom_snapshot)
            if t.direction != 0:
                flags |= _BIT_E2_TRESPASS
                score += 50.0 * t.probability
                direction_int = t.direction
                self._dom_signal_fires += 1
        except Exception:
            log.exception("replay.trespass_failed")

        bid_prices, bid_sizes, ask_prices, ask_sizes = dom_snapshot

        # E3 Counter-spoof — cancel-heavy W1 anomaly. The engine is
        # stateful: it's fed each bar-close snapshot and returns alerts
        # via get_spoof_alerts() as they accumulate. We check for any
        # new alerts produced since the prior bar.
        try:
            pre_alerts = len(self._counter_spoof.get_spoof_alerts())
            self._counter_spoof.ingest_snapshot(
                bid_prices, bid_sizes, ask_prices, ask_sizes,
                timestamp=self._clock.monotonic(),
            )
            post_alerts = self._counter_spoof.get_spoof_alerts()
            if len(post_alerts) > pre_alerts:
                flags |= _BIT_E3_COUNTER_SPOOF
                score += 25.0
                self._dom_signal_fires += 1
        except Exception:
            log.exception("replay.counter_spoof_failed")

        # E4 Iceberg — synthetic refill detection via DOM delta.
        try:
            sigs = self._iceberg.update_dom(
                bid_prices, bid_sizes, ask_prices, ask_sizes,
                timestamp=self._clock.monotonic(),
            )
            if sigs:
                flags |= _BIT_E4_ICEBERG
                score += 25.0
                self._dom_signal_fires += len(sigs)
        except Exception:
            log.exception("replay.iceberg_failed")

        if direction_int > 0:
            direction = "LONG"
        elif direction_int < 0:
            direction = "SHORT"
        else:
            direction = "NONE"
        tier = "NONE" if flags == 0 else "TIER_3"
        return flags, tier, direction, score
