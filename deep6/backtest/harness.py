"""CLI harness for StrategyConfig evaluation on pre-processed sessions."""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from deep6.backtest.param_bounds import PARAM_BOUNDS, validate_config
from deep6.backtest.strategy_config import (
    ApproachDirection,
    BracketExit,
    LevelExit,
    LevelTarget,
    StrategyConfig,
    TimeExit,
    TimingFilter,
)
from deep6.engines.volume_profile import ZoneState, ZoneType

ET = ZoneInfo("America/New_York")
TICK_SIZE = 0.25
TICK_VALUE = 5.0
ROUND_TURN_COMMISSION = 4.12
ROUND_TURN_SLIPPAGE = 5.0
DEFAULT_IS_RATIO = 0.68
DEFAULT_APPROACH_TICKS = int(PARAM_BOUNDS["level_approach_ticks"].default)
PERFECT_METRIC = 999.0


@dataclass(slots=True)
class Trade:
    direction: str
    entry_price: float
    exit_price: float = 0.0
    entry_time: int = 0
    exit_time: int = 0
    exit_reason: str = ""
    bars_held: int = 0
    pnl: float = 0.0
    entry_bar: int = 0
    config_hash: str = ""
    split: str = "is"
    date: str = ""


def load_strategy_config(path: str | Path) -> StrategyConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    config = StrategyConfig.model_validate(payload)
    errors = validate_config(config)
    if errors:
        raise ValueError("; ".join(errors))
    return config


def list_session_files(data_dir: str | Path) -> list[Path]:
    base = Path(data_dir)
    if not base.exists() or not base.is_dir():
        return []
    return sorted(base.glob("session_*.pkl"), key=lambda path: path.stem)


def load_session(path: str | Path) -> dict[str, Any]:
    with Path(path).open("rb") as handle:
        payload = pickle.load(handle)
    if not isinstance(payload, dict):
        raise TypeError(f"Session payload must be dict, got {type(payload).__name__}")
    return payload


def split_session_files(session_files: list[Path], is_ratio: float) -> tuple[list[Path], list[Path]]:
    if not session_files:
        return [], []
    if len(session_files) == 1:
        return session_files[:], []
    split_index = int(len(session_files) * is_ratio)
    split_index = max(1, min(len(session_files) - 1, split_index))
    return session_files[:split_index], session_files[split_index:]


def evaluate_session(config: StrategyConfig, session: dict[str, Any], *, split: str = "is") -> list[Trade]:
    bars = list(session.get("footprint_bars") or [])
    walls = list(session.get("wall_events") or [])
    zones = list(session.get("vp_zones") or [])
    session_date = str(session.get("date") or "")

    if not bars:
        return []

    trades: list[Trade] = []
    open_trade: Trade | None = None
    session_vpoc = compute_session_vpoc(bars)

    for index, bar in enumerate(bars):
        bar_time = get_bar_timestamp(bar)
        bar_walls = [wall for wall in walls if abs(get_wall_timestamp(wall) - bar_time) <= 60.0]

        if open_trade is not None:
            exit_result = check_exits(open_trade, bar, index, config, zones)
            if exit_result is not None:
                open_trade.exit_price = float(exit_result["price"])
                open_trade.exit_time = to_ns_epoch(bar_time)
                open_trade.exit_reason = str(exit_result["reason"])
                open_trade.bars_held = index - open_trade.entry_bar
                open_trade.pnl = compute_pnl(open_trade)
                trades.append(open_trade)
                open_trade = None

        candidate = find_entry_candidate(bar, bar_walls, zones, config, session_vpoc=session_vpoc)
        if open_trade is None and candidate is not None:
            open_trade = Trade(
                direction=get_entry_direction(bar, bar_walls, zones, config, candidate=candidate),
                entry_price=float(get_attr(bar, "close", 0.0)),
                entry_time=to_ns_epoch(bar_time),
                entry_bar=index,
                config_hash=config.config_hash(),
                split=split,
                date=session_date,
            )

    if open_trade is not None:
        last_bar = bars[-1]
        last_time = get_bar_timestamp(last_bar)
        open_trade.exit_price = float(get_attr(last_bar, "close", open_trade.entry_price))
        open_trade.exit_time = to_ns_epoch(last_time)
        open_trade.exit_reason = "session_end"
        open_trade.bars_held = len(bars) - open_trade.entry_bar
        open_trade.pnl = compute_pnl(open_trade)
        trades.append(open_trade)

    return trades


