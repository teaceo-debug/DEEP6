# Options Data Pipeline: Async Architecture

Python async architecture for dual-API options data ingestion. This document covers the
`OptionsPipeline` orchestrator, data flow, backpressure, error recovery, and integration
with the main DEEP6 event loop.

Companion files:
- `../data-shapes.md` — typed dataclasses for all options data structures
- `../signal-interfaces.md` — `OptionsState` schema and signal engine callback contract
- `api-clients.md` — `MassiveClient` and `FlashAlphaClient` implementations

---

## Pipeline Overview

```
                         ┌─────────────────────────────────────────────────────┐
                         │                  DEEP6 Event Loop                   │
                         │                                                     │
  Massive.com WS ──────► │  MassiveClient                                      │
  (quote updates)        │    └─ normalize() ──► massive_q (asyncio.Queue)     │
                         │                              │                      │
                         │                              ▼                      │
  FlashAlpha REST ──────► │  FAClient                DataFusionEngine          │
  (polled 30s-300s)      │    └─ normalize() ──► fa_q (asyncio.Queue)          │
                         │                              │                      │
                         │                              ▼                      │
                         │                         OptionsState                │
                         │                              │                      │
                         │                              ▼                      │
                         │                       signal engine                 │
                         │                    (44-signal async engine)         │
                         └─────────────────────────────────────────────────────┘
```

Key design decisions:
- Each client writes to its own queue. The fusion engine owns the merge logic.
- `OptionsState` is immutable once published. Signal engine gets a snapshot, not a reference.
- Options data is NOT on the hot path. DOM callbacks at 1,000/sec are unaffected.
- If the signal engine is slow, options updates are dropped (oldest first). Options data
  is seconds-stale by nature; dropping a 30s-old update is fine.

---

## OptionsState

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

class DataQuality(Enum):
    FRESH = "fresh"       # both feeds active, data < 5min old
    DEGRADED = "degraded" # one feed down or data 5-30min old
    STALE = "stale"       # both feeds down or data > 30min old

@dataclass(frozen=True)
class OptionsState:
    """Immutable snapshot published to the signal engine."""
    timestamp: datetime

    # From FlashAlpha
    gamma_flip: Optional[float]
    call_wall: Optional[float]
    put_wall: Optional[float]
    net_gex: Optional[float]
    net_dex: Optional[float]
    net_vex: Optional[float]
    net_chex: Optional[float]
    regime: Optional[str]           # "positive" | "negative"
    zero_dte_expected_move: Optional[float]
    zero_dte_pin_score: Optional[float]

    # From Massive.com
    atm_iv: Optional[float]
    put_call_ratio: Optional[float]
    unusual_flow_score: Optional[float]

    # Metadata
    quality: DataQuality = DataQuality.FRESH
    fa_age_seconds: float = 0.0     # seconds since last FA update
    massive_age_seconds: float = 0.0
    conviction_multiplier: float = 1.0  # decays when quality degrades
```

---

## OptionsPipeline

```python
import asyncio
import logging
import time
from collections.abc import Callable, Awaitable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import janus  # thread-safe asyncio queue (for Kronos integration)

from .api_clients import FlashAlphaClient, MassiveClient
from .data_shapes import FASnapshot, MassiveSnapshot
from .signal_interfaces import OptionsState, DataQuality

logger = logging.getLogger("deep6.options.pipeline")


@dataclass
class PipelineConfig:
    fa_poll_interval_seconds: float = 30.0
    massive_symbols: list[str] = None  # e.g. ["QQQ", "SPY"]
    stale_threshold_seconds: float = 300.0   # 5 min
    degraded_threshold_seconds: float = 60.0  # 1 min
    signal_queue_maxsize: int = 10   # drop oldest if signal engine is slow
    reconnect_base_seconds: float = 1.0
    reconnect_max_seconds: float = 60.0

    def __post_init__(self):
        if self.massive_symbols is None:
            self.massive_symbols = ["QQQ"]


