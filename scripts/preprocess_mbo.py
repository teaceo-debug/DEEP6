from __future__ import annotations

import os
import sys
# Ensure project root is on sys.path so deep6.* imports work when running as a script
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import argparse
import math
import pickle
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import databento as db
from tqdm import tqdm

from deep6.backtest.mbo_adapter import DATABENTO_PRICE_SCALE
from deep6.engines.volume_profile import SessionProfile
from deep6.state.footprint import FootprintBar


ET = ZoneInfo("America/New_York")
TRADE_ACTIONS = {"T", "F"}


class NullWallDetector:
    def process_event(
        self,
        price: float,
        size: int,
        side: str,
        action: str,
        order_id: int | str,
        ts_ns: int,
    ) -> None:
        return None

    def get_walls_at_bar_close(self, bar_ts_ns: int) -> list[Any]:
        return []


def _load_wall_detector(min_size: int) -> tuple[Any, str | None]:
    try:
        from deep6.backtest.wall_detector import WallDetector  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on parallel task state
        return NullWallDetector(), f"WallDetector unavailable: {exc}"

    for factory in (
        lambda: WallDetector(min_size=min_size),
        lambda: WallDetector(wall_min_size=min_size),
        lambda: WallDetector(),
    ):
        try:
            return factory(), None
        except TypeError:
            continue
        except Exception as exc:  # pragma: no cover - runtime dependency behavior
            return NullWallDetector(), f"WallDetector init failed, rule-based fallback only: {exc}"

    return NullWallDetector(), "WallDetector signature mismatch, fallback enabled"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _ns_to_et(ts_ns: int) -> datetime:
    return datetime.fromtimestamp(ts_ns / 1e9, tz=UTC).astimezone(ET)


def _normalize_action(value: Any) -> str:
    return getattr(value, "value", value)


def _normalize_side(value: Any) -> str:
    return getattr(value, "value", value)


def _scaled_price(raw_price: Any) -> float:
    try:
        price = float(raw_price) / DATABENTO_PRICE_SCALE
    except Exception:
        return 0.0
    return price if math.isfinite(price) else 0.0


def _aggressor_to_int(side: str) -> int:
    if side == "A":
        return 1
    if side == "B":
        return 2
    return 0


def _event_session_date(record: Any) -> date:
    return _ns_to_et(int(record.ts_event)).date()


def _in_requested_range(session_date: date, start_date: date | None, end_date: date | None) -> bool:
    if start_date and session_date < start_date:
        return False
    if end_date and session_date > end_date:
        return False
    return True


def _is_trading_day(session_date: date) -> bool:
    return session_date.weekday() < 5


def _session_output_path(output_dir: Path, session_date: date) -> Path:
    return output_dir / f"session_{session_date.isoformat()}.pkl"


def _count_events(dbn_path: Path, start_date: date | None, end_date: date | None) -> int:
    store = db.DBNStore.from_file(str(dbn_path))
    count = 0
    for record in store:
        session_date = _event_session_date(record)
        if not _is_trading_day(session_date):
            continue
        if not _in_requested_range(session_date, start_date, end_date):
            continue
        count += 1
    return count


def _finalize_footprint_bar(bar: FootprintBar, bar_end_ns: int, prior_cvd: int) -> FootprintBar:
    bar.timestamp = bar_end_ns / 1e9
    return bar.finalize(prior_cvd)


@dataclass
class SessionAccumulator:
    session_date: date
    wall_detector: Any
    bar_seconds: int
    started_at: float = field(default_factory=time.perf_counter)
    footprint_bars: list[FootprintBar] = field(default_factory=list)
    wall_events: list[Any] = field(default_factory=list)
    session_profile: SessionProfile = field(default_factory=SessionProfile)
    current_bar: FootprintBar = field(default_factory=FootprintBar)
    current_bucket: int | None = None
    prior_cvd: int = 0
    trade_tick_count: int = 0
    mbo_event_count: int = 0

    @property
    def bar_ns(self) -> int:
        return self.bar_seconds * 1_000_000_000

    def process_record(self, record: Any) -> None:
        ts_ns = int(record.ts_event)
        action = _normalize_action(record.action)
        side = _normalize_side(record.side)
        price = _scaled_price(record.price)
        size = int(record.size)
        order_id = getattr(record, "order_id", 0)

        self.mbo_event_count += 1
        self.wall_detector.process_event(price, size, side, action, order_id, ts_ns)

        if action not in TRADE_ACTIONS:
            return

        bucket = ts_ns // self.bar_ns
        if self.current_bucket is None:
            self.current_bucket = bucket
        elif bucket != self.current_bucket:
            self._close_current_bar()
            self.current_bar = FootprintBar()
            self.current_bucket = bucket

        self.current_bar.add_trade(price, size, _aggressor_to_int(side))
        self.trade_tick_count += 1

    def flush(self) -> None:
        self._close_current_bar()

    def _close_current_bar(self) -> None:
        if self.current_bucket is None or self.current_bar.total_vol <= 0:
            return

        bar_end_ns = (self.current_bucket + 1) * self.bar_ns
        closed_bar = _finalize_footprint_bar(self.current_bar, bar_end_ns, self.prior_cvd)
        self.prior_cvd = closed_bar.cvd
        self.footprint_bars.append(closed_bar)
        self.session_profile.add_bar(closed_bar)
        self.session_profile.detect_zones(closed_bar.close)
        self.wall_events.extend(self.wall_detector.get_walls_at_bar_close(bar_end_ns))
        self.current_bar = FootprintBar()

    def to_payload(self, input_file: str, wall_min_size: int, processing_time_sec: float) -> dict[str, Any]:
        vp_zones = self.session_profile.get_active_zones()
        return {
            "date": self.session_date.isoformat(),
            "footprint_bars": self.footprint_bars,
            "wall_events": self.wall_events,
            "vp_zones": vp_zones,
            "metadata": {
                "bar_count": len(self.footprint_bars),
                "wall_count": len(self.wall_events),
                "zone_count": len(vp_zones),
                "tick_count": self.trade_tick_count,
                "event_count": self.mbo_event_count,
                "processing_time_sec": round(processing_time_sec, 3),
                "input_file": input_file,
                "bar_seconds": self.bar_seconds,
                "wall_min_size": wall_min_size,
            },
        }