def check_entry(
    bar: Any,
    bar_walls: list[Any],
    zones: list[Any],
    config: StrategyConfig,
    *,
    session_vpoc: float | None,
) -> bool:
    return find_entry_candidate(bar, bar_walls, zones, config, session_vpoc=session_vpoc) is not None


def find_entry_candidate(
    bar: Any,
    bar_walls: list[Any],
    zones: list[Any],
    config: StrategyConfig,
    *,
    session_vpoc: float | None,
) -> dict[str, Any] | None:
    if not passes_timing_filter(get_bar_timestamp(bar), config.timing_filter):
        return None

    close_price = float(get_attr(bar, "close", 0.0))
    approach_ticks = get_approach_ticks(config)
    candidates: list[dict[str, Any]] = []

    if config.level_target in (LevelTarget.LVN, LevelTarget.HVN):
        target_type = ZoneType[config.level_target.value]
        for zone in zones:
            if not is_zone_active(zone):
                continue
            if get_attr(zone, "zone_type") != target_type:
                continue
            price = zone_mid_price(zone)
            if not within_approach(close_price, price, approach_ticks):
                continue
            if not matches_approach_direction(close_price, price, config.approach_direction):
                continue
            candidates.append(
                {
                    "price": price,
                    "distance": tick_distance(close_price, price),
                    "direction_hint": "LONG" if int(get_attr(zone, "direction", 0)) >= 0 else "SHORT",
                }
            )
    elif config.level_target is LevelTarget.VPOC and session_vpoc is not None:
        if within_approach(close_price, session_vpoc, approach_ticks) and matches_approach_direction(
            close_price,
            session_vpoc,
            config.approach_direction,
        ):
            candidates.append(
                {
                    "price": session_vpoc,
                    "distance": tick_distance(close_price, session_vpoc),
                    "direction_hint": infer_direction_from_relative_position(close_price, session_vpoc),
                }
            )
    else:
        for wall in bar_walls:
            if not matches_wall_target(wall, config.level_target):
                continue
            price = float(get_attr(wall, "price", 0.0))
            if not within_approach(close_price, price, approach_ticks):
                continue
            if not matches_approach_direction(close_price, price, config.approach_direction):
                continue
            candidates.append(
                {
                    "price": price,
                    "distance": tick_distance(close_price, price),
                    "direction_hint": "LONG" if str(get_attr(wall, "side", "")).upper() == "BID" else "SHORT",
                }
            )

    if not candidates:
        return None
    return min(candidates, key=lambda candidate: candidate["distance"])


def get_entry_direction(
    bar: Any,
    bar_walls: list[Any],
    zones: list[Any],
    config: StrategyConfig,
    *,
    candidate: dict[str, Any] | None = None,
) -> str:
    chosen = candidate
    if chosen is None:
        chosen = find_entry_candidate(bar, bar_walls, zones, config, session_vpoc=compute_session_vpoc([bar]))
    if chosen is None:
        return "LONG"
    return str(chosen.get("direction_hint") or "LONG")


def check_exits(open_trade: Trade, bar: Any, bar_index: int, config: StrategyConfig, zones: list[Any]) -> dict[str, Any] | None:
    close_price = float(get_attr(bar, "close", 0.0))

    bracket_result = check_bracket_exit(open_trade, close_price, config.bracket_exit)
    if bracket_result is not None:
        return bracket_result

    level_result = check_level_exit(open_trade, close_price, config.level_exit, zones)
    if level_result is not None:
        return level_result

    bars_held = bar_index - open_trade.entry_bar
    time_result = check_time_exit(close_price, bars_held, config.time_exit)
    if time_result is not None:
        return time_result

    return None


