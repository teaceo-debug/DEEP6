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
OUT_PATH = OUT_DIR / "round33_dynamic_thresholds_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 50
EMA_LOOKBACK = 20
ATR_LOOKBACK = 20
VOL_OF_VOL_LOOKBACK = 10
RTH_START_MINUTE = 9 * 60 + 30
FIRST_HOUR_MINUTES = 60

FilterSpec = tuple[str, str, str, Callable[[pd.DataFrame], pd.Series]]


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


def attach_timeframe_context(observations: pd.DataFrame, context: dict[int, pd.DataFrame]) -> pd.DataFrame:
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

    return df.reset_index(drop=True)


def compute_bar_features(observations: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["body_ratio"] = np.where(out["bar_range"] > 0, out["body"] / out["bar_range"], np.nan)
    out["abs_delta"] = out["bar_delta"].abs()
    out["delta_ratio"] = np.where(out["bar_volume"] > 0, out["abs_delta"] / out["bar_volume"], np.nan)

    out["prior_close"] = by_session["bar_close"].shift(1)
    true_range_parts = pd.concat(
        [
            out["bar_high"] - out["bar_low"],
            (out["bar_high"] - out["prior_close"]).abs(),
            (out["bar_low"] - out["prior_close"]).abs(),
        ],
        axis=1,
    )
    out["true_range"] = true_range_parts.max(axis=1)
    out["atr20"] = by_session["true_range"].transform(
        lambda s: s.rolling(ATR_LOOKBACK, min_periods=ATR_LOOKBACK).mean()
    )
    out["vol_of_vol_10"] = by_session["atr20"].transform(
        lambda s: s.rolling(VOL_OF_VOL_LOOKBACK, min_periods=VOL_OF_VOL_LOOKBACK).std()
    )

    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=EMA_LOOKBACK, adjust=False, min_periods=EMA_LOOKBACK).mean().shift(1)
    )
    out["rolling_20_sma_vol"] = by_session["bar_volume"].transform(
        lambda s: s.shift(1).rolling(EMA_LOOKBACK, min_periods=EMA_LOOKBACK).mean()
    )

    out["range_q25_50"] = by_session["bar_range"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.25)
    )
    out["delta_ratio_q10_50"] = by_session["delta_ratio"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.10)
    )
    out["abs_delta_q10_50"] = by_session["abs_delta"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.10)
    )
    out["abs_delta_q90_50"] = by_session["abs_delta"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.90)
    )
    out["volume_q25_50"] = by_session["bar_volume"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.25)
    )
    out["volume_q75_50"] = by_session["bar_volume"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.75)
    )
    out["volume_q90_50"] = by_session["bar_volume"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.90)
    )
    out["vol_of_vol_q25_50"] = by_session["vol_of_vol_10"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.25)
    )

    out["session_avg_range_so_far"] = by_session["bar_range"].transform(lambda s: s.shift(1).expanding().mean())
    out["session_avg_volume_so_far"] = by_session["bar_volume"].transform(lambda s: s.shift(1).expanding().mean())
    out["is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.20 * out["bar_range"])
    return out


def add_context_flags(observations: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()

    out["is_15m_trend_aligned"] = out["direction_sign"].eq(out["trend_sign_15m"])
    rng_60m = out["range_60m"].replace(0, np.nan)
    out["signal_price"] = np.where(out["direction_sign"] > 0, out["bar_low"], np.where(out["direction_sign"] < 0, out["bar_high"], np.nan))
    out["pos_in_60m"] = (out["signal_price"] - out["low_60m"]) / rng_60m
    out["is_60m_extreme"] = (
        ((out["direction_sign"] > 0) & out["pos_in_60m"].le(0.20))
        | ((out["direction_sign"] < 0) & out["pos_in_60m"].ge(0.80))
    )
    out["has_core_60m_15m_gate"] = out["is_60m_extreme"] & out["is_15m_trend_aligned"]

    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] * 60 + out["minute"]) - RTH_START_MINUTE
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(FIRST_HOUR_MINUTES)

    out["is_killer_1"] = out["pos_in_60m"].between(0.40, 0.60, inclusive="both")
    out["is_killer_2"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])
    out["passes_not_all_killers"] = (~out["is_killer_1"]) & (~out["is_killer_2"])

    out["is_stable_vol_adaptive"] = out["vol_of_vol_10"].lt(out["vol_of_vol_q25_50"])

    bool_cols = [
        "is_doji",
        "is_15m_trend_aligned",
        "is_60m_extreme",
        "has_core_60m_15m_gate",
        "is_first_hour",
        "is_killer_1",
        "is_killer_2",
        "passes_not_all_killers",
        "is_stable_vol_adaptive",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out.reset_index(drop=True)


def compute_fixed_thresholds(sample: pd.DataFrame) -> dict[str, float]:
    non_zero = sample.loc[sample["direction_sign"].ne(0)].copy()
    bar_range = non_zero["bar_range"].dropna()
    bar_volume = non_zero["bar_volume"].dropna()
    return {
        "fixed_range_q25": float(bar_range.quantile(0.25)) if not bar_range.empty else float("nan"),
        "fixed_volume_median": float(bar_volume.median()) if not bar_volume.empty else float("nan"),
    }


def build_trade_sample(observations: pd.DataFrame) -> pd.DataFrame:
    sample = observations.loc[observations["direction_sign"].ne(0)].copy()
    sample["trade_sign"] = sample["direction_sign"]
    for window in FORWARD_WINDOWS:
        sample[f"ret_{window}b_ticks"] = sample["trade_sign"] * sample[f"move_{window}b_ticks"]
    return sample.reset_index(drop=True)


def summarize_filter(code: str, group: str, label: str, df: pd.DataFrame) -> dict[str, object]:
    required_cols = [f"ret_{window}b_ticks" for window in FORWARD_WINDOWS]
    sample = df.dropna(subset=required_cols).copy()
    n = int(len(sample))
    win_rates: dict[int, float] = {}

    for window in FORWARD_WINDOWS:
        returns = sample[f"ret_{window}b_ticks"]
        win_rates[window] = float((returns > 0).mean()) if n else np.nan

    returns_5b = sample["ret_5b_ticks"]
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


def build_filter_specs(thresholds: dict[str, float]) -> list[FilterSpec]:
    fixed_range_q25 = thresholds["fixed_range_q25"]
    fixed_volume_median = thresholds["fixed_volume_median"]

    return [
        (
            "01",
            "A",
            "Range < 50-bar rolling q25 + 60m + 15m",
            lambda df: df["bar_range"].lt(df["range_q25_50"]) & df["has_core_60m_15m_gate"],
        ),
        (
            "02",
            "A",
            "Range < fixed sample q25 + 60m + 15m",
            lambda df: df["bar_range"].lt(fixed_range_q25) & df["has_core_60m_15m_gate"],
        ),
        (
            "03",
            "A",
            "Volume > 2x prior 20-bar EMA + 60m + 15m",
            lambda df: df["rolling_20_ema_vol"].gt(0)
            & df["bar_volume"].gt(2.0 * df["rolling_20_ema_vol"])
            & df["has_core_60m_15m_gate"],
        ),
        (
            "04",
            "A",
            "Volume > 2x fixed median volume + 60m + 15m",
            lambda df: df["bar_volume"].gt(2.0 * fixed_volume_median) & df["has_core_60m_15m_gate"],
        ),
        (
            "05",
            "A",
            "|delta|/vol < 50-bar rolling q10 + 60m + 15m",
            lambda df: df["delta_ratio"].lt(df["delta_ratio_q10_50"]) & df["has_core_60m_15m_gate"],
        ),
        (
            "06",
            "B",
            "Range < 0.5x ATR20 + 60m + 15m",
            lambda df: df["atr20"].gt(0) & df["bar_range"].lt(0.50 * df["atr20"]) & df["has_core_60m_15m_gate"],
        ),
        (
            "07",
            "B",
            "Range < 0.3x ATR20 + 60m + 15m",
            lambda df: df["atr20"].gt(0) & df["bar_range"].lt(0.30 * df["atr20"]) & df["has_core_60m_15m_gate"],
        ),
        (
            "08",
            "B",
            "Range > 2x ATR20 + 60m + 15m",
            lambda df: df["atr20"].gt(0) & df["bar_range"].gt(2.0 * df["atr20"]) & df["has_core_60m_15m_gate"],
        ),
        (
            "09",
            "B",
            "Range 0.3-0.7x ATR20 + 60m + 15m",
            lambda df: df["atr20"].gt(0)
            & df["bar_range"].ge(0.30 * df["atr20"])
            & df["bar_range"].le(0.70 * df["atr20"])
            & df["has_core_60m_15m_gate"],
        ),
        (
            "10",
            "B",
            "Range < 0.5x ATR20 + doji + 60m + 15m + NOT killers",
            lambda df: df["atr20"].gt(0)
            & df["bar_range"].lt(0.50 * df["atr20"])
            & df["is_doji"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
        ),
        (
            "11",
            "C",
            "|delta| > 50-bar rolling q90 + 60m + 15m",
            lambda df: df["abs_delta"].gt(df["abs_delta_q90_50"]) & df["has_core_60m_15m_gate"],
        ),
        (
            "12",
            "C",
            "|delta| < 50-bar rolling q10 + 60m + 15m",
            lambda df: df["abs_delta"].lt(df["abs_delta_q10_50"]) & df["has_core_60m_15m_gate"],
        ),
        (
            "13",
            "C",
            "|delta|/vol < 50-bar rolling q10 + doji + 60m + 15m + NOT killers",
            lambda df: df["delta_ratio"].lt(df["delta_ratio_q10_50"])
            & df["is_doji"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
        ),
        (
            "14",
            "C",
            "Volume > 50-bar rolling q90 + range < 0.5x ATR20 + 60m + 15m",
            lambda df: df["atr20"].gt(0)
            & df["bar_volume"].gt(df["volume_q90_50"])
            & df["bar_range"].lt(0.50 * df["atr20"])
            & df["has_core_60m_15m_gate"],
        ),
        (
            "15",
            "C",
            "Volume in 50-bar rolling 25th-75th pct + 60m + 15m",
            lambda df: df["bar_volume"].ge(df["volume_q25_50"])
            & df["bar_volume"].le(df["volume_q75_50"])
            & df["has_core_60m_15m_gate"],
        ),
        (
            "16",
            "D",
            "Low delta/vol + low range + 60m + 15m + NOT killers",
            lambda df: df["atr20"].gt(0)
            & df["delta_ratio"].lt(df["delta_ratio_q10_50"])
            & df["bar_range"].lt(0.50 * df["atr20"])
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
        ),
        (
            "17",
            "D",
            "High volume + low range + low delta/vol + 60m + 15m + NOT killers",
            lambda df: df["atr20"].gt(0)
            & df["bar_volume"].gt(df["volume_q90_50"])
            & df["bar_range"].lt(0.50 * df["atr20"])
            & df["delta_ratio"].lt(df["delta_ratio_q10_50"])
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
        ),
        (
            "18",
            "D",
            "Low delta/vol + stable vol + first_hour + 60m + 15m + NOT killers",
            lambda df: df["delta_ratio"].lt(df["delta_ratio_q10_50"])
            & df["is_stable_vol_adaptive"]
            & df["is_first_hour"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
        ),
        (
            "19",
            "E",
            "Range < 50% of session avg range so far + 60m + 15m",
            lambda df: df["session_avg_range_so_far"].gt(0)
            & df["bar_range"].lt(0.50 * df["session_avg_range_so_far"])
            & df["has_core_60m_15m_gate"],
        ),
        (
            "20",
            "E",
            "Volume > 200% of session avg volume so far + 60m + 15m",
            lambda df: df["session_avg_volume_so_far"].gt(0)
            & df["bar_volume"].gt(2.0 * df["session_avg_volume_so_far"])
            & df["has_core_60m_15m_gate"],
        ),
    ]


def run_filters(sample: pd.DataFrame, thresholds: dict[str, float]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for code, group, label, predicate in build_filter_specs(thresholds):
        filtered = sample.loc[predicate(sample)].copy()
        results.append(summarize_filter(code, group, label, filtered))

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


def build_result_lookup(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(row["code"]): row for row in rows}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events = load_events()
    bars_1m = load_ohlcv()

    observations = build_observations(events)
    timeframe_context = build_timeframe_context(bars_1m)
    observations = attach_timeframe_context(observations, timeframe_context)
    observations = compute_bar_features(observations)
    observations = add_context_flags(observations)

    sample = build_trade_sample(observations)
    thresholds = compute_fixed_thresholds(sample)
    results = run_filters(sample, thresholds)
    result_lookup = build_result_lookup(results)

    base_all = summarize_filter("00", "BASE", "All non-zero-delta signal bars", sample)
    base_core = summarize_filter(
        "00A",
        "BASE",
        "60m + 15m core gate",
        sample.loc[sample["has_core_60m_15m_gate"]].copy(),
    )
    base_core_not_killers = summarize_filter(
        "00B",
        "BASE",
        "60m + 15m + NOT killers",
        sample.loc[sample["has_core_60m_15m_gate"] & sample["passes_not_all_killers"]].copy(),
    )

    lines = [
        "DEEP6 round33 dynamic threshold analysis",
        "=======================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index.",
        "Trade direction for scoring: sign(bar_delta). Zero-delta bars are excluded from returns.",
        "60m gate = bullish bar_low in bottom 20% of active 60m range / bearish bar_high in top 20% of active 60m range.",
        "15m gate = trade direction matches 15m open-close trend sign.",
        "Adaptive rolling thresholds use the PRIOR 50 deduped signal bars within each session.",
        "Volume EMA uses the PRIOR 20 signal bars within each session. ATR20 = rolling 20-bar mean of true range on deduped signal bars.",
        "Session-relative filters use the expanding mean of PRIOR bars within the same session.",
        "Doji = body < 20% of range.",
        "KILLER_1 = trade-direction anchor sits in the middle 40-60% of the active 60m range. KILLER_2 = bar_volume > 3x prior 20-bar EMA volume.",
        "Stable vol for filter 18 = vol-of-vol(ATR20) below its prior 50-bar rolling 25th percentile within the session.",
        "Fixed thresholds: range q25 and median volume are computed from the full non-zero-delta deduped signal-bar sample.",
        "PF / Avg Ticks columns use 5-bar trade returns, matching prior round scripts.",
        "Persistence: GROWING if WR_30b > WR_5b; STABLE if WR_30b is within 3 percentage points of WR_5b without growth; DECAYING otherwise.",
        "",
        f"Raw event rows loaded:                    {len(events):,}",
        f"Grouped signal bars:                      {len(observations):,}",
        f"Non-zero-delta trade sample:              {len(sample):,}",
        f"15m bars built:                           {len(timeframe_context[15]):,}",
        f"60m bars built:                           {len(timeframe_context[60]):,}",
        f"Core 60m + 15m bars:                      {int(sample['has_core_60m_15m_gate'].sum()):,}",
        f"NOT-killer core bars:                     {int((sample['has_core_60m_15m_gate'] & sample['passes_not_all_killers']).sum()):,}",
        f"Rolling-50 range threshold ready bars:    {int(sample['range_q25_50'].notna().sum()):,}",
        f"Rolling-50 delta-ratio ready bars:        {int(sample['delta_ratio_q10_50'].notna().sum()):,}",
        f"ATR20 ready bars:                         {int(sample['atr20'].notna().sum()):,}",
        f"Session-relative range ready bars:        {int(sample['session_avg_range_so_far'].notna().sum()):,}",
        f"Stable-vol adaptive ready bars:           {int(sample['vol_of_vol_q25_50'].notna().sum()):,}",
        f"Doji bars:                                {int(sample['is_doji'].sum()):,}",
        f"First-hour bars:                          {int(sample['is_first_hour'].sum()):,}",
        f"KILLER_1 hits:                            {int(sample['is_killer_1'].sum()):,}",
        f"KILLER_2 hits:                            {int(sample['is_killer_2'].sum()):,}",
        f"Fixed sample q25 range:                   {fmt_float(thresholds['fixed_range_q25'])}",
        f"Fixed sample median volume:               {fmt_float(thresholds['fixed_volume_median'])}",
        "",
        "Baselines",
        "---------",
        f"All non-zero-delta bars:  {render_summary_line(base_all)}",
        f"60m + 15m core gate:     {render_summary_line(base_core)}",
        f"60m + 15m + NOT killers: {render_summary_line(base_core_not_killers)}",
        "",
        "Adaptive vs fixed checkpoints",
        "-----------------------------",
        f"01 adaptive narrow range: {render_summary_line(result_lookup['01'])}",
        f"02 fixed narrow range:    {render_summary_line(result_lookup['02'])}",
        f"03 adaptive volume spike: {render_summary_line(result_lookup['03'])}",
        f"04 fixed volume spike:    {render_summary_line(result_lookup['04'])}",
        "",
        "20 dynamic-threshold filters ranked by 30b win rate",
        "-----------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