def _write_session_file(path: Path, payload: dict[str, Any]) -> None:
    with path.open("wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)


def run(
    input_path: Path,
    output_dir: Path,
    start_date: date | None,
    end_date: date | None,
    wall_min_size: int,
    bar_seconds: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    total_events = _count_events(input_path, start_date, end_date)
    store = db.DBNStore.from_file(str(input_path))
    progress = tqdm(total=total_events, desc="Processing MBO events")

    current: SessionAccumulator | None = None
    skipped_session: date | None = None
    totals = {
        "sessions": 0,
        "bars": 0,
        "walls": 0,
        "zones": 0,
    }

    def finalize_current() -> None:
        nonlocal current
        if current is None:
            return
        session_path = _session_output_path(output_dir, current.session_date)
        try:
            current.flush()
            payload = current.to_payload(
                input_file=input_path.name,
                wall_min_size=wall_min_size,
                processing_time_sec=time.perf_counter() - current.started_at,
            )
            _write_session_file(session_path, payload)
            totals["sessions"] += 1
            totals["bars"] += payload["metadata"]["bar_count"]
            totals["walls"] += payload["metadata"]["wall_count"]
            totals["zones"] += payload["metadata"]["zone_count"]
            print(
                f"Saved {session_path.name} "
                f"(bars={payload['metadata']['bar_count']}, walls={payload['metadata']['wall_count']}, zones={payload['metadata']['zone_count']})"
            )
        except Exception as exc:
            print(f"[error] Failed session {current.session_date.isoformat()}: {exc}")
        finally:
            current = None

    for record in store:
        session_date = _event_session_date(record)
        if not _is_trading_day(session_date):
            continue
        if not _in_requested_range(session_date, start_date, end_date):
            continue

        progress.update(1)

        if skipped_session == session_date:
            continue

        if current is None or current.session_date != session_date:
            finalize_current()
            existing_path = _session_output_path(output_dir, session_date)
            if existing_path.exists():
                print(f"Skipping {existing_path.stem} (already exists)")
                skipped_session = session_date
                continue
            detector, warning = _load_wall_detector(wall_min_size)
            if warning:
                print(f"[warn] {warning}")
            current = SessionAccumulator(
                session_date=session_date,
                wall_detector=detector,
                bar_seconds=bar_seconds,
            )

        current.process_record(record)

    finalize_current()
    progress.close()

    elapsed = time.perf_counter() - t0
    print(
        "Summary: "
        f"sessions={totals['sessions']} "
        f"bars={totals['bars']} "
        f"walls={totals['walls']} "
        f"zones={totals['zones']} "
        f"processing_time_sec={elapsed:.2f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-process MBO data into session files")
    parser.add_argument("--input", required=True, help="Path to .dbn.zst file")
    parser.add_argument("--output-dir", required=True, help="Output directory for session files")
    parser.add_argument("--start-date", help="Start date YYYY-MM-DD (optional)")
    parser.add_argument("--end-date", help="End date YYYY-MM-DD (optional)")
    parser.add_argument("--wall-min-size", type=int, default=50, help="Wall minimum size")
    parser.add_argument("--bar-seconds", type=int, default=60, help="Bar duration in seconds")
    args = parser.parse_args()

    run(
        input_path=Path(args.input),
        output_dir=Path(args.output_dir),
        start_date=_parse_date(args.start_date),
        end_date=_parse_date(args.end_date),
        wall_min_size=args.wall_min_size,
        bar_seconds=args.bar_seconds,
    )


if __name__ == "__main__":
    main()