def check_bracket_exit(trade: Trade, close_price: float, bracket_exit: BracketExit | None) -> dict[str, Any] | None:
    if bracket_exit is None:
        return None
    stop_distance = float(bracket_exit.stop_ticks) * TICK_SIZE
    target_distance = float(bracket_exit.target_ticks) * TICK_SIZE

    if trade.direction == "LONG":
        if close_price >= trade.entry_price + target_distance:
            return {"price": close_price, "reason": "target"}
        if close_price <= trade.entry_price - stop_distance:
            return {"price": close_price, "reason": "stop"}
        return None

    if close_price <= trade.entry_price - target_distance:
        return {"price": close_price, "reason": "target"}
    if close_price >= trade.entry_price + stop_distance:
        return {"price": close_price, "reason": "stop"}
    return None


def check_level_exit(
    trade: Trade,
    close_price: float,
    level_exit: LevelExit | None,
    zones: list[Any],
) -> dict[str, Any] | None:
    if level_exit is None or not level_exit.exit_at_next_zone:
        return None
    next_zone = find_next_zone(trade, zones)
    if next_zone is None:
        return None

    if trade.direction == "LONG" and close_price >= float(next_zone["trigger_price"]):
        return {"price": close_price, "reason": "level_exit"}
    if trade.direction == "SHORT" and close_price <= float(next_zone["trigger_price"]):
        return {"price": close_price, "reason": "level_exit"}
    return None


def check_time_exit(close_price: float, bars_held: int, time_exit: TimeExit | None) -> dict[str, Any] | None:
    if time_exit is None:
        return None
    if bars_held >= int(time_exit.max_bars_in_trade):
        return {"price": close_price, "reason": "max_bars"}
    return None


def compute_pnl(trade: Trade) -> float:
    if trade.direction == "LONG":
        gross = ((trade.exit_price - trade.entry_price) / TICK_SIZE) * TICK_VALUE
    else:
        gross = ((trade.entry_price - trade.exit_price) / TICK_SIZE) * TICK_VALUE
    return round(gross - ROUND_TURN_COMMISSION - ROUND_TURN_SLIPPAGE, 2)


