"""Tests for KronosDomainAdapter — Kronos bias → DomainScore translation."""
from __future__ import annotations

import time

import pytest

from deep6.engines.bias_contracts import DomainScore
from deep6.engines.kronos_bias import KronosBias
from deep6.engines.kronos_domain import KronosDomainAdapter
from deep6.engines.signal_config import KronosDomainConfig


def _bias(
    direction: int = 1,
    confidence: float = 50.0,
    predicted_close: float = 21000.0,
    current_close: float = 20950.0,
    samples: int = 20,
    inference_time_ms: float = 120.0,
    bars_since_inference: int = 0,
    detail: str = "test",
) -> KronosBias:
    return KronosBias(
        direction=direction,
        confidence=confidence,
        predicted_close=predicted_close,
        current_close=current_close,
        samples=samples,
        inference_time_ms=inference_time_ms,
        bars_since_inference=bars_since_inference,
        detail=detail,
    )


@pytest.fixture
def adapter() -> KronosDomainAdapter:
    return KronosDomainAdapter()


# ── Core translation tests ─────────────────────────────────────────


class TestConfidenceBands:
    """Verify each confidence band maps to the correct magnitude."""

    def test_high_confidence_bull(self, adapter: KronosDomainAdapter) -> None:
        """direction=+1, confidence=85 → score=+3."""
        result = adapter.compute(_bias(direction=1, confidence=85.0))
        assert result.score == 3
        assert result.available is True

    def test_mid_confidence_bull(self, adapter: KronosDomainAdapter) -> None:
        """direction=+1, confidence=60 → score=+2."""
        result = adapter.compute(_bias(direction=1, confidence=60.0))
        assert result.score == 2

    def test_low_confidence_bull(self, adapter: KronosDomainAdapter) -> None:
        """direction=+1, confidence=40 → score=+1."""
        result = adapter.compute(_bias(direction=1, confidence=40.0))
        assert result.score == 1

    def test_below_threshold_bull(self, adapter: KronosDomainAdapter) -> None:
        """direction=+1, confidence=20 → score=0 (below low_conf_threshold)."""
        result = adapter.compute(_bias(direction=1, confidence=20.0))
        assert result.score == 0
        assert result.available is True  # signal exists, just low confidence

    def test_high_confidence_bear(self, adapter: KronosDomainAdapter) -> None:
        """direction=-1, confidence=75 → score=-3."""
        result = adapter.compute(_bias(direction=-1, confidence=75.0))
        assert result.score == -3

    def test_neutral_direction(self, adapter: KronosDomainAdapter) -> None:
        """direction=0, any confidence → score=0, available=True."""
        result = adapter.compute(_bias(direction=0, confidence=80.0))
        assert result.score == 0
        assert result.available is True


# ── Cold start ──────────────────────────────────────────────────────


class TestColdStart:
    def test_none_bias(self, adapter: KronosDomainAdapter) -> None:
        """kronos_bias=None → available=False, score=0."""
        result = adapter.compute(None)
        assert result.score == 0
        assert result.available is False
        assert result.stale is False
        assert result.detail == {"reason": "cold start"}
        assert result.domain == "kronos"
        assert result.max_range == 3


# ── Staleness ───────────────────────────────────────────────────────


class TestStaleness:
    def test_stale_inference(self, adapter: KronosDomainAdapter) -> None:
        """Old inference_ts → stale=True."""
        old_ts = time.time() - 400  # 400s ago, threshold is 300s
        result = adapter.compute(_bias(direction=1, confidence=70.0), inference_ts=old_ts)
        assert result.stale is True
        assert result.score == 3  # score still computed

    def test_fresh_inference(self, adapter: KronosDomainAdapter) -> None:
        """Recent inference_ts → stale=False."""
        result = adapter.compute(
            _bias(direction=-1, confidence=55.0),
            inference_ts=time.time(),
        )
        assert result.stale is False
        assert result.score == -2

    def test_no_timestamp_assumes_fresh(self, adapter: KronosDomainAdapter) -> None:
        """No inference_ts → stale=False (assumed fresh)."""
        result = adapter.compute(_bias(direction=1, confidence=50.0))
        assert result.stale is False


# ── Boundary conditions ─────────────────────────────────────────────


class TestBoundaries:
    def test_exactly_at_high_threshold(self, adapter: KronosDomainAdapter) -> None:
        """confidence == 70.0 (exactly at high_conf_threshold) → magnitude=3."""
        result = adapter.compute(_bias(direction=1, confidence=70.0))
        assert result.score == 3

    def test_exactly_at_low_threshold(self, adapter: KronosDomainAdapter) -> None:
        """confidence == 30.0 (exactly at low_conf_threshold) → magnitude=1."""
        result = adapter.compute(_bias(direction=-1, confidence=30.0))
        assert result.score == -1

    def test_exactly_at_mid_boundary(self, adapter: KronosDomainAdapter) -> None:
        """confidence == 50.0 → magnitude=2."""
        result = adapter.compute(_bias(direction=1, confidence=50.0))
        assert result.score == 2

    def test_zero_confidence(self, adapter: KronosDomainAdapter) -> None:
        """confidence=0 → magnitude=0."""
        result = adapter.compute(_bias(direction=1, confidence=0.0))
        assert result.score == 0

    def test_max_confidence(self, adapter: KronosDomainAdapter) -> None:
        """confidence=100 → magnitude=3."""
        result = adapter.compute(_bias(direction=-1, confidence=100.0))
        assert result.score == -3


# ── Detail propagation ──────────────────────────────────────────────


class TestDetail:
    def test_detail_contains_bias_fields(self, adapter: KronosDomainAdapter) -> None:
        bias = _bias(direction=1, confidence=72.0, samples=20, bars_since_inference=2)
        result = adapter.compute(bias)
        assert result.detail["direction"] == 1
        assert result.detail["confidence"] == 72.0
        assert result.detail["magnitude"] == 3
        assert result.detail["samples"] == 20
        assert result.detail["bars_since_inference"] == 2


# ── Custom config ───────────────────────────────────────────────────


class TestCustomConfig:
    def test_custom_thresholds(self) -> None:
        """Custom config changes band boundaries."""
        cfg = KronosDomainConfig(
            max_range=3,
            high_conf_threshold=80.0,
            low_conf_threshold=40.0,
        )
        adapter = KronosDomainAdapter(config=cfg)

        # 75% is below custom high (80) → magnitude=2 instead of 3
        result = adapter.compute(_bias(direction=1, confidence=75.0))
        assert result.score == 2

        # 35% is below custom low (40) → magnitude=0 instead of 1
        result = adapter.compute(_bias(direction=1, confidence=35.0))
        assert result.score == 0
