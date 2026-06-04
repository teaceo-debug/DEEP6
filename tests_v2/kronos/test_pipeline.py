"""Tests for Kronos async inference pipeline."""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime

from deep6v2.kronos.pipeline import E10Prediction, KronosPipeline
from deep6v2.types.bar import FootprintBar, SessionType
from deep6v2.types.signal import Direction


def make_bar(index: int, close: float = 100.0) -> FootprintBar:
    return FootprintBar(
        open=close - 1.0,
        high=close + 1.0,
        low=close - 2.0,
        close=close,
        delta=10,
        total_volume=100,
        bid_volumes={close - 0.25: 40},
        ask_volumes={close: 60},
        poc_price=close,
        poc_volume=50,
        vah=close + 2.0,
        val=close - 2.0,
        cvd=20.0,
        bar_index=index,
        timestamp=datetime(2026, 1, 1, 9, 30),
        session_type=SessionType.RTH,
    )


class BlockingModel:
    def __init__(self, predicted_close: float) -> None:
        self.is_loaded = True
        self.predicted_close = predicted_close
        self.started = threading.Event()
        self.release = threading.Event()

    def predict(self, ohlcv_data: list[dict[str, float]]) -> dict[str, float]:
        self.started.set()
        self.release.wait(timeout=2)
        return {"close": self.predicted_close}


class LoadedModel:
    def __init__(self, predicted_close: float) -> None:
        self.is_loaded = True
        self.predicted_close = predicted_close
        self.calls = 0

    def predict(self, ohlcv_data: list[dict[str, float]]) -> dict[str, float]:
        self.calls += 1
        return {"close": self.predicted_close}


def test_ohlcv_buffer_accumulates_and_caps_at_512() -> None:
    pipeline = KronosPipeline()
    try:
        for index in range(520):
            pipeline.add_bar(make_bar(index, close=100.0 + index))

        assert len(pipeline._ohlcv_buffer) == 512
        assert pipeline._ohlcv_buffer[0]["close"] == 108.0
        assert pipeline._ohlcv_buffer[-1]["close"] == 619.0
    finally:
        pipeline.shutdown()


def test_inference_only_triggers_at_interval() -> None:
    model = LoadedModel(predicted_close=112.0)
    pipeline = KronosPipeline(model_manager=model, inference_interval=20)
    try:
        for index in range(10):
            pipeline.add_bar(make_bar(index, close=100.0 + index))

        first = asyncio.run(pipeline.maybe_infer(current_close=109.0))
        assert first is None
        assert model.calls == 0

        for index in range(10, 20):
            pipeline.add_bar(make_bar(index, close=100.0 + index))

        second = asyncio.run(pipeline.maybe_infer(current_close=119.0))
        assert second is not None
        assert second.direction == Direction.BEARISH
        assert model.calls == 1
    finally:
        pipeline.shutdown()


def test_stale_prediction_returned_when_inference_running() -> None:
    model = BlockingModel(predicted_close=120.0)
    pipeline = KronosPipeline(model_manager=model, inference_interval=1)
    pipeline._last_prediction = E10Prediction(Direction.BEARISH, 0.4, stale=False)
    try:
        for index in range(10):
            pipeline.add_bar(make_bar(index, close=100.0 + index))

        async def exercise() -> tuple[E10Prediction | None, E10Prediction | None]:
            first_task = asyncio.create_task(pipeline.maybe_infer(current_close=109.0))
            await asyncio.sleep(0)
            assert await asyncio.to_thread(model.started.wait, 1.0)
            stale = await pipeline.maybe_infer(current_close=109.0)
            model.release.set()
            completed = await first_task
            return stale, completed

        stale, completed = asyncio.run(exercise())

        assert stale == E10Prediction(Direction.BEARISH, 0.4, stale=True)
        assert completed == E10Prediction(Direction.BULLISH, 1.0, stale=False)
    finally:
        model.release.set()
        pipeline.shutdown()


def test_pipeline_works_without_model_and_returns_neutral_prediction() -> None:
    pipeline = KronosPipeline(model_manager=None, inference_interval=1)
    try:
        for index in range(10):
            pipeline.add_bar(make_bar(index, close=100.0 + index))

        result = asyncio.run(pipeline.maybe_infer(current_close=109.0))

        assert result == E10Prediction(Direction.NEUTRAL, 0.0, stale=False)
        assert pipeline.get_latest() == result
    finally:
        pipeline.shutdown()


def test_shutdown_completes() -> None:
    pipeline = KronosPipeline()
    pipeline.shutdown()
