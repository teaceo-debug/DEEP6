from __future__ import annotations

import pytest

from deep6v2.orderflow.vpin import VPINCalculator, VPINResult


class TestBucketAccumulation:
    def test_no_result_before_bucket_full(self) -> None:
        calc = VPINCalculator(bucket_size=500)
        result = calc.add_volume(100, 100)
        assert result is None

    def test_result_when_bucket_completes(self) -> None:
        calc = VPINCalculator(bucket_size=500)
        calc.add_volume(200, 200)
        result = calc.add_volume(50, 50)
        assert result is not None
        assert isinstance(result, VPINResult)

    def test_multiple_adds_before_bucket(self) -> None:
        calc = VPINCalculator(bucket_size=100)
        assert calc.add_volume(30, 20) is None
        assert calc.add_volume(20, 10) is None
        result = calc.add_volume(10, 10)
        assert result is not None


class TestVPINCalculation:
    def test_balanced_volume_low_vpin(self) -> None:
        calc = VPINCalculator(bucket_size=100, window_size=5)
        # Fill balanced buckets
        for _ in range(5):
            result = calc.add_volume(50, 50)
        assert result is not None
        assert result.value == pytest.approx(0.0)
        assert result.multiplier == 1.0

    def test_fully_imbalanced_high_vpin(self) -> None:
        calc = VPINCalculator(bucket_size=100, window_size=5)
        # All buy, no sell
        for _ in range(5):
            result = calc.add_volume(100, 0)
        assert result is not None
        assert result.value == pytest.approx(1.0)
        assert result.multiplier == 1.1

    def test_moderate_imbalance(self) -> None:
        calc = VPINCalculator(bucket_size=100, window_size=2)
        # 80 buy, 20 sell → imbalance 60/100 per bucket
        calc.add_volume(80, 20)
        result = calc.add_volume(80, 20)
        assert result is not None
        assert result.value == pytest.approx(0.6)
        assert result.multiplier == 1.05

    def test_empty_buckets(self) -> None:
        calc = VPINCalculator(bucket_size=100)
        assert calc.current_vpin == 0.0
        assert calc.get_multiplier() == 1.0


class TestMultiplierThresholds:
    def test_high_vpin_multiplier(self) -> None:
        calc = VPINCalculator(bucket_size=100, window_size=1)
        # 90 buy, 10 sell → vpin = 0.8
        result = calc.add_volume(90, 10)
        assert result is not None
        assert result.value == pytest.approx(0.8)
        assert result.multiplier == 1.1
        assert calc.get_multiplier() == 1.1

    def test_medium_vpin_multiplier(self) -> None:
        calc = VPINCalculator(bucket_size=100, window_size=1)
        # 80 buy, 20 sell → vpin = 0.6
        result = calc.add_volume(80, 20)
        assert result is not None
        assert result.multiplier == 1.05
        assert calc.get_multiplier() == 1.05

    def test_low_vpin_multiplier(self) -> None:
        calc = VPINCalculator(bucket_size=100, window_size=1)
        # 60 buy, 40 sell → vpin = 0.2
        result = calc.add_volume(60, 40)
        assert result is not None
        assert result.multiplier == 1.0
        assert calc.get_multiplier() == 1.0

    def test_current_vpin_updates(self) -> None:
        calc = VPINCalculator(bucket_size=100, window_size=1)
        assert calc.current_vpin == 0.0
        calc.add_volume(100, 0)
        assert calc.current_vpin == pytest.approx(1.0)


class TestWindowBehavior:
    def test_window_rolls_over(self) -> None:
        calc = VPINCalculator(bucket_size=100, window_size=2)
        # First bucket: all buy (imbalance = 100)
        calc.add_volume(100, 0)
        # Second bucket: balanced (imbalance = 0)
        calc.add_volume(50, 50)
        # VPIN = (100 + 0) / (100 + 100) = 0.5
        assert calc.current_vpin == pytest.approx(0.5)
        # Third bucket: balanced — window drops first bucket
        result = calc.add_volume(50, 50)
        assert result is not None
        # Window now has two balanced: (0 + 0) / (100 + 100) = 0.0
        assert result.value == pytest.approx(0.0)
