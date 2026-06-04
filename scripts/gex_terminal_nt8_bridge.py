"""GEX Terminal NT8 Bridge — polls gex_terminal /state and writes NT8 JSON.

Reads the GEX Terminal snapshot from http://localhost:8780/state every 10s,
maps it into a flat NT8-friendly payload, and atomically writes it to
gex_terminal_nt8.json in the NT8 templates folder.

Usage:
    python scripts/gex_terminal_nt8_bridge.py              # Start bridge loop
    python scripts/gex_terminal_nt8_bridge.py --dry-run    # Single fetch + print, then exit
    python scripts/gex_terminal_nt8_bridge.py --output /path/to/file.json
    python scripts/gex_terminal_nt8_bridge.py --interval 5 # Poll every 5s
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gex_nt8_bridge")

SCHEMA_VERSION = 1
GEX_TERMINAL_URL = "http://localhost:8780"
POLL_INTERVAL = 10  # seconds
STALE_AFTER_SECONDS = 90  # NT8 side should consider data stale past this

# NT8 output paths — platform-dependent
_NT8_PATH_WIN = r"C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\gex_terminal_nt8.json"
_NT8_PATH_WSL = "/mnt/c/Users/Tea/Documents/NinjaTrader 8/templates/DEEP6/gex_terminal_nt8.json"


def _default_output_path() -> Path:
    """Return the correct output path for the current platform."""
    if sys.platform == "win32":
        return Path(_NT8_PATH_WIN)
    wsl_path = Path(_NT8_PATH_WSL)
    if wsl_path.parent.exists():
        return wsl_path
    return Path(_NT8_PATH_WIN)


def _safe_float(value, default: float = 0.0) -> float:
    """Convert to float, treating None/missing as default."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_int(value, default: int = 0) -> int:
    """Convert to int, treating None/missing as default."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _fetch_state(url: str) -> dict | None:
    """Fetch /state JSON from gex_terminal. Returns None on failure."""
    try:
        with urllib.request.urlopen(f"{url}/state", timeout=5) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read())
    except Exception as exc:
        logger.warning("Failed to fetch %s/state: %s", url, exc)
        return None


def _map_snapshot_to_nt8(snapshot: dict) -> dict:
    """Map GEXTerminalSnapshot dict into flat NT8 payload."""
    bias = snapshot.get("bias") or {}
    levels = snapshot.get("levels") or {}
    dealer = snapshot.get("dealer") or {}
    flow = snapshot.get("flow") or {}
    dark_pool = snapshot.get("dark_pool") or {}
    institutional = snapshot.get("institutional") or {}
    narrative = snapshot.get("narrative") or {}
    dp_levels_out = institutional.get("dp_levels") or []
    grid = institutional.get("signal_grid") or {}

    return {
        "schema_version": SCHEMA_VERSION,
        "as_of": time.time(),
        "stale_after_seconds": STALE_AFTER_SECONDS,
        "status": "ok",
        "bias_direction": bias.get("direction", "NEUTRAL"),
        "bias_confidence": _safe_int(bias.get("confidence"), 0),
        "bias_grade": bias.get("grade", "C"),
        "regime_name": bias.get("regime_name", "Unknown"),
        "gamma_flip": _safe_float(levels.get("gamma_flip")),
        "call_wall": _safe_float(levels.get("call_wall")),
        "put_wall": _safe_float(levels.get("put_wall")),
        "zero_dte_magnet": _safe_float(levels.get("zero_dte_magnet")),
        "hvl": _safe_float(levels.get("hvl")),
        "expected_move_up": _safe_float(levels.get("expected_move_up")),
        "expected_move_down": _safe_float(levels.get("expected_move_down")),
        "dealer_regime": dealer.get("regime", "neutral"),
        "hedge_direction": dealer.get("hedge_direction", "neutral"),
        "flow_direction": flow.get("direction", "neutral"),
        "flow_intensity": _safe_float(flow.get("intensity")),
        "headline": (narrative.get("text") or "")[:240],
        "dark_pool_levels_nq": dark_pool.get("levels_nq") or [],
        "dp_levels_count": len(dp_levels_out),
        "dp_levels": [
            {
                "price": _safe_float(level.get("price_nq")),
                "type": level.get("level_type", "NEUTRAL"),
                "premium": _safe_float(level.get("total_premium")),
                "count": _safe_int(level.get("print_count")),
            }
            for level in dp_levels_out[:5]
            if isinstance(level, dict)
        ],
        "signal_confluence_buy": _safe_int(grid.get("confluence_buy")),
        "signal_confluence_sell": _safe_int(grid.get("confluence_sell")),
        "swing_equilibrium": _safe_float(
            (institutional.get("swing_equilibrium") or {}).get("price_nq")
        ),
        "dp_bias": institutional.get("dp_bias", "NEUTRAL"),
        "primary_magnet": _safe_float(snapshot.get("primary_magnet")) or None,
        "magnet_confidence": _safe_float(snapshot.get("magnet_confidence")) or None,
        "direction_signal": snapshot.get("direction_signal", "FLAT"),
        "direction_confidence": _safe_int(snapshot.get("direction_confidence"), 0),
        "direction_reason": (snapshot.get("direction_reason") or "")[:120],
    }


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically via temp file + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(serialized)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def _run_bridge_loop(output_path: Path, *, dry_run: bool = False, interval: int = POLL_INTERVAL) -> None:
    """Inner bridge loop — poll, map, write. Raises on unexpected errors."""
    iteration = 0
    while True:
        snapshot = _fetch_state(GEX_TERMINAL_URL)

        if snapshot is None:
            payload = {
                "schema_version": SCHEMA_VERSION,
                "as_of": time.time(),
                "stale_after_seconds": STALE_AFTER_SECONDS,
                "status": "unavailable",
                "bias_direction": "NEUTRAL",
                "bias_confidence": 0,
                "bias_grade": "F",
                "regime_name": "Offline",
                "gamma_flip": 0.0,
                "call_wall": 0.0,
                "put_wall": 0.0,
                "zero_dte_magnet": 0.0,
                "hvl": 0.0,
                "expected_move_up": 0.0,
                "expected_move_down": 0.0,
                "dealer_regime": "neutral",
                "hedge_direction": "neutral",
                "flow_direction": "neutral",
                "flow_intensity": 0.0,
                "headline": "",
                "dark_pool_levels_nq": [],
                "dp_levels_count": 0,
                "dp_levels": [],
                "signal_confluence_buy": 0,
                "signal_confluence_sell": 0,
                "swing_equilibrium": 0.0,
                "dp_bias": "NEUTRAL",
                "primary_magnet": None,
                "magnet_confidence": None,
                "direction_signal": "FLAT",
                "direction_confidence": 0,
                "direction_reason": "",
            }
            logger.warning("[%d] GEX Terminal unreachable — writing offline payload", iteration)
        else:
            payload = _map_snapshot_to_nt8(snapshot)

        if dry_run:
            print(json.dumps(payload, indent=2))
            logger.info("Dry run complete.")
            return

        _atomic_write_json(output_path, payload)
        iteration += 1
        logger.info(
            "[%d] %s conf=%d%% grade=%s regime=%s",
            iteration,
            payload["bias_direction"],
            payload["bias_confidence"],
            payload["bias_grade"],
            payload["regime_name"],
        )

        time.sleep(interval)


def run_bridge(output_path: Path, *, dry_run: bool = False, interval: int = POLL_INTERVAL) -> None:
    """Main bridge entry with crash recovery. Retries with exponential backoff."""
    logger.info("GEX Terminal NT8 Bridge starting")
    logger.info("  Source: %s/state", GEX_TERMINAL_URL)
    logger.info("  Output: %s", output_path)
    logger.info("  Interval: %ds", interval)

    if dry_run:
        _run_bridge_loop(output_path, dry_run=True, interval=interval)
        return

    retry_count = 0
    max_retries = 100  # effectively infinite for a long-running service

    while retry_count < max_retries:
        try:
            _run_bridge_loop(output_path, dry_run=False, interval=interval)
        except KeyboardInterrupt:
            logger.info("Bridge stopped by user (KeyboardInterrupt)")
            break
        except Exception as exc:
            retry_count += 1
            wait = min(30, 2 ** min(retry_count, 5))  # max 30s backoff
            logger.error(
                "Bridge crashed (attempt %d/%d): %s — retrying in %ds",
                retry_count, max_retries, exc, wait,
            )
            time.sleep(wait)

    if retry_count >= max_retries:
        logger.error("Bridge exhausted all %d retries — exiting", max_retries)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GEX Terminal NT8 Bridge — gex_terminal /state → NT8 JSON file"
    )
    parser.add_argument("--dry-run", action="store_true", help="Single fetch + print, then exit")
    parser.add_argument("--output", type=str, default=None, help="Output JSON path")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL, help="Poll interval in seconds")
    parser.add_argument("--url", type=str, default=None, help="GEX Terminal base URL")
    args = parser.parse_args()

    global GEX_TERMINAL_URL
    if args.url is not None:
        GEX_TERMINAL_URL = args.url

    output_path = Path(args.output) if args.output else _default_output_path()

    # Ignore SIGHUP for background operation
    try:
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
    except (AttributeError, OSError):
        pass

    try:
        run_bridge(output_path, dry_run=args.dry_run, interval=args.interval)
    except KeyboardInterrupt:
        pass
    logger.info("GEX Terminal NT8 Bridge stopped.")


if __name__ == "__main__":
    main()
