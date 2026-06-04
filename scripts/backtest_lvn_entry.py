#!/usr/bin/env python3
from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "backtests" / "nq_1yr_1m.csv"

TICK_SIZE = 0.25
TICK_VALUE = 5.0
STOP_TICKS = 20
TARGET_TICKS = 32
MAX_BARS_IN_TRADE = 60
COMMISSION_RT = 4.12
SLIPPAGE_RT_DOLLARS = 2.50
TRADE_COST_RT = COMMISSION_RT + SLIPPAGE_RT_DOLLARS

ROWS = 200
STRENGTHS = (5, 10, 15)
APPROACH_TICKS = (4, 8, 12)
PROFILE_PERIODS = ("daily", "weekly", "monthly")
MODELS = ("A", "B", "C")

RTH_START_MINUTE = 9 * 60 + 30
BLACKOUT_START_MINUTE = 15 * 60 + 30
RTH_END_MINUTE = 16 * 60
LAST_SESSION_BAR_MINUTE = 15 * 60 + 59
IS_FRACTION = 0.68
PROGRESS_EVERY = 50_000


@dataclass(frozen=True)
class Config:
    model: Literal["A", "B", "C"]
    profile_period: Literal["daily", "weekly", "monthly"]
    strength: int
    approach_ticks: int


@dataclass
class Trade:
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry_date: object
    exit_date: object
    direction: int
    entry_price: float
    exit_price: float
    pnl_ticks: float
    pnl_dollars: float
    bars_held: int
    exit_reason: str


def load_bars(path: Path) -> pd.DataFrame:
    print(f"Loading bars from {path} ...")
    df = pd.read_csv(
        path,
        usecols=["ts_event", "open", "high", "low", "close", "volume", "symbol"],
        parse_dates=["ts_event"],
    )
    df = df.sort_values("ts_event").reset_index(drop=True)

    ts_utc = pd.to_datetime(df["ts_event"], utc=True)
    ts_et = ts_utc.dt.tz_convert(ZoneInfo("America/New_York"))
    minute = ts_et.dt.hour * 60 + ts_et.dt.minute

    df["ts_et"] = ts_et.dt.tz_localize(None)
    df["session_date"] = ts_et.dt.date
    df["minute"] = minute
    df["entry_allowed"] = minute < BLACKOUT_START_MINUTE
    df["daily_key"] = ts_et.dt.strftime("%Y-%m-%d")

    week_start = (ts_et.dt.normalize() - pd.to_timedelta(ts_et.dt.weekday, unit="D")).dt.tz_localize(None)
    df["weekly_key"] = week_start.dt.strftime("%Y-%m-%d")
    df["monthly_key"] = ts_et.dt.to_period("M").astype(str)

    rth_mask = (minute >= RTH_START_MINUTE) & (minute < RTH_END_MINUTE)
    df = df.loc[rth_mask].reset_index(drop=True)
    df["vol_avg20"] = df["volume"].rolling(20, min_periods=20).mean().shift(1)

    print(
        f"Loaded {len(df):,} RTH bars across {df['session_date'].nunique():,} sessions "
        f"for {df['symbol'].iloc[0]}"
    )
    return df


