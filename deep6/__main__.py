"""DEEP6 v2.0 — main asyncio entry point.

Startup sequence:
1. Build SharedState (all sub-components)
2. Initialize SQLite persistence
3. Connect Rithmic (Issue #49: 500ms delay after connect)
4. Register DOM and tick callbacks
5. Subscribe to NQ ORDER_BOOK + LAST_TRADE + BBO
6. Launch BarBuilders (1m and 5m) + SessionManager as asyncio tasks
7. Run event loop until KeyboardInterrupt or fatal error

Per D-13: asyncio event loop with uvloop drives all I/O and signal computation.
Per D-16: GC management at session boundaries is handled in SessionManager (Plan 03).
Per T-04-02: structlog config must NOT include rithmic_password in any bound context.
"""
import asyncio
import structlog
import uvloop
from async_rithmic import DataType

from deep6.config import Config
from deep6.data.bar_builder import BarBuilder
from deep6.data.rithmic import connect_rithmic, register_callbacks
from deep6.state.shared import SharedState

log = structlog.get_logger()


async def main(config: Config) -> None:
    """Assemble and run the DEEP6 data pipeline."""
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

    # 3. Connect Rithmic (Issue #49: connect_rithmic includes 500ms delay)
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

    # 5. Launch long-running tasks
    session_mgr = state.session_manager()
    tasks = [
        asyncio.create_task(bb_1m.run(),        name="bar_builder_1m"),
        asyncio.create_task(bb_5m.run(),        name="bar_builder_5m"),
        asyncio.create_task(session_mgr.run(),  name="session_manager"),
    ]
    log.info("deep6.running", task_count=len(tasks))

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        log.info("deep6.shutdown_requested")
    except Exception as exc:
        log.exception("deep6.fatal_error", exc=str(exc))
        raise
    finally:
        for task in tasks:
            task.cancel()
        log.info("deep6.stopped")


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
