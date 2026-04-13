#!/usr/bin/env python3
"""Event loop lag measurement during DOM callback load.

Measures asyncio event loop lag using a scheduling probe:
  - Schedule a callback 10ms in the future via asyncio.sleep(0.010)
  - Measure actual elapsed time when it fires
  - Lag = actual_elapsed - 10ms

Reports max lag, P99 lag, P95 lag, and P50 lag over a configurable measurement window.
Target: max lag < 1ms under 1,000+ DOM callbacks/sec (DATA-06).

Usage:
    python scripts/measure_loop_lag.py --duration 60
    python -m scripts.measure_loop_lag --duration 30

Per DATA-06: event loop must handle 1,000+ DOM callbacks/sec with max lag < 1ms.
Per T-04-04: LAG_SAMPLES is a module-level list; single event loop; no concurrent writers.
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

# Add project root to path for script execution
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
import uvloop
from deep6.config import Config
from deep6.data.bar_builder import BarBuilder
from deep6.data.rithmic import connect_rithmic, register_callbacks
from deep6.state.shared import SharedState
from async_rithmic import DataType

log = structlog.get_logger()

# Per T-04-04: module-level; single event loop thread; no concurrent mutation possible
LAG_SAMPLES: list[float] = []


async def probe_loop_lag(probe_interval: float = 0.010, duration: int = 60) -> None:
    """Continuously probe event loop lag by scheduling sleep callbacks.

    For each probe cycle:
      1. Record time before sleep
      2. Await asyncio.sleep(probe_interval)
      3. Compute lag = (actual_elapsed - probe_interval) * 1000 ms
      4. Append to LAG_SAMPLES

    Higher lag indicates the event loop was blocked by other callbacks.
    """
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        scheduled_at = time.monotonic()
        await asyncio.sleep(probe_interval)
        actual_elapsed = time.monotonic() - scheduled_at
        lag_ms = (actual_elapsed - probe_interval) * 1000.0
        LAG_SAMPLES.append(lag_ms)


def report_lag(samples: list[float]) -> None:
    """Print lag statistics to stdout with PASS/WARN verdict."""
    if not samples:
        print("No lag samples collected.")
        return

    samples_sorted = sorted(samples)
    n = len(samples_sorted)
    p50  = samples_sorted[int(n * 0.50)]
    p95  = samples_sorted[int(n * 0.95)]
    p99  = samples_sorted[int(n * 0.99)]
    max_lag = samples_sorted[-1]
    mean_lag = sum(samples_sorted) / n

    print()
    print("=== Event Loop Lag Report (DATA-06) ===")
    print(f"Samples:   {n}")
    print(f"P50 lag:   {p50:.3f} ms")
    print(f"P95 lag:   {p95:.3f} ms")
    print(f"P99 lag:   {p99:.3f} ms")
    print(f"Max lag:   {max_lag:.3f} ms")
    print(f"Mean lag:  {mean_lag:.3f} ms")
    print()

    if max_lag < 1.0:
        print("PASS: Max lag < 1ms — event loop meets DATA-06 target.")
    elif max_lag < 5.0:
        print(f"WARN: Max lag {max_lag:.2f}ms is between 1ms-5ms. Acceptable but investigate "
              f"if signal latency becomes a concern.")
    else:
        print(f"FAIL: Max lag {max_lag:.2f}ms exceeds 5ms threshold. "
              f"Investigate blocking callbacks in DOM feed or bar builder.")


async def run_measurement(config: Config, duration: int) -> None:
    """Connect to Rithmic, measure loop lag under live DOM load.

    Runs the full pipeline (DOM feed, tick feed, bar builders) plus the lag probe
    coroutine simultaneously. The probe competes with real callbacks for event loop
    time — giving a realistic measurement of lag under production load.
    """
    state = SharedState.build(config)
    await state.persistence.initialize()

    bb_1m = BarBuilder(period_seconds=60, label="1m", state=state)
    bb_5m = BarBuilder(period_seconds=300, label="5m", state=state)
    state.bar_builders = [bb_1m, bb_5m]

    client = await connect_rithmic(config)
    register_callbacks(client, state)
    await client.subscribe_to_market_data(
        config.instrument, config.exchange, DataType.ORDER_BOOK
    )
    await client.subscribe_to_market_data(
        config.instrument, config.exchange, DataType.LAST_TRADE
    )

    log.info("measure_loop_lag.started", duration_secs=duration)

    session_mgr = state.session_manager()
    probe_task = asyncio.create_task(
        probe_loop_lag(probe_interval=0.010, duration=duration),
        name="loop_lag_probe",
    )
    pipeline_tasks = [
        asyncio.create_task(bb_1m.run(),        name="bar_builder_1m"),
        asyncio.create_task(bb_5m.run(),        name="bar_builder_5m"),
        asyncio.create_task(session_mgr.run(),  name="session_manager"),
    ]

    # Wait for probe to finish (duration seconds), then cancel pipeline
    try:
        await probe_task
    finally:
        for task in pipeline_tasks:
            task.cancel()

    report_lag(LAG_SAMPLES)


def main() -> None:
    """CLI entry point."""
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )
    parser = argparse.ArgumentParser(
        description="Measure asyncio event loop lag under live DOM callback load"
    )
    parser.add_argument(
        "--duration", type=int, default=60,
        help="Measurement window in seconds (default: 60)"
    )
    args = parser.parse_args()

    config = Config.from_env()
    with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
        runner.run(run_measurement(config, args.duration))


if __name__ == "__main__":
    main()
