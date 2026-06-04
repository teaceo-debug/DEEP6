from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any

import pandas as pd

try:
    import databento as db
except ImportError:  # pragma: no cover - runtime dependency guard
    db = None  # type: ignore[assignment]

from deep6.ml.depth_radar.episode import InteractionOutcome, SnapshotEvent, TouchEvent, WallEpisode, WallIntent, WallState
from deep6.ml.depth_radar.mbo_wall_engine import MBOWallEngine
from deep6v2.signals.engines.wall_intent import WallIntentDetector


INTENT_ORDER = [intent.value for intent in WallIntent]
FINAL_STATE_ORDER = [
    WallState.PULLED.value,
    WallState.CONSUMED.value,
    WallState.STALE.value,
    WallState.ESTABLISHED.value,
    WallState.EXHAUSTED.value,
]
TOUCH_OUTCOME_ORDER = [outcome.value for outcome in InteractionOutcome]
MODIFIER_ORDER = ["suppressor", "confirmer", "strong_confirmer", "reversal", "breakout"]
PROGRESS_EVERY = 1_000_000


class DepthRadarBacktestHarness:
    def __init__(
        self,
        *,
        input_path: str,
        output_dir: str,
        min_wall_size: int = 50,
        snapshot_interval: int = 5,
        tick_size: float = 0.25,
        touch_distance_ticks: int = 4,
        bounce_ticks: int = 8,
        break_ticks: int = 4,
        lookforward_sec: int = 30,
        stale_distance_ticks: int = 10,
        stale_timeout_sec: int = 15,
        reappear_timeout_sec: int = 2,
        with_signals: bool = False,
    ) -> None:
        self.input_path = Path(input_path).expanduser().resolve()
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.min_wall_size = int(min_wall_size)
        self.snapshot_interval = int(snapshot_interval)
        self.tick_size = float(tick_size)
        self.with_signals = bool(with_signals)
        self._engine = MBOWallEngine(
            min_wall_size=self.min_wall_size,
            tick_size=self.tick_size,
            snapshot_interval_sec=self.snapshot_interval,
            touch_distance_ticks=int(touch_distance_ticks),
            bounce_ticks=int(bounce_ticks),
            break_ticks=int(break_ticks),
            lookforward_sec=int(lookforward_sec),
            stale_distance_ticks=int(stale_distance_ticks),
            stale_timeout_sec=int(stale_timeout_sec),
            reappear_timeout_sec=int(reappear_timeout_sec),
        )
        self._detector = WallIntentDetector()
        self._completed: list[WallEpisode] = []
        self._event_count = 0
        self._active_snapshot_count = 0
        self._max_active_walls = 0
        self._session_dates: set[str] = set()
        self._first_timestamp: pd.Timestamp | None = None
        self._last_timestamp: pd.Timestamp | None = None
        self._next_active_snapshot_time: pd.Timestamp | None = None

    def run(self) -> int:
        if db is None:
            raise RuntimeError("databento is not installed. Install it with `pip install databento`.")
        if not self.input_path.exists():
            raise FileNotFoundError(f"Databento MBO file not found: {self.input_path}")

        started_at = time.perf_counter()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._replay_file()
        report = self._build_report(started_at)
        touch_rows = self._build_touch_analysis_rows()
        self._write_outputs(report, touch_rows)
        self._print_report(report)
        return 0

    def _replay_file(self) -> None:
        self._engine.reset()
        self._completed = []
        self._event_count = 0
        self._active_snapshot_count = 0
        self._max_active_walls = 0
        self._session_dates = set()
        self._first_timestamp = None
        self._last_timestamp = None
        self._next_active_snapshot_time = None

        store = db.DBNStore.from_file(str(self.input_path))
        for record in store:
            self._process_record(record)

        if self._engine.last_timestamp is not None:
            self._sample_active_walls(self._engine.last_timestamp, force=True)
            self._completed.extend(self._engine.flush_all())

    def _process_record(self, record: Any) -> None:
        action = self._decode_char(getattr(record, "action", None))
        if action is None:
            return
        timestamp = self._timestamp_from_record(record)
        self._event_count += 1
        self._first_timestamp = timestamp if self._first_timestamp is None else self._first_timestamp
        self._last_timestamp = timestamp
        self._session_dates.add(str(timestamp.tz_convert("UTC").date()))

        self._engine.process_event(
            action=action,
            side=self._decode_char(getattr(record, "side", "N")) or "N",
            order_id=int(getattr(record, "order_id", 0) or 0),
            price=self._price_from_record(record),
            size=int(getattr(record, "size", 0) or 0),
            timestamp=timestamp,
        )
        self._sample_active_walls(timestamp)
        self._completed.extend(self._engine.get_completed_episodes())

        if self._event_count % PROGRESS_EVERY == 0:
            print(
                f"[progress] {self._event_count:,} events processed, "
                f"{self._engine.active_count:,} active walls, {len(self._completed):,} completed episodes"
            )

    def _sample_active_walls(self, timestamp: pd.Timestamp, force: bool = False) -> None:
        if self._next_active_snapshot_time is None:
            self._next_active_snapshot_time = timestamp
        while force or (self._next_active_snapshot_time is not None and timestamp >= self._next_active_snapshot_time):
            active_walls = self._engine.get_active_walls()
            self._active_snapshot_count += 1
            self._max_active_walls = max(self._max_active_walls, len(active_walls))
            if force:
                break
            self._next_active_snapshot_time = self._next_active_snapshot_time + pd.Timedelta(seconds=self.snapshot_interval)

    def _build_report(self, started_at: float) -> dict[str, Any]:
        elapsed_wall = max(time.perf_counter() - started_at, 1e-9)
        episode_rows = [episode.to_parquet_rows()["episode"] for episode in self._completed]
        touch_rows = self._build_touch_analysis_rows()

        durations = [float(row.get("duration_sec", 0.0) or 0.0) for row in episode_rows]
        max_sizes = [float(row.get("max_wall_size", 0.0) or 0.0) for row in episode_rows]
        intent_counts = Counter(str(row.get("intent_label") or "UNKNOWN") for row in episode_rows)
        final_state_counts = Counter(str(row.get("final_state") or "UNKNOWN") for row in episode_rows)
        touch_outcome_counts = Counter(str(row.get("outcome") or "UNKNOWN") for row in touch_rows if row.get("outcome"))

        report: dict[str, Any] = {
            "file": self.input_path.name,
            "input_path": str(self.input_path),
            "output_dir": str(self.output_dir),
            "mbo_events": int(self._event_count),
            "replay_elapsed_sec": float(elapsed_wall),
            "events_per_sec": float(self._event_count / elapsed_wall) if elapsed_wall > 0 else 0.0,
            "first_timestamp": self._first_timestamp.isoformat() if self._first_timestamp is not None else None,
            "last_timestamp": self._last_timestamp.isoformat() if self._last_timestamp is not None else None,
            "trading_days": int(len(self._session_dates)),
            "active_wall_snapshot_count": int(self._active_snapshot_count),
            "max_active_walls": int(self._max_active_walls),
            "episode_statistics": {
                "total_episodes": int(len(episode_rows)),
                "by_intent": self._format_counter(intent_counts, INTENT_ORDER),
                "by_final_state": self._format_counter(final_state_counts, FINAL_STATE_ORDER),
                "avg_duration_sec": float(mean(durations)) if durations else 0.0,
                "median_duration_sec": float(median(durations)) if durations else 0.0,
                "max_duration_sec": float(max(durations, default=0.0)),
                "avg_max_size": float(mean(max_sizes)) if max_sizes else 0.0,
            },
            "touch_outcomes": {
                "total_touches": int(len(touch_rows)),
                "by_outcome": self._format_counter(touch_outcome_counts, TOUCH_OUTCOME_ORDER),
                "bounce_rate_by_intent": self._bounce_rate_by_intent(touch_rows),
            },
            "wall_intent_accuracy": self._build_rule_accuracy(episode_rows),
            "touch_analysis_rows": int(len(touch_rows)),
        }

        if self.with_signals:
            report["signal_modifier_evaluation"] = self._evaluate_signal_modifiers(touch_rows)

        return report

    def _build_rule_accuracy(self, episode_rows: list[dict[str, Any]]) -> dict[str, Any]:
        spoof_rows = [row for row in episode_rows if str(row.get("intent_label") or "") == WallIntent.SPOOF_LIKE.value]
        reserve_rows = [row for row in episode_rows if str(row.get("intent_label") or "") == WallIntent.RESERVE_REFRESH.value]
        passive_rows = [row for row in episode_rows if str(row.get("intent_label") or "") == WallIntent.PASSIVE_REAL.value]
        return {
            "spoof_like_pulled_before_test": self._ratio_payload(
                numerator=sum(
                    1
                    for row in spoof_rows
                    if str(row.get("final_state") or "") == WallState.PULLED.value and int(row.get("touch_count", 0) or 0) == 0
                ),
                denominator=len(spoof_rows),
                description="SPOOF_LIKE walls pulled before test",
            ),
            "reserve_refresh_refilled_2x": self._ratio_payload(
                numerator=sum(1 for row in reserve_rows if self._episode_max_feature(row.get("episode_id"), "refills_so_far") >= 2.0),
                denominator=len(reserve_rows),
                description="RESERVE_REFRESH walls refilled 2+x",
            ),
            "passive_real_survived_30s": self._ratio_payload(
                numerator=sum(1 for row in passive_rows if float(row.get("duration_sec", 0.0) or 0.0) >= 30.0),
                denominator=len(passive_rows),
                description="PASSIVE_REAL walls survived 30s+",
            ),
        }

    def _build_touch_analysis_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for episode in self._completed:
            for touch_index, touch in enumerate(episode.touches):
                snapshot = self._nearest_snapshot_for_touch(episode, touch)
                state_value = snapshot.state.value if snapshot is not None else (
                    episode.final_state.value if episode.final_state is not None else "UNKNOWN"
                )
                row: dict[str, Any] = {
                    "episode_id": episode.episode_id,
                    "touch_index": int(touch_index),
                    "session_date": episode.session_date,
                    "timestamp": touch.timestamp.isoformat(),
                    "resolution_time": touch.resolution_time.isoformat() if touch.resolution_time is not None else None,
                    "side": episode.side,
                    "price": float(touch.wall_price),
                    "mid_price": float(touch.mid_price),
                    "wall_size": int(touch.wall_size),
                    "intent": episode.intent_label.value if episode.intent_label is not None else None,
                    "state_at_touch": state_value,
                    "final_state": episode.final_state.value if episode.final_state is not None else None,
                    "outcome": touch.outcome.value if touch.outcome is not None else None,
                    "duration_sec": float((touch.resolution_time - touch.timestamp).total_seconds()) if touch.resolution_time is not None else None,
                }
                if self.with_signals:
                    modifier_eval = self._evaluate_touch_with_detector(episode, touch, state_value)
                    row.update(modifier_eval)
                rows.append(row)
        return rows

    def _evaluate_touch_with_detector(self, episode: WallEpisode, touch: TouchEvent, state_value: str) -> dict[str, Any]:
        wall_payload = {
            "price": float(touch.wall_price),
            "side": episode.side,
            "intent": episode.intent_label.value if episode.intent_label is not None else None,
            "state": state_value,
            "interaction": touch.outcome.value if touch.outcome is not None else None,
        }
        self._detector.update([wall_payload], mid_price=float(touch.mid_price), tick_size=self.tick_size)
        modifiers = self._detector.get_modifiers()
        modifier_types = [str(modifier.get("type") or "") for modifier in modifiers]
        reasons = [str(modifier.get("reason") or "") for modifier in modifiers]
        return {
            "modifier_count": int(len(modifiers)),
            "modifier_types": "|".join(modifier_types),
            "modifier_reasons": "|".join(reasons),
            "modifier_alignment": "|".join(
                self._modifier_alignment_label(modifier_type, episode, touch) for modifier_type in modifier_types
            ),
        }

    def _evaluate_signal_modifiers(self, touch_rows: list[dict[str, Any]]) -> dict[str, Any]:
        counts: dict[str, dict[str, int]] = {
            modifier_type: {"fired": 0, "correct": 0} for modifier_type in MODIFIER_ORDER
        }
        for row in touch_rows:
            modifier_types = [item for item in str(row.get("modifier_types") or "").split("|") if item]
            alignment_labels = [item for item in str(row.get("modifier_alignment") or "").split("|") if item]
            for modifier_type, alignment in zip(modifier_types, alignment_labels, strict=False):
                if modifier_type not in counts:
                    counts[modifier_type] = {"fired": 0, "correct": 0}
                counts[modifier_type]["fired"] += 1
                if alignment == "correct":
                    counts[modifier_type]["correct"] += 1
        return {
            modifier_type: self._ratio_payload(
                numerator=values["correct"],
                denominator=values["fired"],
                description=f"{modifier_type} modifier hit rate",
            )
            for modifier_type, values in counts.items()
        }

    def _modifier_alignment_label(self, modifier_type: str, episode: WallEpisode, touch: TouchEvent) -> str:
        outcome = touch.outcome.value if touch.outcome is not None else None
        final_state = episode.final_state.value if episode.final_state is not None else None
        if modifier_type == "suppressor":
            return "correct" if final_state == WallState.PULLED.value else "incorrect"
        if modifier_type in {"confirmer", "strong_confirmer", "reversal"}:
            return "correct" if outcome == InteractionOutcome.BOUNCE.value else "incorrect"
        if modifier_type == "breakout":
            return "correct" if outcome == InteractionOutcome.BREAK.value else "incorrect"
        return "unknown"

    def _nearest_snapshot_for_touch(self, episode: WallEpisode, touch: TouchEvent) -> SnapshotEvent | None:
        prior = [snapshot for snapshot in episode.snapshots if snapshot.timestamp <= touch.timestamp]
        if prior:
            return prior[-1]
        future = [snapshot for snapshot in episode.snapshots if snapshot.timestamp > touch.timestamp]
        if future:
            return future[0]
        return None

    def _episode_max_feature(self, episode_id: Any, feature_name: str) -> float:
        target = str(episode_id or "")
        if not target:
            return 0.0
        maxima: list[float] = []
        for episode in self._completed:
            if episode.episode_id != target:
                continue
            maxima.extend(float(snapshot.features.get(feature_name, 0.0) or 0.0) for snapshot in episode.snapshots)
            maxima.extend(float(touch.features.get(feature_name, 0.0) or 0.0) for touch in episode.touches)
            break
        return float(max(maxima, default=0.0))

    def _bounce_rate_by_intent(self, touch_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for intent in INTENT_ORDER:
            subset = [row for row in touch_rows if str(row.get("intent") or "") == intent]
            bounces = sum(1 for row in subset if str(row.get("outcome") or "") == InteractionOutcome.BOUNCE.value)
            result[intent] = self._ratio_payload(
                numerator=bounces,
                denominator=len(subset),
                description=f"BOUNCE rate at {intent} walls",
            )
        return result

    def _write_outputs(self, report: dict[str, Any], touch_rows: list[dict[str, Any]]) -> None:
        stats_path = self.output_dir / "episode_stats.json"
        csv_path = self.output_dir / "touch_analysis.csv"
        stats_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        pd.DataFrame(touch_rows).to_csv(csv_path, index=False)

    def _print_report(self, report: dict[str, Any]) -> None:
        print("\n=== DEPTH RADAR BACKTEST REPORT ===")
        print(f"File: {report['file']}")
        print(f"MBO Events: {report['mbo_events']:,}")
        print(f"Duration: {report['trading_days']} trading days")

        episode_stats = report["episode_statistics"]
        print("\n--- Episode Statistics ---")
        print(f"Total episodes:     {episode_stats['total_episodes']:,}")
        print("By intent:")
        self._print_distribution_block(episode_stats["by_intent"], INTENT_ORDER)
        print("\nBy final state:")
        self._print_distribution_block(episode_stats["by_final_state"], FINAL_STATE_ORDER)
        print(f"\nAvg duration:       {episode_stats['avg_duration_sec']:.1f}s")
        print(f"Median duration:    {episode_stats['median_duration_sec']:.1f}s")
        print(f"Max duration:       {episode_stats['max_duration_sec']:.1f}s")
        print(f"Avg max_size:       {episode_stats['avg_max_size']:.1f} contracts")

        touch_stats = report["touch_outcomes"]
        print("\n--- Touch Outcomes ---")
        print(f"Total touches:      {touch_stats['total_touches']:,}")
        self._print_distribution_block(touch_stats["by_outcome"], TOUCH_OUTCOME_ORDER, indent="  ")
        print()
        for intent in [WallIntent.PASSIVE_REAL.value, WallIntent.SPOOF_LIKE.value, WallIntent.RESERVE_REFRESH.value]:
            values = touch_stats["bounce_rate_by_intent"].get(intent, self._ratio_payload(0, 0, ""))
            print(f"{values['description']}:  {values['pct']:.1f}%")

        print("\n--- Wall Intent Accuracy (rule-based) ---")
        for key in [
            "spoof_like_pulled_before_test",
            "reserve_refresh_refilled_2x",
            "passive_real_survived_30s",
        ]:
            values = report["wall_intent_accuracy"][key]
            print(f"{values['description']}:  {values['pct']:.1f}%")

        if self.with_signals and "signal_modifier_evaluation" in report:
            print("\n--- Signal Modifier Evaluation ---")
            for modifier_type in MODIFIER_ORDER:
                values = report["signal_modifier_evaluation"].get(modifier_type)
                if values is None:
                    continue
                print(
                    f"{modifier_type}: {values['numerator']}/{values['denominator']} "
                    f"({values['pct']:.1f}%)"
                )

        print("\n--- Performance ---")
        print(f"Replay elapsed:     {report['replay_elapsed_sec']:.2f}s")
        print(f"Events/sec:         {report['events_per_sec']:,.0f}")
        print(f"Active snapshots:   {report['active_wall_snapshot_count']:,}")
        print(f"Max active walls:   {report['max_active_walls']:,}")
        print(f"Saved:              {self.output_dir / 'episode_stats.json'}")
        print(f"Saved:              {self.output_dir / 'touch_analysis.csv'}")

    @staticmethod
    def _format_counter(counter: Counter[str], ordered_labels: list[str]) -> dict[str, dict[str, Any]]:
        total = int(sum(counter.values()))
        payload: dict[str, dict[str, Any]] = {}
        seen = set(ordered_labels)
        for label in ordered_labels:
            count = int(counter.get(label, 0))
            payload[label] = {"count": count, "pct": (count / total * 100.0) if total else 0.0}
        for label, count in counter.items():
            if label in seen:
                continue
            count_int = int(count)
            payload[label] = {"count": count_int, "pct": (count_int / total * 100.0) if total else 0.0}
        return payload

    @staticmethod
    def _ratio_payload(numerator: int, denominator: int, description: str) -> dict[str, Any]:
        return {
            "description": description,
            "numerator": int(numerator),
            "denominator": int(denominator),
            "pct": (float(numerator) / float(denominator) * 100.0) if denominator else 0.0,
        }

    @staticmethod
    def _print_distribution_block(
        block: dict[str, dict[str, Any]],
        ordered_labels: list[str],
        *,
        indent: str = "  ",
    ) -> None:
        printed: set[str] = set()
        for label in ordered_labels:
            values = block.get(label)
            if values is None:
                continue
            printed.add(label)
            print(f"{indent}{label:<18} {values['count']:>7,} ({values['pct']:.1f}%)")
        for label, values in block.items():
            if label in printed:
                continue
            print(f"{indent}{label:<18} {values['count']:>7,} ({values['pct']:.1f}%)")

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


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay Databento MBO into MBOWallEngine and score wall quality")
    parser.add_argument("--input", required=True, help="Path to Databento DBN/ZST MBO file")
    parser.add_argument("--output-dir", required=True, help="Directory for episode_stats.json and touch_analysis.csv")
    parser.add_argument("--min-wall-size", type=int, default=50, help="Minimum wall size in contracts")
    parser.add_argument("--snapshot-interval", type=int, default=5, help="Snapshot cadence in seconds")
    parser.add_argument("--tick-size", type=float, default=0.25, help="Instrument tick size")
    parser.add_argument("--touch-distance-ticks", type=int, default=4, help="Touch band width in ticks")
    parser.add_argument("--bounce-ticks", type=int, default=8, help="Bounce threshold in ticks")
    parser.add_argument("--break-ticks", type=int, default=4, help="Break threshold in ticks")
    parser.add_argument("--lookforward-sec", type=int, default=30, help="Touch resolution horizon in seconds")
    parser.add_argument("--stale-distance-ticks", type=int, default=10, help="Distance from BBO/mid to mark stale")
    parser.add_argument("--stale-timeout-sec", type=int, default=15, help="Seconds a wall can stay stale before retirement")
    parser.add_argument("--reappear-timeout-sec", type=int, default=2, help="Seconds to wait before zero-size retirement")
    parser.add_argument(
        "--with-signals",
        action="store_true",
        help="Evaluate WallIntentDetector modifiers against realized touch outcomes",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    harness = DepthRadarBacktestHarness(
        input_path=args.input,
        output_dir=args.output_dir,
        min_wall_size=args.min_wall_size,
        snapshot_interval=args.snapshot_interval,
        tick_size=args.tick_size,
        touch_distance_ticks=args.touch_distance_ticks,
        bounce_ticks=args.bounce_ticks,
        break_ticks=args.break_ticks,
        lookforward_sec=args.lookforward_sec,
        stale_distance_ticks=args.stale_distance_ticks,
        stale_timeout_sec=args.stale_timeout_sec,
        reappear_timeout_sec=args.reappear_timeout_sec,
        with_signals=args.with_signals,
    )
    try:
        return harness.run()
    except Exception as exc:  # noqa: BLE001
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
