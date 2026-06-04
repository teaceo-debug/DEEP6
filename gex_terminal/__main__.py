"""GEX Terminal entry point."""
from __future__ import annotations

import atexit
import argparse
import os
import signal
import sys
from pathlib import Path


PID_FILE = Path.home() / ".deep6" / "gexdoctor_v2.pid"


def acquire_pid_lock() -> None:
    """Write PID file. Exit if another instance is running."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    if PID_FILE.exists():
        try:
            existing_pid = int(PID_FILE.read_text().strip())
            os.kill(existing_pid, 0)
            print(f"ERROR: GEX Terminal already running (PID {existing_pid})")
            print(f"  PID file: {PID_FILE}")
            print("  Kill the existing process or delete the PID file to start a new instance.")
            sys.exit(1)
        except (ProcessLookupError, ValueError, PermissionError, OSError):
            PID_FILE.unlink(missing_ok=True)

    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    atexit.register(release_pid_lock)


def release_pid_lock() -> None:
    """Remove PID file on exit."""
    PID_FILE.unlink(missing_ok=True)


def handle_shutdown(signum, frame):
    """Handle SIGINT/SIGTERM gracefully."""
    print("\nGEX Terminal shutting down...")
    release_pid_lock()
    sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GEX Doctor v2.0 — Institutional Options Bias Terminal"
    )
    parser.add_argument("--port", type=int, help="Server port (default: 8780)")
    parser.add_argument("--refresh", type=int, help="Refresh interval in seconds (default: 30)")
    parser.add_argument("--dry-run", action="store_true", help="Validate config and exit")
    parser.add_argument("--log-level", default="INFO", help="Log level (default: INFO)")
    args = parser.parse_args()

    from gex_terminal.config import Settings

    settings = Settings(
        **({"server_port": args.port} if args.port else {}),
        **({"refresh_interval_sec": args.refresh} if args.refresh else {}),
        **({"log_level": args.log_level} if args.log_level else {}),
    )

    from gex_terminal.engine.logger import setup_logging, write_audit

    setup_logging(settings.log_level)
    write_audit({"event": "startup", "dry_run": args.dry_run, "port": settings.server_port})

    if not args.dry_run:
        acquire_pid_lock()
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)

    if args.dry_run:
        print("GEX Terminal v2.0 — Config validated")
        print(f"  Port: {settings.server_port}")
        print(f"  Refresh: {settings.refresh_interval_sec}s")
        print(f"  Claude model: {settings.claude_model}")
        print(f"  DEEP6 URL: {settings.deep6_bias_url}")
        print(f"  FlashAlpha key: {'SET' if settings.flashalpha_api_key else 'NOT SET'}")
        print(f"  Massive key: {'SET' if settings.massive_api_key else 'NOT SET'}")
        print(f"  UW key: {'SET' if settings.uw_api_key else 'NOT SET'}")
        print(f"  Anthropic key: {'SET' if settings.anthropic_api_key else 'NOT SET'}")
        sys.exit(0)

    import uvicorn
    from gex_terminal.server import app

    write_audit({"event": "server_start", "port": settings.server_port})
    uvicorn.run(app, host="0.0.0.0", port=settings.server_port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()
