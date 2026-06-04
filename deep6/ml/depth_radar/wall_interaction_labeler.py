"""Stream Databento MBO data into labeled wall-interaction examples."""
from __future__ import annotations

import argparse
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import databento as db
except ImportError:  # pragma: no cover - runtime dependency guard
    db = None  # type: ignore[assignment]

from deep6.data.databento_live import (
    _ACTION_ADD,
    _ACTION_CANCEL,
    _ACTION_CLEAR,
    _ACTION_FILL,
    _ACTION_MODIFY,
    _ACTION_TRADE,
    _SIDE_ASK,
    _SIDE_BID,
)


log = logging.getLogger(__name__)

RTH_START = time(13, 30)
RTH_END = time(20, 0)
SNAPSHOT_IMAGE = 3
PRUNE_EVERY_RECORDS = 500_000
DEFAULT_PRUNE_STALE_SEC = 900.0
INTERACTION_FEATURE_NAMES = [
    "wall_size",
    "wall_max_size",
    "wall_duration_sec",
    "wall_side",
    "wall_refill_count",
    "wall_modification_count",
    "wall_cancellation_events",
    "approach_speed",
    "book_imbalance",
    "distance_from_wall",
    "spread",
    "hour_of_day",
    "minute_of_hour",
    "cumulative_delta",
    "price_momentum_10s",
]
LABEL_COLUMNS = [
    "timestamp",
    "deadline_time",
    "session_date",
    "wall_price",
    "mid_price",
    "best_bid",
    "best_ask",
    *INTERACTION_FEATURE_NAMES,
    "label",
]


def _is_rth(ts: pd.Timestamp) -> bool:
    current = ts.tz_convert("UTC").time()
    return RTH_START <= current < RTH_END


def _session_end(ts: pd.Timestamp) -> pd.Timestamp:
    ts_utc = ts.tz_convert("UTC")
    return pd.Timestamp.combine(ts_utc.date(), RTH_END).tz_localize("UTC")


@dataclass
class _BookState:
    orders: dict[int, tuple[float, int, str]] = field(default_factory=dict)
    bid_levels: dict[float, int] = field(default_factory=lambda: defaultdict(int))
    ask_levels: dict[float, int] = field(default_factory=lambda: defaultdict(int))
    _snapshot_active: bool = False
    _snapshot_seen_orders: set[int] = field(default_factory=set)

    def clear(self) -> None:
        self.orders.clear()
        self.bid_levels.clear()
        self.ask_levels.clear()
        self._snapshot_active = False
        self._snapshot_seen_orders.clear()

    def start_snapshot(self) -> None:
        if not self._snapshot_active:
            self._snapshot_active = True
            self._snapshot_seen_orders.clear()

    def mark_snapshot_order(self, order_id: int) -> None:
        if self._snapshot_active and order_id > 0:
            self._snapshot_seen_orders.add(order_id)

    def finish_snapshot(self) -> None:
        if not self._snapshot_active:
            return
        stale_orders = [order_id for order_id in self.orders if order_id not in self._snapshot_seen_orders]
        for order_id in stale_orders:
            price, size, side = self.orders.pop(order_id)
            self._level_map(side)[price] -= size
            self._cleanup_level(side, price)
        self._snapshot_active = False
        self._snapshot_seen_orders.clear()

    def apply(self, order_id: int, price: float, size: int, side: str, action: str) -> None:
        if side not in (_SIDE_BID, _SIDE_ASK):
            return
        levels = self._level_map(side)
        if action == _ACTION_ADD:
            previous = self.orders.get(order_id)
            if previous is not None:
                prev_price, prev_size, prev_side = previous
                self._level_map(prev_side)[prev_price] -= prev_size
                self._cleanup_level(prev_side, prev_price)
            self.orders[order_id] = (price, size, side)
            levels[price] += size
            return
        if action == _ACTION_MODIFY:
            previous = self.orders.get(order_id)
            if previous is not None:
                prev_price, prev_size, prev_side = previous
                self._level_map(prev_side)[prev_price] -= prev_size
                self._cleanup_level(prev_side, prev_price)
            self.orders[order_id] = (price, size, side)
            levels[price] += size
            return
        if action == _ACTION_CANCEL:
            previous = self.orders.pop(order_id, None)
            if previous is None:
                return
            prev_price, prev_size, prev_side = previous
            self._level_map(prev_side)[prev_price] -= prev_size
            self._cleanup_level(prev_side, prev_price)
            return
        if action in (_ACTION_FILL, _ACTION_TRADE):
            previous = self.orders.get(order_id)
            if previous is None:
                return
            prev_price, prev_size, prev_side = previous
            fill_size = max(size, 0)
            new_size = prev_size - fill_size
            prev_levels = self._level_map(prev_side)
            prev_levels[prev_price] -= min(fill_size, prev_size)
            if new_size <= 0:
                self.orders.pop(order_id, None)
            else:
                self.orders[order_id] = (prev_price, new_size, prev_side)
            self._cleanup_level(prev_side, prev_price)

    def best_bid(self) -> float:
        return max(self.bid_levels) if self.bid_levels else 0.0

    def best_ask(self) -> float:
        return min(self.ask_levels) if self.ask_levels else 0.0

    def top_levels(self, depth: int = 10) -> tuple[list[float], list[int], list[float], list[int]]:
        bid_prices = sorted(self.bid_levels, reverse=True)[:depth]
        ask_prices = sorted(self.ask_levels)[:depth]
        return (
            bid_prices,
            [int(self.bid_levels[price]) for price in bid_prices],
            ask_prices,
            [int(self.ask_levels[price]) for price in ask_prices],
        )

    def level_size(self, side: str, price: float) -> int:
        return int(self._level_map(side).get(price, 0))

    def _level_map(self, side: str) -> dict[float, int]:
        return self.bid_levels if side == _SIDE_BID else self.ask_levels

    def _cleanup_level(self, side: str, price: float) -> None:
        levels = self._level_map(side)
        if levels.get(price, 0) <= 0:
            levels.pop(price, None)


