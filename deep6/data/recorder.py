"""Live feed recorder — tees on_tick + on_order_book events to disk.

Produces daily zstd-compressed JSONL files suitable for later replay through
the same `make_tick_callback` / `make_dom_callback` the live path uses. No
additional data-vendor cost: every byte comes from the already-paid Rithmic
subscription.

Event schema (one JSON object per line):
    tick: {"t": ts_ns, "k": "tick", "p": price, "s": size, "a": aggressor}
    dom:  {"t": ts_ns, "k": "dom",  "bp": [...], "bs": [...], "ap": [...], "as": [...]}

Hot-path safety:
  * Callbacks enqueue to a bounded asyncio.Queue and return immediately.
  * A background writer task drains the queue, serializes, and streams
    through zstandard. The file I/O cost never touches the feed thread.
  * If the queue saturates (recorder can't keep up), events are dropped
    and a throttled warning is logged. Feed integrity outranks recorder
    completeness — DOM at 1,000/sec must never block.

Daily rotation (UTC) keeps individual files small enough to process.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
import zstandard as zstd

log = structlog.get_logger()


class LiveRecorder:
    """Append raw tick + DOM events to a daily compressed JSONL file."""

    _EVALUABLE_UPDATE_TYPES = frozenset(("SOLO", "END"))

    def __init__(self, base_dir: str | Path, queue_size: int = 50_000, zstd_level: int = 3):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._queue_size = queue_size
        self._zstd_level = zstd_level
        self._q: asyncio.Queue | None = None
        self._task: asyncio.Task | None = None
        self._file = None
        self._compressor = None
        self._current_date: str | None = None
        self._dropped: int = 0
        self._written: int = 0

    async def start(self) -> None:
        self._q = asyncio.Queue(maxsize=self._queue_size)
        self._task = asyncio.create_task(self._writer_loop())
        log.info("recorder.started", dir=str(self.base_dir))

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._close_file()
        log.info("recorder.stopped", written=self._written, dropped=self._dropped)

    @property
    def stats(self) -> dict[str, int]:
        return {"written": self._written, "dropped": self._dropped}

    # -------------------------------------------------------------------------
    # async-rithmic callbacks — attach via `client.on_tick += recorder.on_tick`
    # -------------------------------------------------------------------------

    async def on_tick(self, tick: Any) -> None:
        """Tee LAST_TRADE ticks. Non-LAST_TRADE events are ignored."""
        from async_rithmic import DataType

        if getattr(tick, "data_type", None) != DataType.LAST_TRADE:
            return
        lt = getattr(tick, "last_trade", None)
        if lt is None:
            return
        price = getattr(lt, "price", None)
        size = getattr(lt, "size", None)
        if price is None or size is None:
            return
        self._enqueue({
            "t": time.time_ns(),
            "k": "tick",
            "p": price,
            "s": size,
            "a": getattr(lt, "aggressor", 0),
        })

    async def on_order_book(self, update: Any) -> None:
        """Tee complete DOM snapshots only (SOLO or END update_type)."""
        if getattr(update, "update_type", None) not in self._EVALUABLE_UPDATE_TYPES:
            return
        bids = getattr(update, "bids", None) or []
        asks = getattr(update, "asks", None) or []
        self._enqueue({
            "t": time.time_ns(),
            "k": "dom",
            "bp": [lv.price for lv in bids],
            "bs": [lv.size for lv in bids],
            "ap": [lv.price for lv in asks],
            "as": [lv.size for lv in asks],
        })

    # -------------------------------------------------------------------------
    # Internals
    # -------------------------------------------------------------------------

    def _enqueue(self, event: dict) -> None:
        if self._q is None:
            return
        try:
            self._q.put_nowait(event)
        except asyncio.QueueFull:
            self._dropped += 1
            if self._dropped == 1 or self._dropped % 1000 == 0:
                log.warning("recorder.queue_full", dropped=self._dropped)

    async def _writer_loop(self) -> None:
        assert self._q is not None
        try:
            while True:
                event = await self._q.get()
                self._write_event(event)
        except asyncio.CancelledError:
            # Drain remaining events on graceful shutdown
            while self._q is not None and not self._q.empty():
                self._write_event(self._q.get_nowait())
            raise

    def _write_event(self, event: dict) -> None:
        self._rotate_if_needed()
        line = (json.dumps(event, separators=(",", ":")) + "\n").encode("utf-8")
        self._compressor.write(line)  # type: ignore[union-attr]
        self._written += 1

    def _rotate_if_needed(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today == self._current_date and self._compressor is not None:
            return
        self._close_file()
        path = self.base_dir / f"{today}.jsonl.zst"
        self._file = path.open("ab")
        self._compressor = zstd.ZstdCompressor(level=self._zstd_level).stream_writer(self._file)
        self._current_date = today
        log.info("recorder.rotate", path=str(path))

    def _close_file(self) -> None:
        if self._compressor is not None:
            try:
                self._compressor.close()
            except Exception as exc:
                log.warning("recorder.compressor_close_failed", error=str(exc))
            self._compressor = None
        if self._file is not None:
            try:
                self._file.close()
            except Exception as exc:
                log.warning("recorder.file_close_failed", error=str(exc))
            self._file = None


def attach_recorder(client: Any, recorder: LiveRecorder) -> None:
    """Attach recorder callbacks alongside the live signal-path callbacks.

    Call this AFTER `register_callbacks(client, state)` so the recorder sees
    the same events the signal engine sees. async-rithmic's `+=` subscription
    fans events to every registered handler.
    """
    client.on_tick += recorder.on_tick
    client.on_order_book += recorder.on_order_book
    log.info("recorder.attached")
