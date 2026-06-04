"""Copilot CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging

from .config import CopilotConfig
from .session import SessionManager


def main() -> None:
    parser = argparse.ArgumentParser(description="DEEP6 AI Chart Copilot", prog="deep6.copilot")
    parser.add_argument("--dry-run", action="store_true", help="Run without side effects")
    parser.add_argument("--test-overlay", action="store_true", help="Test overlay wiring")
    parser.add_argument("--config", type=str, default=None, help="Optional config path")
    parser.add_argument("--override-rth", action="store_true", help="Skip RTH gate (run outside market hours)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    config = CopilotConfig.from_env(args.config)
    print("Copilot starting...")
    if args.dry_run:
        print("Dry run enabled")
        print("Dry run: config loaded OK")
        return
    if args.test_overlay:
        print("Overlay test enabled")
        return
    if args.config:
        print(f"Config: {args.config}")

    session = SessionManager(config, override_rth=args.override_rth)
    asyncio.run(session.run_until_shutdown())


if __name__ == "__main__":
    main()
