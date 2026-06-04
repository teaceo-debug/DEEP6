"""Bias Bridge — polls NQ Atlas and writes bias_v3.json for NinjaTrader.

Reads GEX data from NQ Atlas (http://localhost:8766/gex) every 10 seconds,
feeds it into MarketBiasEngine, and writes the resulting snapshot to
bias_v3.json in the NT8 templates folder.

Usage:
    python scripts/bias_bridge.py              # Start bridge
    python scripts/bias_bridge.py --dry-run    # Single fetch + print, then exit
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import time
from pathlib import Path

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deep6.engines.bias_json_writer import BiasJsonWriter
from deep6.engines.gex_options_domain import GEXSnapshot
from deep6.engines.market_bias_engine import MarketBiasEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bias_bridge")

ATLAS_URL = "http://localhost:8766"
POLL_INTERVAL = 10  # seconds

# NT8 bias_v3.json output path — works on both Windows and WSL
_NT8_BIAS_PATH_WIN = r"C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\bias_v3.json"
_NT8_BIAS_PATH_WSL = "/mnt/c/Users/Tea/Documents/NinjaTrader 8/templates/DEEP6/bias_v3.json"


def _default_output_path() -> Path:
    """Return the correct bias_v3.json path for the current platform."""
    if sys.platform == "win32":
        return Path(_NT8_BIAS_PATH_WIN)
    # WSL or Linux — use /mnt/c path
    wsl_path = Path(_NT8_BIAS_PATH_WSL)
    if wsl_path.parent.exists():
        return wsl_path
    # Fallback to Windows expandvars
    return Path(os.path.expandvars(_NT8_BIAS_PATH_WIN))


def _safe_float(value, default: float = 0.0) -> float:
    """Convert to float, treating None/missing as default."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _parse_gex_response(data: dict) -> GEXSnapshot:
    """Parse NQ Atlas /gex JSON into a GEXSnapshot."""
    return GEXSnapshot(
        spot=_safe_float(data.get("spot")),
        flip_level=_safe_float(data.get("flip_level")),
        call_wall=_safe_float(data.get("call_wall")),
        put_wall=_safe_float(data.get("put_wall")),
        net_gex=_safe_float(data.get("net_gex")),
        regime_sign=int(data.get("regime_sign") or 0),
        flow_direction=0,
        updated_at=time.time(),
    )


def _parse_bias_flow(bias_data: dict) -> int:
    """Extract flow direction from NQ Atlas /bias endpoint."""
    direction = (bias_data.get("direction") or "NEUTRAL").upper()
    if "BULL" in direction:
        return 1
    if "BEAR" in direction:
        return -1
    return 0


def _fetch_json_sync(url: str) -> dict | None:
    """Fetch JSON from URL using stdlib (no httpx needed)."""
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read())
    except Exception:
        return None


async def fetch_atlas_sync() -> tuple[GEXSnapshot | None, float]:
    """Fetch GEX + bias from NQ Atlas using stdlib urllib (no httpx)."""
    loop = asyncio.get_running_loop()

    try:
        gex_data = await loop.run_in_executor(None, _fetch_json_sync, f"{ATLAS_URL}/gex")
        if not gex_data:
            logger.warning("Atlas /gex returned no data")
            return None, 0.0

        snapshot = _parse_gex_response(gex_data)

        # Flow direction from /bias
        bias_data = await loop.run_in_executor(None, _fetch_json_sync, f"{ATLAS_URL}/bias")
        if bias_data:
            snapshot.flow_direction = _parse_bias_flow(bias_data)

        # NQ price from /state
        nq_price = 0.0
        state_data = await loop.run_in_executor(None, _fetch_json_sync, f"{ATLAS_URL}/state")
        if state_data:
            nq_price = _safe_float(state_data.get("spots", {}).get("NQ"))

        return snapshot, nq_price

    except Exception as e:
        logger.error("Atlas fetch error: %s", e)
        return None, 0.0


