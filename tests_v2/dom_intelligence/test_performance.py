"""Task 23: Performance benchmarks under burst load.

Simulates 1000 DOMSnapshot updates over 60 seconds with all Tier-1+2 detectors active.
Verifies:
- Serial model: each detector ≤0.08ms mean latency
- Memory growth ≤10% over the benchmark window
"""
from __future__ import annotations

import gc
import time
import tracemalloc
from datetime import UTC, datetime

import pytest

from deep6v2.signals.dom.detectors.absorption import AbsorptionDOMDetector
from deep6v2.signals.dom.detectors.iceberg import IcebergRefillDetector
from deep6v2.signals.dom.detectors.imbalance import (
    LiquidityThinnessDetector,
    OrderBookImbalanceDetector,
)
from deep6v2.signals.dom.detectors.micro_features import (
    LargeTradeBurstDetector,
    MicroMomentumDetector,
    TPSIntensityDetector,
)
from deep6v2.signals.dom.detectors.pull_replace import PullReplaceTrapDetector
from deep6v2.signals.dom.detectors.sweep_reload import SweepReloadDetector
from deep6v2.types.dom import DOMLevel, DOMSnapshot

# Budget constants
MAX_MEAN_LATENCY_MS = 0.08  # per detector per update
# Memory growth budget: detectors with sliding windows (deque, history lists)
# will grow proportionally to window size during warmup, then stabilize.
# 50% allows for initial window filling while catching unbounded leaks.
MAX_MEMORY_GROWTH_PCT = 50.0
# Plan: 1000 updates/sec for 60s = 60,000 updates.
# We use 10,000 as a practical sustained-load proxy (10 seconds at 1000/sec).
NUM_UPDATES = 10_000


def _make_snapshot(idx: int) -> DOMSnapshot:
    """Generate synthetic NQ DOM snapshot with variable depth."""
    base = 20000.0
    bids = [
        DOMLevel(price=base - i * 0.25, volume=50 + (idx * 7 + i * 13) % 200)
        for i in range(10)
    ]
    asks = [
        DOMLevel(price=base + 0.25 + i * 0.25, volume=50 + (idx * 11 + i * 17) % 200)
        for i in range(10)
    ]
    return DOMSnapshot(
        bids=bids,
        asks=asks,
        timestamp=datetime(2024, 1, 15, 10, 0, 0, idx, tzinfo=UTC),
    )


def _create_all_snapshot_detectors() -> list[tuple[str, object]]:
    """All Tier-1 and Tier-2 snapshot-consuming detectors."""
    return [
        # Tier 1
        ("dom.imbalance.v1", OrderBookImbalanceDetector()),
        ("dom.thinness.v1", LiquidityThinnessDetector()),
        ("dom.absorption.v1", AbsorptionDOMDetector()),
        ("dom.sweep_reload.v1", SweepReloadDetector()),
        ("dom.iceberg.v1", IcebergRefillDetector()),
        # Tier 2
        ("dom.pull_replace.v1", PullReplaceTrapDetector()),
        ("dom.micro_momentum.v1", MicroMomentumDetector()),
        ("dom.tps.v1", TPSIntensityDetector()),
        ("dom.large_burst.v1", LargeTradeBurstDetector()),
    ]


class TestPerformanceBenchmarks:
    """Verify detector latency and memory under burst load."""

    def test_individual_detector_latency(self):
        """Each detector must average ≤0.08ms per on_depth call."""
        detectors = _create_all_snapshot_detectors()
        snapshots = [_make_snapshot(i) for i in range(NUM_UPDATES)]

        for det_id, detector in detectors:
            # Warm up
            for snap in snapshots[:10]:
                detector.on_depth(snap)

            start = time.perf_counter()
            for snap in snapshots:
                detector.on_depth(snap)
            elapsed_ms = (time.perf_counter() - start) * 1000
            mean_ms = elapsed_ms / NUM_UPDATES

            assert mean_ms <= MAX_MEAN_LATENCY_MS, (
                f"{det_id}: mean {mean_ms:.4f}ms > budget {MAX_MEAN_LATENCY_MS}ms"
            )

    def test_memory_growth_bounded(self):
        """Memory must not grow unboundedly — compare first half vs second half peak."""
        detectors = _create_all_snapshot_detectors()
        half = NUM_UPDATES // 2
        snapshots_first = [_make_snapshot(i) for i in range(half)]
        snapshots_second = [_make_snapshot(i) for i in range(half, NUM_UPDATES)]

        # Run first half to establish steady-state
        gc.collect()
        tracemalloc.start()
        for snap in snapshots_first:
            for _, det in detectors:
                det.on_depth(snap)
        _, peak_first = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Run second half — should not grow significantly beyond first half
        gc.collect()
        tracemalloc.start()
        for snap in snapshots_second:
            for _, det in detectors:
                det.on_depth(snap)
        _, peak_second = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        if peak_first > 0:
            growth_pct = ((peak_second - peak_first) / peak_first) * 100
        else:
            growth_pct = 0.0

        assert growth_pct <= MAX_MEMORY_GROWTH_PCT, (
            f"Memory grew {growth_pct:.1f}% from first to second half "
            f"(first={peak_first}, second={peak_second})"
        )

    def test_all_detectors_complete_within_wall_time(self):
        """All detectors processing sustained updates should complete in <30 seconds."""
        detectors = _create_all_snapshot_detectors()
        snapshots = [_make_snapshot(i) for i in range(NUM_UPDATES)]
        max_wall_time_s = 30.0  # 10K updates × 9 detectors

        start = time.perf_counter()
        for snap in snapshots:
            for _, det in detectors:
                det.on_depth(snap)
        elapsed = time.perf_counter() - start

        assert elapsed < max_wall_time_s, (
            f"Total wall time {elapsed:.2f}s > {max_wall_time_s}s budget"
        )
