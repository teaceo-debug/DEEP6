"""DEEP6 production-mode startup script.

Starts the FastAPI server (exposing /ws/live, /api/session/status, …) and,
for --source=live, the full async-rithmic data pipeline that drives the
44-signal engines → ScorerResult → LiveBridge → WSManager broadcast.

Usage:
    python scripts/run_live.py                      # defaults to --source=demo
    python scripts/run_live.py --source=demo        # synthetic NQ data (no engine)
    python scripts/run_live.py --source=live        # real engine (Rithmic/Databento feed)
    python scripts/run_live.py --port 8765          # custom port (default 8765)
    python scripts/run_live.py --source=live --data-source=rithmic

--source=demo:
    Starts the FastAPI server then spawns ``scripts/demo_broadcast.py`` as a
    subprocess that posts to ``/api/live/test-broadcast``. The dashboard
    receives realistic NQ market data without any Rithmic connection.

--source=live:
    Starts the FastAPI server AND the full DEEP6 data pipeline:
        Rithmic/Databento → DOM + tick callbacks → BarBuilder (1m, 5m)
        → SharedState.on_bar_close → LiveSignalPipeline (narrative +
        per-category engines + scorer) → LiveBridge → WSManager.broadcast()

    All in one asyncio event loop. ``DEEP6_DATA_SOURCE`` env var or the
    ``--data-source`` flag chooses between ``rithmic`` and ``databento``
    (default: whatever Config.from_env() resolves to — typically
    ``databento`` in repo default, ``rithmic`` when RITHMIC_USER is set).

Gates preserved (do NOT bypass):
    D-03  aggressor verification — in tick_feed / rithmic.py
    D-06  RTH gate — in BarBuilder._is_rth (only RTH bars close)
    D-17  FreezeGuard — in tick_feed + BarBuilder.run

The live bar-close callback fans every closed bar through the full scorer
and hands the result to the LiveBridge for WS broadcast. TYPE_C or better
also fires on_signal_fired.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import subprocess  # noqa: F401  (still referenced by some docs)
import sys
from pathlib import Path

import structlog
import uvicorn

log = logging.getLogger("deep6.run_live")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)

# Configure structlog once so DEEP6 engine logs render consistently.
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


# ---------------------------------------------------------------------------
# Demo source
# ---------------------------------------------------------------------------

async def _run_demo_broadcaster(base_url: str) -> None:
    """Spawn scripts/demo_broadcast.py as a subprocess and stream its stdout."""
    demo_script = str(SCRIPTS_DIR / "demo_broadcast.py")
    cmd = [sys.executable, demo_script, "--url", base_url, "--seed", "-1"]
    log.info("demo_broadcaster: starting  cmd=%s", " ".join(cmd))

    # Small delay so uvicorn has time to bind the port before demo hits it.
    await asyncio.sleep(1.5)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout is not None
    try:
        async for line in proc.stdout:
            sys.stdout.write(line.decode(errors="replace"))
            sys.stdout.flush()
    except asyncio.CancelledError:
        proc.terminate()
        await proc.wait()
        raise


# ---------------------------------------------------------------------------
# Live engine source
# ---------------------------------------------------------------------------

async def _run_live_engine(app, data_source: str | None) -> None:  # noqa: ANN001
    """Assemble and run the full DEEP6 pipeline in this event loop.

    Mirrors ``deep6.__main__.main`` but (a) reuses the FastAPI app's
    WSManager / LiveBridge so every bar close fans out to dashboard clients,
    and (b) wires ``state._on_bar_close_fn`` to the 44-signal pipeline.

    The bridge is available at ``app.state.live_bridge``; the ws_manager
    singleton is at ``app.state.ws_manager`` (both are set by the lifespan).
    """
    # Imports deferred so FastAPI / env config is settled first.
    from async_rithmic import DataType

    from deep6.config import Config
    from deep6.data.bar_builder import BarBuilder
    from deep6.data.rithmic import connect_rithmic, register_callbacks
    from deep6.engines.live_pipeline import LiveSignalPipeline
    from deep6.scoring.scorer import SignalTier
    from deep6.state.shared import SharedState

    bridge = app.state.live_bridge
    log.info("live_engine: bridge ready  session_start_ts=%.0f",
             bridge.session_start_ts)

    cfg = Config.from_env()
    if data_source:
        # CLI flag overrides env var / Config default.
        object.__setattr__(cfg, "data_source", data_source)

    log.info("live_engine: building SharedState  instrument=%s data_source=%s",
             cfg.instrument, cfg.data_source)

    state = SharedState.build(cfg)
    await state.persistence.initialize()

    # Attach the FastAPI EventStore (if the lifespan created one) so walk-forward
    # / setup-transition persistence routes through the same DB.
    event_store = getattr(app.state, "event_store", None)
    if event_store is not None:
        state.attach_event_store(event_store)

    # Dual-timeframe BarBuilders (D-04, D-05).
    bb_1m = BarBuilder(period_seconds=cfg.primary_bar_seconds, label="1m", state=state)
    bb_5m = BarBuilder(period_seconds=cfg.secondary_bar_seconds, label="5m", state=state)
    state.bar_builders = [bb_1m, bb_5m]
    log.info("live_engine: bar builders ready  timeframes=1m,5m")

    # Signal pipeline — instantiated once, one copy of per-timeframe engines.
    pipeline = LiveSignalPipeline(timeframes=("1m", "5m"))

    # Bar-close hook — fires on every closed RTH bar. Runs the signal stack,
    # pushes the score to the dashboard, and emits a signal event for TYPE_C+.
    async def _on_bar_close(label: str, bar) -> None:  # noqa: ANN001
        try:
            result = pipeline.run_bar(label, bar, state)
        except Exception:
            log.exception("live_engine.pipeline_failed label=%s", label)
            result = None

        # Always broadcast the bar to the dashboard so the footprint chart
        # updates in real time.
        try:
            await bridge.on_bar_close(bar)
        except Exception:
            log.exception("live_engine.bridge.on_bar_close_failed label=%s", label)

        if result is None:
            return

        # Score card update on every bar (TYPE_* or QUIET).
        try:
            await bridge.on_score_update(result)
        except Exception:
            log.exception("live_engine.bridge.on_score_update_failed label=%s", label)

        # Signal fire — TYPE_C or better.
        if isinstance(result.tier, SignalTier) and result.tier.value >= SignalTier.TYPE_C.value:
            try:
                await bridge.on_signal_fired(result)
            except Exception:
                log.exception("live_engine.bridge.on_signal_fired_failed label=%s", label)

        # Drive the setup state machine (phase 12-04). Non-fatal on error.
        try:
            await state.feed_scorer_result(
                label=label,
                scorer_result=result,
                slingshot_result=(
                    state.last_slingshot_1m if label == "1m" else state.last_slingshot_5m
                ),
                current_bar_index=pipeline._bar_index.get(label, 0) - 1,
            )
        except Exception:
            log.exception("live_engine.feed_scorer_result_failed label=%s", label)

    state._on_bar_close_fn = _on_bar_close

    # Long-running tasks — BarBuilders + SessionManager, plus feed.
    session_mgr = state.session_manager()
    tasks: list[asyncio.Task] = [
        asyncio.create_task(bb_1m.run(), name="bar_builder_1m"),
        asyncio.create_task(bb_5m.run(), name="bar_builder_5m"),
        asyncio.create_task(session_mgr.run(), name="session_manager"),
    ]

    # Data source: Databento live OR Rithmic.
    if cfg.data_source == "databento":
        from deep6.data.factory import create_feed  # local import

        feed = create_feed("databento", cfg)

        async def _feed_wrapper() -> None:
            try:
                await feed.start(state)
            except Exception:
                log.exception("live_engine.databento_feed_crashed")
                raise

        tasks.append(asyncio.create_task(_feed_wrapper(), name="databento_live_feed"))
        log.info("live_engine: databento subscribed  instrument=%s symbol=NQ.c.0",
                 cfg.instrument)
    else:
        client = await connect_rithmic(cfg)
        register_callbacks(client, state)
        await client.subscribe_to_market_data(
            cfg.instrument, cfg.exchange, DataType.ORDER_BOOK
        )
        await client.subscribe_to_market_data(
            cfg.instrument, cfg.exchange, DataType.LAST_TRADE
        )
        await client.subscribe_to_market_data(
            cfg.instrument, cfg.exchange, DataType.BBO
        )
        log.info("live_engine: rithmic subscribed  instrument=%s  types=ORDER_BOOK,LAST_TRADE,BBO",
                 cfg.instrument)

    # Periodic bridge status — every 10s so the dashboard's keepalive panel
    # stays fresh even on thin volume days.
    async def _status_loop() -> None:
        while True:
            try:
                await bridge.periodic_status()
            except Exception:
                log.exception("live_engine.periodic_status_failed")
            await asyncio.sleep(10.0)

    tasks.append(asyncio.create_task(_status_loop(), name="bridge_status_loop"))

    log.info("live_engine: running  task_count=%d", len(tasks))

    # Wait until any task exits or the server is cancelled.
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for t in done:
            exc = t.exception()
            if exc is not None:
                log.error("live_engine.task_failed  name=%s  exc=%s", t.get_name(), exc)
    except asyncio.CancelledError:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

async def _main(source: str, host: str, port: int, data_source: str | None) -> None:
    """Start uvicorn + data source concurrently in one event loop."""
    from deep6.api.app import app  # import here so env vars are set first

    base_url = f"http://{host}:{port}"

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        loop="asyncio",
    )
    server = uvicorn.Server(config)

    if source == "demo":
        log.info("run_live: source=demo  url=%s", base_url)
        await asyncio.gather(
            server.serve(),
            _run_demo_broadcaster(base_url),
        )
    elif source == "live":
        log.info("run_live: source=live  url=%s  data_source=%s",
                 base_url, data_source or "(env/config default)")

        async def _start_engine_after_boot() -> None:
            # Wait for uvicorn to bind the port and finish lifespan startup.
            await asyncio.sleep(0.5)
            await _run_live_engine(app, data_source)

        await asyncio.gather(
            server.serve(),
            _start_engine_after_boot(),
        )
    else:
        log.error("run_live: unknown --source=%r  (use 'demo' or 'live')", source)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DEEP6 production-mode startup — FastAPI + data source"
    )
    parser.add_argument(
        "--source",
        choices=["demo", "live"],
        default="demo",
        help="Data source: 'demo' (synthetic) or 'live' (real feed). Default: demo",
    )
    parser.add_argument(
        "--data-source",
        choices=["rithmic", "databento"],
        default=None,
        help="For --source=live only: which market data provider. Overrides "
             "DEEP6_DATA_SOURCE env var. Default: use env / Config value.",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", os.environ.get("DEEP6_API_PORT", "8765"))),
        help="Bind port (default: 8765 — matches dashboard NEXT_PUBLIC_WS_URL)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(_main(args.source, args.host, args.port, args.data_source))
    except KeyboardInterrupt:
        log.info("run_live: stopped by user")


if __name__ == "__main__":
    main()
