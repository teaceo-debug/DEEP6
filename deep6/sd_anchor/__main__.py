"""SD Anchor AI sidecar — CLI entrypoint.

Launch:
    python -m deep6.sd_anchor --dry-run       # validate imports, print config, exit
    python -m deep6.sd_anchor                  # start sidecar loop + webhook server
    python -m deep6.sd_anchor --port 8780      # custom port
    python -m deep6.sd_anchor --data-root /tmp # custom data directory
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

logger = logging.getLogger("deep6.sd_anchor")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="deep6.sd_anchor",
        description="DEEP6 SD Anchor AI — HERMES sidecar observation bridge",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate imports and config, then exit",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8780,
        help="Webhook server port (default: 8780)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Webhook server bind address (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--data-root",
        type=str,
        default="data/sd_anchor",
        help="Root directory for audit/disagreement logs (default: data/sd_anchor)",
    )
    parser.add_argument(
        "--hermes-timeout",
        type=float,
        default=30.0,
        help="HERMES review timeout in seconds (default: 30.0)",
    )
    return parser.parse_args()


def _dry_run(args: argparse.Namespace) -> None:
    """Validate that all imports resolve and config is sane."""
    from deep6.sd_anchor.sidecar import SDSidecar, validate_candidate  # noqa: F401
    from deep6.sd_anchor.types import HermesVerdict  # noqa: F401

    sidecar = SDSidecar(
        data_root=Path(args.data_root),
        hermes_timeout_sec=args.hermes_timeout,
    )
    print(f"[dry-run] SDSidecar created  data_root={sidecar._data_root}")
    print(f"[dry-run] HERMES timeout     {sidecar._hermes_timeout}s")
    print(f"[dry-run] Webhook would bind {args.host}:{args.port}")

    # Validate a synthetic candidate round-trips
    sample = {
        "anchor_id": "dry-run-test",
        "symbol": "NQ1!",
        "timeframe_primary": "5",
        "direction": "bullish",
        "anchor_low_price": 20000.0,
        "anchor_high_price": 20050.0,
        "anchor_low_bar_time": 1700000000,
        "anchor_high_bar_time": 1700000300,
        "pine_confidence_score": 85,
        "pine_state": "candidate",
    }
    errors = validate_candidate(sample)
    if errors:
        print(f"[dry-run] FAIL — sample validation errors: {errors}")
        sys.exit(1)
    print("[dry-run] Sample candidate validates OK")
    print("[dry-run] All checks passed")


async def _run(args: argparse.Namespace) -> None:
    """Start the sidecar loop and webhook server."""
    from deep6.sd_anchor.sidecar import SDSidecar
    from deep6.sd_anchor.webhook import create_webhook_app

    sidecar = SDSidecar(
        data_root=Path(args.data_root),
        hermes_timeout_sec=args.hermes_timeout,
    )

    app = create_webhook_app(sidecar)

    # Graceful shutdown on SIGINT/SIGTERM
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    # Start sidecar background task
    sidecar_task = sidecar.start_background()
    logger.info(
        "sd_anchor.starting host=%s port=%d data_root=%s",
        args.host, args.port, args.data_root,
    )

    # Start uvicorn
    try:
        import uvicorn

        config = uvicorn.Config(
            app,
            host=args.host,
            port=args.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        serve_task = asyncio.create_task(server.serve())

        # Wait for shutdown signal or server exit
        done, _ = await asyncio.wait(
            [serve_task, asyncio.create_task(shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )
    except KeyboardInterrupt:
        pass
    finally:
        await sidecar.stop()
        if not sidecar_task.done():
            sidecar_task.cancel()
        logger.info("sd_anchor.stopped")


def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if args.dry_run:
        _dry_run(args)
        return

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
