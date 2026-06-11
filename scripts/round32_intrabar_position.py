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
OUT_PATH = OUT_DIR / "round32_intrabar_position_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
RTH_START_MINUTE = 9 * 60 + 30
FIRST_HOUR_MINUTES = 60
EPSILON = 1e-9

FilterSpec = tuple[
    str,
    str,
    str,
    Callable[[pd.DataFrame], pd.Series],
    Callable[[pd.DataFrame], int | pd.Series],
]


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


def classify_persistence(win_rate_5b: float, win_rate_30b: float) -> str:
    if pd.isna(win_rate_5b) or pd.isna(win_rate_30b):
        return "NO_DATA"
    delta = win_rate_30b - win_rate_5b
    if delta > 0:
        return "GROWING"
    if abs(delta) < 0.03:
        return "STABLE"
    return "DECAYING"


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
    return df.sort_values(["session_date", "bar_ts", "global_index", "signal_id"], kind="stable").reset_index(drop=True)


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
        .sort_values(["session_date", "bar_ts", "global_index"], kind="stable")
        .reset_index(drop=True)
    )

    observations["direction_sign"] = np.sign(observations["bar_delta"].fillna(0.0)).astype(int)
    observations["direction"] = np.select(
        [observations["direction_sign"] > 0, observations["direction_sign"] < 0],
        ["BULLISH", "BEARISH"],
        default="FLAT",
    )
    for window in FORWARD_WINDOWS:
        observations[f"move_{window}b_ticks"] = (
            observations[f"fwd_close_{window}b"] - observations["bar_close"]
        ) / TICK_SIZE
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

    numeric_cols = [
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_delta",
        "bar_volume",
        "open_15m",
        "high_15m",
        "low_15m",
        "close_15m",
        "volume_15m",
        "range_15m",
        "open_60m",
        "high_60m",
        "low_60m",
        "close_60m",
        "volume_60m",
        "range_60m",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for tf in TIMEFRAMES:
        trend_col = f"trend_sign_{tf}m"
        if trend_col in df.columns:
            df[trend_col] = pd.to_numeric(df[trend_col], errors="coerce").fillna(0).astype(int)

    return df


def normalize_direction(direction: int | pd.Series, df: pd.DataFrame) -> pd.Series:
    if isinstance(direction, pd.Series):
        series = direction.reindex(df.index)
    else:
        series = pd.Series(direction, index=df.index)
    series = pd.to_numeric(series, errors="coerce").fillna(0.0)
    return np.sign(series).astype(int)


def anchor_pos_60m(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    rng_60m = df["range_60m"].replace(0, np.nan)
    anchor = np.where(direction_sign > 0, df["bar_low"], np.where(direction_sign < 0, df["bar_high"], np.nan))
    return pd.Series((anchor - df["low_60m"]) / rng_60m, index=df.index)


def is_60m_extreme_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    pos_60m = anchor_pos_60m(df, direction_sign)
    return ((direction_sign > 0) & pos_60m.le(0.20)) | ((direction_sign < 0) & pos_60m.ge(0.80))


def is_15m_trend_aligned_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    return direction_sign.ne(0) & direction_sign.eq(df["trend_sign_15m"])


def has_core_60m_15m_gate_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    return is_60m_extreme_for(df, direction) & is_15m_trend_aligned_for(df, direction)


def passes_not_all_killers_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    pos_60m = anchor_pos_60m(df, direction_sign)
    not_middle_60m = ~pos_60m.between(0.40, 0.60, inclusive="both")
    return direction_sign.ne(0) & not_middle_60m & (~df["is_volume_spike_3x"])


def compute_intrabar_features(observations: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    valid_range = out["bar_range"].gt(0)

    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["body_high"] = np.maximum(out["bar_open"], out["bar_close"])
    out["body_low"] = np.minimum(out["bar_open"], out["bar_close"])
    out["upper_wick"] = out["bar_high"] - out["body_high"]
    out["lower_wick"] = out["body_low"] - out["bar_low"]
    out["dominant_wick"] = np.maximum(out["upper_wick"], out["lower_wick"])
    out["body_ratio"] = np.where(valid_range, out["body"] / out["bar_range"], np.nan)
    out["close_position"] = np.where(valid_range, (out["bar_close"] - out["bar_low"]) / out["bar_range"], np.nan)
    out["open_position"] = np.where(valid_range, (out["bar_open"] - out["bar_low"]) / out["bar_range"], np.nan)
    out["wick_to_body_ratio"] = np.where(
        out["body"].gt(0),
        out["dominant_wick"] / out["body"],
        np.where(out["dominant_wick"].gt(0), np.inf, np.nan),
    )

    out["prev_close"] = by_session["bar_close"].shift(1)
    out["is_green_bar"] = out["bar_close"].gt(out["bar_open"])
    out["is_red_bar"] = out["bar_close"].lt(out["bar_open"])
    out["is_close_middle"] = out["close_position"].between(0.40, 0.60, inclusive="both")
    out["is_full_body"] = out["body_ratio"].gt(0.80)
    out["is_spinning_top"] = out["upper_wick"].gt(out["body"]) & out["lower_wick"].gt(out["body"])
    out["has_no_upper_wick"] = out["upper_wick"].abs().le(EPSILON)
    out["has_extreme_wick_rejection"] = out["wick_to_body_ratio"].gt(3.0)

    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])

    out["has_core_60m_15m_gate"] = has_core_60m_15m_gate_for(out, out["direction_sign"])
    out["passes_not_all_killers"] = passes_not_all_killers_for(out, out["direction_sign"])

    bool_cols = [
        "is_green_bar",
        "is_red_bar",
        "is_close_middle",
        "is_full_body",
        "is_spinning_top",
        "has_no_upper_wick",
        "has_extreme_wick_rejection",
        "is_volume_spike_3x",
        "has_core_60m_15m_gate",
        "passes_not_all_killers",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)

    return out


def add_time_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] * 60 + out["minute"]) - RTH_START_MINUTE
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(FIRST_HOUR_MINUTES)
    out["is_first_hour"] = out["is_first_hour"].fillna(False).astype(bool)
    return out


