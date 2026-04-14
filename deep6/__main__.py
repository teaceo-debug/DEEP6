"""DEEP6 v2.0 — main asyncio entry point.

Startup sequence:
1. Build SharedState (all sub-components)
2. Initialize SQLite persistence
3. Connect Rithmic (Issue #49: 500ms delay after connect)
4. Register DOM and tick callbacks
5. Subscribe to NQ ORDER_BOOK + LAST_TRADE + BBO
6. Launch BarBuilders (1m and 5m) + SessionManager as asyncio tasks
7. Run event loop until SIGTERM / SIGINT or fatal error

Per D-13: asyncio event loop with uvloop drives all I/O and signal computation.
Per D-16: GC management at session boundaries is handled in SessionManager (Plan 03).
Per T-04-02: structlog config must NOT include rithmic_password in any bound context.

Shutdown: SIGTERM and SIGINT are handled via asyncio signal handlers. Every task
is cancelled, persistence is closed, SQLite WAL is flushed, and final metrics are
logged before the event loop exits.
"""
import asyncio
import signal
import structlog
import uvloop
from async_rithmic import DataType

from deep6.config import Config
from deep6.data.bar_builder import BarBuilder
from deep6.data.rithmic import connect_rithmic, register_callbacks
from deep6.state.shared import SharedState

log = structlog.get_logger()

_shutdown_event: asyncio.Event | None = None
_shutting_down: bool = False


async def shutdown(state: SharedState, tasks: list[asyncio.Task] | None = None) -> None:
    """Graceful shutdown: cancel tasks, close persistence, flush WAL, log metrics.

    Idempotent — safe to invoke from multiple signal handlers.
    """
    global _shutting_down
    if _shutting_down:
        return
    _shutting_down = True

    log.info("deep6.shutdown.begin")

    # 1. Cancel all running tasks except the current one.
    current = asyncio.current_task()
    pending = [t for t in (tasks or asyncio.all_tasks()) if t is not current and not t.done()]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
        log.info("deep6.shutdown.tasks_cancelled", count=len(pending))

    # 2. Run component-level shutdown hooks if they exist.
    shutdown_hook = getattr(state, "shutdown", None)
    if callable(shutdown_hook):
        try:
            result = shutdown_hook()
            if asyncio.iscoroutine(result):
                await result
            log.info("deep6.shutdown.state_hook_done")
        except Exception as exc:  # noqa: BLE001
            log.warning("deep6.shutdown.state_hook_failed", exc=str(exc))

    # 3. Close persistence + flush SQLite WAL.
    persistence = getattr(state, "persistence", None)
    if persistence is not None:
        close_hook = getattr(persistence, "close", None)
        if callable(close_hook):
            try:
                result = close_hook()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:  # noqa: BLE001
                log.warning("deep6.shutdown.persistence_close_failed", exc=str(exc))
        await _flush_wal(persistence)

    # 4. Final metrics.
    try:
        metrics = {
            "session_id": getattr(getattr(state, "session", None), "session_id", None),
            "bar_builders": len(getattr(state, "bar_builders", []) or []),
        }
        log.info("deep6.shutdown.metrics", **{k: v for k, v in metrics.items() if v is not None})
    except Exception:  # noqa: BLE001
        pass

    log.info("deep6.shutdown.complete")

    if _shutdown_event is not None:
        _shutdown_event.set()


async def _flush_wal(persistence) -> None:
    """Best-effort SQLite WAL checkpoint on shutdown."""
    db_path = getattr(persistence, "db_path", None)
    if not db_path:
        return
    try:
        import aiosqlite

        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            await db.commit()
        log.info("deep6.shutdown.wal_flushed", db=str(db_path))
    except Exception as exc:  # noqa: BLE001
        log.warning("deep6.shutdown.wal_flush_failed", exc=str(exc))


async def main(config: Config) -> None:
    """Assemble and run the DEEP6 data pipeline."""
    global _shutdown_event
    _shutdown_event = asyncio.Event()

    log.info("deep6.starting", version="2.0.0", instrument=config.instrument)

    # 1. Build SharedState with all sub-components
    state = SharedState.build(config)
    await state.persistence.initialize()
    log.info("deep6.state_ready")

    # 2. Create dual-timeframe BarBuilders (D-04, D-05)
    bb_1m = BarBuilder(period_seconds=config.primary_bar_seconds,   label="1m", state=state)
    bb_5m = BarBuilder(period_seconds=config.secondary_bar_seconds,  label="5m", state=state)
    state.bar_builders = [bb_1m, bb_5m]
    log.info("deep6.bar_builders_ready", timeframes=["1m", "5m"])

    # 3. Connect the selected data source (phase 14: Databento Live or Rithmic)
    session_mgr = state.session_manager()
    tasks = [
        asyncio.create_task(bb_1m.run(),        name="bar_builder_1m"),
        asyncio.create_task(bb_5m.run(),        name="bar_builder_5m"),
        asyncio.create_task(session_mgr.run(),  name="session_manager"),
    ]

    if config.data_source == "databento":
        from deep6.data.factory import create_feed

        feed = create_feed("databento", config)
        tasks.append(
            asyncio.create_task(feed.start(state), name="databento_live_feed")
        )
        log.info(
            "deep6.databento_subscribed",
            instrument=config.instrument,
            symbol="NQ.c.0",
            schema="mbo",
        )
    else:
        client = await connect_rithmic(config)
        register_callbacks(client, state)
        log.info("deep6.rithmic_connected")

        # 4. Subscribe to market data (D-01: 40+ L2 levels for NQ)
        await client.subscribe_to_market_data(
            config.instrument, config.exchange, DataType.ORDER_BOOK
        )
        await client.subscribe_to_market_data(
            config.instrument, config.exchange, DataType.LAST_TRADE
        )
        await client.subscribe_to_market_data(
            config.instrument, config.exchange, DataType.BBO
        )
        log.info(
            "deep6.subscribed",
            instrument=config.instrument,
            data_types=["ORDER_BOOK", "LAST_TRADE", "BBO"],
        )
    log.info("deep6.running", task_count=len(tasks))

    # 6. Register POSIX signal handlers for graceful shutdown.
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(
                    shutdown(state, tasks), name=f"shutdown_{s.name}"
                ),
            )
        except NotImplementedError:
            # Windows / restricted environments — fall back to default handling.
            pass

    try:
        # Wait either for all long-running tasks to exit or for the shutdown
        # event to be set by a signal handler.
        gather_task = asyncio.create_task(
            asyncio.gather(*tasks, return_exceptions=True), name="main_gather"
        )
        shutdown_wait = asyncio.create_task(_shutdown_event.wait(), name="shutdown_wait")
        done, _pending = await asyncio.wait(
            {gather_task, shutdown_wait}, return_when=asyncio.FIRST_COMPLETED
        )
        for t in _pending:
            t.cancel()
    except asyncio.CancelledError:
        log.info("deep6.shutdown_requested")
    except Exception as exc:
        log.exception("deep6.fatal_error", exc=str(exc))
        await shutdown(state, tasks)
        raise
    finally:
        if not _shutting_down:
            await shutdown(state, tasks)


def cli_entry() -> None:
    """CLI entry point: load config from environment, run with uvloop.

    Per D-13: asyncio.Runner with uvloop.new_event_loop — not deprecated uvloop.install().
    Per T-04-02: structlog configured here; password MUST NOT appear in any processor.
    """
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )
    config = Config.from_env()
    with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
        runner.run(main(config))


if __name__ == "__main__":
    cli_entry()