def split_is_oos(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    split_idx = int(len(df) * IS_FRACTION)
    if split_idx <= 0 or split_idx >= len(df):
        raise ValueError("Unable to create 68/32 walk-forward split.")

    split_session = df.iloc[split_idx]["session_date"]
    while split_idx < len(df) and df.iloc[split_idx]["session_date"] == split_session:
        split_idx += 1

    is_df = df.iloc[:split_idx].copy().reset_index(drop=True)
    oos_df = df.iloc[split_idx:].copy().reset_index(drop=True)
    print(
        f"Walk-forward split: IS={len(is_df):,} bars ({is_df['session_date'].min()} -> {is_df['session_date'].max()}), "
        f"OOS={len(oos_df):,} bars ({oos_df['session_date'].min()} -> {oos_df['session_date'].max()})"
    )
    return is_df, oos_df


def build_period_profile(period_df: pd.DataFrame, rows: int) -> tuple[np.ndarray, float, float]:
    period_low = float(period_df["low"].min())
    period_high = float(period_df["high"].max())
    profile = np.zeros(rows, dtype=float)

    if not math.isfinite(period_low) or not math.isfinite(period_high) or period_high <= period_low:
        return profile, period_low, period_high

    bin_size = (period_high - period_low) / rows
    edges = period_low + np.arange(rows + 1, dtype=float) * bin_size

    lows = period_df["low"].to_numpy(dtype=float)
    highs = period_df["high"].to_numpy(dtype=float)
    volumes = period_df["volume"].to_numpy(dtype=float)

    for low, high, volume in zip(lows, highs, volumes):
        if volume <= 0:
            continue

        if high <= low:
            idx = int(np.clip((low - period_low) / bin_size, 0, rows - 1))
            profile[idx] += volume
            continue

        start_idx = int(np.clip((low - period_low) / bin_size, 0, rows - 1))
        end_idx = int(np.clip((high - period_low) / bin_size, 0, rows - 1))
        bar_range = high - low

        for idx in range(start_idx, end_idx + 1):
            overlap_low = max(low, edges[idx])
            overlap_high = min(high, edges[idx + 1])
            overlap = overlap_high - overlap_low
            if overlap > 0:
                profile[idx] += volume * (overlap / bar_range)

    return profile, period_low, period_high


def detect_lvns(profile: np.ndarray, period_low: float, period_high: float, rows: int, strength: int) -> np.ndarray:
    if profile.size == 0 or period_high <= period_low or rows <= strength * 2:
        return np.empty(0, dtype=float)

    bin_size = (period_high - period_low) / rows
    centers = period_low + (np.arange(rows, dtype=float) + 0.5) * bin_size
    levels: list[float] = []

    for idx in range(strength, rows - strength):
        center_vol = profile[idx]
        if center_vol <= 0:
            continue
        neighbors = profile[idx - strength : idx + strength + 1]
        if center_vol < np.min(np.concatenate((neighbors[:strength], neighbors[strength + 1 :]))) :
            levels.append(centers[idx])

    return np.array(levels, dtype=float)


def build_levels_for_dataset(
    df: pd.DataFrame,
    period_name: str,
    rows: int,
    strengths: tuple[int, ...],
) -> dict[int, dict[str, np.ndarray]]:
    period_col = f"{period_name}_key"
    result: dict[int, dict[str, np.ndarray]] = {strength: {} for strength in strengths}
    processed = 0
    next_progress = PROGRESS_EVERY

    print(f"Building {period_name} LVN profiles ...")
    for period_key, period_df in df.groupby(period_col, sort=False):
        profile, period_low, period_high = build_period_profile(period_df, rows)
        for strength in strengths:
            result[strength][str(period_key)] = detect_lvns(profile, period_low, period_high, rows, strength)

        processed += len(period_df)
        while processed >= next_progress:
            print(f"  {period_name}: processed {next_progress:,} bars")
            next_progress += PROGRESS_EVERY

    return result


def build_all_levels(df: pd.DataFrame) -> dict[str, dict[int, dict[str, np.ndarray]]]:
    return {
        period_name: build_levels_for_dataset(df, period_name, ROWS, STRENGTHS)
        for period_name in PROFILE_PERIODS
    }


def trade_pnl_dollars(direction: int, entry_price: float, exit_price: float) -> tuple[float, float]:
    pnl_ticks = direction * (exit_price - entry_price) / TICK_SIZE
    pnl_dollars = pnl_ticks * TICK_VALUE - TRADE_COST_RT
    return float(pnl_ticks), float(pnl_dollars)


def finalize_trade(
    trades: list[Trade],
    entry_ts: pd.Timestamp,
    entry_date: object,
    direction: int,
    entry_price: float,
    exit_ts: pd.Timestamp,
    exit_date: object,
    exit_price: float,
    bars_held: int,
    exit_reason: str,
) -> None:
    pnl_ticks, pnl_dollars = trade_pnl_dollars(direction, entry_price, exit_price)
    trades.append(
        Trade(
            entry_ts=entry_ts,
            exit_ts=exit_ts,
            entry_date=entry_date,
            exit_date=exit_date,
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl_ticks=pnl_ticks,
            pnl_dollars=pnl_dollars,
            bars_held=bars_held,
            exit_reason=exit_reason,
        )
    )


def signal_model_a(
    prev_close: float,
    close_price: float,
    bar_volume: float,
    vol_avg20: float,
    levels: np.ndarray,
) -> int:
    if levels.size == 0 or np.isnan(vol_avg20) or bar_volume < vol_avg20:
        return 0

    if close_price > prev_close and np.any((prev_close < levels) & (close_price >= levels)):
        return 1
    if close_price < prev_close and np.any((prev_close > levels) & (close_price <= levels)):
        return -1
    return 0


def signal_model_b(
    prev_close: float,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    band: float,
    levels: np.ndarray,
) -> int:
    if levels.size == 0:
        return 0

    long_hit = (prev_close > levels) & (low_price <= levels + band) & (close_price > levels) & (close_price >= open_price)
    if np.any(long_hit):
        return 1

    short_hit = (prev_close < levels) & (high_price >= levels - band) & (close_price < levels) & (close_price <= open_price)
    if np.any(short_hit):
        return -1

    return 0


def signal_model_c(prev_close: float, open_price: float, close_price: float, band: float, levels: np.ndarray) -> int:
    if levels.size == 0:
        return 0

    near_mask = np.abs(levels - close_price) <= band
    if not np.any(near_mask):
        return 0

    nearby = levels[near_mask]
    nearest = float(nearby[np.argmin(np.abs(nearby - close_price))])
    if prev_close > nearest:
        return 1
    if prev_close < nearest:
        return -1
    if close_price > open_price:
        return 1
    if close_price < open_price:
        return -1
    return 0


def run_backtest(
    df: pd.DataFrame,
    config: Config,
    levels_by_period: dict[str, dict[int, dict[str, np.ndarray]]],
) -> list[Trade]:
    period_col = f"{config.profile_period}_key"
    level_lookup = levels_by_period[config.profile_period][config.strength]
    band = config.approach_ticks * TICK_SIZE

    ts = df["ts_et"].to_numpy()
    session_dates = df["session_date"].to_numpy()
    minutes = df["minute"].to_numpy(dtype=int)
    entry_allowed = df["entry_allowed"].to_numpy(dtype=bool)
    period_keys = df[period_col].astype(str).to_numpy()

    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    volumes = df["volume"].to_numpy(dtype=float)
    vol_avg20 = df["vol_avg20"].to_numpy(dtype=float)

    trades: list[Trade] = []

    active = False
    direction = 0
    entry_price = 0.0
    entry_ts = ts[0]
    entry_date = session_dates[0]
    bars_held = 0

    for idx in range(1, len(df)):
        if idx % PROGRESS_EVERY == 0:
            print(f"  {config.model}/{config.profile_period}/s{config.strength}/a{config.approach_ticks}: processed {idx:,} bars")

        current_ts = ts[idx]
        current_date = session_dates[idx]

        if active and current_date != session_dates[idx - 1]:
            finalize_trade(
                trades,
                entry_ts,
                entry_date,
                direction,
                entry_price,
                ts[idx - 1],
                session_dates[idx - 1],
                closes[idx - 1],
                bars_held,
                "session_gap_flatten",
            )
            active = False

        if active:
            stop_price = entry_price - STOP_TICKS * TICK_SIZE if direction > 0 else entry_price + STOP_TICKS * TICK_SIZE
            target_price = entry_price + TARGET_TICKS * TICK_SIZE if direction > 0 else entry_price - TARGET_TICKS * TICK_SIZE

            if direction > 0:
                if lows[idx] <= stop_price:
                    finalize_trade(trades, entry_ts, entry_date, direction, entry_price, current_ts, current_date, stop_price, bars_held + 1, "stop")
                    active = False
                    continue
                if highs[idx] >= target_price:
                    finalize_trade(trades, entry_ts, entry_date, direction, entry_price, current_ts, current_date, target_price, bars_held + 1, "target")
                    active = False
                    continue
            else:
                if highs[idx] >= stop_price:
                    finalize_trade(trades, entry_ts, entry_date, direction, entry_price, current_ts, current_date, stop_price, bars_held + 1, "stop")
                    active = False
                    continue
                if lows[idx] <= target_price:
                    finalize_trade(trades, entry_ts, entry_date, direction, entry_price, current_ts, current_date, target_price, bars_held + 1, "target")
                    active = False
                    continue

            bars_held += 1
            if minutes[idx] >= LAST_SESSION_BAR_MINUTE:
                finalize_trade(trades, entry_ts, entry_date, direction, entry_price, current_ts, current_date, closes[idx], bars_held, "session_end")
                active = False
                continue
            if bars_held >= MAX_BARS_IN_TRADE:
                finalize_trade(trades, entry_ts, entry_date, direction, entry_price, current_ts, current_date, closes[idx], bars_held, "max_bars")
                active = False
                continue

        if active or not entry_allowed[idx]:
            continue

        levels = level_lookup.get(period_keys[idx], np.empty(0, dtype=float))
        if levels.size == 0:
            continue

        signal = 0
        if config.model == "A":
            signal = signal_model_a(closes[idx - 1], closes[idx], volumes[idx], vol_avg20[idx], levels)
        elif config.model == "B":
            signal = signal_model_b(closes[idx - 1], opens[idx], highs[idx], lows[idx], closes[idx], band, levels)
        else:
            signal = signal_model_c(closes[idx - 1], opens[idx], closes[idx], band, levels)

        if signal == 0:
            continue

        active = True
        direction = signal
        entry_price = float(closes[idx])
        entry_ts = current_ts
        entry_date = current_date
        bars_held = 0

    if active:
        finalize_trade(trades, entry_ts, entry_date, direction, entry_price, ts[-1], session_dates[-1], closes[-1], bars_held, "end_of_data")

    return trades


def compute_metrics(trades: list[Trade]) -> dict[str, float]:
    if not trades:
        return {
            "trade_count": 0,
            "win_rate": 0.0,
            "avg_win_ticks": 0.0,
            "avg_loss_ticks": 0.0,
            "profit_factor": 0.0,
            "total_pnl": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "avg_bars_held": 0.0,
        }

    pnl_ticks = np.array([trade.pnl_ticks for trade in trades], dtype=float)
    pnl_dollars = np.array([trade.pnl_dollars for trade in trades], dtype=float)
    bars_held = np.array([trade.bars_held for trade in trades], dtype=float)

    wins = pnl_dollars > 0
    losses = pnl_dollars < 0
    gross_profit = float(pnl_dollars[wins].sum())
    gross_loss = float(-pnl_dollars[losses].sum())
    equity = np.cumsum(pnl_dollars)
    peaks = np.maximum.accumulate(equity)
    drawdown = peaks - equity

    daily_pnl = pd.Series(pnl_dollars, index=pd.Index([trade.exit_date for trade in trades], name="date")).groupby(level=0).sum()
    sharpe = 0.0
    if len(daily_pnl) > 1:
        daily_std = float(daily_pnl.std(ddof=1))
        if daily_std > 0:
            sharpe = float(daily_pnl.mean() / daily_std * math.sqrt(252.0))

    return {
        "trade_count": int(len(trades)),
        "win_rate": float(wins.mean() * 100.0),
        "avg_win_ticks": float(pnl_ticks[wins].mean()) if np.any(wins) else 0.0,
        "avg_loss_ticks": float(pnl_ticks[losses].mean()) if np.any(losses) else 0.0,
        "profit_factor": float(gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0),
        "total_pnl": float(pnl_dollars.sum()),
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.max()) if len(drawdown) else 0.0,
        "avg_bars_held": float(bars_held.mean()),
    }