def compute_metrics(trades: list[Trade]) -> dict[str, float | int]:
    if not trades:
        return {
            "win_rate": 0.0,
            "avg_rr": 0.0,
            "profit_factor": 0.0,
            "total_pnl": 0.0,
            "trade_count": 0,
            "max_drawdown": 0.0,
        }

    pnls = [float(trade.pnl) for trade in trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    avg_win = gross_profit / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0

    running = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for pnl in pnls:
        running += pnl
        peak = max(peak, running)
        max_drawdown = max(max_drawdown, peak - running)

    return {
        "win_rate": round(len(wins) / len(trades), 4),
        "avg_rr": round(ratio_or_perfect(avg_win, avg_loss), 4),
        "profit_factor": round(ratio_or_perfect(gross_profit, gross_loss), 4),
        "total_pnl": round(sum(pnls), 2),
        "trade_count": len(trades),
        "max_drawdown": round(max_drawdown, 2),
    }


def build_result_payload(is_trades: list[Trade], oos_trades: list[Trade]) -> dict[str, Any]:
    is_metrics = compute_metrics(is_trades)
    oos_metrics = compute_metrics(oos_trades)
    rejection_reasons: list[str] = []

    is_trade_count = int(is_metrics["trade_count"])
    if is_trade_count < 30:
        rejection_reasons.append(f"insufficient trades (IS): {is_trade_count} < 30")

    fitness_passed = True
    fitness_thresholds = (
        ("is_win_rate", float(is_metrics["win_rate"]), 0.55),
        ("is_avg_rr", float(is_metrics["avg_rr"]), 1.5),
        ("oos_win_rate", float(oos_metrics["win_rate"]), 0.55),
        ("oos_avg_rr", float(oos_metrics["avg_rr"]), 1.5),
    )
    for name, actual, threshold in fitness_thresholds:
        if actual < threshold:
            fitness_passed = False
            rejection_reasons.append(f"{name} {actual:.4f} < {threshold:.2f} threshold")

    if is_trade_count < 30:
        fitness_passed = False

    return {
        "is_metrics": is_metrics,
        "oos_metrics": oos_metrics,
        "trade_count": len(is_trades) + len(oos_trades),
        "total_trade_count": len(is_trades) + len(oos_trades),
        "fitness_passed": fitness_passed,
        "status": "rejected" if is_trade_count < 30 else "completed",
        "rejection_reasons": rejection_reasons,
    }


def run_harness(
    config: StrategyConfig,
    data_dir: str | Path,
    *,
    is_ratio: float = DEFAULT_IS_RATIO,
    verbose: bool = False,
) -> dict[str, Any]:
    session_files = list_session_files(data_dir)
    if not session_files:
        raise FileNotFoundError("No session files found in data-dir")

    is_files, oos_files = split_session_files(session_files, is_ratio)
    if verbose:
        print(
            f"Loaded {len(session_files)} sessions (IS={len(is_files)}, OOS={len(oos_files)}) from {Path(data_dir)}",
            file=sys.stderr,
        )

    is_trades: list[Trade] = []
    oos_trades: list[Trade] = []

    for path in is_files:
        if verbose:
            print(f"Evaluating IS session: {path.name}", file=sys.stderr)
        is_trades.extend(evaluate_session(config, load_session(path), split="is"))

    for path in oos_files:
        if verbose:
            print(f"Evaluating OOS session: {path.name}", file=sys.stderr)
        oos_trades.extend(evaluate_session(config, load_session(path), split="oos"))

    return build_result_payload(is_trades, oos_trades)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DEEP6 StrategyConfig backtest harness")
    parser.add_argument("--config", required=True, help="Path to StrategyConfig YAML")
    parser.add_argument("--data-dir", required=True, help="Directory containing session_YYYY-MM-DD.pkl files")
    parser.add_argument("--validate", action="store_true", help="Run pipeline validation and require >0 trades")
    parser.add_argument("--verbose", action="store_true", help="Emit progress to stderr")
    parser.add_argument("--is-ratio", type=float, default=DEFAULT_IS_RATIO, help="In-sample split ratio")
    args = parser.parse_args(argv)

    try:
        config = load_strategy_config(args.config)
        result = run_harness(config, args.data_dir, is_ratio=args.is_ratio, verbose=args.verbose)
        if args.validate:
            if int(result["total_trade_count"]) <= 0:
                print("VALIDATION FAIL: trade_count <= 0", file=sys.stderr)
                return 1
            print(f"VALIDATION PASS: trade_count={result['total_trade_count']}")
            return 0
        print(json.dumps(result, separators=(",", ":"), allow_nan=False))
        return 0
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - CLI safety net
        print(f"Harness failed: {exc}", file=sys.stderr)
        return 1


def get_approach_ticks(config: StrategyConfig) -> int:
    return int(get_attr(config, "level_approach_ticks", DEFAULT_APPROACH_TICKS))


def within_approach(close_price: float, level_price: float, approach_ticks: int) -> bool:
    return tick_distance(close_price, level_price) <= float(approach_ticks)


def matches_approach_direction(close_price: float, level_price: float, direction: ApproachDirection) -> bool:
    if direction is ApproachDirection.EITHER:
        return True
    if direction is ApproachDirection.ABOVE:
        return close_price > level_price
    return close_price < level_price


def matches_wall_target(wall: Any, target: LevelTarget) -> bool:
    classification = str(get_attr(wall, "classification", "")).upper()
    if target is LevelTarget.ANY_WALL:
        return True
    if target is LevelTarget.GENUINE_WALL:
        return classification == "GENUINE"
    if target is LevelTarget.ICEBERG_WALL:
        return classification == "ICEBERG"
    return False


def passes_timing_filter(bar_time_seconds: float, timing_filter: TimingFilter) -> bool:
    dt = datetime.fromtimestamp(bar_time_seconds, tz=ET)
    minutes = dt.hour * 60 + dt.minute
    if timing_filter is TimingFilter.ANY:
        return True
    if timing_filter is TimingFilter.LONDON:
        return 180 <= minutes < 480
    if timing_filter is TimingFilter.NY_AM:
        return 570 <= minutes < 690
    if timing_filter is TimingFilter.NY_PM:
        return 810 <= minutes < 960
    if timing_filter is TimingFilter.RTH_OPEN:
        return 570 <= minutes < 630
    if timing_filter is TimingFilter.MIDDAY_BLOCK_EXCLUDED:
        return not (630 <= minutes < 780)
    return True


def compute_session_vpoc(bars: list[Any]) -> float | None:
    profile: dict[int, int] = {}
    for bar in bars:
        levels = get_attr(bar, "levels")
        if isinstance(levels, dict):
            for tick, level in levels.items():
                bid_vol = int(get_attr(level, "bid_vol", 0))
                ask_vol = int(get_attr(level, "ask_vol", 0))
                profile[int(tick)] = profile.get(int(tick), 0) + bid_vol + ask_vol
    if profile:
        return max(profile.items(), key=lambda item: item[1])[0] * TICK_SIZE
    if bars:
        return float(get_attr(bars[-1], "poc_price", 0.0)) or None
    return None


def is_zone_active(zone: Any) -> bool:
    state = get_attr(zone, "state")
    return state is None or state != ZoneState.INVALIDATED


def zone_mid_price(zone: Any) -> float:
    top_price = float(get_attr(zone, "top_price", 0.0))
    bot_price = float(get_attr(zone, "bot_price", 0.0))
    return (top_price + bot_price) / 2.0


def infer_direction_from_relative_position(close_price: float, level_price: float) -> str:
    return "LONG" if close_price >= level_price else "SHORT"


def find_next_zone(trade: Trade, zones: list[Any]) -> dict[str, float] | None:
    candidates: list[dict[str, float]] = []
    for zone in zones:
        if not is_zone_active(zone):
            continue
        top_price = float(get_attr(zone, "top_price", 0.0))
        bot_price = float(get_attr(zone, "bot_price", 0.0))
        mid_price = (top_price + bot_price) / 2.0
        if trade.direction == "LONG" and mid_price > trade.entry_price:
            candidates.append({"trigger_price": bot_price, "distance": mid_price - trade.entry_price})
        if trade.direction == "SHORT" and mid_price < trade.entry_price:
            candidates.append({"trigger_price": top_price, "distance": trade.entry_price - mid_price})
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: candidate["distance"])


def get_bar_timestamp(bar: Any) -> float:
    raw = get_attr(bar, "ts")
    if raw is None:
        raw = get_attr(bar, "timestamp", 0.0)
    return to_epoch_seconds(raw)


def get_wall_timestamp(wall: Any) -> float:
    raw = get_attr(wall, "detected_at", 0.0)
    return to_epoch_seconds(raw)


def to_epoch_seconds(value: Any) -> float:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=ET)
        return float(value.timestamp())
    if isinstance(value, (int, float)):
        numeric = float(value)
        if abs(numeric) > 1_000_000_000_000:
            return numeric / 1_000_000_000.0
        return numeric
    return float(value or 0.0)


def to_ns_epoch(value: float) -> int:
    return int(round(float(value) * 1_000_000_000))


def tick_distance(a: float, b: float) -> float:
    return abs(a - b) / TICK_SIZE


def ratio_or_perfect(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return PERFECT_METRIC if numerator > 0 else 0.0
    return numerator / denominator


def get_attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_IS_RATIO",
    "Trade",
    "build_result_payload",
    "check_entry",
    "check_exits",
    "compute_metrics",
    "compute_pnl",
    "evaluate_session",
    "load_strategy_config",
    "main",
    "run_harness",
]
