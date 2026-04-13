"""Kronos inference latency benchmark — MPS vs CPU on M2 Mac.

Measures per-request latency for KronosSubprocessBridge using fallback
momentum bias (when Kronos model is not installed) or real inference
(when Kronos is installed and the model is cached from HuggingFace).

Usage:
    python scripts/benchmark_kronos.py

Output:
    Latency table and device recommendation printed to stdout.
    Exits 0 always — benchmark result is informational, not pass/fail.

If Kronos model is not installed, fallback latency is benchmarked and
a NOTE is printed explaining how to install the real model.
"""
from __future__ import annotations

import random
import sys
import time
from typing import Optional

# Ensure deep6 package is importable when run from repo root
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from deep6.engines.signal_config import KronosConfig
from deep6.engines.kronos_worker import KronosWorkerProcess


# ──────────────────────────────────────────────────────────────────────────────
# Synthetic NQ-like OHLCV data generation
# ──────────────────────────────────────────────────────────────────────────────

def _generate_synthetic_bars(n: int = 100, seed: int = 42) -> list[dict]:
    """Generate n synthetic NQ-like OHLCV bars via random walk.

    Produces realistic NQ bar characteristics:
    - Price ~17000, random walk ±15 pts/bar
    - Bar range 10-30 pts
    - Volume 500-5000 contracts
    """
    random.seed(seed)
    bars = []
    price = 17000.0

    for _ in range(n):
        # Random walk step
        price += random.uniform(-15.0, 15.0)

        bar_range = random.uniform(10.0, 30.0)
        open_ = price + random.uniform(-bar_range / 2, bar_range / 2)
        high = open_ + random.uniform(0, bar_range)
        low = open_ - random.uniform(0, bar_range)
        close = random.uniform(low, high)
        volume = random.uniform(500.0, 5000.0)

        bars.append({
            "open": round(open_, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close, 2),
            "volume": round(volume, 0),
        })

    return bars


# ──────────────────────────────────────────────────────────────────────────────
# Benchmark runner
# ──────────────────────────────────────────────────────────────────────────────

def _benchmark_device(
    device: str,
    bars: list[dict],
    num_samples: int = 5,
    n_runs: int = 4,
) -> dict:
    """Benchmark one device configuration.

    Args:
        device:      "cpu" or "mps"
        bars:        100 synthetic OHLCV bars
        num_samples: Kronos stochastic samples per inference
        n_runs:      Number of timing runs to average

    Returns:
        dict with keys: device, avg_ms, min_ms, max_ms, used_fallback
    """
    cfg = KronosConfig(device=device, num_samples=num_samples)
    worker = KronosWorkerProcess(cfg)

    try:
        worker.start()

        # Health check
        healthy = worker.ping()
        if not healthy:
            return {
                "device": device,
                "avg_ms": float("nan"),
                "min_ms": float("nan"),
                "max_ms": float("nan"),
                "used_fallback": True,
                "error": "subprocess did not respond to ping",
            }

        latencies = []
        used_fallback = False

        for i in range(n_runs):
            t0 = time.perf_counter()
            result = worker.request_inference(bars, num_samples=num_samples)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed_ms)

            # Detect fallback path (samples==0 means no real Kronos inference)
            if hasattr(result, "samples") and result.samples == 0:
                used_fallback = True

        return {
            "device": device,
            "avg_ms": sum(latencies) / len(latencies),
            "min_ms": min(latencies),
            "max_ms": max(latencies),
            "used_fallback": used_fallback,
        }

    finally:
        worker.stop()


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Run the benchmark and print results + recommendation."""
    print("=== Kronos Inference Latency Benchmark ===")
    print(f"Bars: 100 synthetic NQ bars | Samples per call: 5 | Runs: 4\n")

    bars = _generate_synthetic_bars(n=100)
    NUM_SAMPLES = 5

    results: list[dict] = []

    # Run A: CPU
    print("Benchmarking device=cpu ...", end=" ", flush=True)
    cpu_result = _benchmark_device("cpu", bars, num_samples=NUM_SAMPLES)
    results.append(cpu_result)
    print("done")

    # Run B: MPS (Apple Silicon) — may silently fall back to CPU inside subprocess
    print("Benchmarking device=mps  ...", end=" ", flush=True)
    mps_result = _benchmark_device("mps", bars, num_samples=NUM_SAMPLES)
    results.append(mps_result)
    print("done")

    print()

    # ── Results table ──────────────────────────────────────────────────────────
    budget_ms = 400.0  # 5-bar cadence in a 1-min chart = 5×60s; single inference budget

    def _fmt_ms(v: float) -> str:
        return f"{v:.0f}ms" if v == v else "N/A"  # nan check

    print(f"{'Device':<8} | {'Samples':<7} | {'Avg Latency':<12} | {'Min':<8} | {'Max':<8} | Recommendation")
    print("-" * 72)

    recommendations = {}
    for r in results:
        avg = r["avg_ms"]
        rec = "PREFERRED" if avg <= budget_ms else "FALLBACK"
        recommendations[r["device"]] = (avg, rec)
        print(
            f"{r['device']:<8} | {NUM_SAMPLES:<7} | {_fmt_ms(avg):<12} | "
            f"{_fmt_ms(r['min_ms']):<8} | {_fmt_ms(r['max_ms']):<8} | {rec}"
        )

    print()

    # ── Recommendation ────────────────────────────────────────────────────────
    mps_avg = recommendations["mps"][0]
    cpu_avg = recommendations["cpu"][0]

    if mps_avg == mps_avg and mps_avg <= budget_ms:
        print(f"RECOMMENDATION: Use device=mps — latency within budget ({mps_avg:.0f}ms <= {budget_ms:.0f}ms)")
    elif cpu_avg == cpu_avg and cpu_avg <= budget_ms:
        print(f"RECOMMENDATION: Use device=cpu — mps unavailable or too slow ({cpu_avg:.0f}ms <= {budget_ms:.0f}ms)")
    else:
        print(
            f"WARNING: Both devices exceed latency budget ({budget_ms:.0f}ms). "
            "Consider num_samples=10."
        )

    # ── Fallback notice ───────────────────────────────────────────────────────
    any_fallback = any(r.get("used_fallback") for r in results)
    if any_fallback:
        print()
        print(
            "NOTE: Kronos model not installed — fallback momentum bias was benchmarked.\n"
            "Install Kronos from https://github.com/shiyu-coder/Kronos to benchmark real inference."
        )


if __name__ == "__main__":
    main()