def build_trade_sample(source_df: pd.DataFrame, direction: int | pd.Series) -> pd.DataFrame:
    sample = source_df.copy()
    sample["trade_sign"] = normalize_direction(direction, sample)
    sample = sample.loc[sample["trade_sign"].ne(0)].copy()
    for window in FORWARD_WINDOWS:
        sample[f"ret_{window}b_ticks"] = sample["trade_sign"] * sample[f"move_{window}b_ticks"]
    return sample.reset_index(drop=True)


def summarize_filter(code: str, group: str, label: str, sample: pd.DataFrame) -> dict[str, object]:
    required_cols = [f"ret_{window}b_ticks" for window in FORWARD_WINDOWS]
    clean = sample.dropna(subset=required_cols).copy()
    n = int(len(clean))
    win_rates: dict[int, float] = {}

    for window in FORWARD_WINDOWS:
        returns = clean[f"ret_{window}b_ticks"]
        win_rates[window] = float((returns > 0).mean()) if n else np.nan

    returns_5b = clean["ret_5b_ticks"]
    wins_5b = int((returns_5b > 0).sum())
    ci_low, ci_high, win_rate_5b = wilson_ci(n, wins_5b)

    return {
        "code": code,
        "group": group,
        "label": label,
        "n": n,
        "wr_5b": win_rate_5b,
        "wr_10b": win_rates[10],
        "wr_30b": win_rates[30],
        "pf_5b": profit_factor(returns_5b) if n else np.nan,
        "avg_ticks_5b": float(returns_5b.mean()) if n else np.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "persistence": classify_persistence(win_rate_5b, win_rates[30]),
    }


