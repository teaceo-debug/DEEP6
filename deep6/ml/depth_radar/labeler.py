"""Retrospective wall labeling pipeline for historical Databento MBO data."""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import databento as db
except ImportError:  # pragma: no cover - handled at runtime
    db = None  # type: ignore[assignment]

from deep6.data.databento_live import (
    _ACTION_ADD,
    _ACTION_CANCEL,
    _ACTION_CLEAR,
    _ACTION_FILL,
    _ACTION_MODIFY,
    _ACTION_TRADE,
    _OrderBookState,
    _SIDE_ASK,
    _SIDE_BID,
)
from deep6.state.dom import DOMState


log = logging.getLogger(__name__)

_OUTPUT_COLUMNS = [
    "timestamp",
    "completion_time",
    "price",
    "side",
    "original_size",
    "max_size",
    "duration_sec",
    "modification_count",
    "cancellation_events",
    "refill_count",
    "price_crossed",
    "filled_volume",
    "label",
]


@dataclass
class WallTracker:
    """Tracks the lifecycle of a significant aggregated price level."""

    price: float
    side: str
    first_seen: pd.Timestamp
    last_update: pd.Timestamp
    original_size: int
    max_size: int
    current_size: int
    modification_count: int = 0
    cancellation_events: int = 0
    refill_count: int = 0
    price_crossed: bool = False
    price_cross_time: pd.Timestamp | None = None
    filled_volume: int = 0
    completion_time: pd.Timestamp | None = None
    _below_half: bool = field(default=False, init=False, repr=False)

    def update(self, timestamp: pd.Timestamp, new_size: int) -> None:
        """Update wall state from the latest aggregated size."""
        size = max(int(new_size), 0)
        previous = self.current_size

        if size != previous:
            self.modification_count += 1
        if previous > 0 and size == 0:
            self.cancellation_events += 1

        reference_max = max(self.max_size, previous)
        if reference_max > 0:
            if size < reference_max * 0.5:
                self._below_half = True
            elif self._below_half and size >= reference_max * 0.5 and size > previous:
                self.refill_count += 1
                self._below_half = False

        self.current_size = size
        if size > self.max_size:
            self.max_size = size
            self._below_half = False
        self.last_update = timestamp

    def mark_fill(self, timestamp: pd.Timestamp, fill_size: int, new_size: int) -> None:
        """Record resting liquidity being consumed at this level."""
        self.filled_volume += max(int(fill_size), 0)
        self.update(timestamp, new_size)

    def mark_price_cross(self, timestamp: pd.Timestamp) -> None:
        if not self.price_crossed:
            self.price_crossed = True
            self.price_cross_time = timestamp

    def complete(self, timestamp: pd.Timestamp) -> None:
        self.completion_time = timestamp

    @property
    def duration_sec(self) -> float:
        end = self.completion_time or self.last_update
        return max((end - self.first_seen).total_seconds(), 0.0)

    def label(self, average_wall_size: float | None = None) -> str:
        """Return the retrospective lifecycle label for this wall."""
        duration = self.duration_sec
        avg_size = max(float(average_wall_size or self.original_size or 1), 1.0)
        significant_fill = max(int(self.original_size * 0.25), 1)

        if duration <= 0.5 and self.max_size > 5.0 * avg_size and self.filled_volume == 0:
            return "SPOOF"
        if self.refill_count >= 2:
            return "ICEBERG"
        if (
            self.price_crossed
            and self.price_cross_time is not None
            and self.completion_time is not None
            and (self.completion_time - self.price_cross_time).total_seconds() <= 60.0
        ):
            return "STALE"
        if duration >= 30.0 and (self.filled_volume >= significant_fill or not self.price_crossed):
            return "GENUINE"
        if self.filled_volume >= max(int(self.max_size * 0.25), significant_fill):
            return "GENUINE"
        if self.price_crossed:
            return "STALE"
        return "GENUINE"


