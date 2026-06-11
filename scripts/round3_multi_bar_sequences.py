#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data/backtests/signal_events.csv"
OHLCV_CSV = ROOT / "data/backtests/nq_1yr_1m.csv"
OUT_DIR = ROOT / "data/backtests/analysis"
OUT_PATH = OUT_DIR / "round3_multi_bar_sequences_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20


def fmt_float(value: float) -> str:
    if pd.isna(value):
        return "nan"
    if np.isinf(value):
        return "inf"
    return f"{value:,.2f}"


def fmt_pct(value: float) -> str:
    if pd.isna(value):
        return "nan"
    return f"{value * 100:.1f}%"


def fmt_ci(low: float, high: float) -> str:
    return f"[{low * 100:.1f}%, {high * 100:.1f}%]"


def profit_factor(returns: pd.Series) -> float:
    wins = returns[returns > 0].sum()
    losses = -returns[returns <= 0].sum()
    if losses <= 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / losses)


def wilson_ci(n: int, k: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return 0.0, 0.0, 0.0
    p_hat = k / n
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, center - margin), min(1.0, center + margin), p_hat


def status_flag(n: int, ci_low: float) -> str:
    if n < 15:
        return "LOW_N"
    if n >= 30 and ci_low > 0.50:
        return "VALIDATED"
    if n >= 15 and ci_low > 0.45:
        return "PROMISING"
    return ""


def load_ohlcv() -> pd.DataFrame:
    bars = pd.read_csv(
        OHLCV_CSV,
        usecols=["ts_event", "open", "high", "low", "close", "volume"],
        parse_dates=["ts_event"],
        low_memory=False,
    )
    bars["ts_event"] = pd.to_datetime(bars["ts_event"], utc=True).dt.tz_convert(EASTERN)
    return bars.sort_values("ts_event").reset_index(drop=True)


def load_events() -> pd.DataFrame:
    dtypes = {
        "session_date": "string",
        "signal_id": "string",
        "category": "string",
        "bar_index": "int32",
        "global_index": "int32",
        "bar_delta": "float64",
        "bar_volume": "float64",
    }
    cols = [
        "session_date",
        "bar_ts",
        "bar_index",
        "global_index",
        "signal_id",
        "category",
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_delta",
        "bar_volume",
        "fwd_close_5b",
        "fwd_close_10b",
        "fwd_close_30b",
    ]
    df = pd.read_csv(EVENTS_CSV, usecols=cols, dtype=dtypes, low_memory=False)
    numeric_cols = [
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_delta",
        "bar_volume",
        "fwd_close_5b",
        "fwd_close_10b",
        "fwd_close_30b",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["bar_ts"] = pd.to_datetime(df["bar_ts"], utc=True, errors="coerce").dt.tz_convert(EASTERN)
    return df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)


def build_observations(events: pd.DataFrame) -> pd.DataFrame:
    observations = (
        events.groupby("global_index", as_index=False, sort=False)
        .agg(
            session_date=("session_date", "first"),
            bar_ts=("bar_ts", "first"),
            bar_index=("bar_index", "first"),
            bar_open=("bar_open", "first"),
            bar_high=("bar_high", "first"),
            bar_low=("bar_low", "first"),
            bar_close=("bar_close", "first"),
            bar_delta=("bar_delta", "first"),
            bar_volume=("bar_volume", "first"),
            fwd_close_5b=("fwd_close_5b", "first"),
            fwd_close_10b=("fwd_close_10b", "first"),
            fwd_close_30b=("fwd_close_30b", "first"),
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
        )
        .sort_values("global_index", kind="stable")
        .reset_index(drop=True)
    )
    observations["direction_sign"] = np.sign(observations["bar_delta"].fillna(0.0)).astype(int)
    observations["direction"] = np.select(
        [observations["direction_sign"] > 0, observations["direction_sign"] < 0],
        ["BULLISH", "BEARISH"],
        default="FLAT",
    )
    for window in FORWARD_WINDOWS:
        observations[f"move_{window}b_ticks"] = (observations[f"fwd_close_{window}b"] - observations["bar_close"]) / TICK_SIZE
        observations[f"ret_{window}b_ticks"] = observations["direction_sign"] * observations[f"move_{window}b_ticks"]
    return observations