def render_summary_line(row: dict[str, object]) -> str:
    return (
        f"N={int(row['n']):,} | WR5={fmt_pct(float(row['wr_5b']))} | WR10={fmt_pct(float(row['wr_10b']))} | "
        f"WR30={fmt_pct(float(row['wr_30b']))} | PF5={fmt_float(float(row['pf_5b']))} | "
        f"Avg5={fmt_float(float(row['avg_ticks_5b']))}t | CI5={fmt_ci(float(row['ci_low']), float(row['ci_high']))} | "
        f"Persistence={row['persistence']}"
    )


def build_filter_specs() -> list[FilterSpec]:
    return [
        (
            "01",
            "A",
            "Close in bottom 20% + bullish signal + 60m + 15m",
            lambda df: df["close_position"].le(0.20)
            & df["direction_sign"].gt(0)
            & has_core_60m_15m_gate_for(df, 1),
            lambda df: 1,
        ),
        (
            "02",
            "A",
            "Close in top 20% + bearish signal + 60m + 15m",
            lambda df: df["close_position"].ge(0.80)
            & df["direction_sign"].lt(0)
            & has_core_60m_15m_gate_for(df, -1),
            lambda df: -1,
        ),
        (
            "03",
            "A",
            "Close in bottom 20% + bullish + 60m + 15m + NOT killers",
            lambda df: df["close_position"].le(0.20)
            & df["direction_sign"].gt(0)
            & has_core_60m_15m_gate_for(df, 1)
            & passes_not_all_killers_for(df, 1),
            lambda df: 1,
        ),
        (
            "04",
            "A",
            "Close in top 20% + bearish + 60m + 15m + NOT killers",
            lambda df: df["close_position"].ge(0.80)
            & df["direction_sign"].lt(0)
            & has_core_60m_15m_gate_for(df, -1)
            & passes_not_all_killers_for(df, -1),
            lambda df: -1,
        ),
        (
            "05",
            "A",
            "Close in middle 40%-60% + 60m + 15m",
            lambda df: df["is_close_middle"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "06",
            "B",
            "Close above open + bullish signal + 60m + 15m",
            lambda df: df["is_green_bar"] & df["direction_sign"].gt(0) & has_core_60m_15m_gate_for(df, 1),
            lambda df: 1,
        ),
        (
            "07",
            "B",
            "Close below open + bullish signal + 60m + 15m",
            lambda df: df["is_red_bar"] & df["direction_sign"].gt(0) & has_core_60m_15m_gate_for(df, 1),
            lambda df: 1,
        ),
        (
            "08",
            "B",
            "Close above open + bearish signal + 60m + 15m",
            lambda df: df["is_green_bar"] & df["direction_sign"].lt(0) & has_core_60m_15m_gate_for(df, -1),
            lambda df: -1,
        ),
        (
            "09",
            "B",
            "Close below open + bearish signal + 60m + 15m",
            lambda df: df["is_red_bar"] & df["direction_sign"].lt(0) & has_core_60m_15m_gate_for(df, -1),
            lambda df: -1,
        ),
        (
            "10",
            "B",
            "|close-open| > 80% of range + 60m + 15m",
            lambda df: df["is_full_body"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "11",
            "C",
            "Upper wick > lower wick + bearish signal + 60m + 15m",
            lambda df: df["upper_wick"].gt(df["lower_wick"])
            & df["direction_sign"].lt(0)
            & has_core_60m_15m_gate_for(df, -1),
            lambda df: -1,
        ),
        (
            "12",
            "C",
            "Lower wick > upper wick + bullish signal + 60m + 15m",
            lambda df: df["lower_wick"].gt(df["upper_wick"])
            & df["direction_sign"].gt(0)
            & has_core_60m_15m_gate_for(df, 1),
            lambda df: 1,
        ),
        (
            "13",
            "C",
            "Both wicks > body + 60m + 15m",
            lambda df: df["is_spinning_top"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "14",
            "C",
            "No upper wick + 60m + 15m",
            lambda df: df["has_no_upper_wick"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "15",
            "C",
            "Dominant wick / body > 3 + 60m + 15m",
            lambda df: df["has_extreme_wick_rejection"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "16",
            "D",
            "Current close > prior close + bullish signal + 60m + 15m",
            lambda df: df["prev_close"].notna()
            & df["bar_close"].gt(df["prev_close"])
            & df["direction_sign"].gt(0)
            & has_core_60m_15m_gate_for(df, 1),
            lambda df: 1,
        ),
        (
            "17",
            "D",
            "Current close < prior close + bullish signal + 60m + 15m",
            lambda df: df["prev_close"].notna()
            & df["bar_close"].lt(df["prev_close"])
            & df["direction_sign"].gt(0)
            & has_core_60m_15m_gate_for(df, 1),
            lambda df: 1,
        ),
        (
            "18",
            "D",
            "Current close > prior close + bearish signal + 60m + 15m",
            lambda df: df["prev_close"].notna()
            & df["bar_close"].gt(df["prev_close"])
            & df["direction_sign"].lt(0)
            & has_core_60m_15m_gate_for(df, -1),
            lambda df: -1,
        ),
        (
            "19",
            "D",
            "Current close < prior close + bearish signal + 60m + 15m",
            lambda df: df["prev_close"].notna()
            & df["bar_close"].lt(df["prev_close"])
            & df["direction_sign"].lt(0)
            & has_core_60m_15m_gate_for(df, -1),
            lambda df: -1,
        ),
        (
            "20",
            "E",
            "Lower wick > upper wick + close in bottom 20% + bullish + 60m + 15m + NOT killers + first_hour",
            lambda df: df["lower_wick"].gt(df["upper_wick"])
            & df["close_position"].le(0.20)
            & df["direction_sign"].gt(0)
            & has_core_60m_15m_gate_for(df, 1)
            & passes_not_all_killers_for(df, 1)
            & df["is_first_hour"],
            lambda df: 1,
        ),
    ]


def run_filters(df: pd.DataFrame) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for code, group, label, predicate, direction_fn in build_filter_specs():
        mask = predicate(df).fillna(False)
        filtered = df.loc[mask].copy()
        direction = direction_fn(df)
        if isinstance(direction, pd.Series):
            direction = direction.loc[mask]
        sample = build_trade_sample(filtered, direction)
        results.append(summarize_filter(code, group, label, sample))

    results.sort(
        key=lambda row: (
            float("-inf") if pd.isna(row["wr_30b"]) else float(row["wr_30b"]),
            float("-inf") if pd.isna(row["wr_10b"]) else float(row["wr_10b"]),
            float("-inf") if pd.isna(row["wr_5b"]) else float(row["wr_5b"]),
            int(row["n"]),
        ),
        reverse=True,
    )
    return results


def render_table(rows: list[dict[str, object]]) -> list[str]:
    headers = [
        "Filter",
        "N",
        "WR 5b",
        "WR 10b",
        "WR 30b",
        "PF 5b",
        "Avg Ticks 5b",
        "Wilson 95% CI (5b)",
        "Persistence",
    ]
    data_rows: list[list[str]] = []

    for row in rows:
        data_rows.append(
            [
                f"{row['code']}. [{row['group']}] {row['label']}",
                f"{int(row['n']):,}",
                fmt_pct(float(row["wr_5b"])),
                fmt_pct(float(row["wr_10b"])),
                fmt_pct(float(row["wr_30b"])),
                fmt_float(float(row["pf_5b"])),
                fmt_float(float(row["avg_ticks_5b"])),
                fmt_ci(float(row["ci_low"]), float(row["ci_high"])),
                str(row["persistence"]),
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


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events = load_events()
    bars_1m = load_ohlcv()

    observations = build_observations(events)
    timeframe_context = build_timeframe_context(bars_1m)
    observations = attach_context(observations, timeframe_context)
    observations = compute_intrabar_features(observations)
    observations = add_time_flags(observations)

    all_signal_bars = build_trade_sample(observations, observations["direction_sign"])
    core_signal_bars = all_signal_bars.loc[all_signal_bars["has_core_60m_15m_gate"]].copy()
    core_not_killers = core_signal_bars.loc[core_signal_bars["passes_not_all_killers"]].copy()
    core_not_killers_first_hour = core_signal_bars.loc[
        core_signal_bars["passes_not_all_killers"] & core_signal_bars["is_first_hour"]
    ].copy()

    baseline_all = summarize_filter("00", "BASE", "All non-zero-delta signal bars", all_signal_bars)
    baseline_core = summarize_filter("00A", "BASE", "60m + 15m core sample", core_signal_bars)
    baseline_core_not_killers = summarize_filter(
        "00B",
        "BASE",
        "60m + 15m + NOT killers",
        core_not_killers,
    )
    baseline_core_not_killers_first_hour = summarize_filter(
        "00C",
        "BASE",
        "60m + 15m + NOT killers + first_hour",
        core_not_killers_first_hour,
    )
    results = run_filters(observations)

    lines = [
        "DEEP6 round32 intrabar position analysis",
        "=======================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index.",
        "Bullish signal = direction_sign > 0 from bar_delta. Bearish signal = direction_sign < 0 from bar_delta.",
        "close_position = (bar_close - bar_low) / (bar_high - bar_low). open_position = (bar_open - bar_low) / (bar_high - bar_low).",
        "Upper wick = high - max(open, close). Lower wick = min(open, close) - low. Body = abs(close - open).",
        "60m + 15m = trade-direction 60m extreme (bull anchor in bottom 20%, bear anchor in top 20%) plus 15m open-close trend alignment.",
        "NOT killers = NOT killer_1 (trade anchor in middle 40%-60% of the active 60m range) AND NOT killer_2 (bar_volume > 3x prior 20-bar EMA).",
        "first_hour = 09:30-10:29 ET. Dominant wick/body > 3 treats zero-body bars with non-zero dominant wick as infinite rejection.",
        "PF, Avg Ticks, and Wilson CI are reported on the 5-bar horizon; WR columns show 5b / 10b / 30b as requested.",
        "Rows are sorted by 30b WR, then 10b WR, then 5b WR, then N.",
        "",
        f"Raw event rows loaded:                 {len(events):,}",
        f"Grouped signal bars:                   {len(observations):,}",
        f"Tradable non-zero-delta bars:          {len(all_signal_bars):,}",
        f"15m bars built:                        {len(timeframe_context[15]):,}",
        f"60m bars built:                        {len(timeframe_context[60]):,}",
        f"60m + 15m core bars:                   {len(core_signal_bars):,}",
        f"60m + 15m + NOT killers bars:          {len(core_not_killers):,}",
        f"60m + 15m + NOT killers + first_hour:  {len(core_not_killers_first_hour):,}",
        f"Close in bottom 20% bars:              {int(observations['close_position'].le(0.20).sum()):,}",
        f"Close in top 20% bars:                 {int(observations['close_position'].ge(0.80).sum()):,}",
        f"Full-body bars (>80% range):           {int(observations['is_full_body'].sum()):,}",
        f"Spinning-top bars:                     {int(observations['is_spinning_top'].sum()):,}",
        f"No-upper-wick bars:                    {int(observations['has_no_upper_wick'].sum()):,}",
        f"Extreme wick/body>3 bars:              {int(observations['has_extreme_wick_rejection'].sum()):,}",
        "",
        "Baselines",
        "---------",
        f"All non-zero-delta bars:          {render_summary_line(baseline_all)}",
        f"60m + 15m core:                   {render_summary_line(baseline_core)}",
        f"60m + 15m + NOT killers:          {render_summary_line(baseline_core_not_killers)}",
        f"60m + 15m + NOT killers + 1st hr: {render_summary_line(baseline_core_not_killers_first_hour)}",
        "",
        "20 requested intrabar-position filters sorted by 30b WR",
        "----------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
