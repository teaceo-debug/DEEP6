from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from deep6v2.types.dom import DOMLevel, DOMSnapshot
from deep6v2.types.dom_intelligence import DetectorTier, ReplaySafety
from deep6v2.types.signal import Direction, SignalId


_MODULE_PATH = Path(__file__).resolve().parents[2] / "deep6v2" / "signals" / "dom" / "detectors" / "micro_features.py"
_SPEC = spec_from_file_location("deep6v2.signals.dom.detectors.micro_features", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

MicroMomentumDetector = _MODULE.MicroMomentumDetector
TPSIntensityDetector = _MODULE.TPSIntensityDetector
LargeTradeBurstDetector = _MODULE.LargeTradeBurstDetector


def _snapshot(*, bids: list[int], asks: list[int], base_price: float = 20000.0) -> DOMSnapshot:
    return DOMSnapshot(
        timestamp=datetime(2026, 5, 27, 14, 30, tzinfo=UTC),
        bids=[DOMLevel(price=base_price - (idx * 0.25), volume=v) for idx, v in enumerate(bids)],
        asks=[DOMLevel(price=base_price + 0.25 + (idx * 0.25), volume=v) for idx, v in enumerate(asks)],
    )


def _snapshot_at_price(base_price: float) -> DOMSnapshot:
    return _snapshot(bids=[100, 100], asks=[100, 100], base_price=base_price)


# ---------------------------------------------------------------------------
# MicroMomentumDetector
# ---------------------------------------------------------------------------

class TestMicroMomentumDetector:
    def test_fires_bullish_on_upward_velocity(self) -> None:
        det = MicroMomentumDetector(window_size=3, momentum_threshold=0.25)
        # Feed 3 snapshots with rising mid-price: 20000.125, 20001.125, 20002.125
        events = []
        for price in [20000.0, 20001.0, 20002.0]:
            events = det.on_depth(_snapshot_at_price(price))

        assert len(events) == 1
        event = events[0]
        assert event.detector_id == "dom.micro_momentum.v1"
        assert event.signal_id is SignalId.REGIME_CHANGE
        assert event.direction is Direction.BULLISH
        assert event.tier is DetectorTier.HEURISTIC
        assert event.replay_safety is ReplaySafety.REPLAY_DEGRADED
        # velocity = (20002.125 - 20000.125) / 3 = 0.6667
        assert event.metadata["velocity"] > 0.25

    def test_fires_bearish_on_downward_velocity(self) -> None:
        det = MicroMomentumDetector(window_size=3, momentum_threshold=0.25)
        for price in [20002.0, 20001.0, 20000.0]:
            events = det.on_depth(_snapshot_at_price(price))

        assert len(events) == 1
        assert events[0].direction is Direction.BEARISH
        assert events[0].metadata["velocity"] < -0.25

    def test_stays_silent_below_threshold(self) -> None:
        det = MicroMomentumDetector(window_size=5, momentum_threshold=1.0)
        for price in [20000.0, 20000.25, 20000.50, 20000.75, 20001.0]:
            events = det.on_depth(_snapshot_at_price(price))

        # velocity = 1.0 / 5 = 0.2 < 1.0 threshold
        assert events == []

    def test_stays_silent_before_window_filled(self) -> None:
        det = MicroMomentumDetector(window_size=5, momentum_threshold=0.01)
        for price in [20000.0, 20005.0, 20010.0]:
            events = det.on_depth(_snapshot_at_price(price))
        # Only 3 snapshots fed, window is 5
        assert events == []

    def test_reset_clears_state(self) -> None:
        det = MicroMomentumDetector(window_size=3, momentum_threshold=0.25)
        for price in [20000.0, 20001.0]:
            det.on_depth(_snapshot_at_price(price))
        det.reset()
        # After reset, window is empty — needs 3 fresh snapshots
        for price in [20000.0, 20000.0, 20000.0]:
            events = det.on_depth(_snapshot_at_price(price))
        assert events == []

    def test_handles_empty_bids_or_asks(self) -> None:
        det = MicroMomentumDetector(window_size=3, momentum_threshold=0.1)
        empty_snap = DOMSnapshot(
            timestamp=datetime(2026, 5, 27, 14, 30, tzinfo=UTC),
            bids=[],
            asks=[DOMLevel(price=20000.25, volume=100)],
        )
        events = det.on_depth(empty_snap)
        assert events == []


# ---------------------------------------------------------------------------
# TPSIntensityDetector
# ---------------------------------------------------------------------------

class TestTPSIntensityDetector:
    def test_fires_when_avg_tps_exceeds_threshold(self) -> None:
        det = TPSIntensityDetector(window_size=3, tps_threshold=5.0)
        snap = _snapshot(bids=[100], asks=[100])

        # 3 snapshots with 10 trades each
        for _ in range(3):
            for _ in range(10):
                det.update_trade(5, is_buy=True)
            events = det.on_depth(snap)

        assert len(events) == 1
        event = events[0]
        assert event.detector_id == "dom.tps.v1"
        assert event.signal_id is SignalId.REGIME_CHANGE
        assert event.tier is DetectorTier.HEURISTIC
        assert event.replay_safety is ReplaySafety.REPLAY_DEGRADED
        assert event.metadata["avg_tps"] == 10.0
        assert event.direction is Direction.BULLISH

    def test_bearish_when_sell_dominates(self) -> None:
        det = TPSIntensityDetector(window_size=2, tps_threshold=3.0)
        snap = _snapshot(bids=[100], asks=[100])

        for _ in range(2):
            for _ in range(5):
                det.update_trade(10, is_buy=False)
            events = det.on_depth(snap)

        assert len(events) == 1
        assert events[0].direction is Direction.BEARISH

    def test_stays_silent_below_tps_threshold(self) -> None:
        det = TPSIntensityDetector(window_size=3, tps_threshold=10.0)
        snap = _snapshot(bids=[100], asks=[100])

        for _ in range(3):
            det.update_trade(5, is_buy=True)
            events = det.on_depth(snap)

        # avg = 1.0 trade/snapshot < 10.0
        assert events == []

    def test_stays_silent_before_window_filled(self) -> None:
        det = TPSIntensityDetector(window_size=5, tps_threshold=1.0)
        snap = _snapshot(bids=[100], asks=[100])

        for _ in range(20):
            det.update_trade(5, is_buy=True)
        events = det.on_depth(snap)
        # Only 1 snapshot, window is 5
        assert events == []

    def test_reset_clears_state(self) -> None:
        det = TPSIntensityDetector(window_size=2, tps_threshold=3.0)
        snap = _snapshot(bids=[100], asks=[100])

        for _ in range(5):
            det.update_trade(5, is_buy=True)
        det.on_depth(snap)
        det.reset()

        # After reset, fresh start — 1 snapshot only, window = 2
        det.update_trade(5, is_buy=True)
        events = det.on_depth(snap)
        assert events == []

    def test_no_trades_no_fire(self) -> None:
        det = TPSIntensityDetector(window_size=2, tps_threshold=0.5)
        snap = _snapshot(bids=[100], asks=[100])

        for _ in range(2):
            events = det.on_depth(snap)

        # avg_tps = 0 / 2 = 0.0 < 0.5
        assert events == []


# ---------------------------------------------------------------------------
# LargeTradeBurstDetector
# ---------------------------------------------------------------------------

class TestLargeTradeBurstDetector:
    def test_fires_on_burst_of_large_trades(self) -> None:
        det = LargeTradeBurstDetector(large_trade_size=10, burst_count=3, burst_window=3)
        snap = _snapshot(bids=[100], asks=[100])

        for _ in range(3):
            det.update_trade(25, is_buy=True)  # large
            det.update_trade(5, is_buy=True)   # small, ignored
            events = det.on_depth(snap)

        assert len(events) == 1
        event = events[0]
        assert event.detector_id == "dom.large_burst.v1"
        assert event.signal_id is SignalId.REGIME_CHANGE
        assert event.tier is DetectorTier.HEURISTIC
        assert event.replay_safety is ReplaySafety.REPLAY_DEGRADED
        assert event.metadata["total_large_trades"] == 3
        assert event.direction is Direction.BULLISH

    def test_bearish_on_sell_heavy_burst(self) -> None:
        det = LargeTradeBurstDetector(large_trade_size=10, burst_count=2, burst_window=2)
        snap = _snapshot(bids=[100], asks=[100])

        for _ in range(2):
            det.update_trade(50, is_buy=False)
            events = det.on_depth(snap)

        assert len(events) == 1
        assert events[0].direction is Direction.BEARISH
        assert events[0].metadata["large_sell_volume"] == 100

    def test_stays_silent_below_burst_count(self) -> None:
        det = LargeTradeBurstDetector(large_trade_size=10, burst_count=5, burst_window=3)
        snap = _snapshot(bids=[100], asks=[100])

        for _ in range(3):
            det.update_trade(15, is_buy=True)  # 1 large per snapshot
            events = det.on_depth(snap)

        # total_large = 3 < burst_count 5
        assert events == []

    def test_small_trades_ignored(self) -> None:
        det = LargeTradeBurstDetector(large_trade_size=50, burst_count=1, burst_window=3)
        snap = _snapshot(bids=[100], asks=[100])

        for _ in range(3):
            det.update_trade(10, is_buy=True)  # all small
            events = det.on_depth(snap)

        assert events == []

    def test_stays_silent_before_window_filled(self) -> None:
        det = LargeTradeBurstDetector(large_trade_size=5, burst_count=1, burst_window=5)
        snap = _snapshot(bids=[100], asks=[100])

        det.update_trade(100, is_buy=True)
        events = det.on_depth(snap)
        # 1 snapshot, window = 5
        assert events == []

    def test_reset_clears_state(self) -> None:
        det = LargeTradeBurstDetector(large_trade_size=10, burst_count=2, burst_window=2)
        snap = _snapshot(bids=[100], asks=[100])

        det.update_trade(50, is_buy=True)
        det.on_depth(snap)
        det.reset()

        # After reset, need 2 fresh snapshots
        det.update_trade(50, is_buy=True)
        events = det.on_depth(snap)
        assert events == []
