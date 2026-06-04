"""Append-only store for raw MBO events before transformation."""
from __future__ import annotations

import asyncio
from collections import deque
from pathlib import Path
from datetime import datetime
from typing import Deque

import pyarrow as pa
import pyarrow.parquet as pq


class RawEventStore:
    FLUSH_EVERY = 10_000
    FLUSH_INTERVAL_S = 5.0

    def __init__(self, base_dir: str | Path = "data/cross_market/raw"):
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._buffer: Deque[dict] = deque()
        self._total = 0
        self._flush_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        if self._flush_task:
            self._flush_task.cancel()
        await self._flush_to_disk()

    def append(self, event: dict) -> None:
        """Thread-safe append (called from event loop only)."""
        self._buffer.append(event)
        self._total += 1
        if len(self._buffer) >= self.FLUSH_EVERY:
            asyncio.create_task(self._flush_to_disk())

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(self.FLUSH_INTERVAL_S)
            await self._flush_to_disk()

    async def _flush_to_disk(self) -> None:
        if not self._buffer:
            return
        batch = list(self._buffer)
        self._buffer.clear()
        date_str = datetime.utcnow().strftime("%Y%m%d")
        path = self._base / f"mbo_{date_str}.parquet"
        table = pa.Table.from_pylist(batch)
        if path.exists():
            existing = pq.read_table(path)
            table = pa.concat_tables([existing, table])
        pq.write_table(table, path, compression="snappy")

    @property
    def total_events(self) -> int:
        return self._total