def build_timeframe_context(bars_1m: pd.DataFrame) -> dict[int, pd.DataFrame]:
    context: dict[int, pd.DataFrame] = {}
    base = bars_1m.set_index("ts_event")

    for tf in TIMEFRAMES:
        tf_bars = (
            base.resample(f"{tf}min")
            .agg(
                open=("open", "first"),
                high=("high", "max"),
                low=("low", "min"),
                close=("close", "last"),
                volume=("volume", "sum"),
            )
            .dropna()
            .reset_index()
        )
        tf_bars["range"] = tf_bars["high"] - tf_bars["low"]
        tf_bars["trend_sign"] = np.sign(tf_bars["close"] - tf_bars["open"]).astype(int)
        context[tf] = tf_bars

    return context


def attach_context(observations: pd.DataFrame, context: dict[int, pd.DataFrame]) -> pd.DataFrame:
    df = observations.copy()
    for tf, ctx in context.items():
        bucket_col = f"bucket_{tf}m"
        df[bucket_col] = df["bar_ts"].dt.floor(f"{tf}min")
        renamed = ctx.rename(
            columns={
                "ts_event": bucket_col,
                "open": f"open_{tf}m",
                "high": f"high_{tf}m",
                "low": f"low_{tf}m",
                "close": f"close_{tf}m",
                "volume": f"volume_{tf}m",
                "range": f"range_{tf}m",
                "trend_sign": f"trend_sign_{tf}m",
            }
        )
        df = df.merge(renamed, on=bucket_col, how="left", validate="many_to_one")

    df["bar_high"] = pd.to_numeric(df["bar_high"], errors="coerce")
    df["bar_low"] = pd.to_numeric(df["bar_low"], errors="coerce")
    df["bar_close"] = pd.to_numeric(df["bar_close"], errors="coerce")
    return df


