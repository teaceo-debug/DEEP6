"""Synthetic tests for Databento MBO replay engine."""
from __future__ import annotations

import pytest

from cross_market.replay.mbo_replay_engine import MBOReplayEngine
from cross_market.types.mbo_event import MBOAction, MBOEvent, MBOSide


def make_test_events() -> list[MBOEvent]:
    return [
        MBOEvent(
            timestamp_exchange_ns=1_000,
            timestamp_recv_ns=1_000,
            symbol="NQ.c.0",
            action=MBOAction.ADD,
            side=MBOSide.BID,
            price=21550.0,
            size=100,
            order_id="O001",
            sequence_id=1,
        ),
        MBOEvent(
            timestamp_exchange_ns=2_000,
            timestamp_recv_ns=2_000,
            symbol="NQ.c.0",
            action=MBOAction.TRADE,
            side=MBOSide.BID,
            price=21550.0,
            size=50,
            order_id="O001",
            sequence_id=2,
        ),
        MBOEvent(
            timestamp_exchange_ns=3_000,
            timestamp_recv_ns=3_000,
            symbol="NQ.c.0",
            action=MBOAction.CANCEL,
            side=MBOSide.BID,
            price=21550.0,
            size=50,
            order_id="O001",
            sequence_id=3,
        ),
    ]


def test_replay_engine_no_file() -> None:
    engine = MBOReplayEngine(path=None)
    assert list(engine.stream_sync()) == []
    assert engine.event_count == 0


def test_replay_engine_counts_events_sync() -> None:
    engine = MBOReplayEngine.from_synthetic_events(make_test_events())
    events = list(engine.stream_sync())
    assert len(events) == 3
    assert engine.event_count == 3
    assert events[0].action == MBOAction.ADD
    assert events[-1].action == MBOAction.CANCEL


@pytest.mark.asyncio
async def test_replay_engine_streams_synthetic_events_async() -> None:
    engine = MBOReplayEngine.from_synthetic_events(make_test_events())
    events = [event async for event in engine.stream()]
    assert [event.sequence_id for event in events] == [1, 2, 3]
    assert engine.event_count == 3


def test_replay_engine_preserves_synthetic_events() -> None:
    source_events = make_test_events()
    engine = MBOReplayEngine.from_synthetic_events(source_events)
    assert engine._synthetic_events == source_events
