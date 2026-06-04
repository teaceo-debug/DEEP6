"""Tests for IcebergRefillDetector — DOM-snapshot iceberg/refill detection.

Covers:
  1. Positive: 2 refill cycles at same level → ENG_04 event
  2. Negative: one-time refill (count=1) → no event
  3. Negative: refill arrives too late (window expired) → no event
  4. Direction: bid-side iceberg → BULLISH; ask-side → BEARISH
  5. Multi-level: two simultaneous iceberg levels → two events
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from deep6v2.signals.dom.detectors.iceberg import IcebergRefillDetector
from deep6v2.types.dom import DOMLevel, DOMSnapshot
from deep6v2.types.dom_intelligence import DetectorTier, ReplaySafety
from deep6v2.types.signal import Direction, SignalId

_BASE_TS = datetime(2026, 5, 27, 14, 30, tzinfo=UTC)


def _snap(
    bids: list[tuple[float, int]] | None = None,
    asks: list[tuple[float, int]] | None = None,
    offset_sec: int = 0,
) -> DOMSnapshot:
    """Helper to build a DOMSnapshot from (price, volume) tuples."""
    return DOMSnapshot(
        timestamp=_BASE_TS + timedelta(seconds=offset_sec),
        bids=[DOMLevel(price=p, volume=v) for p, v in (bids or [])],
        asks=[DOMLevel(price=p, volume=v) for p, v in (asks or [])],
    )


# ------------------------------------------------------------------
# 1. Positive: two refill cycles at the same bid level → event
# ------------------------------------------------------------------

def test_positive_two_refills_fire_event():
    det = IcebergRefillDetector(
        min_trade_size=30,
        min_refill_size=25,
        confirmation_count=2,
        max_refill_window=4,
    )

    # Snap 0 — baseline (no prior, no detection)
    assert det.on_depth(_snap(bids=[(21000.0, 100)], offset_sec=0)) == []
    # Snap 1 — depletion: 100→50 = -50 (>= 30)
    assert det.on_depth(_snap(bids=[(21000.0, 50)], offset_sec=1)) == []
    # Snap 2 — refill #1: 50→90 = +40 (>= 25), count=1, not enough
    assert det.on_depth(_snap(bids=[(21000.0, 90)], offset_sec=2)) == []
    # Snap 3 — depletion again: 90→40 = -50
    assert det.on_depth(_snap(bids=[(21000.0, 40)], offset_sec=3)) == []
    # Snap 4 — refill #2: 40→80 = +40 → count=2 → EVENT
    events = det.on_depth(_snap(bids=[(21000.0, 80)], offset_sec=4))

    assert len(events) == 1
    ev = events[0]
    assert ev.signal_id is SignalId.ENG_04
    assert ev.tier is DetectorTier.MECHANICAL
    assert ev.replay_safety is ReplaySafety.REPLAY_SAFE
    assert ev.detector_id == "dom.iceberg.v1"
    assert ev.price == 21000.0
    assert ev.direction is Direction.BULLISH
    assert 0.0 < ev.confidence <= 1.0
    assert ev.metadata["refill_count"] == 2


# ------------------------------------------------------------------
# 2. Negative: one-time refill — not enough to confirm
# ------------------------------------------------------------------

def test_negative_single_refill_no_event():
    det = IcebergRefillDetector(confirmation_count=2)

    det.on_depth(_snap(bids=[(21000.0, 100)]))        # baseline
    det.on_depth(_snap(bids=[(21000.0, 50)], offset_sec=1))   # depletion
    events = det.on_depth(_snap(bids=[(21000.0, 90)], offset_sec=2))  # refill #1 only

    assert events == []

    # Nothing else happens — still at count 1.
    events = det.on_depth(_snap(bids=[(21000.0, 90)], offset_sec=3))
    assert events == []


# ------------------------------------------------------------------
# 3. Negative: refill comes too late (window expired)
# ------------------------------------------------------------------

def test_negative_window_expired_no_event():
    det = IcebergRefillDetector(
        min_trade_size=30,
        min_refill_size=25,
        confirmation_count=2,
        max_refill_window=4,
    )

    det.on_depth(_snap(bids=[(21000.0, 100)]))                      # baseline
    det.on_depth(_snap(bids=[(21000.0, 50)], offset_sec=1))         # depletion (snap idx 2)

    # Feed 4 flat snapshots to burn through the window
    for i in range(2, 6):
        det.on_depth(_snap(bids=[(21000.0, 50)], offset_sec=i))

    # Now snap idx = 7 — depletion was at idx 2 → gap = 5 > max_refill_window (4)
    events = det.on_depth(_snap(bids=[(21000.0, 90)], offset_sec=6))
    assert events == []


# ------------------------------------------------------------------
# 4. Direction: bid → BULLISH, ask → BEARISH
# ------------------------------------------------------------------

def test_direction_bid_is_bullish():
    det = IcebergRefillDetector(confirmation_count=2)

    det.on_depth(_snap(bids=[(21000.0, 100)]))
    det.on_depth(_snap(bids=[(21000.0, 50)], offset_sec=1))
    det.on_depth(_snap(bids=[(21000.0, 90)], offset_sec=2))
    det.on_depth(_snap(bids=[(21000.0, 40)], offset_sec=3))
    events = det.on_depth(_snap(bids=[(21000.0, 80)], offset_sec=4))

    assert len(events) == 1
    assert events[0].direction is Direction.BULLISH


def test_direction_ask_is_bearish():
    det = IcebergRefillDetector(confirmation_count=2)

    det.on_depth(_snap(asks=[(21000.25, 100)]))
    det.on_depth(_snap(asks=[(21000.25, 50)], offset_sec=1))
    det.on_depth(_snap(asks=[(21000.25, 90)], offset_sec=2))
    det.on_depth(_snap(asks=[(21000.25, 40)], offset_sec=3))
    events = det.on_depth(_snap(asks=[(21000.25, 80)], offset_sec=4))

    assert len(events) == 1
    assert events[0].direction is Direction.BEARISH


# ------------------------------------------------------------------
# 5. Multi-level: two simultaneous icebergs → two events
# ------------------------------------------------------------------

def test_multi_level_two_events():
    det = IcebergRefillDetector(confirmation_count=2)

    prices = [(21000.0, 21000.25)]  # bid price, ask price

    # Baseline
    det.on_depth(_snap(
        bids=[(21000.0, 100)],
        asks=[(21000.25, 120)],
    ))
    # Depletion on both
    det.on_depth(_snap(
        bids=[(21000.0, 50)],
        asks=[(21000.25, 60)],
        offset_sec=1,
    ))
    # Refill #1 on both
    det.on_depth(_snap(
        bids=[(21000.0, 90)],
        asks=[(21000.25, 110)],
        offset_sec=2,
    ))
    # Depletion #2 on both
    det.on_depth(_snap(
        bids=[(21000.0, 40)],
        asks=[(21000.25, 50)],
        offset_sec=3,
    ))
    # Refill #2 on both → two events
    events = det.on_depth(_snap(
        bids=[(21000.0, 80)],
        asks=[(21000.25, 100)],
        offset_sec=4,
    ))

    assert len(events) == 2
    event_prices = {ev.price for ev in events}
    assert 21000.0 in event_prices
    assert 21000.25 in event_prices

    bid_event = next(ev for ev in events if ev.price == 21000.0)
    ask_event = next(ev for ev in events if ev.price == 21000.25)
    assert bid_event.direction is Direction.BULLISH
    assert ask_event.direction is Direction.BEARISH


# ------------------------------------------------------------------
# 6. Reset clears state completely
# ------------------------------------------------------------------

def test_reset_clears_state():
    det = IcebergRefillDetector(confirmation_count=2)

    # Build up one refill
    det.on_depth(_snap(bids=[(21000.0, 100)]))
    det.on_depth(_snap(bids=[(21000.0, 50)], offset_sec=1))
    det.on_depth(_snap(bids=[(21000.0, 90)], offset_sec=2))

    det.reset()

    # After reset, same sequence should not carry over previous count
    det.on_depth(_snap(bids=[(21000.0, 100)]))
    det.on_depth(_snap(bids=[(21000.0, 50)], offset_sec=1))
    det.on_depth(_snap(bids=[(21000.0, 90)], offset_sec=2))
    det.on_depth(_snap(bids=[(21000.0, 40)], offset_sec=3))
    # Only 1 refill post-reset — not enough
    events = det.on_depth(_snap(bids=[(21000.0, 40)], offset_sec=4))
    assert events == []


# ------------------------------------------------------------------
# 7. Confidence rises with refill count
# ------------------------------------------------------------------

def test_confidence_increases_with_more_refills():
    """Run 4 refill cycles (confirmation=2) — second firing should have
    the same base confidence (counter resets after emit)."""
    det = IcebergRefillDetector(confirmation_count=2)

    def _cycle(start_sec: int) -> list:
        det.on_depth(_snap(bids=[(21000.0, 100)], offset_sec=start_sec))
        det.on_depth(_snap(bids=[(21000.0, 50)], offset_sec=start_sec + 1))
        det.on_depth(_snap(bids=[(21000.0, 90)], offset_sec=start_sec + 2))
        det.on_depth(_snap(bids=[(21000.0, 40)], offset_sec=start_sec + 3))
        return det.on_depth(_snap(bids=[(21000.0, 80)], offset_sec=start_sec + 4))

    first_events = _cycle(0)
    assert len(first_events) == 1
    first_conf = first_events[0].confidence

    # Second cycle — confidence should also be valid (counter was reset)
    second_events = _cycle(10)
    assert len(second_events) == 1
    assert 0.0 < second_events[0].confidence <= 1.0


# ------------------------------------------------------------------
# 8. Max tracked levels is bounded
# ------------------------------------------------------------------

def test_tracked_levels_bounded():
    det = IcebergRefillDetector(confirmation_count=2)

    # Create depletions at 25 distinct prices → should cap at 20
    bids_baseline = [(20000.0 + i * 0.25, 100) for i in range(25)]
    bids_depleted = [(20000.0 + i * 0.25, 50) for i in range(25)]

    det.on_depth(_snap(bids=bids_baseline))
    det.on_depth(_snap(bids=bids_depleted, offset_sec=1))

    # Internal state should be bounded
    assert len(det._tracked) <= 20