def compute_bar_features(observations: pd.DataFrame) -> pd.DataFrame:
    bars = observations.copy()
    by_session = bars.groupby("session_date", sort=False)

    bars["bar_range"] = bars["bar_high"] - bars["bar_low"]
    bars["body"] = (bars["bar_close"] - bars["bar_open"]).abs()
    bars["body_high"] = np.maximum(bars["bar_open"], bars["bar_close"])
    bars["body_low"] = np.minimum(bars["bar_open"], bars["bar_close"])
    bars["upper_wick"] = bars["bar_high"] - bars["body_high"]
    bars["lower_wick"] = bars["body_low"] - bars["bar_low"]

    bars["prev_close"] = by_session["bar_close"].shift(1)
    bars["close_to_close_change"] = bars["bar_close"] - bars["prev_close"]
    bars["close_to_close_sign"] = np.sign(bars["close_to_close_change"].fillna(0.0)).astype(int)

    bars["prior_bar_delta"] = by_session["bar_delta"].shift(1)
    bars["prior_high"] = by_session["bar_high"].shift(1)
    bars["prior_low"] = by_session["bar_low"].shift(1)
    bars["prior_bar_range"] = by_session["bar_range"].shift(1)
    bars["prior_body_high"] = by_session["body_high"].shift(1)
    bars["prior_body_low"] = by_session["body_low"].shift(1)
    bars["range_1"] = by_session["bar_range"].shift(1)
    bars["range_2"] = by_session["bar_range"].shift(2)
    bars["range_3"] = by_session["bar_range"].shift(3)
    bars["range_4"] = by_session["bar_range"].shift(4)
    bars["prior_close_sign_1"] = by_session["close_to_close_sign"].shift(1)
    bars["prior_close_sign_2"] = by_session["close_to_close_sign"].shift(2)
    bars["prior_close_sign_3"] = by_session["close_to_close_sign"].shift(3)

    bars["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    bars["range_q75"] = by_session["bar_range"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.75)
    )
    bars["prior_range_q75"] = by_session["range_q75"].shift(1)

    bars["is_doji"] = bars["bar_range"].gt(0) & bars["body"].lt(0.10 * bars["bar_range"])
    bars["is_delta_reversal"] = (
        bars["prior_bar_delta"].notna()
        & bars["prior_bar_delta"].ne(0)
        & bars["direction_sign"].ne(0)
        & np.sign(bars["bar_delta"]).ne(np.sign(bars["prior_bar_delta"]))
    )
    bars["is_volume_spike_2x"] = (
        bars["rolling_20_ema_vol"].gt(0)
        & bars["bar_volume"].gt(2.0 * bars["rolling_20_ema_vol"])
    )
    bars["is_volume_spike_150"] = (
        bars["rolling_20_ema_vol"].gt(0)
        & bars["bar_volume"].gt(1.5 * bars["rolling_20_ema_vol"])
    )
    bars["is_volume_dryup"] = (
        bars["rolling_20_ema_vol"].gt(0)
        & bars["bar_volume"].lt(0.5 * bars["rolling_20_ema_vol"])
    )
    bars["prior_is_volume_dryup"] = by_session["is_volume_dryup"].shift(1).fillna(False).astype(bool)
    bars["prior_is_doji"] = by_session["is_doji"].shift(1).fillna(False).astype(bool)
    bars["is_prior_wide_range"] = (
        bars["prior_bar_range"].notna()
        & bars["prior_range_q75"].notna()
        & bars["prior_bar_range"].gt(bars["prior_range_q75"])
    )

    same_direction_close_run = (
        bars["prior_close_sign_1"].notna()
        & bars["prior_close_sign_1"].eq(bars["prior_close_sign_2"])
        & bars["prior_close_sign_2"].eq(bars["prior_close_sign_3"])
        & bars["prior_close_sign_1"].ne(0)
    )
    bars["prior_three_close_dir"] = np.where(same_direction_close_run, bars["prior_close_sign_1"], 0)
    bars["is_doji_after_strong_move"] = (
        bars["is_doji"]
        & bars["direction_sign"].ne(0)
        & same_direction_close_run
        & pd.Series(bars["prior_three_close_dir"], index=bars.index).eq(-bars["direction_sign"])
    )

    bars["is_hammer"] = (
        bars["body"].gt(0)
        & bars["lower_wick"].gt(2.0 * bars["body"])
        & bars["upper_wick"].lt(0.5 * bars["body"])
        & bars["bar_close"].gt(bars["bar_open"])
    )
    bars["is_shooting_star"] = (
        bars["body"].gt(0)
        & bars["upper_wick"].gt(2.0 * bars["body"])
        & bars["lower_wick"].lt(0.5 * bars["body"])
        & bars["bar_close"].lt(bars["bar_open"])
    )
    bars["hammer_direction_sign"] = np.where(bars["is_hammer"], 1, 0)
    bars["shooting_star_direction_sign"] = np.where(bars["is_shooting_star"], -1, 0)

    bars["is_engulfing"] = (
        bars["prior_body_high"].notna()
        & bars["body_high"].gt(bars["prior_body_high"])
        & bars["body_low"].lt(bars["prior_body_low"])
    )
    bars["is_bullish_engulf"] = bars["is_engulfing"] & bars["bar_close"].gt(bars["bar_open"])
    bars["is_bearish_engulf"] = bars["is_engulfing"] & bars["bar_close"].lt(bars["bar_open"])
    bars["engulf_direction_sign"] = np.select(
        [bars["is_bullish_engulf"], bars["is_bearish_engulf"]],
        [1, -1],
        default=0,
    )

    bars["is_four_narrowing_then_expansion"] = (
        bars["range_4"].notna()
        & bars["range_4"].gt(bars["range_3"])
        & bars["range_3"].gt(bars["range_2"])
        & bars["range_2"].gt(bars["range_1"])
        & bars["range_1"].gt(0)
        & bars["bar_range"].gt(1.5 * bars["range_1"])
    )

    bars["is_inside_bar"] = bars["bar_high"].lt(bars["prior_high"]) & bars["bar_low"].gt(bars["prior_low"])
    bars["prior_is_inside_bar"] = by_session["is_inside_bar"].shift(1).fillna(False).astype(bool)
    bars["is_upside_inside_breakout"] = (
        bars["prior_is_inside_bar"]
        & bars["bar_high"].gt(bars["prior_high"])
        & bars["bar_low"].ge(bars["prior_low"])
    )
    bars["is_downside_inside_breakout"] = (
        bars["prior_is_inside_bar"]
        & bars["bar_low"].lt(bars["prior_low"])
        & bars["bar_high"].le(bars["prior_high"])
    )
    bars["inside_breakout_direction_sign"] = np.select(
        [bars["is_upside_inside_breakout"], bars["is_downside_inside_breakout"]],
        [1, -1],
        default=0,
    )
    return bars


