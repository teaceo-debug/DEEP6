"""Generate synthetic golden sessions for the parity harness (Task 21).

Run once to create/regenerate all 3 fixture files:
    python -m tests_v2.dom_intelligence.fixtures.generate_golden_sessions

Uses GoldenSessionRecorder + GoldenSessionSerializer — never hand-crafted JSON.
"""

from __future__ import annotations

import random
from pathlib import Path

from deep6v2.signals.dom.golden_session import (
    GoldenSessionRecorder,
    GoldenSessionSerializer,
)
from deep6v2.types.dom import DOMUpdate
from deep6v2.types.dom_intelligence import (
    DOMIntelligenceEvent,
    DOMIntelligenceFeatureRow,
    DOMIntelligenceOutput,
    DetectorTier,
    ReplaySafety,
)
from deep6v2.types.execution import OrderSide
from deep6v2.types.signal import Direction, SignalId
import numpy as np

FIXTURES_DIR = Path(__file__).parent
BASE_TS_NS = 1_700_000_000_000_000_000  # synthetic epoch anchor


def _make_clock(start_ns: int = BASE_TS_NS, step_ns: int = 1_000_000):
    """Monotonic synthetic clock yielding incrementing nanosecond timestamps."""
    current = start_ns

    def tick() -> int:
        nonlocal current
        current += step_ns
        return current

    return tick


def _dom_update(side: OrderSide, price: float, volume: int, level: int = 0) -> DOMUpdate:
    return DOMUpdate(side=side, level=level, price=price, volume=volume)


# ---------------------------------------------------------------------------
# Session 1: Quiet RTH — stable prices, low activity
# ---------------------------------------------------------------------------
def generate_quiet_rth() -> None:
    rng = random.Random(42)
    clock = _make_clock()
    recorder = GoldenSessionRecorder(
        clock=clock,
        metadata={"scenario": "quiet_rth", "synthetic": True, "duration_events": 50},
    )

    base_price = 20000.0
    for i in range(55):
        side = OrderSide.BUY if i % 2 == 0 else OrderSide.SELL
        offset = rng.choice([0.0, 0.25, 0.50, 0.75, 1.0])
        price = base_price + offset if side == OrderSide.SELL else base_price - offset
        volume = rng.randint(50, 200)
        level = rng.randint(0, 5)
        recorder.record_update(_dom_update(side, price, volume, level))

    # 2 quiet intelligence outputs — no events
    for bar_idx in range(2):
        output = DOMIntelligenceOutput(
            events=[],
            feature_row=DOMIntelligenceFeatureRow(
                timestamp_ns=clock(),
                feature_names=["spread", "depth_imbalance"],
                feature_values=np.array([0.25, 1.02]),
                bar_index=bar_idx,
                session_id="golden_quiet_rth",
                source_detector_ids=[],
            ),
            evaluated_at_ns=clock(),
            bar_index=bar_idx,
            dom_state_version=bar_idx + 1,
        )
        recorder.record_output(output)

    record = recorder.finalize("golden_quiet_rth", instrument="NQ")
    GoldenSessionSerializer.to_file(record, str(FIXTURES_DIR / "golden_quiet_rth.json"))
    print(f"[OK] golden_quiet_rth.json — {len(record.dom_updates)} updates, {len(record.intelligence_outputs)} outputs")


# ---------------------------------------------------------------------------
# Session 2: Volatile — price movement, detector events firing
# ---------------------------------------------------------------------------
def generate_volatile() -> None:
    rng = random.Random(123)
    clock = _make_clock()
    recorder = GoldenSessionRecorder(
        clock=clock,
        metadata={"scenario": "volatile_session", "synthetic": True, "duration_events": 80},
    )

    price = 20000.0
    for i in range(85):
        side = OrderSide.BUY if rng.random() < 0.5 else OrderSide.SELL
        # Simulate directional movement + noise
        drift = rng.choice([-0.50, -0.25, 0.0, 0.25, 0.50, 0.75, 1.0])
        price = max(20000.0, min(20050.0, price + drift))
        # Mix of thin and thick levels — some 500+ contract walls
        volume = rng.choice([30, 80, 120, 250, 350, 520, 600]) if rng.random() < 0.3 else rng.randint(50, 200)
        level = rng.randint(0, 10)
        recorder.record_update(_dom_update(side, round(price * 4) / 4, volume, level))

    signal_pool = [SignalId.ABS_01, SignalId.EXH_01, SignalId.IMB_01, SignalId.DELT_01, SignalId.TRAP_01]
    detector_pool = ["absorption_detector", "exhaustion_detector", "imbalance_scanner", "delta_divergence", "trap_detector"]

    for bar_idx in range(5):
        n_events = rng.randint(2, 3)
        events = []
        for _ in range(n_events):
            sig_idx = rng.randint(0, len(signal_pool) - 1)
            events.append(
                DOMIntelligenceEvent(
                    signal_id=signal_pool[sig_idx],
                    tier=DetectorTier.MECHANICAL,
                    replay_safety=ReplaySafety.REPLAY_SAFE,
                    direction=rng.choice([Direction.BULLISH, Direction.BEARISH]),
                    confidence=round(rng.uniform(0.55, 0.95), 3),
                    price=round(20000.0 + rng.uniform(0, 50), 2),
                    timestamp_ns=clock(),
                    detector_id=detector_pool[sig_idx],
                    metadata={"synthetic": True},
                )
            )

        output = DOMIntelligenceOutput(
            events=events,
            feature_row=DOMIntelligenceFeatureRow(
                timestamp_ns=clock(),
                feature_names=["spread", "depth_imbalance", "delta_ratio"],
                feature_values=np.array([rng.uniform(0.25, 2.0), rng.uniform(0.5, 2.0), rng.uniform(-1.0, 1.0)]),
                bar_index=bar_idx,
                session_id="golden_volatile",
                source_detector_ids=[e.detector_id for e in events],
            ),
            evaluated_at_ns=clock(),
            bar_index=bar_idx,
            dom_state_version=bar_idx + 1,
        )
        recorder.record_output(output)

    record = recorder.finalize("golden_volatile", instrument="NQ")
    GoldenSessionSerializer.to_file(record, str(FIXTURES_DIR / "golden_volatile.json"))
    print(f"[OK] golden_volatile.json — {len(record.dom_updates)} updates, {len(record.intelligence_outputs)} outputs")