async def fetch_atlas(client) -> tuple[GEXSnapshot | None, float]:
    """Fetch GEX + bias from NQ Atlas. Returns (snapshot, nq_price)."""
    if not _HAS_HTTPX:
        return await fetch_atlas_sync()

    try:
        gex_resp = await client.get(f"{ATLAS_URL}/gex", timeout=5.0)
        if gex_resp.status_code != 200:
            logger.warning("Atlas /gex returned %d", gex_resp.status_code)
            return None, 0.0

        gex_data = gex_resp.json()
        snapshot = _parse_gex_response(gex_data)

        # Try to get flow direction from /bias
        try:
            bias_resp = await client.get(f"{ATLAS_URL}/bias", timeout=5.0)
            if bias_resp.status_code == 200:
                bias_data = bias_resp.json()
                snapshot.flow_direction = _parse_bias_flow(bias_data)
        except Exception:
            pass

        # Try to get NQ price from /state
        nq_price = 0.0
        try:
            state_resp = await client.get(f"{ATLAS_URL}/state", timeout=5.0)
            if state_resp.status_code == 200:
                state_data = state_resp.json()
                spots = state_data.get("spots", {})
                nq_price = _safe_float(spots.get("NQ"))
        except Exception:
            pass

        return snapshot, nq_price

    except Exception as e:
        if "ConnectError" in type(e).__name__:
            logger.error("Cannot connect to NQ Atlas at %s — is it running?", ATLAS_URL)
        else:
            logger.error("Atlas fetch error: %s", e)
        return None, 0.0


async def run_bridge(output_path: Path, dry_run: bool = False) -> None:
    """Main bridge loop."""
    engine = MarketBiasEngine()
    writer = BiasJsonWriter()

    logger.info("Bias Bridge starting")
    logger.info("  Atlas: %s", ATLAS_URL)
    logger.info("  Output: %s", output_path)
    logger.info("  Interval: %ds", POLL_INTERVAL)

    client = None
    if _HAS_HTTPX:
        client = httpx.AsyncClient()

    try:
        # Verify Atlas is reachable
        health_data = await asyncio.get_running_loop().run_in_executor(
            None, _fetch_json_sync, f"{ATLAS_URL}/health"
        )
        if health_data:
            logger.info("Atlas health: %s (uptime %ds)", health_data.get("status"), health_data.get("uptime_sec", 0))
        else:
            logger.error("NQ Atlas not reachable at %s — start it first: python run_atlas.py", ATLAS_URL)
            if dry_run:
                return
            logger.info("Will retry every %ds...", POLL_INTERVAL)

        iteration = 0
        while True:
            gex_snapshot, nq_price = await fetch_atlas(client)

            snapshot = engine.compute_bias(
                gex_snapshot=gex_snapshot,
                price=nq_price if nq_price > 0 else None,
            )

            writer.write(snapshot, output_path)
            iteration += 1

            gex_score = snapshot.domain_detail.get("gex", {}).get("score", "?")
            logger.info(
                "[%d] %s score=%d conf=%.0f%% mode=%s gex=%s",
                iteration,
                snapshot.bias_label,
                snapshot.bias_score,
                snapshot.confidence * 100,
                snapshot.mode,
                gex_score,
            )

            if dry_run:
                logger.info("Dry run complete. Snapshot written to %s", output_path)
                return

            await asyncio.sleep(POLL_INTERVAL)
    finally:
        if client is not None:
            await client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bias Bridge — NQ Atlas → bias_v3.json")
    parser.add_argument("--dry-run", action="store_true", help="Single fetch, then exit")
    parser.add_argument("--output", type=str, default=None, help="Output JSON path (default: NT8 templates)")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else _default_output_path()

    if args.dry_run:
        asyncio.run(run_bridge(output_path, dry_run=True))
    else:
        # Ignore SIGHUP so the process survives when the launching terminal exits
        try:
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
        except (AttributeError, OSError):
            pass  # SIGHUP not available on Windows

        try:
            asyncio.run(run_bridge(output_path))
        except KeyboardInterrupt:
            pass
        logger.info("Bias Bridge stopped.")


if __name__ == "__main__":
    main()