def add_context_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    rng_60m = out["range_60m"].replace(0, np.nan)
    out["pos_60m_low"] = (out["bar_low"] - out["low_60m"]) / rng_60m
    out["pos_60m_high"] = (out["bar_high"] - out["low_60m"]) / rng_60m
    out["is_60m_extreme_bullish"] = out["pos_60m_low"].le(0.20)
    out["is_60m_extreme_bearish"] = out["pos_60m_high"].ge(0.80)
    out["is_15m_trend_aligned_delta"] = out["direction_sign"].eq(out["trend_sign_15m"])
    return out


def normalize_direction(direction: int | pd.Series, df: pd.DataFrame) -> pd.Series:
    if isinstance(direction, pd.Series):
        series = direction.reindex(df.index)
    else:
        series = pd.Series(direction, index=df.index)
    series = pd.to_numeric(series, errors="coerce").fillna(0.0)
    return np.sign(series).astype(int)


def is_60m_extreme_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    return ((direction_sign > 0) & df["is_60m_extreme_bullish"]) | (
        (direction_sign < 0) & df["is_60m_extreme_bearish"]
    )


def is_15m_trend_aligned_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    return direction_sign.ne(0) & direction_sign.eq(df["trend_sign_15m"])


def summarize_filter(code: str, label: str, df: pd.DataFrame, direction: int | pd.Series) -> dict:
    direction_sign = normalize_direction(direction, df)
    valid = direction_sign.ne(0)
    sample = df.loc[valid].copy()
    sample["trade_direction_sign"] = direction_sign.loc[valid]

    windows: dict[int, dict[str, float | int]] = {}
    for window in FORWARD_WINDOWS:
        returns = (sample["trade_direction_sign"] * sample[f"move_{window}b_ticks"]).dropna()
        wins = int((returns > 0).sum())
        window_n = int(len(returns))
        windows[window] = {
            "n": window_n,
            "win_rate": (wins / window_n) if window_n else np.nan,
            "avg_return": float(returns.mean()) if window_n else np.nan,
        }

    returns_5b = (sample["trade_direction_sign"] * sample["move_5b_ticks"]).dropna()
    n = int(len(returns_5b))
    wins_5b = int((returns_5b > 0).sum())
    ci_low, ci_high, win_rate_5b = wilson_ci(n, wins_5b)

    return {
        "code": code,
        "label": label,
        "n": n,
        "wr_5b": win_rate_5b,
        "wr_10b": windows[10]["win_rate"],
        "wr_30b": windows[30]["win_rate"],
        "pf_5b": profit_factor(returns_5b) if n else np.nan,
        "avg_ticks_5b": float(returns_5b.mean()) if n else np.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "flag": status_flag(n, ci_low),
        "windows": windows,
    }