@dataclass
class WallState:
    price: float
    side: str
    first_seen: pd.Timestamp
    last_update: pd.Timestamp
    current_size: int
    max_size: int
    original_size: int
    threshold_since: pd.Timestamp | None = None
    modification_count: int = 0
    cancellation_events: int = 0
    refill_count: int = 0
    in_interaction: bool = False
    interaction_cooldown_until: pd.Timestamp | None = None
    _below_half: bool = field(default=False, init=False, repr=False)

    def update(self, timestamp: pd.Timestamp, new_size: int, threshold: int) -> None:
        size = max(int(new_size), 0)
        previous = self.current_size
        if previous != size:
            self.modification_count += 1
        if previous > 0 and size == 0:
            self.cancellation_events += 1
        elif previous == 0 and size > 0:
            self.cancellation_events += 1
        reference_max = max(self.max_size, previous)
        if reference_max > 0:
            if size < reference_max * 0.5:
                self._below_half = True
            elif self._below_half and size >= reference_max * 0.5 and size > previous:
                self.refill_count += 1
                self._below_half = False
        if size > self.max_size:
            self.max_size = size
            self._below_half = False
        self.current_size = size
        self.last_update = timestamp
        if size >= threshold:
            if self.threshold_since is None:
                self.threshold_since = timestamp
        else:
            self.threshold_since = None
            self.in_interaction = False
            self.interaction_cooldown_until = None

    def qualified(self, now: pd.Timestamp, min_duration_sec: float) -> bool:
        return self.current_size > 0 and (now - self.first_seen).total_seconds() >= min_duration_sec

    def duration_sec(self, now: pd.Timestamp) -> float:
        return max((now - self.first_seen).total_seconds(), 0.0)


