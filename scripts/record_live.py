"""Run the live Rithmic feed with the recorder attached.

Pure data-accumulation mode — connects to Rithmic, attaches LiveRecorder,
and runs indefinitely, writing daily JSONL.zst files to data/recordings/.
No signal processing, no bar building, no risk. Just: data in -> disk.

Use this to accumulate training data at $0 (beyond the Rithmic subscription
you already pay for) while Phase 13's full backtest engine is under
construction.

Usage:
    python scripts/record_live.py [--symbol NQ] [--dir data/recordings]

Stop with Ctrl-C — the recorder drains its queue on shutdown.
"""
from __future__ import annotations

import argparse
import asyncio
import signal
from pathlib import Path

import structlog

from deep6.config import Config
from deep6.data.recorder import LiveRecorder, attach_recorder
from deep6.data.rithmic import connect_rithmic

log = structlog.get_logger()


async def run(symbol: str, exchange: str, base_dir: Path) -> None:
    config = Config.from_env()
    client = await connect_rithmic(config)

    recorder = LiveRecorder(base_dir=base_dir)
    await recorder.start()
    attach_recorder(client, recorder)

    await client.subscribe_to_market_data(symbol, exchange)
    log.info("record.subscribed", symbol=symbol, exchange=exchange)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    try:
        # Periodic stats every 60s
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                log.info("record.stats", **recorder.stats)
    finally:
        log.info("record.shutting_down")
        try:
            await client.unsubscribe_from_market_data(symbol, exchange)
        except Exception as exc:
            log.warning("record.unsubscribe_failed", error=str(exc))
        await recorder.stop()
        try:
            await client.disconnect()
        except Exception as exc:
            log.warning("record.disconnect_failed", error=str(exc))


def main() -> None:
    parser = argparse.ArgumentParser(description="Record live Rithmic feed to daily JSONL.zst files")
    parser.add_argument("--symbol", default="NQM6", help="Rithmic symbol (e.g., NQM6 for June '26 NQ)")
    parser.add_argument("--exchange", default="CME", help="Exchange code")
    parser.add_argument("--dir", default="data/recordings", help="Output directory")
    args = parser.parse_args()

    asyncio.run(run(args.symbol, args.exchange, Path(args.dir)))


if __name__ == "__main__":
    main()
