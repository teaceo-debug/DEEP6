"""Replay Databento MBO sessions into causal DepthRadar wall episodes."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import databento as db
except ImportError:  # pragma: no cover - runtime dependency guard
    db = None  # type: ignore[assignment]

from deep6.ml.depth_radar.episode import WallEpisode
from deep6.ml.depth_radar.mbo_wall_engine import MBOWallEngine


log = logging.getLogger(__name__)


class EpisodeLabeler:
    """Thin offline wrapper around MBOWallEngine file replay + parquet output."""

    def __init__(
        self,
        min_wall_size: int = 50,
        tick_size: float = 0.25,
        snapshot_interval_sec: int = 2,
        touch_distance_ticks: int = 4,
        bounce_ticks: int = 8,
        break_ticks: int = 4,
        lookforward_sec: int = 30,
        stale_distance_ticks: int = 10,
        stale_timeout_sec: int = 15,
        reappear_timeout_sec: int = 2,
    ) -> None:
        self.min_wall_size = int(min_wall_size)
        self.tick_size = float(tick_size)
        self.snapshot_interval_sec = int(snapshot_interval_sec)
        self.touch_distance_ticks = int(touch_distance_ticks)
        self.bounce_ticks = int(bounce_ticks)
        self.break_ticks = int(break_ticks)
        self.lookforward_sec = int(lookforward_sec)
        self.stale_distance_ticks = int(stale_distance_ticks)
        self.stale_timeout_sec = int(stale_timeout_sec)
        self.reappear_timeout_sec = int(reappear_timeout_sec)

        self._engine = MBOWallEngine(
            min_wall_size=self.min_wall_size,
            tick_size=self.tick_size,
            snapshot_interval_sec=self.snapshot_interval_sec,
            touch_distance_ticks=self.touch_distance_ticks,
            bounce_ticks=self.bounce_ticks,
            break_ticks=self.break_ticks,
            lookforward_sec=self.lookforward_sec,
            stale_distance_ticks=self.stale_distance_ticks,
            stale_timeout_sec=self.stale_timeout_sec,
            reappear_timeout_sec=self.reappear_timeout_sec,
        )
        self._completed: list[WallEpisode] = []

    def process_mbo_file(self, input_path: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        if db is None:
            raise RuntimeError("databento is not installed. Install it with `pip install databento`.")
        path = Path(input_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Databento MBO file not found: {path}")

        self._engine.reset()
        self._completed = []
        store = db.DBNStore.from_file(str(path))
        for record in store:
            self._process_record(record)

        if self._engine.last_timestamp is not None:
            self._completed.extend(self._engine.flush_all())

        return self._build_frames()

    def run(self, input_path: str, output_dir: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        episodes, snapshots, touches = self.process_mbo_file(input_path)
        output = Path(output_dir).expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)
        episodes.to_parquet(output / "episodes.parquet", index=False)
        snapshots.to_parquet(output / "snapshots.parquet", index=False)
        touches.to_parquet(output / "touches.parquet", index=False)
        log.info(
            "episode_labeler.completed episodes=%s snapshots=%s touches=%s output_dir=%s",
            len(episodes),
            len(snapshots),
            len(touches),
            output,
        )
        print(f"Wrote {len(episodes)} episodes, {len(snapshots)} snapshots, {len(touches)} touches to {output}")
        return episodes, snapshots, touches

    def _process_record(self, record: Any) -> None:
        action = self._decode_char(getattr(record, "action", None))
        if action is None:
            return
        self._engine.process_event(
            action=action,
            side=self._decode_char(getattr(record, "side", "N")) or "N",
            order_id=int(getattr(record, "order_id", 0) or 0),
            price=self._price_from_record(record),
            size=int(getattr(record, "size", 0) or 0),
            timestamp=self._timestamp_from_record(record),
        )
        self._completed.extend(self._engine.get_completed_episodes())

    def _build_frames(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        episode_rows: list[dict[str, Any]] = []
        snapshot_rows: list[dict[str, Any]] = []
        touch_rows: list[dict[str, Any]] = []
        for episode in self._completed:
            rows = episode.to_parquet_rows()
            episode_rows.append(rows["episode"])
            snapshot_rows.extend(rows["snapshots"])
            touch_rows.extend(rows["touches"])
        episodes = pd.DataFrame(episode_rows)
        snapshots = pd.DataFrame(snapshot_rows)
        touches = pd.DataFrame(touch_rows)
        return episodes, snapshots, touches

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
    parser = argparse.ArgumentParser(description="Build causal DepthRadar wall episodes from Databento MBO replay")
    parser.add_argument("--input", required=True, help="Path to Databento DBN/ZST MBO file")
    parser.add_argument("--output-dir", required=True, help="Output directory for parquet files")
    parser.add_argument("--min-wall-size", type=int, default=50, help="Minimum wall size in contracts")
    parser.add_argument("--snapshot-interval-sec", type=int, default=2, help="Snapshot cadence in seconds")
    return parser


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    args = _build_arg_parser().parse_args()
    labeler = EpisodeLabeler(
        min_wall_size=args.min_wall_size,
        snapshot_interval_sec=args.snapshot_interval_sec,
    )
    labeler.run(args.input, args.output_dir)


__all__ = ["EpisodeLabeler"]
