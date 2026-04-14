"""DEEP6 production-mode startup script.

Creates the FastAPI app + LiveBridge and optionally wires them to a data source.

Usage:
    python scripts/run_live.py                  # defaults to --source=demo
    python scripts/run_live.py --source=demo    # demo broadcaster (no engine needed)
    python scripts/run_live.py --source=live    # real engine (Rithmic feed required)
    python scripts/run_live.py --port 8000      # custom port (default 8000)

--source=demo:
    Starts the FastAPI server, then spawns demo_broadcast.py as a subprocess
    that posts to /api/live/test-broadcast.  The dashboard receives realistic
    NQ market data without any Rithmic connection.  Use this for UI development
    and smoke-testing.

--source=live:
    Starts the FastAPI server and initialises the real engine stack (Rithmic
    feed + signal engines + scorer).  The LiveBridge (app.state.live_bridge)
    is passed to the engine so every bar close / signal fire / tape print
    reaches the dashboard via WSManager.broadcast().

    NOTE: The real engine wiring is scaffolded as commented stubs below.
    The integration points are:
        1. FootprintBuilder.on_bar_close  → bridge.on_bar_close(bar)
        2. score_bar() result             → bridge.on_score_update(result)
        3. tier >= TYPE_C                 → bridge.on_signal_fired(result)
        4. Rithmic on_trade callback      → bridge.on_tape_print(trade)
        5. asyncio periodic task          → bridge.periodic_status() every 10s

Mixed mode (engine partially ready):
    Start with --source=demo, then add real-engine calls to the live_bridge
    for the subsystems that are ready.  The dashboard cannot distinguish
    which messages come from demo vs real engine.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import uvicorn

log = logging.getLogger("deep6.run_live")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)

# Absolute path to repo root (scripts/ is one level down)
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


# ---------------------------------------------------------------------------
# Demo source
# ---------------------------------------------------------------------------

async def _run_demo_broadcaster(base_url: str) -> None:
    """Spawn demo_broadcast.py as a subprocess and stream its stdout."""
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
# Live engine source (scaffold — wire real engine here)
# ---------------------------------------------------------------------------

async def _run_live_engine(app) -> None:  # noqa: ANN001
    """Scaffold for real engine integration.

    Replace the stub body below with actual engine initialisation once the
    Rithmic feed and signal engine are ready.

    The bridge is available at: app.state.live_bridge
    The ws_manager is available at: app.state.ws_manager
    """
    bridge = app.state.live_bridge
    log.info("live_engine: bridge ready  session_start_ts=%.0f", bridge.session_start_ts)

    # -----------------------------------------------------------------------
    # STUB — replace this section with real engine wiring:
    #
    # from deep6.rithmic.feed import RithmicFeed
    # from deep6.state.footprint import FootprintBuilder
    # from deep6.scoring.scorer import score_bar
    # from deep6.engines.narrative import build_narrative
    #
    # feed = RithmicFeed(...)
    # builder = FootprintBuilder(on_bar_close=_on_bar_close)
    #
    # async def _on_bar_close(bar):
    #     # 1. Score the bar
    #     result = score_bar(narrative, delta_signals, ..., bar_close=bar.close)
    #     # 2. Always push score update
    #     await bridge.on_score_update(result)
    #     # 3. Push bar to dashboard
    #     await bridge.on_bar_close(bar)
    #     # 4. Push signal if tier >= TYPE_C
    #     if result.tier.value >= 1:  # TYPE_C = 1
    #         await bridge.on_signal_fired(result)
    #
    # async def _on_trade(trade):
    #     await bridge.on_tape_print(trade)
    #
    # await feed.connect()
    # await feed.subscribe(on_trade=_on_trade)
    # -----------------------------------------------------------------------

    # Periodic status loop — keep alive while engine runs
    log.warning(
        "live_engine: STUB mode — no real Rithmic feed connected.\n"
        "  Wire the engine in scripts/run_live.py _run_live_engine() "
        "and restart with --source=live."
    )
    while True:
        await bridge.periodic_status()
        await asyncio.sleep(10.0)


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

async def _main(source: str, host: str, port: int) -> None:
    """Start uvicorn + data source concurrently."""
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
        log.info("run_live: source=live  url=%s", base_url)
        # Wait for uvicorn to bind then start engine
        async def _start_engine_after_boot() -> None:
            await asyncio.sleep(0.5)
            await _run_live_engine(app)

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
        help="Data source: 'demo' (no engine) or 'live' (real Rithmic feed). "
             "Default: demo",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
        help="Bind port (default: 8000)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(_main(args.source, args.host, args.port))
    except KeyboardInterrupt:
        log.info("run_live: stopped by user")


if __name__ == "__main__":
    main()