# ---------------------------------------------------------------------------
# Session 3: Disconnect/Reconnect lifecycle
# ---------------------------------------------------------------------------
def generate_disconnect() -> None:
    rng = random.Random(999)
    clock = _make_clock()
    recorder = GoldenSessionRecorder(
        clock=clock,
        metadata={"scenario": "disconnect_reconnect", "synthetic": True, "has_lifecycle_event": True},
    )

    base_price = 20005.0

    # Phase 1: 40 updates before disconnect
    for i in range(40):
        side = OrderSide.BUY if i % 2 == 0 else OrderSide.SELL
        offset = rng.choice([0.0, 0.25, 0.50, 0.75])
        price = base_price + offset if side == OrderSide.SELL else base_price - offset
        volume = rng.randint(60, 250)
        level = rng.randint(0, 8)
        recorder.record_update(_dom_update(side, price, volume, level))

    # Pre-disconnect intelligence output (with event)
    pre_event = DOMIntelligenceEvent(
        signal_id=SignalId.ABS_02,
        tier=DetectorTier.MECHANICAL,
        replay_safety=ReplaySafety.REPLAY_SAFE,
        direction=Direction.BULLISH,
        confidence=0.72,
        price=20005.25,
        timestamp_ns=clock(),
        detector_id="absorption_detector",
        metadata={"phase": "pre_disconnect"},
    )
    pre_output = DOMIntelligenceOutput(
        events=[pre_event],
        feature_row=DOMIntelligenceFeatureRow(
            timestamp_ns=clock(),
            feature_names=["spread", "depth_imbalance"],
            feature_values=np.array([0.50, 1.15]),
            bar_index=0,
            session_id="golden_disconnect",
            source_detector_ids=["absorption_detector"],
        ),
        evaluated_at_ns=clock(),
        bar_index=0,
        dom_state_version=1,
    )
    recorder.record_output(pre_output)

    # Phase 2: 30 updates after reconnect (gap in timestamps implied)
    # Advance clock to simulate reconnect gap
    gap_clock = _make_clock(start_ns=clock() + 5_000_000_000, step_ns=1_000_000)
    recorder._clock = gap_clock

    for i in range(35):
        side = OrderSide.BUY if rng.random() < 0.5 else OrderSide.SELL
        offset = rng.choice([0.0, 0.25, 0.50, 1.0, 1.25])
        price = base_price + 2.0 + offset if side == OrderSide.SELL else base_price + 2.0 - offset
        volume = rng.randint(50, 300)
        level = rng.randint(0, 8)
        recorder.record_update(_dom_update(side, price, volume, level))

    # Post-reconnect intelligence output
    post_event = DOMIntelligenceEvent(
        signal_id=SignalId.EXH_02,
        tier=DetectorTier.MECHANICAL,
        replay_safety=ReplaySafety.REPLAY_SAFE,
        direction=Direction.BEARISH,
        confidence=0.68,
        price=20007.50,
        timestamp_ns=gap_clock(),
        detector_id="exhaustion_detector",
        metadata={"phase": "post_reconnect"},
    )
    post_output = DOMIntelligenceOutput(
        events=[post_event],
        feature_row=DOMIntelligenceFeatureRow(
            timestamp_ns=gap_clock(),
            feature_names=["spread", "depth_imbalance"],
            feature_values=np.array([0.75, 0.88]),
            bar_index=1,
            session_id="golden_disconnect",
            source_detector_ids=["exhaustion_detector"],
        ),
        evaluated_at_ns=gap_clock(),
        bar_index=1,
        dom_state_version=2,
    )
    recorder.record_output(post_output)

    record = recorder.finalize("golden_disconnect", instrument="NQ")
    GoldenSessionSerializer.to_file(record, str(FIXTURES_DIR / "golden_disconnect.json"))
    print(f"[OK] golden_disconnect.json — {len(record.dom_updates)} updates, {len(record.intelligence_outputs)} outputs")


def main() -> None:
    print("Generating golden session fixtures...")
    generate_quiet_rth()
    generate_volatile()
    generate_disconnect()
    print("Done. All fixtures written to", FIXTURES_DIR)


if __name__ == "__main__":
    main()