@dataclass
class InteractionEvent:
    timestamp: pd.Timestamp
    deadline_time: pd.Timestamp
    session_date: str
    wall_price: float
    mid_price: float
    best_bid: float
    best_ask: float
    wall_size: int
    wall_max_size: int
    wall_duration_sec: float
    wall_side: int
    wall_refill_count: int
    wall_modification_count: int
    wall_cancellation_events: int
    approach_speed: float
    book_imbalance: float
    distance_from_wall: float
    spread: float
    hour_of_day: int
    minute_of_hour: int
    cumulative_delta: float
    price_momentum_10s: float
    bounce_distance: float
    break_distance: float
    label: str | None = None
    max_mid: float = field(default=float("-inf"))
    min_mid: float = field(default=float("inf"))

    def resolve_label(self) -> str:
        if self.wall_side == 1:
            broke = self.max_mid >= self.wall_price + self.break_distance
            bounced = (self.wall_price - self.min_mid) >= self.bounce_distance and not broke
        else:
            broke = self.min_mid <= self.wall_price - self.break_distance
            bounced = (self.max_mid - self.wall_price) >= self.bounce_distance and not broke
        if broke:
            return "BREAK"
        if bounced:
            return "BOUNCE"
        return "HOLD"

    def to_row(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "deadline_time": self.deadline_time,
            "session_date": self.session_date,
            "wall_price": self.wall_price,
            "mid_price": self.mid_price,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "wall_size": self.wall_size,
            "wall_max_size": self.wall_max_size,
            "wall_duration_sec": self.wall_duration_sec,
            "wall_side": self.wall_side,
            "wall_refill_count": self.wall_refill_count,
            "wall_modification_count": self.wall_modification_count,
            "wall_cancellation_events": self.wall_cancellation_events,
            "approach_speed": self.approach_speed,
            "book_imbalance": self.book_imbalance,
            "distance_from_wall": self.distance_from_wall,
            "spread": self.spread,
            "hour_of_day": self.hour_of_day,
            "minute_of_hour": self.minute_of_hour,
            "cumulative_delta": self.cumulative_delta,
            "price_momentum_10s": self.price_momentum_10s,
            "label": self.label,
        }