def format_metric_block(metrics: dict[str, float]) -> str:
    return (
        f"N={metrics['trade_count']:>4d} "
        f"WR={metrics['win_rate']:>5.1f}% "
        f"PF={metrics['profit_factor']:>5.2f} "
        f"PnL=${metrics['total_pnl']:>9,.0f} "
        f"Sh={metrics['sharpe']:>6.2f} "
        f"MDD=${metrics['max_drawdown']:>8,.0f} "
        f"AvgW={metrics['avg_win_ticks']:>6.1f}t "
        f"AvgL={metrics['avg_loss_ticks']:>6.1f}t "
        f"Hold={metrics['avg_bars_held']:>5.1f}"
    )


def print_results(results: list[dict[str, object]]) -> None:
    best_candidates = [row for row in results if row["oos_metrics"]["trade_count"] >= 20]
    best_row = max(best_candidates, key=lambda row: row["oos_metrics"]["sharpe"], default=None)

    print("\nFULL CONFIGURATION TABLE")
    print("=" * 180)
    for row in results:
        marker = " << BEST" if best_row is not None and row["config"] == best_row["config"] else ""
        cfg: Config = row["config"]
        passed = row["passes_oos"]
        print(
            f"{cfg.model} | {cfg.profile_period:<7} | s={cfg.strength:>2d} | a={cfg.approach_ticks:>2d} | "
            f"IS {format_metric_block(row['is_metrics'])} | "
            f"OOS {format_metric_block(row['oos_metrics'])} | PASS={str(passed):<5}{marker}"
        )

    print("\nBEST-BY-PROFILE PERIOD")
    print("=" * 180)
    summary_rows: list[tuple[str, dict[str, object]]] = []
    for period_name in PROFILE_PERIODS:
        candidates = [row for row in results if row["config"].profile_period == period_name and row["oos_metrics"]["trade_count"] >= 20]
        if not candidates:
            continue
        summary_rows.append((period_name, max(candidates, key=lambda row: row["oos_metrics"]["sharpe"])))

    if summary_rows:
        print(f"{'Period':<10} {'Model':<5} {'Strength':>8} {'Approach':>9} {'OOS Trades':>10} {'OOS WR%':>8} {'OOS PF':>8} {'OOS Sharpe':>11} {'OOS PnL$':>11} {'Pass':>6}")
        for period_name, row in summary_rows:
            cfg: Config = row["config"]
            oos = row["oos_metrics"]
            print(
                f"{period_name:<10} {cfg.model:<5} {cfg.strength:>8d} {cfg.approach_ticks:>9d} "
                f"{oos['trade_count']:>10d} {oos['win_rate']:>8.1f} {oos['profit_factor']:>8.2f} "
                f"{oos['sharpe']:>11.2f} {oos['total_pnl']:>11,.2f} {str(row['passes_oos']):>6}"
            )

    if best_row is None:
        print("\nNo configuration met the minimum 20 OOS trade threshold.")
        return

    cfg = best_row["config"]
    print("\nBEST CONFIGURATION")
    print("=" * 180)
    print(
        f"Model {cfg.model} | {cfg.profile_period} | strength={cfg.strength} | approach_ticks={cfg.approach_ticks} | "
        f"passes_oos={best_row['passes_oos']}"
    )
    print(f"IS  {format_metric_block(best_row['is_metrics'])}")
    print(f"OOS {format_metric_block(best_row['oos_metrics'])}")


