"""Massive GEX Map → gex_nq.json bridge.

Reads massive_gex_map.json (written by massive_gex_map_service.py every 45s)
and transforms it into the gex_nq.json format that GEXDoctor.cs expects.

Usage:
    python scripts/massive_to_gex_nq_bridge.py              # Loop (30s interval)
    python scripts/massive_to_gex_nq_bridge.py --once       # Single write, exit
    python scripts/massive_to_gex_nq_bridge.py --interval 15
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("massive_gex_nq_bridge")

# Input: massive_gex_map.json (written by massive_gex_map_service.py)
_MASSIVE_JSON_WIN = r"C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\massive_gex_map.json"
_MASSIVE_JSON_WSL = "/mnt/c/Users/Tea/Documents/NinjaTrader 8/templates/DEEP6/massive_gex_map.json"

# Output: gex_nq.json (read by GEXDoctor.cs)
_GEX_NQ_JSON_WIN = r"C:\Users\Public\Documents\NinjaTrader 8\bin\Custom\AddOns\gex_nq.json"
_GEX_NQ_JSON_WSL = "/mnt/c/Users/Public/Documents/NinjaTrader 8/bin/Custom/AddOns/gex_nq.json"

POLL_INTERVAL = 30
STALE_AFTER_SECONDS = 300


def _resolve_path(win: str, wsl: str) -> Path:
    if sys.platform == "win32":
        return Path(win)
    wsl_path = Path(wsl)
    if wsl_path.parent.exists():
        return wsl_path
    return Path(win)


def _read_massive_map(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except Exception as exc:
        logger.error("Failed to read massive_gex_map.json: %s", exc)
        return None


def _extract_level(levels: list[dict], role: str) -> float | None:
    for level in levels:
        if level.get("role") == role or level.get("key") == role:
            price = level.get("mapped_price") or level.get("price")
            if price is not None and price > 0:
                return float(price)
    return None


def _extract_net_gex(levels: list[dict]) -> float:
    total = 0.0
    for level in levels:
        gex = level.get("gex") or level.get("value") or 0.0
        total += float(gex)
    return total


def _determine_regime(flip: float | None, nq_spot: float | None, net_gex: float) -> str:
    if flip is not None and nq_spot is not None:
        if nq_spot > flip:
            return "POS_GEX"
        return "NEG_GEX"
    if net_gex > 0:
        return "POS_GEX"
    if net_gex < 0:
        return "NEG_GEX"
    return "NEUTRAL"


def _determine_bias(regime: str, flip: float | None, nq_spot: float | None) -> str:
    if regime == "POS_GEX":
        return "bullish"
    if regime == "NEG_GEX":
        return "bearish"
    return "neutral"


def _build_invalidation(regime: str, flip: float | None) -> tuple[float | None, str]:
    if flip is None:
        return None, ""
    if regime == "POS_GEX":
        return flip - 10.0, "Break below gamma flip invalidates bullish regime"
    if regime == "NEG_GEX":
        return flip + 10.0, "Break above gamma flip invalidates bearish regime"
    return flip, "Gamma flip crossover changes regime"


def _build_lean(regime: str, nq_spot: float | None, flip: float | None) -> str:
    if regime == "POS_GEX":
        return "Positive gamma: dealers long gamma, dampening volatility. Mean-reversion favored, fade extremes toward call wall."
    if regime == "NEG_GEX":
        return "Negative gamma: dealers short gamma, amplifying moves. Trend-following favored, momentum breaks through put wall."
    return "Neutral regime: no clear dealer hedging bias. Wait for regime clarity before directional positioning."


def transform(massive_data: dict) -> dict | None:
    """Transform massive_gex_map.json → gex_nq.json format."""
    assets = massive_data.get("assets", [])
    if not assets:
        logger.warning("No assets in massive_gex_map.json")
        return None

    asset = assets[0]
    levels = asset.get("levels", [])
    if not isinstance(levels, list):
        levels = []

    nq_spot = asset.get("futures_spot")
    qqq_spot = asset.get("underlying_spot")

    flip = _extract_level(levels, "gamma_flip")
    call_wall = _extract_level(levels, "call_wall")
    put_wall = _extract_level(levels, "put_wall")
    net_gex = _extract_net_gex(levels)

    regime = _determine_regime(flip, nq_spot, net_gex)
    bias = _determine_bias(regime, flip, nq_spot)
    invalidation_level, invalidation_reason = _build_invalidation(regime, flip)
    lean = _build_lean(regime, nq_spot, flip)

    # Primary magnet: call wall in positive gamma, put wall in negative
    if regime == "POS_GEX" and call_wall:
        primary_magnet = call_wall
        magnet_confidence = 0.7
    elif regime == "NEG_GEX" and put_wall:
        primary_magnet = put_wall
        magnet_confidence = 0.7
    else:
        primary_magnet = flip
        magnet_confidence = 0.5

    return {
        "instrument": "NQ",
        "flip": flip,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "next_call": None,
        "next_put": None,
        "net_gex": net_gex,
        "regime": regime,
        "primary_magnet": primary_magnet,
        "magnet_confidence": magnet_confidence,
        "bias_direction": bias,
        "invalidation_level": invalidation_level,
        "invalidation_reason": invalidation_reason,
        "lean": lean,
        "pin_risk": None,
        "max_pain": None,
        "caveats": [],
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": "massive_gex_bridge",
        "stale_after_seconds": STALE_AFTER_SECONDS,
        "nq_spot": nq_spot,
        "qqq_spot": qqq_spot,
    }


def atomic_write(path: Path, data: dict) -> None:
    """Write JSON atomically via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        suffix=".tmp",
        prefix=".gex_nq_bridge.",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def run_once(input_path: Path, output_path: Path) -> bool:
    """Single transform cycle. Returns True on success."""
    massive_data = _read_massive_map(input_path)
    if massive_data is None:
        return False

    payload = transform(massive_data)
    if payload is None:
        return False

    atomic_write(output_path, payload)
    logger.info(
        "Wrote gex_nq.json: flip=%.0f  CW=%.0f  PW=%.0f  regime=%s  NQ=%.0f",
        payload.get("flip") or 0,
        payload.get("call_wall") or 0,
        payload.get("put_wall") or 0,
        payload.get("regime", "?"),
        payload.get("nq_spot") or 0,
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="massive_gex_map.json → gex_nq.json bridge")
    parser.add_argument("--once", action="store_true", help="Single write and exit")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL, help="Poll interval (sec)")
    parser.add_argument("--input", type=str, default=None, help="Input path override")
    parser.add_argument("--output", type=str, default=None, help="Output path override")
    args = parser.parse_args()

    input_path = Path(args.input) if args.input else _resolve_path(_MASSIVE_JSON_WIN, _MASSIVE_JSON_WSL)
    output_path = Path(args.output) if args.output else _resolve_path(_GEX_NQ_JSON_WIN, _GEX_NQ_JSON_WSL)

    logger.info("Input:  %s", input_path)
    logger.info("Output: %s", output_path)

    if args.once:
        success = run_once(input_path, output_path)
        sys.exit(0 if success else 1)

    logger.info("Starting loop (interval=%ds)", args.interval)
    while True:
        try:
            run_once(input_path, output_path)
        except Exception as exc:
            logger.error("Cycle error: %s", exc)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
