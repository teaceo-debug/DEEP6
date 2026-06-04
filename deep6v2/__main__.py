"""Unified startup: python -m deep6v2"""

from __future__ import annotations

import argparse
import asyncio
import gc
import signal
import sys

from deep6v2.logging import configure_logging, get_logger


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="deep6v2")
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--live", action="store_true")
    p.add_argument("--paper", action="store_true")
    p.add_argument("--dev", action="store_true", help="Console logging")
    p.add_argument(
        "--max-bars",
        type=int,
        default=0,
        help="Auto-exit after N bars (0=unlimited)",
    )
    return p.parse_args(argv)


async def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    configure_logging(dev_mode=args.dev)
    log = get_logger("main")

    mode = "live" if args.live else ("paper" if args.paper else "dry-run")
    log.info("system_starting", mode=mode)

    # Startup sequence:
    # 1. Load config
    # 2. Initialize clock
    # 3. Create signal registry
    # 4. Create scorer
    # 5. Create FSM
    # 6. Start subsystems (stubs for now)

    log.info("system_started")

    # GC management placeholder
    # gc.disable() at RTH open, gc.enable() at RTH close

    if args.max_bars > 0:
        log.info("auto_exit", max_bars=args.max_bars)
        return

    # In production: await shutdown_event.wait()
    log.info("shutting_down")


def run() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
