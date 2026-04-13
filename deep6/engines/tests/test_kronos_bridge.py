"""Tests for KronosSubprocessBridge — event-loop-safe E10 bias engine.

Per 06-01-PLAN.md Task 2 TDD requirements.
All tests mock the worker subprocess — no real subprocess started here.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace as dc_replace
from unittest.mock import MagicMock, patch

import pytest

from deep6.engines.kronos_bias import KronosBias, KronosSubprocessBridge
from deep6.engines.signal_config import KronosConfig


def _make_bias(confidence: float = 80.0, direction: int = 1) -> KronosBias:
    """Helper: build a valid KronosBias for mock returns."""
    return KronosBias(
        direction=direction,
        confidence=confidence,
        predicted_close=17010.0,
        current_close=17000.0,
        samples=20,
        inference_time_ms=200.0,
        bars_since_inference=0,
        detail="KRONOS: BULL bias conf=80% pred=17010.00 (200ms, 20 samples)",
    )


def _make_bridge(cfg: KronosConfig | None = None) -> KronosSubprocessBridge:
    """Helper: create bridge with mocked worker (no subprocess spawned)."""
    cfg = cfg or KronosConfig()
    bridge = KronosSubprocessBridge(cfg)
    # Replace the real worker with a mock so no subprocess is created
    mock_worker = MagicMock()
    mock_worker.request_inference.return_value = _make_bias()
    bridge._worker = mock_worker
    return bridge


class TestBridgeInsufficientData:
    """Bridge returns zero-confidence bias when buffer is too small."""

    def test_bridge_insufficient_data(self):
        """Fewer than 20 bars → direction=0, confidence=0."""
        bridge = _make_bridge()

        for i in range(5):
            bridge.add_bar(17000 + i, 17010 + i, 16995 + i, 17005 + i, 1000.0)

        result = asyncio.run(bridge.get_bias())

        assert result.direction == 0
        assert result.confidence == 0
        assert result.samples == 0
        assert "insufficient" in result.detail.lower()


class TestBridgeDecay:
    """Bridge applies 0.95^n confidence decay between inferences."""

    def test_bridge_decay(self):
        """After inference, decay is applied for bars_since elapsed bars."""
        bridge = _make_bridge()

        # Add 20 bars to fill buffer and trigger initial inference
        for i in range(20):
            bridge.add_bar(17000.0 + i, 17010.0 + i, 16995.0 + i, 17005.0 + i, 1000.0)

        # First call triggers inference (bars_since was 20 >= interval=5)
        asyncio.run(bridge.get_bias())

        # Manually set bars_since=3 to simulate 3 bars elapsed since last inference
        bridge._bars_since = 3

        # Call again — should NOT re-infer (3 < inference_interval=5)
        result = asyncio.run(bridge.get_bias())

        expected_confidence = 80.0 * (0.95 ** 3)
        assert result.confidence == pytest.approx(expected_confidence, abs=0.1)
        # Worker should only have been called once (the initial inference)
        assert bridge._worker.request_inference.call_count == 1


class TestBridgeReInferAtInterval:
    """Bridge re-infers after inference_interval bars."""

    def test_bridge_reinfer_at_interval(self):
        """After bars_since >= inference_interval, re-inference is triggered."""
        bridge = _make_bridge()

        # Fill buffer to trigger initial inference
        for i in range(20):
            bridge.add_bar(17000.0 + i, 17010.0 + i, 16995.0 + i, 17005.0 + i, 1000.0)

        # First inference
        asyncio.run(bridge.get_bias())
        assert bridge._worker.request_inference.call_count == 1

        # Advance bars_since to the threshold
        bridge._bars_since = 5  # == inference_interval

        # Second call should trigger re-inference
        asyncio.run(bridge.get_bias())
        assert bridge._worker.request_inference.call_count == 2


class TestGetBiasIsCoroutine:
    """get_bias() must be a coroutine (awaitable in async context)."""

    def test_get_bias_is_coroutine(self):
        """asyncio.iscoroutinefunction(bridge.get_bias) must be True."""
        bridge = _make_bridge()
        assert asyncio.iscoroutinefunction(bridge.get_bias)


class TestBridgeRunInExecutor:
    """Bridge delegates blocking recv to run_in_executor (non-blocking)."""

    def test_bridge_uses_run_in_executor(self):
        """get_bias() must call loop.run_in_executor when inferring."""
        import inspect
        from deep6.engines import kronos_bias

        source = inspect.getsource(KronosSubprocessBridge.get_bias)
        assert "run_in_executor" in source, (
            "get_bias() must use run_in_executor to avoid blocking the event loop"
        )