def build_filter_specs() -> list[tuple[str, str, Callable[[pd.DataFrame], pd.Series], Callable[[pd.DataFrame], int | pd.Series]]]:
    return [
        (
            "01",
            "Doji + 60m_extreme + delta reversal",
            lambda df: df["is_doji"] & df["is_delta_reversal"] & is_60m_extreme_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "02",
            "Doji + 60m_extreme + volume spike (>2x 20-bar EMA)",
            lambda df: df["is_doji"] & df["is_volume_spike_2x"] & is_60m_extreme_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "03",
            "Doji + 60m_extreme + prior bar wide range (>75th percentile)",
            lambda df: df["is_doji"] & df["is_prior_wide_range"] & is_60m_extreme_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "04",
            "Doji after 3-bar strong move + 60m_extreme",
            lambda df: df["is_doji_after_strong_move"] & is_60m_extreme_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "05",
            "Double doji (2 consecutive dojis) + 60m_extreme",
            lambda df: df["is_doji"] & df["prior_is_doji"] & is_60m_extreme_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "06",
            "Hammer + 60m_extreme",
            lambda df: df["is_hammer"] & is_60m_extreme_for(df, 1),
            lambda df: 1,
        ),
        (
            "07",
            "Shooting star + 60m_extreme",
            lambda df: df["is_shooting_star"] & is_60m_extreme_for(df, -1),
            lambda df: -1,
        ),
        (
            "08",
            "Hammer + 60m_extreme + 15m_trend_aligned",
            lambda df: df["is_hammer"] & is_60m_extreme_for(df, 1) & is_15m_trend_aligned_for(df, 1),
            lambda df: 1,
        ),
        (
            "09",
            "Shooting star + 60m_extreme + 15m_trend_aligned",
            lambda df: df["is_shooting_star"] & is_60m_extreme_for(df, -1) & is_15m_trend_aligned_for(df, -1),
            lambda df: -1,
        ),
        (
            "10",
            "Bullish engulf + 60m_extreme",
            lambda df: df["is_bullish_engulf"] & is_60m_extreme_for(df, 1),
            lambda df: 1,
        ),
        (
            "11",
            "Bearish engulf + 60m_extreme",
            lambda df: df["is_bearish_engulf"] & is_60m_extreme_for(df, -1),
            lambda df: -1,
        ),
        (
            "12",
            "Engulfing + 60m_extreme + 15m_trend_aligned",
            lambda df: df["engulf_direction_sign"].ne(0)
            & is_60m_extreme_for(df, df["engulf_direction_sign"])
            & is_15m_trend_aligned_for(df, df["engulf_direction_sign"]),
            lambda df: df["engulf_direction_sign"],
        ),
        (
            "13",
            "4+ narrowing ranges then expansion + 60m_extreme",
            lambda df: df["is_four_narrowing_then_expansion"] & is_60m_extreme_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "14",
            "Inside bar -> breakout bar + 60m_extreme",
            lambda df: df["inside_breakout_direction_sign"].ne(0)
            & is_60m_extreme_for(df, df["inside_breakout_direction_sign"]),
            lambda df: df["inside_breakout_direction_sign"],
        ),
        (
            "15",
            "Volume dry-up (<50% EMA) then spike (>150% EMA) + 60m_extreme",
            lambda df: df["prior_is_volume_dryup"]
            & df["is_volume_spike_150"]
            & is_60m_extreme_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
    ]


def run_filters(df: pd.DataFrame) -> list[dict]:
    results: list[dict] = []
    for code, label, predicate, direction_fn in build_filter_specs():
        mask = predicate(df)
        filtered = df.loc[mask].copy()
        direction = direction_fn(df)
        if isinstance(direction, pd.Series):
            direction = direction.loc[mask]
        results.append(summarize_filter(code, label, filtered, direction))
    return results


def render_table(rows: list[dict]) -> list[str]:
    headers = ["Filter", "N", "WR 5b", "WR 10b", "WR 30b", "PF 5b", "Avg Ticks 5b", "Wilson 95% CI (5b)", "Flag"]
    data_rows: list[list[str]] = []

    for row in rows:
        data_rows.append(
            [
                f"{row['code']}. {row['label']}",
                f"{row['n']:,}",
                fmt_pct(row["wr_5b"]),
                fmt_pct(row["wr_10b"]),
                fmt_pct(row["wr_30b"]),
                fmt_float(row["pf_5b"]),
                fmt_float(row["avg_ticks_5b"]),
                fmt_ci(row["ci_low"], row["ci_high"]),
                row["flag"],
            ]
        )

    widths = [len(header) for header in headers]
    for data_row in data_rows:
        for idx, cell in enumerate(data_row):
            widths[idx] = max(widths[idx], len(cell))

    def pad(cells: list[str]) -> str:
        return " | ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(cells))

    lines = [pad(headers), "-+-".join("-" * width for width in widths)]
    for data_row in data_rows:
        lines.append(pad(data_row))
    return lines


def render_summary_line(row: dict) -> str:
    return (
        f"N={row['n']:,} | WR5={fmt_pct(row['wr_5b'])} | WR10={fmt_pct(row['wr_10b'])} | "
        f"WR30={fmt_pct(row['wr_30b'])} | PF5={fmt_float(row['pf_5b'])} | "
        f"Avg5={fmt_float(row['avg_ticks_5b'])}t | CI5={fmt_ci(row['ci_low'], row['ci_high'])}"
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events = load_events()
    bars_1m = load_ohlcv()
    observations = build_observations(events)
    context = build_timeframe_context(bars_1m)
    observations = attach_context(observations, context)
    observations = compute_bar_features(observations)
    observations = add_context_flags(observations)

    non_zero_delta = observations[observations["direction_sign"].ne(0)].copy()
    delta_extreme_mask = is_60m_extreme_for(non_zero_delta, non_zero_delta["direction_sign"])
    doji_extreme_mask = observations["is_doji"] & is_60m_extreme_for(observations, observations["direction_sign"])

    baseline_all = summarize_filter("00", "All non-zero-delta signal bars", non_zero_delta, non_zero_delta["direction_sign"])
    baseline_60m = summarize_filter(
        "00A",
        "All non-zero-delta bars at 60m extreme",
        non_zero_delta.loc[delta_extreme_mask].copy(),
        non_zero_delta.loc[delta_extreme_mask, "direction_sign"],
    )
    baseline_doji = summarize_filter(
        "00B",
        "Doji + 60m_extreme",
        observations.loc[doji_extreme_mask].copy(),
        observations.loc[doji_extreme_mask, "direction_sign"],
    )
    results = run_filters(observations)

    lines = [
        "DEEP6 round 3 multi-bar sequence analysis",
        "==========================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index.",
        "Bar-sequence features are computed on the deduped global_index bar stream from signal_events.csv, following the round2_novel_bar_patterns.py workflow.",
        "5b/10b/30b returns are measured from bar_close to the forward close and multiplied by the filter direction.",
        "Direction rules: doji / compression / volume-sequence filters use sign(bar_delta); hammer = +1; shooting star = -1; bullish engulf = +1; bearish engulf = -1; inside-bar breakout uses breakout side.",
        "Doji = body/range < 0.10. Hammer / shooting star / engulfing follow the user-provided wick/body/body-containment rules.",
        "Doji-after-strong-move = prior 3 close-to-close moves all point the same way and opposite the doji trade direction.",
        "4+ narrowing ranges then expansion = prior four ranges strictly contract, then current range expands to >1.5x the prior bar range.",
        "Inside-bar breakout = prior bar is an inside bar and current bar breaks only one side of that prior range.",
        "60m_extreme = bullish setup anchors off bar_low in the bottom 20% of the 60m range; bearish setup anchors off bar_high in the top 20%.",
        "15m_trend_aligned compares the pattern direction to the 15m open-close sign.",
        "Status flags: VALIDATED = N>=30 and Wilson lower bound >50%; PROMISING = N>=15 and Wilson lower bound >45%; LOW_N = N<15.",
        "Requested filters are shown in the exact order requested.",
        "",
        f"Raw event rows loaded:          {len(events):,}",
        f"Grouped observations:           {len(observations):,}",
        f"15m bars built:                 {len(context[15]):,}",
        f"60m bars built:                 {len(context[60]):,}",
        f"Non-zero-delta observations:    {len(non_zero_delta):,}",
        f"Delta-directed 60m extremes:    {int(delta_extreme_mask.sum()):,}",
        f"Doji + 60m_extreme baseline N:  {int(doji_extreme_mask.sum()):,}",
        "",
        "Baselines",
        "---------",
        f"All non-zero-delta bars: {render_summary_line(baseline_all)}",
        f"60m extreme only:        {render_summary_line(baseline_60m)}",
        f"Doji + 60m_extreme:      {render_summary_line(baseline_doji)}",
        "",
        "15 requested multi-bar sequence filters",
        "---------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