class WallInteractionLabeler:
    """Streaming Databento MBO replay into wall interaction labels."""

    def __init__(
        self,
        min_wall: int = 50,
        tick_size: float = 0.25,
        min_wall_duration_sec: float = 10.0,
        interaction_ticks: int = 4,
        bounce_ticks: int = 8,
        break_ticks: int = 4,
        lookforward_sec: int = 300,
        prune_stale_sec: float = DEFAULT_PRUNE_STALE_SEC,
    ) -> None:
        self.min_wall = int(min_wall)
        self.tick_size = float(tick_size)
        self.min_wall_duration_sec = float(min_wall_duration_sec)
        self.interaction_ticks = int(interaction_ticks)
        self.bounce_ticks = int(bounce_ticks)
        self.break_ticks = int(break_ticks)
        self.lookforward_sec = int(lookforward_sec)
        self.prune_stale_sec = float(prune_stale_sec)
        self._book = _BookState()
        self._walls: dict[tuple[str, float], WallState] = {}
        self._pending: list[InteractionEvent] = []
        self._rows: list[dict[str, Any]] = []
        self._price_window: deque[tuple[pd.Timestamp, float]] = deque()
        self._last_mid: float = 0.0
        self._last_mid_ts: pd.Timestamp | None = None
        self._last_ts: pd.Timestamp | None = None
        self._current_session: str | None = None
        self._current_in_rth = False
        self._cumulative_delta = 0.0
        self._records_processed = 0

    def process_mbo_file(self, input_path: str) -> pd.DataFrame:
        if db is None:
            raise RuntimeError("databento is not installed. Install it with `pip install databento`.")
        path = Path(input_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Databento MBO file not found: {path}")

        self._reset()
        store = db.DBNStore.from_file(str(path))
        for record in store:
            self._records_processed += 1
            self._process_record(record)
            if self._records_processed % PRUNE_EVERY_RECORDS == 0:
                self._batch_prune()

        self._book.finish_snapshot()
        if self._last_ts is not None:
            self._finalize_expired(self._last_ts, force=True)

        frame = pd.DataFrame(self._rows, columns=LABEL_COLUMNS)
        if not frame.empty:
            frame.sort_values("timestamp", kind="stable", inplace=True)
            frame.reset_index(drop=True, inplace=True)
        return frame

    def run(self, input_path: str, output_path: str) -> pd.DataFrame:
        frame = self.process_mbo_file(input_path)
        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(output, index=False)
        counts = frame["label"].value_counts().to_dict() if not frame.empty else {}
        log.info(
            "wall_interaction_labeler.completed rows=%s output_path=%s label_distribution=%s",
            len(frame),
            output,
            counts,
        )
        print(f"Wrote {len(frame)} wall interactions to {output}")
        if counts:
            print(f"Class distribution: {counts}")
        return frame

    def _reset(self) -> None:
        self._book.clear()
        self._walls.clear()
        self._pending.clear()
        self._rows.clear()
        self._price_window.clear()
        self._last_mid = 0.0
        self._last_mid_ts = None
        self._last_ts = None
        self._current_session = None
        self._current_in_rth = False
        self._cumulative_delta = 0.0
        self._records_processed = 0

    def _process_record(self, record: Any) -> None:
        action = self._decode_char(getattr(record, "action", None))
        if action is None:
            return
        timestamp = self._timestamp_from_record(record)
        self._last_ts = timestamp
        self._handle_session_transition(timestamp)
        if not self._current_in_rth:
            return

        update_type = int(getattr(record, "update_type", 0) or 0)
        if update_type == SNAPSHOT_IMAGE:
            self._book.start_snapshot()
        else:
            self._book.finish_snapshot()

        side = self._decode_char(getattr(record, "side", None)) or "N"
        order_id = int(getattr(record, "order_id", 0) or 0)
        if update_type == SNAPSHOT_IMAGE:
            self._book.mark_snapshot_order(order_id)

        if action == _ACTION_CLEAR:
            self._book.clear()
            if self._current_in_rth:
                self._advance_market_state(timestamp)
            return

        price = self._price_from_record(record)
        size = int(getattr(record, "size", 0) or 0)
        if action in (_ACTION_ADD, _ACTION_MODIFY, _ACTION_CANCEL, _ACTION_FILL, _ACTION_TRADE):
            self._book.apply(order_id, price, size, side, action)

        if action == _ACTION_TRADE:
            self._update_cumulative_delta(side, size)

        if side in (_SIDE_BID, _SIDE_ASK):
            self._update_wall_state(timestamp, side, price)

        self._advance_market_state(timestamp)

    def _handle_session_transition(self, timestamp: pd.Timestamp) -> None:
        in_rth = _is_rth(timestamp)
        session_id = str(timestamp.tz_convert("UTC").date())
        if self._current_session is None:
            self._current_session = session_id
            self._current_in_rth = in_rth
            return
        session_changed = session_id != self._current_session
        rth_boundary_crossed = self._current_in_rth != in_rth
        if session_changed or rth_boundary_crossed:
            self._finalize_expired(timestamp, force=True)
            self._book.clear()
            self._walls.clear()
            self._price_window.clear()
            self._last_mid = 0.0
            self._last_mid_ts = None
            if session_changed or in_rth:
                self._cumulative_delta = 0.0
            self._current_session = session_id
        self._current_in_rth = in_rth

    def _update_wall_state(self, timestamp: pd.Timestamp, side: str, price: float) -> None:
        normalized_price = self._normalize_price(price)
        current_size = self._book.level_size(side, normalized_price)
        key = (side, normalized_price)
        tracker = self._walls.get(key)
        if tracker is None:
            if current_size <= 0:
                return
            tracker = WallState(
                price=normalized_price,
                side=side,
                first_seen=timestamp,
                last_update=timestamp,
                current_size=current_size,
                max_size=current_size,
                original_size=current_size,
                threshold_since=timestamp if current_size >= self.min_wall else None,
            )
            self._walls[key] = tracker
            return
        tracker.update(timestamp, current_size, self.min_wall)

    def _advance_market_state(self, timestamp: pd.Timestamp) -> None:
        best_bid = self._book.best_bid()
        best_ask = self._book.best_ask()
        if best_bid <= 0 or best_ask <= 0:
            self._finalize_expired(timestamp)
            return
        mid_price = (best_bid + best_ask) / 2.0
        self._update_price_window(timestamp, mid_price)
        self._finalize_expired(timestamp)
        self._detect_interactions(timestamp, mid_price, best_bid, best_ask)
        self._last_mid = mid_price
        self._last_mid_ts = timestamp

    def _update_price_window(self, timestamp: pd.Timestamp, mid_price: float) -> None:
        self._price_window.append((timestamp, mid_price))
        cutoff = timestamp - pd.Timedelta(seconds=max(self.lookforward_sec, 10))
        while self._price_window and self._price_window[0][0] < cutoff:
            self._price_window.popleft()

    def _detect_interactions(self, timestamp: pd.Timestamp, mid_price: float, best_bid: float, best_ask: float) -> None:
        band = self.interaction_ticks * self.tick_size
        seen_keys: set[tuple[str, float]] = set()
        base_tick = round(mid_price / self.tick_size)
        for offset in range(-self.interaction_ticks, self.interaction_ticks + 1):
            price = self._normalize_price((base_tick + offset) * self.tick_size)
            for side in (_SIDE_BID, _SIDE_ASK):
                key = (side, price)
                tracker = self._walls.get(key)
                if tracker is None:
                    continue
                seen_keys.add(key)
                if not tracker.qualified(timestamp, self.min_wall_duration_sec) or tracker.max_size < self.min_wall:
                    tracker.in_interaction = False
                    continue
                if tracker.interaction_cooldown_until is not None and timestamp < tracker.interaction_cooldown_until:
                    tracker.in_interaction = True
                    continue
                distance = abs(mid_price - tracker.price)
                if distance > band or tracker.current_size <= 0:
                    tracker.in_interaction = False
                    continue
                if tracker.in_interaction:
                    continue
                deadline = timestamp + pd.Timedelta(seconds=self.lookforward_sec)
                if deadline > _session_end(timestamp):
                    tracker.in_interaction = True
                    tracker.interaction_cooldown_until = _session_end(timestamp)
                    continue
                tracker.in_interaction = True
                tracker.interaction_cooldown_until = _session_end(timestamp)
                self._pending.append(
                    InteractionEvent(
                        timestamp=timestamp,
                        deadline_time=deadline,
                        session_date=str(timestamp.tz_convert("UTC").date()),
                        wall_price=tracker.price,
                        mid_price=mid_price,
                        best_bid=best_bid,
                        best_ask=best_ask,
                        wall_size=tracker.current_size,
                        wall_max_size=tracker.max_size,
                        wall_duration_sec=tracker.duration_sec(timestamp),
                        wall_side=1 if side == _SIDE_ASK else 0,
                        wall_refill_count=tracker.refill_count,
                        wall_modification_count=tracker.modification_count,
                        wall_cancellation_events=tracker.cancellation_events,
                        approach_speed=self._approach_speed(timestamp, tracker.price, side),
                        book_imbalance=self._book_imbalance(),
                        distance_from_wall=distance / self.tick_size,
                        spread=(best_ask - best_bid) / self.tick_size,
                        hour_of_day=int(timestamp.hour),
                        minute_of_hour=int(timestamp.minute),
                        cumulative_delta=self._cumulative_delta,
                        price_momentum_10s=self._price_momentum_10s(timestamp),
                        bounce_distance=self.bounce_ticks * self.tick_size,
                        break_distance=self.break_ticks * self.tick_size,
                    )
                )
        for key, tracker in self._walls.items():
            if key not in seen_keys:
                band_distance = abs(mid_price - tracker.price)
                if band_distance > band or tracker.current_size < self.min_wall:
                    tracker.in_interaction = False

    def _approach_speed(self, timestamp: pd.Timestamp, wall_price: float, side: str) -> float:
        if not self._price_window:
            return 0.0
        target_cutoff = timestamp - pd.Timedelta(seconds=10)
        reference_ts, reference_price = self._price_window[0]
        for ts, price in self._price_window:
            reference_ts, reference_price = ts, price
            if ts >= target_cutoff:
                break
        elapsed = max((timestamp - reference_ts).total_seconds(), 1e-9)
        current_mid = self._price_window[-1][1]
        if side == _SIDE_ASK:
            move_toward = current_mid - reference_price
        else:
            move_toward = reference_price - current_mid
        return (move_toward / self.tick_size) / elapsed

    def _price_momentum_10s(self, timestamp: pd.Timestamp) -> float:
        if not self._price_window:
            return 0.0
        target_cutoff = timestamp - pd.Timedelta(seconds=10)
        reference_price = self._price_window[0][1]
        for ts, price in self._price_window:
            reference_price = price
            if ts >= target_cutoff:
                break
        return (self._price_window[-1][1] - reference_price) / self.tick_size

    def _book_imbalance(self) -> float:
        _, bid_sizes, _, ask_sizes = self._book.top_levels(10)
        bid_volume = float(sum(bid_sizes))
        ask_volume = float(sum(ask_sizes))
        total = bid_volume + ask_volume
        if total <= 0:
            return 0.0
        return (bid_volume - ask_volume) / total

    def _finalize_expired(self, timestamp: pd.Timestamp, force: bool = False) -> None:
        remaining: list[InteractionEvent] = []
        for interaction in self._pending:
            if not force and interaction.deadline_time > timestamp:
                remaining.append(interaction)
                continue
            if force and timestamp < interaction.deadline_time:
                continue
            self._hydrate_interaction_outcome(interaction)
            interaction.label = interaction.resolve_label()
            self._rows.append(interaction.to_row())
        self._pending = remaining

    def _hydrate_interaction_outcome(self, interaction: InteractionEvent) -> None:
        max_mid = interaction.mid_price
        min_mid = interaction.mid_price
        for ts, mid_price in self._price_window:
            if ts < interaction.timestamp:
                continue
            if ts > interaction.deadline_time:
                break
            if mid_price > max_mid:
                max_mid = mid_price
            if mid_price < min_mid:
                min_mid = mid_price
        interaction.max_mid = max_mid
        interaction.min_mid = min_mid

    def _batch_prune(self) -> None:
        if self._last_ts is None:
            return
        cutoff = self._last_ts - pd.Timedelta(seconds=self.prune_stale_sec)
        stale_keys = [
            key
            for key, wall in self._walls.items()
            if wall.current_size <= 0 and wall.last_update < cutoff
        ]
        for key in stale_keys:
            self._walls.pop(key, None)
        self._finalize_expired(self._last_ts)
        log.info(
            "wall_interaction_labeler.progress records=%s active_walls=%s pending_interactions=%s rows=%s",
            self._records_processed,
            len(self._walls),
            len(self._pending),
            len(self._rows),
        )

    def _update_cumulative_delta(self, side: str, size: int) -> None:
        if side == _SIDE_ASK:
            self._cumulative_delta += size
        elif side == _SIDE_BID:
            self._cumulative_delta -= size

    def _timestamp_from_record(self, record: Any) -> pd.Timestamp:
        ts_ns = int(getattr(record, "ts_event", 0) or 0)
        if ts_ns <= 0:
            raise RuntimeError("Encountered MBO record without ts_event")
        return pd.to_datetime(ts_ns, unit="ns", utc=True)

    def _price_from_record(self, record: Any) -> float:
        raw_price = getattr(record, "price", 0) or 0
        if isinstance(raw_price, int):
            price = raw_price / 1e9
        else:
            price = float(raw_price)
            if price > 1_000_000:
                price /= 1e9
        return self._normalize_price(price)

    def _normalize_price(self, price: float) -> float:
        ticks = round(float(price) / self.tick_size)
        return round(ticks * self.tick_size, 10)

    @staticmethod
    def _decode_char(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, (bytes, bytearray)):
            return value.decode("ascii", errors="replace")
        if isinstance(value, int):
            return chr(value)
        return str(value)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Label NQ wall interactions from Databento MBO replay")
    parser.add_argument("--input", required=True, help="Path to Databento DBN/ZST MBO file")
    parser.add_argument("--output", required=True, help="Output parquet path")
    parser.add_argument("--min-wall", type=int, default=50, help="Minimum wall size in contracts")
    parser.add_argument("--tick-size", type=float, default=0.25, help="Instrument tick size")
    return parser


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    args = _build_arg_parser().parse_args()
    labeler = WallInteractionLabeler(min_wall=args.min_wall, tick_size=args.tick_size)
    labeler.run(args.input, args.output)