class WallLabeler:
    """Offline MBO replay pipeline that labels resting walls by lifecycle."""

    def __init__(self, min_wall_size: int = 50, min_duration_sec: int = 5, tick_size: float = 0.25) -> None:
        self.min_wall_size = int(min_wall_size)
        self.min_duration_sec = int(min_duration_sec)
        self.tick_size = float(tick_size)
        self._book = _OrderBookState()
        self._dom = DOMState()
        self._active_walls: dict[tuple[str, float], WallTracker] = {}
        self._completed_walls: list[WallTracker] = []
        self._last_timestamp: pd.Timestamp | None = None

    def process_mbo_file(self, input_path: str) -> pd.DataFrame:
        """Process a local Databento DBN file into labeled wall examples."""
        if db is None:
            raise RuntimeError(
                "databento is not installed. Install it with `pip install databento`."
            )

        path = Path(input_path)
        if not path.exists():
            raise FileNotFoundError(f"Databento MBO file not found: {path}")

        self._reset_runtime_state()

        store = db.DBNStore.from_file(str(path))
        for record in store:
            self._process_record(record)

        if self._last_timestamp is not None:
            self._flush_all(self._last_timestamp)

        return self._build_dataframe()

    def run(self, input_path: str, output_path: str, dry_run: bool = False) -> pd.DataFrame:
        """Run the pipeline and optionally persist the labeled dataset."""
        df = self.process_mbo_file(input_path)

        if dry_run:
            counts = df["label"].value_counts().to_dict() if not df.empty else {}
            log.info("wall_labeler.dry_run", rows=len(df), label_distribution=counts)
            print("Label distribution:")
            if not counts:
                print("  <no labeled walls>")
            else:
                for label, count in sorted(counts.items()):
                    print(f"  {label}: {count}")
            return df

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            df.to_parquet(output, index=False)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to write parquet output: {output}") from exc

        counts = df["label"].value_counts().to_dict() if not df.empty else {}
        log.info(
            "wall_labeler.completed",
            rows=len(df),
            output_path=str(output),
            label_distribution=counts,
        )
        print(f"Wrote {len(df)} labeled walls to {output}")
        return df

    def _reset_runtime_state(self) -> None:
        self._book.clear()
        self._dom = DOMState()
        self._active_walls.clear()
        self._completed_walls.clear()
        self._last_timestamp = None

    def _process_record(self, record: Any) -> None:
        action = self._decode_char(getattr(record, "action", None))
        if action is None:
            return

        timestamp = self._timestamp_from_record(record)
        self._last_timestamp = timestamp
        side_code = self._decode_char(getattr(record, "side", "N")) or "N"

        if action == _ACTION_CLEAR:
            self._book.clear()
            self._refresh_dom(timestamp)
            self._mark_crossed_walls(timestamp)
            self._prune_inactive(timestamp, force=True)
            return

        price = self._price_from_record(record)
        size = int(getattr(record, "size", 0) or 0)
        order_id = int(getattr(record, "order_id", 0) or 0)

        if action in (_ACTION_ADD, _ACTION_MODIFY, _ACTION_CANCEL, _ACTION_FILL, _ACTION_TRADE):
            self._book.apply(order_id, price, size, side_code, action)
            self._refresh_dom(timestamp)

        if side_code in (_SIDE_BID, _SIDE_ASK) and action in (
            _ACTION_ADD,
            _ACTION_MODIFY,
            _ACTION_CANCEL,
            _ACTION_FILL,
            _ACTION_TRADE,
        ):
            side = "bid" if side_code == _SIDE_BID else "ask"
            level_price = self._normalize_price(price)
            current_size = self._current_level_size(side_code, level_price)
            tracker = self._active_walls.get((side, level_price))

            if tracker is None and current_size >= self.min_wall_size:
                tracker = WallTracker(
                    price=level_price,
                    side=side,
                    first_seen=timestamp,
                    last_update=timestamp,
                    original_size=current_size,
                    max_size=current_size,
                    current_size=current_size,
                )
                self._active_walls[(side, level_price)] = tracker
            elif tracker is not None:
                if action in (_ACTION_FILL, _ACTION_TRADE):
                    tracker.mark_fill(timestamp, size, current_size)
                else:
                    tracker.update(timestamp, current_size)

        self._mark_crossed_walls(timestamp)
        self._prune_inactive(timestamp)

    def _refresh_dom(self, timestamp: pd.Timestamp) -> None:
        bid_prices, bid_sizes, ask_prices, ask_sizes = self._book.top_levels()
        self._dom.update(bid_prices, bid_sizes, ask_prices, ask_sizes, ts=timestamp.timestamp())

    def _mark_crossed_walls(self, timestamp: pd.Timestamp) -> None:
        best_bid, _ = self._dom.best_bid()
        best_ask, _ = self._dom.best_ask()

        for tracker in self._active_walls.values():
            if tracker.price_crossed:
                continue
            if tracker.side == "bid" and best_bid > 0 and best_bid < tracker.price:
                tracker.mark_price_cross(timestamp)
            elif tracker.side == "ask" and best_ask > 0 and best_ask > tracker.price:
                tracker.mark_price_cross(timestamp)

    def _prune_inactive(self, timestamp: pd.Timestamp, force: bool = False) -> None:
        completed_keys: list[tuple[str, float]] = []
        for key, tracker in self._active_walls.items():
            if force:
                tracker.complete(timestamp)
                completed_keys.append(key)
                continue

            if tracker.current_size > 0:
                continue

            inactive_for = (timestamp - tracker.last_update).total_seconds()
            if inactive_for >= self.min_duration_sec:
                tracker.complete(timestamp)
                completed_keys.append(key)

        for key in completed_keys:
            self._completed_walls.append(self._active_walls.pop(key))

    def _flush_all(self, timestamp: pd.Timestamp) -> None:
        self._prune_inactive(timestamp, force=True)

    def _build_dataframe(self) -> pd.DataFrame:
        if not self._completed_walls:
            return pd.DataFrame(columns=_OUTPUT_COLUMNS)

        average_wall_size = sum(w.original_size for w in self._completed_walls) / len(self._completed_walls)
        rows = []
        for wall in self._completed_walls:
            completion_time = wall.completion_time or wall.last_update
            rows.append(
                {
                    "timestamp": wall.first_seen,
                    "completion_time": completion_time,
                    "price": wall.price,
                    "side": wall.side,
                    "original_size": wall.original_size,
                    "max_size": wall.max_size,
                    "duration_sec": wall.duration_sec,
                    "modification_count": wall.modification_count,
                    "cancellation_events": wall.cancellation_events,
                    "refill_count": wall.refill_count,
                    "price_crossed": wall.price_crossed,
                    "filled_volume": wall.filled_volume,
                    "label": wall.label(average_wall_size),
                }
            )

        return pd.DataFrame(rows, columns=_OUTPUT_COLUMNS)

    def _current_level_size(self, side_code: str, price: float) -> int:
        if side_code == _SIDE_BID:
            return int(self._book.bid_levels.get(price, 0))
        return int(self._book.ask_levels.get(price, 0))

    def _timestamp_from_record(self, record: Any) -> pd.Timestamp:
        ts_ns = int(getattr(record, "ts_event", 0) or 0)
        if ts_ns <= 0:
            raise RuntimeError("Encountered MBO record without a valid ts_event timestamp")
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
        if self.tick_size <= 0:
            return round(float(price), 10)
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
    parser = argparse.ArgumentParser(description="Label DOM walls from MBO replay")
    parser.add_argument("--input", required=True, help="Path to Databento MBO file")
    parser.add_argument(
        "--output",
        default="labeled_walls.parquet",
        help="Output parquet path",
    )
    parser.add_argument("--min-size", type=int, default=50, help="Min wall size (contracts)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report distribution only",
    )
    return parser


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    args = _build_arg_parser().parse_args()
    labeler = WallLabeler(min_wall_size=args.min_size)
    labeler.run(args.input, args.output, dry_run=args.dry_run)
