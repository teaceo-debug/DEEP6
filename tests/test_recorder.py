"""Unit tests for deep6.data.recorder.LiveRecorder.

Verifies:
- tick and DOM events serialize correctly
- non-LAST_TRADE ticks are ignored
- non-SOLO/END DOM updates are ignored
- events round-trip through zstd decompression
- queue saturation increments dropped counter without raising
- start/stop lifecycle is clean
"""
from __future__ import annotations

import asyncio
import json
import types
from pathlib import Path

import pytest
import zstandard as zstd

from deep6.data.recorder import LiveRecorder


def _fake_tick(price: float, size: int, aggressor: int, data_type: str = "LAST_TRADE"):
    from async_rithmic import DataType
    dt = DataType.LAST_TRADE if data_type == "LAST_TRADE" else DataType.BBO
    return types.SimpleNamespace(
        data_type=dt,
        last_trade=types.SimpleNamespace(price=price, size=size, aggressor=aggressor),
    )


def _fake_dom(bids: list[tuple[float, int]], asks: list[tuple[float, int]], update_type: str = "SOLO"):
    return types.SimpleNamespace(
        update_type=update_type,
        bids=[types.SimpleNamespace(price=p, size=s) for p, s in bids],
        asks=[types.SimpleNamespace(price=p, size=s) for p, s in asks],
    )


def _read_events(path: Path) -> list[dict]:
    dctx = zstd.ZstdDecompressor()
    with path.open("rb") as f:
        with dctx.stream_reader(f) as reader:
            raw = reader.read()
    return [json.loads(line) for line in raw.decode("utf-8").splitlines() if line]


@pytest.mark.asyncio
async def test_records_tick_and_dom(tmp_path: Path):
    rec = LiveRecorder(tmp_path)
    await rec.start()
    await rec.on_tick(_fake_tick(20000.5, 3, aggressor=1))
    await rec.on_order_book(_fake_dom([(20000.0, 10), (19999.75, 5)], [(20000.25, 8)]))
    # Let writer drain
    await asyncio.sleep(0.05)
    await rec.stop()

    files = list(tmp_path.glob("*.jsonl.zst"))
    assert len(files) == 1, f"expected one daily file, got {files}"
    events = _read_events(files[0])
    assert len(events) == 2
    tick, dom = events
    assert tick["k"] == "tick" and tick["p"] == 20000.5 and tick["s"] == 3 and tick["a"] == 1
    assert dom["k"] == "dom" and dom["bp"] == [20000.0, 19999.75] and dom["as"] == [8]


@pytest.mark.asyncio
async def test_ignores_non_last_trade_ticks(tmp_path: Path):
    rec = LiveRecorder(tmp_path)
    await rec.start()
    await rec.on_tick(_fake_tick(20000.0, 1, 1, data_type="BBO"))
    await asyncio.sleep(0.05)
    await rec.stop()
    files = list(tmp_path.glob("*.jsonl.zst"))
    if files:
        assert _read_events(files[0]) == []


@pytest.mark.asyncio
async def test_ignores_incomplete_dom_updates(tmp_path: Path):
    rec = LiveRecorder(tmp_path)
    await rec.start()
    await rec.on_order_book(_fake_dom([(20000.0, 10)], [], update_type="BEGIN"))
    await rec.on_order_book(_fake_dom([(20000.0, 10)], [], update_type="MIDDLE"))
    await asyncio.sleep(0.05)
    await rec.stop()
    files = list(tmp_path.glob("*.jsonl.zst"))
    if files:
        assert _read_events(files[0]) == []


@pytest.mark.asyncio
async def test_queue_saturation_drops_events(tmp_path: Path):
    # Tiny queue; writer never runs so all enqueues after the first fill drop.
    rec = LiveRecorder(tmp_path, queue_size=2)
    await rec.start()
    # Stall the writer by cancelling it so the queue fills
    rec._task.cancel()  # type: ignore[union-attr]
    try:
        await rec._task  # type: ignore[union-attr]
    except asyncio.CancelledError:
        pass

    for _ in range(20):
        await rec.on_tick(_fake_tick(20000.0, 1, 1))

    assert rec.stats["dropped"] >= 15
    # stop() should still be safe
    await rec.stop()
