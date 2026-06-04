"""Async inference pipeline: ThreadPoolExecutor for Kronos + janus queue for results."""
from __future__ import annotations

import asyncio
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from queue import Empty, Full
from typing import Any

from deep6v2.types.bar import FootprintBar
from deep6v2.types.signal import Direction

try:
    import janus
except ImportError:  # pragma: no cover - optional dependency
    janus = None  # type: ignore[assignment]


@dataclass(frozen=True)
class E10Prediction:
    direction: Direction
    strength: float
    stale: bool


class KronosPipeline:
    def __init__(self, model_manager: Any = None, inference_interval: int = 5, pool_size: int = 1) -> None:
        self._model = model_manager
        self._interval = inference_interval
        self._executor = ThreadPoolExecutor(max_workers=pool_size)
        self._ohlcv_buffer: deque[dict[str, float]] = deque(maxlen=512)
        self._last_prediction: E10Prediction | None = None
        self._bars_since_inference = 0
        self._inference_running = False
        self._result_queue: Any | None = janus.Queue(maxsize=1) if janus is not None else None

    def add_bar(self, bar: FootprintBar) -> None:
        """Add bar to OHLCV buffer."""
        self._ohlcv_buffer.append(
            {
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": float(bar.total_volume),
            }
        )
        self._bars_since_inference += 1

    async def maybe_infer(self, current_close: float) -> E10Prediction | None:
        """Trigger inference if interval reached. Non-blocking — uses stale if busy."""
        self._drain_result_queue()

        if self._inference_running:
            if self._last_prediction is None:
                return None
            return E10Prediction(
                direction=self._last_prediction.direction,
                strength=self._last_prediction.strength,
                stale=True,
            )
        if self._bars_since_inference < self._interval:
            return self._last_prediction
        if len(self._ohlcv_buffer) < 10:
            return None

        self._inference_running = True
        self._bars_since_inference = 0
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(self._executor, self._sync_infer, current_close)
            self._last_prediction = result
            self._publish_result(result)
            return result
        finally:
            self._inference_running = False

    def _sync_infer(self, current_close: float) -> E10Prediction:
        """Synchronous inference in thread pool."""
        if self._model is not None and getattr(self._model, "is_loaded", False):
            prediction = self._model.predict(list(self._ohlcv_buffer))
            predicted_close = float(prediction.get("close", current_close))
        else:
            predicted_close = current_close

        diff = predicted_close - current_close
        if abs(diff) < 0.01:
            return E10Prediction(Direction.NEUTRAL, 0.0, stale=False)

        direction = Direction.BULLISH if diff > 0 else Direction.BEARISH
        strength = min(abs(diff) / 10.0, 1.0)
        return E10Prediction(direction, strength, stale=False)

    def get_latest(self) -> E10Prediction | None:
        self._drain_result_queue()
        return self._last_prediction

    def shutdown(self) -> None:
        if self._result_queue is not None:
            self._result_queue.close()
        self._executor.shutdown(wait=False)

    def _publish_result(self, result: E10Prediction) -> None:
        if self._result_queue is None:
            return
        sync_queue = self._result_queue.sync_q
        try:
            sync_queue.put_nowait(result)
        except Full:
            try:
                sync_queue.get_nowait()
            except Empty:
                pass
            sync_queue.put_nowait(result)

    def _drain_result_queue(self) -> None:
        if self._result_queue is None:
            return
        sync_queue = self._result_queue.sync_q
        while True:
            try:
                self._last_prediction = sync_queue.get_nowait()
            except Empty:
                break


__all__ = ["E10Prediction", "KronosPipeline"]