class OptionsPipeline:
    """
    Orchestrates dual-feed options data ingestion.

    Lifecycle:
        pipeline = OptionsPipeline(fa_client, massive_client, config)
        pipeline.on_state_update = my_signal_engine.handle_options_state
        await pipeline.start()
        # ... runs until stop() called
        await pipeline.stop()

    The pipeline does NOT create its own event loop. It must be started
    from within the existing DEEP6 event loop.
    """

    def __init__(
        self,
        fa_client: FlashAlphaClient,
        massive_client: MassiveClient,
        config: PipelineConfig,
    ):
        self._fa = fa_client
        self._massive = massive_client
        self._config = config

        # Internal queues — bounded to prevent memory growth
        self._fa_q: asyncio.Queue[FASnapshot] = asyncio.Queue(maxsize=50)
        self._massive_q: asyncio.Queue[MassiveSnapshot] = asyncio.Queue(maxsize=200)

        # Signal engine callback (set before start())
        self.on_state_update: Optional[Callable[[OptionsState], Awaitable[None]]] = None

        # State tracking
        self._last_fa_snapshot: Optional[FASnapshot] = None
        self._last_massive_snapshot: Optional[MassiveSnapshot] = None
        self._last_fa_time: Optional[float] = None
        self._last_massive_time: Optional[float] = None

        # Tasks
        self._tasks: list[asyncio.Task] = []
        self._running = False

        # Metrics (exposed via metrics property)
        self._metrics = {
            "fa_update_count": 0,
            "massive_update_count": 0,
            "fusion_count": 0,
            "signal_emit_count": 0,
            "signal_drop_count": 0,
            "fa_error_count": 0,
            "massive_error_count": 0,
            "fa_reconnect_count": 0,
            "massive_reconnect_count": 0,
        }

    async def start(self) -> None:
        """Start all pipeline tasks. Non-blocking — returns immediately."""
        if self._running:
            logger.warning("pipeline.start() called but already running")
            return

        self._running = True
        logger.info("options_pipeline.start", extra={"config": vars(self._config)})

        self._tasks = [
            asyncio.create_task(self._run_fa_poller(), name="fa_poller"),
            asyncio.create_task(self._run_massive_ws(), name="massive_ws"),
            asyncio.create_task(self._run_fusion_engine(), name="fusion_engine"),
        ]

        # Log task creation
        for task in self._tasks:
            logger.debug("task.created", extra={"task": task.get_name()})

    async def stop(self, timeout: float = 10.0) -> None:
        """Graceful shutdown. Cancels tasks and waits up to `timeout` seconds."""
        if not self._running:
            return

        self._running = False
        logger.info("options_pipeline.stop", extra={"timeout": timeout})

        for task in self._tasks:
            task.cancel()

        results = await asyncio.gather(*self._tasks, return_exceptions=True)
        for task, result in zip(self._tasks, results):
            if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                logger.error(
                    "task.stop_error",
                    extra={"task": task.get_name(), "error": str(result)},
                )

        self._tasks.clear()
        logger.info("options_pipeline.stopped")

    @property
    def metrics(self) -> dict:
        """Snapshot of pipeline metrics. Safe to call from any coroutine."""
        return dict(self._metrics)

    def is_healthy(self) -> bool:
        """
        Returns True only if:
        - Both feeds have received at least one update
        - Both feeds have data fresher than stale_threshold_seconds
        - All pipeline tasks are running (not done/cancelled)
        """
        now = time.monotonic()
        threshold = self._config.stale_threshold_seconds

        fa_ok = (
            self._last_fa_time is not None
            and (now - self._last_fa_time) < threshold
        )
        massive_ok = (
            self._last_massive_time is not None
            and (now - self._last_massive_time) < threshold
        )
        tasks_ok = all(not t.done() for t in self._tasks)

        return fa_ok and massive_ok and tasks_ok

    def _compute_quality(self) -> tuple[DataQuality, float]:
        """
        Returns (DataQuality, conviction_multiplier).
        Conviction decays linearly from 1.0 at degraded_threshold to 0.3 at stale_threshold.
        """
        now = time.monotonic()
        degraded_t = self._config.degraded_threshold_seconds
        stale_t = self._config.stale_threshold_seconds

        fa_age = (now - self._last_fa_time) if self._last_fa_time else float("inf")
        massive_age = (now - self._last_massive_time) if self._last_massive_time else float("inf")
        max_age = max(fa_age, massive_age)

        if max_age < degraded_t:
            return DataQuality.FRESH, 1.0
        elif max_age < stale_t:
            # Linear decay: 1.0 at degraded_t, 0.3 at stale_t
            progress = (max_age - degraded_t) / (stale_t - degraded_t)
            conviction = 1.0 - (0.7 * progress)
            return DataQuality.DEGRADED, max(0.3, conviction)
        else:
            return DataQuality.STALE, 0.1

    # -------------------------------------------------------------------------
    # FA Poller
    # -------------------------------------------------------------------------

    async def _run_fa_poller(self) -> None:
        """
        Polls FlashAlpha at configured interval. Handles reconnection with
        exponential backoff. Writes FASnapshot to self._fa_q.
        """
        backoff = self._config.reconnect_base_seconds
        symbols = self._config.massive_symbols  # same symbols for FA

        while self._running:
            try:
                snapshot = await self._fa.get_full_snapshot(symbols[0])
                await self._fa_q.put(snapshot)
                self._metrics["fa_update_count"] += 1
                backoff = self._config.reconnect_base_seconds  # reset on success

                logger.debug(
                    "fa.poll_ok",
                    extra={"symbol": symbols[0], "regime": snapshot.regime},
                )
                await asyncio.sleep(self._config.fa_poll_interval_seconds)

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                self._metrics["fa_error_count"] += 1
                logger.warning(
                    "fa.poll_error",
                    extra={"error": str(exc), "backoff": backoff},
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._config.reconnect_max_seconds)
                self._metrics["fa_reconnect_count"] += 1

    # -------------------------------------------------------------------------
    # Massive WebSocket
    # -------------------------------------------------------------------------

    async def _run_massive_ws(self) -> None:
        """
        Maintains WebSocket connection to Massive.com. Auto-reconnects with
        exponential backoff. Writes MassiveSnapshot to self._massive_q.
        """
        backoff = self._config.reconnect_base_seconds

        while self._running:
            try:
                async def on_quote(snapshot: MassiveSnapshot) -> None:
                    # Non-blocking put: drop oldest if queue full (backpressure)
                    if self._massive_q.full():
                        try:
                            self._massive_q.get_nowait()
                            self._metrics["signal_drop_count"] += 1
                        except asyncio.QueueEmpty:
                            pass
                    await self._massive_q.put(snapshot)
                    self._metrics["massive_update_count"] += 1

                await self._massive.subscribe_quotes(
                    self._config.massive_symbols,
                    callback=on_quote,
                )
                # subscribe_quotes blocks until disconnect
                backoff = self._config.reconnect_base_seconds

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                self._metrics["massive_error_count"] += 1
                logger.warning(
                    "massive.ws_error",
                    extra={"error": str(exc), "backoff": backoff},
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._config.reconnect_max_seconds)
                self._metrics["massive_reconnect_count"] += 1

    # -------------------------------------------------------------------------
    # Fusion Engine
    # -------------------------------------------------------------------------

    async def _run_fusion_engine(self) -> None:
        """
        Reads from both queues, merges into OptionsState, emits to signal engine.

        Uses asyncio.wait with FIRST_COMPLETED to drain whichever queue has data.
        This avoids blocking on one queue while the other has updates.
        """
        while self._running:
            try:
                # Wait for either queue to have data (100ms timeout to check _running)
                fa_get = asyncio.ensure_future(self._fa_q.get())
                massive_get = asyncio.ensure_future(self._massive_q.get())

                done, pending = await asyncio.wait(
                    {fa_get, massive_get},
                    timeout=0.1,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Cancel pending futures to avoid leaks
                for fut in pending:
                    fut.cancel()
                    try:
                        await fut
                    except (asyncio.CancelledError, Exception):
                        pass

                for fut in done:
                    result = fut.result()
                    if isinstance(result, FASnapshot):
                        self._last_fa_snapshot = result
                        self._last_fa_time = time.monotonic()
                        logger.debug("fusion.fa_update", extra={"regime": result.regime})
                    elif isinstance(result, MassiveSnapshot):
                        self._last_massive_snapshot = result
                        self._last_massive_time = time.monotonic()
                        logger.debug("fusion.massive_update", extra={"atm_iv": result.atm_iv})

                if done:
                    await self._emit_state()
                    self._metrics["fusion_count"] += 1

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("fusion.error", extra={"error": str(exc)})
                await asyncio.sleep(0.1)

    async def _emit_state(self) -> None:
        """Build OptionsState from latest snapshots and call signal engine callback."""
        if self.on_state_update is None:
            return

        quality, conviction = self._compute_quality()
        now = time.monotonic()

        fa = self._last_fa_snapshot
        massive = self._last_massive_snapshot

        state = OptionsState(
            timestamp=datetime.utcnow(),
            gamma_flip=fa.gamma_flip if fa else None,
            call_wall=fa.call_wall if fa else None,
            put_wall=fa.put_wall if fa else None,
            net_gex=fa.net_gex if fa else None,
            net_dex=fa.net_dex if fa else None,
            net_vex=fa.net_vex if fa else None,
            net_chex=fa.net_chex if fa else None,
            regime=fa.regime if fa else None,
            zero_dte_expected_move=fa.zero_dte_expected_move if fa else None,
            zero_dte_pin_score=fa.zero_dte_pin_score if fa else None,
            atm_iv=massive.atm_iv if massive else None,
            put_call_ratio=massive.put_call_ratio if massive else None,
            unusual_flow_score=massive.unusual_flow_score if massive else None,
            quality=quality,
            fa_age_seconds=(now - self._last_fa_time) if self._last_fa_time else float("inf"),
            massive_age_seconds=(now - self._last_massive_time) if self._last_massive_time else float("inf"),
            conviction_multiplier=conviction,
        )

        try:
            await self.on_state_update(state)
            self._metrics["signal_emit_count"] += 1
        except Exception as exc:
            logger.error("signal_emit.error", extra={"error": str(exc)})
```

---

## Integration with DEEP6 Main Loop

The pipeline must share the existing event loop. Don't call `asyncio.run()` inside it.

```python
# In deep6v2/main.py or wherever the main loop is started

async def main():
    # Existing DEEP6 setup
    rithmic_client = RithmicClient(config)
    signal_engine = SignalEngine(config)

    # Options pipeline setup
    fa_client = FlashAlphaClient(api_key=os.environ["FLASHALPHA_API_KEY"])
    massive_client = MassiveClient(api_key=os.environ["MASSIVE_API_KEY"])

    pipeline_config = PipelineConfig(
        fa_poll_interval_seconds=30.0,
        massive_symbols=["QQQ"],
        stale_threshold_seconds=300.0,
    )
    pipeline = OptionsPipeline(fa_client, massive_client, pipeline_config)

    # Wire signal engine callback
    pipeline.on_state_update = signal_engine.handle_options_state

    # Start everything — pipeline.start() is non-blocking
    await rithmic_client.connect()
    await pipeline.start()

    # Health check loop (runs alongside DOM callbacks)
    async def health_monitor():
        while True:
            await asyncio.sleep(60)
            if not pipeline.is_healthy():
                logger.warning(
                    "options_pipeline.unhealthy",
                    extra={"metrics": pipeline.metrics},
                )

    asyncio.create_task(health_monitor(), name="options_health_monitor")

    # Main loop — DOM callbacks drive everything else
    await rithmic_client.run_forever()

    # Shutdown
    await pipeline.stop(timeout=10.0)
    await rithmic_client.disconnect()
```

---

## Backpressure Handling

Options data is not latency-critical. The signal engine processes DOM callbacks at 1,000/sec;
options updates arrive at most every few seconds. Two backpressure scenarios:

**Scenario 1: Signal engine is slow**

The `_massive_q` is bounded (`maxsize=200`). If the fusion engine can't drain it fast enough,
`_run_massive_ws` drops the oldest item before inserting the new one. This is intentional:
a 30-second-old quote update is worthless.

```python
# In _run_massive_ws on_quote callback:
if self._massive_q.full():
    try:
        self._massive_q.get_nowait()  # drop oldest
        self._metrics["signal_drop_count"] += 1
    except asyncio.QueueEmpty:
        pass
await self._massive_q.put(snapshot)
```

**Scenario 2: Both clients down**

The fusion engine keeps emitting `OptionsState` with the last known snapshots, but
`quality` degrades from `FRESH` to `DEGRADED` to `STALE` and `conviction_multiplier`
decays toward 0.1. The signal engine should check `state.quality` before using options
signals for trade decisions.

```python
# In signal engine:
async def handle_options_state(self, state: OptionsState) -> None:
    if state.quality == DataQuality.STALE:
        # Don't use options signals for new entries
        self._options_signals_active = False
        return

    conviction = state.conviction_multiplier
    # Scale signal weights by conviction
    self._update_options_context(state, conviction)
```

---

## Structured Logging Reference

All log events use `extra={}` for structured fields. Use a JSON formatter in production.

| Event | Level | Key Fields |
|-------|-------|-----------|
| `options_pipeline.start` | INFO | config |
| `options_pipeline.stop` | INFO | timeout |
| `options_pipeline.stopped` | INFO | |
| `fa.poll_ok` | DEBUG | symbol, regime |
| `fa.poll_error` | WARNING | error, backoff |
| `massive.ws_error` | WARNING | error, backoff |
| `fusion.fa_update` | DEBUG | regime |
| `fusion.massive_update` | DEBUG | atm_iv |
| `fusion.error` | ERROR | error |
| `signal_emit.error` | ERROR | error |
| `options_pipeline.unhealthy` | WARNING | metrics |

---

## Metrics Reference

Access via `pipeline.metrics` (returns a dict snapshot, safe to call anytime).

| Key | Description |
|-----|-------------|
| `fa_update_count` | Total successful FA poll responses |
| `massive_update_count` | Total Massive quote updates received |
| `fusion_count` | Total fusion engine cycles that produced a state |
| `signal_emit_count` | Total OptionsState objects emitted to signal engine |
| `signal_drop_count` | Queue overflow drops (backpressure events) |
| `fa_error_count` | FA poll errors (network, 5xx, parse) |
| `massive_error_count` | Massive WS errors (disconnect, parse) |
| `fa_reconnect_count` | FA reconnection attempts |
| `massive_reconnect_count` | Massive WS reconnection attempts |

Expose these via a simple HTTP endpoint or log them periodically:

```python
async def log_metrics_periodically(pipeline: OptionsPipeline, interval: float = 300.0):
    while True:
        await asyncio.sleep(interval)
        logger.info("options_pipeline.metrics", extra=pipeline.metrics)
```
