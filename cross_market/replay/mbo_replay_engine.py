"""Databento MBO -> MBOEvent replay engine."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator, Iterator, Optional

from cross_market.types.mbo_event import MBOAction, MBOEvent, MBOSide


ACTION_MAP = {
    "A": MBOAction.ADD,
    "C": MBOAction.CANCEL,
    "M": MBOAction.MODIFY,
    "T": MBOAction.TRADE,
    "F": MBOAction.FILL,
    "R": MBOAction.CLEAR,
}

SIDE_MAP = {
    "A": MBOSide.ASK,
    "B": MBOSide.BID,
    "N": MBOSide.NONE,
}

DATABENTO_PRICE_SCALE = 1e9


class MBOReplayEngine:
    """Replay DBN MBO records at max speed or scaled realtime."""

    def __init__(self, path: str | Path | None, speed: float = 0.0, symbol: str = "NQ.c.0") -> None:
        self.path = Path(path) if path else None
        self.speed = speed
        self.symbol = symbol
        self._event_count = 0
        self._synthetic_events: list[MBOEvent] = []

    async def stream(self) -> AsyncIterator[MBOEvent]:
        prev_ts_ns: Optional[int] = None
        for event in self._iter_events(reset_count=True):
            if self.speed > 0 and prev_ts_ns is not None:
                delay_ns = event.timestamp_exchange_ns - prev_ts_ns
                delay_s = delay_ns / 1e9 / self.speed
                if delay_s > 0:
                    await asyncio.sleep(min(delay_s, 0.1))
            prev_ts_ns = event.timestamp_exchange_ns
            self._event_count += 1
            yield event

    def stream_sync(self) -> Iterator[MBOEvent]:
        for event in self._iter_events(reset_count=True):
            self._event_count += 1
            yield event

    @staticmethod
    def from_synthetic_events(events: list[MBOEvent]) -> "MBOReplayEngine":
        engine = MBOReplayEngine(path=None)
        engine._synthetic_events = list(events)
        return engine

    @property
    def event_count(self) -> int:
        return self._event_count

    def _iter_events(self, reset_count: bool) -> Iterator[MBOEvent]:
        if reset_count:
            self._event_count = 0

        if self._synthetic_events:
            yield from self._synthetic_events
            return

        if self.path is None or not self.path.exists():
            return

        try:
            import databento as db
        except ImportError as exc:
            raise ImportError(
                "databento package required for replay. Install: pip install databento"
            ) from exc

        store = db.DBNStore.from_file(str(self.path))
        for index, record in enumerate(store):
            event = self._convert_record(record, fallback_sequence=index)
            if event is not None:
                yield event

    def _convert_record(self, record: object, fallback_sequence: int) -> Optional[MBOEvent]:
        if not hasattr(record, "action"):
            return None
        try:
            action = ACTION_MAP.get(getattr(record, "action"))
            if action is None:
                return None
            side = SIDE_MAP.get(getattr(record, "side", "N"), MBOSide.NONE)
            ts_ns = int(getattr(record, "ts_event"))
            return MBOEvent(
                timestamp_exchange_ns=ts_ns,
                timestamp_recv_ns=ts_ns,
                source="databento",
                symbol=self.symbol,
                action=action,
                side=side,
                price=float(getattr(record, "price")) / DATABENTO_PRICE_SCALE,
                size=int(getattr(record, "size", 0)),
                order_id=str(getattr(record, "order_id", 0)),
                sequence_id=int(getattr(record, "sequence", fallback_sequence)),
                priority=getattr(record, "ts_in_delta", None),
            )
        except Exception:
            return None