def main() -> None:
    df = load_bars(DATA_PATH)
    is_df, oos_df = split_is_oos(df)

    is_levels = build_all_levels(is_df)
    oos_levels = build_all_levels(oos_df)

    results: list[dict[str, object]] = []
    configs = [Config(model, profile_period, strength, approach_ticks) for model, profile_period, strength, approach_ticks in product(MODELS, PROFILE_PERIODS, STRENGTHS, APPROACH_TICKS)]

    print(f"Running {len(configs)} configurations ...")
    for config_idx, config in enumerate(configs, start=1):
        print(
            f"\n[{config_idx:>3d}/{len(configs)}] model={config.model} period={config.profile_period} "
            f"strength={config.strength} approach={config.approach_ticks}"
        )

        is_trades = run_backtest(is_df, config, is_levels)
        oos_trades = run_backtest(oos_df, config, oos_levels)
        is_metrics = compute_metrics(is_trades)
        oos_metrics = compute_metrics(oos_trades)
        passes_oos = (
            oos_metrics["trade_count"] >= 20
            and oos_metrics["win_rate"] > 50.0
            and oos_metrics["profit_factor"] > 1.2
        )
        results.append(
            {
                "config": config,
                "is_metrics": is_metrics,
                "oos_metrics": oos_metrics,
                "passes_oos": passes_oos,
            }
        )

    results.sort(
        key=lambda row: (
            row["oos_metrics"]["trade_count"] >= 20,
            row["oos_metrics"]["sharpe"],
            row["oos_metrics"]["total_pnl"],
        ),
        reverse=True,
    )
    print_results(results)


if __name__ == "__main__":
    main()
