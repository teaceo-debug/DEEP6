#!/usr/bin/env python
"""NQ ATLAS — Options-Positioning Bias Engine

Usage:
    python run_atlas.py            # Start server at localhost:8766
    python run_atlas.py --dry-run  # Validate config, test API access, exit
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

import uvicorn

from nq_atlas.ai_bias import BiasInterpreter
from nq_atlas.config import Settings
from nq_atlas.flashalpha_client import FlashAlphaClient
from nq_atlas.flow import FlowEngine
from nq_atlas.massive_client import MassiveClient
from nq_atlas.orchestrator import compute_loop
from nq_atlas.server import app, set_state
from nq_atlas.state import AtlasState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("nq_atlas")


async def _dry_run(settings: Settings, client: MassiveClient) -> None:
    """Validate config and API access, then exit."""
    logger.info("NQ ATLAS dry-run starting...")
    logger.info(
        "Config loaded: port=%d, underlying=%s, refresh=%ds",
        settings.port,
        settings.underlying,
        settings.refresh_interval_sec,
    )

    try:
        result = await client.validate_connection()
        if result["connected"]:
            greeks = "yes" if result["has_greeks"] else "no (will compute from IV)"
            logger.info("Massive API: connected (Greeks: %s)", greeks)
            print("Ready")
            return

        logger.error("Massive API: FAILED — check NQ_ATLAS_MASSIVE_API_KEY")
        sys.exit(1)
    finally:
        await client.close()


async def main(settings: Settings) -> None:
    """Start all concurrent tasks."""
    state = AtlasState(refresh_interval_sec=settings.refresh_interval_sec)
    state.spots["underlying_sym"] = settings.underlying
    set_state(state)

    client = MassiveClient(api_key=settings.massive_api_key, min_oi=settings.min_oi)
    interpreter = BiasInterpreter(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
    )
    flow_engine = FlowEngine()
    fa_client = None
    if settings.flashalpha_api_key:
        fa_client = FlashAlphaClient(
            api_key=settings.flashalpha_api_key,
            symbol=settings.underlying,
        )
        logger.info("FlashAlpha client initialized (%s)", settings.underlying)
    else:
        logger.info("FlashAlpha: no API key configured, running Massive-only")

    uv_config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_level="warning",
        loop="asyncio",
    )
    uv_server = uvicorn.Server(uv_config)

    logger.info("NQ ATLAS starting on http://%s:%d", settings.host, settings.port)

    tasks = [
        asyncio.create_task(
            client.poll_loop(state, settings.refresh_interval_sec),
            name="poll_loop",
        ),
        asyncio.create_task(compute_loop(state, flow_engine), name="compute_loop"),
        asyncio.create_task(
            interpreter.interpret_loop(state, settings.ai_refresh_sec),
            name="ai_loop",
        ),
        asyncio.create_task(uv_server.serve(), name="uvicorn"),
    ]
    if fa_client:
        tasks.append(
            asyncio.create_task(
                fa_client.poll_loop(state, settings.flashalpha_refresh_sec),
                name="flashalpha_loop",
            )
        )

    shutdown_event = asyncio.Event()

    def _handle_shutdown(signum, frame):
        logger.info("Shutting down gracefully...")
        shutdown_event.set()

    try:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, lambda: _handle_shutdown(None, None))
        loop.add_signal_handler(signal.SIGTERM, lambda: _handle_shutdown(None, None))
    except (NotImplementedError, AttributeError):
        signal.signal(signal.SIGINT, _handle_shutdown)
        signal.signal(signal.SIGTERM, _handle_shutdown)

    shutdown_task = asyncio.create_task(shutdown_event.wait(), name="shutdown_wait")

    try:
        await asyncio.wait([shutdown_task, *tasks], return_when=asyncio.FIRST_COMPLETED)
    finally:
        shutdown_task.cancel()
        uv_server.should_exit = True
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await client.close()
        logger.info("NQ ATLAS stopped.")


def cli() -> None:
    parser = argparse.ArgumentParser(description="NQ ATLAS bias engine")
    parser.add_argument("--dry-run", action="store_true", help="Validate config and exit")
    args = parser.parse_args()

    settings = Settings()

    if args.dry_run:
        client = MassiveClient(api_key=settings.massive_api_key, min_oi=settings.min_oi)
        asyncio.run(_dry_run(settings, client))
    else:
        asyncio.run(main(settings))


if __name__ == "__main__":
    cli()
