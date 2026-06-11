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
OUT_PATH = OUT_DIR / "round12_bar_microstructure_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
VOLUME_LOOKBACK = 10
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

    for col in ["bar_open", "bar_high", "bar_low", "bar_close", "bar_delta", "bar_volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.reset_index(drop=True)


def compute_bar_features(observations: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["upper_wick"] = out["bar_high"] - np.maximum(out["bar_open"], out["bar_close"])
    out["lower_wick"] = np.minimum(out["bar_open"], out["bar_close"]) - out["bar_low"]
    out["delta_ratio"] = np.where(out["bar_volume"] > 0, out["bar_delta"].abs() / out["bar_volume"], np.nan)
    out["abs_delta"] = out["bar_delta"].abs()
    out["price_change"] = out["bar_close"] - out["bar_open"]
    out["price_sign"] = np.sign(out["price_change"]).astype(int)
    out["body_ratio"] = np.where(out["bar_range"] > 0, out["body"] / out["bar_range"], np.nan)

    out["prior_bar_range"] = by_session["bar_range"].shift(1)
    out["bar_range_2"] = by_session["bar_range"].shift(2)
    out["prior_price_sign"] = by_session["price_sign"].shift(1)
    out["price_sign_2"] = by_session["price_sign"].shift(2)
    out["prior_abs_delta"] = by_session["abs_delta"].shift(1)
    out["abs_delta_2"] = by_session["abs_delta"].shift(2)
    out["prior_bar_delta"] = by_session["bar_delta"].shift(1)
    out["prior_bar_volume"] = by_session["bar_volume"].shift(1)
    out["bar_volume_2"] = by_session["bar_volume"].shift(2)
    out["bar_volume_3"] = by_session["bar_volume"].shift(3)

    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    out["range_q25"] = by_session["bar_range"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.25)
    )
    out["rolling_vol_max_10"] = by_session["bar_volume"].transform(
        lambda s: s.rolling(VOLUME_LOOKBACK, min_periods=VOLUME_LOOKBACK).max()
    )

    out["is_high_delta_ratio"] = out["delta_ratio"].gt(0.50)
    out["is_low_delta_ratio"] = out["delta_ratio"].lt(0.10)
    out["is_very_low_delta_ratio"] = out["delta_ratio"].lt(0.05)
    out["is_price_delta_divergence"] = (
        out["price_sign"].ne(0)
        & out["direction_sign"].ne(0)
        & out["price_sign"].eq(-out["direction_sign"])
    )
    out["is_price_delta_alignment"] = (
        out["price_sign"].ne(0)
        & out["direction_sign"].ne(0)
        & out["price_sign"].eq(out["direction_sign"])
    )

    out["is_volume_spike_2x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(2.0 * out["rolling_20_ema_vol"])
    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])
    out["is_low_participation"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].lt(0.5 * out["rolling_20_ema_vol"])
    out["is_narrow_range"] = out["bar_range"].lt(out["range_q25"])
    out["is_climactic_volume"] = out["rolling_vol_max_10"].notna() & out["bar_volume"].eq(out["rolling_vol_max_10"])
    out["is_release_pattern"] = (
        out["bar_volume_3"].gt(out["bar_volume_2"])
        & out["bar_volume_2"].gt(out["prior_bar_volume"])
        & out["is_volume_spike_2x"]
        & out["bar_volume"].gt(out["prior_bar_volume"])
    )

    out["is_full_body"] = out["bar_range"].gt(0) & out["body"].gt(0.80 * out["bar_range"])
    out["is_doji_family"] = out["bar_range"].gt(0) & out["body"].lt(0.20 * out["bar_range"])
    out["is_dual_rejection"] = out["upper_wick"].gt(out["body"]) & out["lower_wick"].gt(out["body"])
    out["is_one_sided_wick"] = out["body"].gt(0) & (
        ((out["upper_wick"].gt(3.0 * out["body"])) & (out["lower_wick"].lt(0.20 * out["body"])))
        | ((out["lower_wick"].gt(3.0 * out["body"])) & (out["upper_wick"].lt(0.20 * out["body"])))
    )

    out["is_compression"] = (
        out["prior_bar_range"].notna()
        & out["bar_range_2"].notna()
        & out["bar_range"].lt(out["prior_bar_range"])
        & out["bar_range"].lt(out["bar_range_2"])
    )
    out["is_body_reversal_2bar"] = (
        out["price_sign"].ne(0)
        & out["prior_price_sign"].abs().eq(1)
        & out["price_sign_2"].abs().eq(1)
        & out["prior_price_sign"].eq(-out["price_sign"])
        & out["price_sign_2"].eq(-out["price_sign"])
    )
    out["is_shrinking_delta_3bar"] = (
        out["abs_delta_2"].notna()
        & out["prior_abs_delta"].notna()
        & out["abs_delta_2"].gt(out["prior_abs_delta"])
        & out["prior_abs_delta"].gt(out["abs_delta"])
    )
    out["is_delta_flip_volume_spike"] = (
        out["prior_bar_delta"].notna()
        & out["prior_bar_delta"].ne(0)
        & out["direction_sign"].ne(0)
        & np.sign(out["prior_bar_delta"]).ne(out["direction_sign"])
        & out["is_volume_spike_2x"]
    )

    return out


def compute_cvd_features(observations: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    by_session = out.groupby("session_date", sort=False)

    out["cvd"] = by_session["bar_delta"].cumsum()
    by_session = out.groupby("session_date", sort=False)

    out["prior_session_price_high"] = by_session["bar_high"].transform(lambda s: s.cummax().shift(1))
    out["prior_session_price_low"] = by_session["bar_low"].transform(lambda s: s.cummin().shift(1))
    out["prior_cvd_high"] = by_session["cvd"].transform(lambda s: s.cummax().shift(1))
    out["prior_cvd_low"] = by_session["cvd"].transform(lambda s: s.cummin().shift(1))

    out["is_price_new_session_high"] = out["prior_session_price_high"].notna() & out["bar_high"].gt(out["prior_session_price_high"])
    out["is_price_new_session_low"] = out["prior_session_price_low"].notna() & out["bar_low"].lt(out["prior_session_price_low"])
    out["is_cvd_divergence"] = (
        (out["is_price_new_session_high"] & out["prior_cvd_high"].notna() & out["cvd"].lt(out["prior_cvd_high"]))
        | (out["is_price_new_session_low"] & out["prior_cvd_low"].notna() & out["cvd"].gt(out["prior_cvd_low"]))
    )
    return out


def compute_thresholds(df: pd.DataFrame) -> dict[str, float]:
    volume = df.loc[df["direction_sign"].ne(0), "bar_volume"].dropna()
    return {
        "volume_tercile_low": float(volume.quantile(1 / 3)) if not volume.empty else float("nan"),
        "volume_tercile_high": float(volume.quantile(2 / 3)) if not volume.empty else float("nan"),
    }


def add_context_flags(df: pd.DataFrame, thresholds: dict[str, float]) -> pd.DataFrame:
    out = df.copy()
    out["is_15m_trend_aligned"] = out["direction_sign"].eq(out["trend_sign_15m"])

    rng_60m = out["range_60m"].replace(0, np.nan)
    anchor = np.where(out["direction_sign"] > 0, out["bar_low"], np.where(out["direction_sign"] < 0, out["bar_high"], np.nan))
    out["pos_in_60m"] = (anchor - out["low_60m"]) / rng_60m
    out["is_60m_extreme"] = (
        ((out["direction_sign"] > 0) & out["pos_in_60m"].le(0.20))
        | ((out["direction_sign"] < 0) & out["pos_in_60m"].ge(0.80))
    )

    low = thresholds["volume_tercile_low"]
    high = thresholds["volume_tercile_high"]
    out["is_middle_tercile_volume"] = out["bar_volume"].ge(low) & out["bar_volume"].le(high)
    out["is_killer_1"] = out["pos_in_60m"].between(0.40, 0.60, inclusive="both")
    out["is_killer_2"] = out["is_volume_spike_3x"]
    out["passes_not_all_killers"] = (~out["is_killer_1"]) & (~out["is_killer_2"])

    bool_cols = [
        "is_15m_trend_aligned",
        "is_60m_extreme",
        "is_middle_tercile_volume",
        "is_killer_1",
        "is_killer_2",
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


def build_trade_sample(observations: pd.DataFrame) -> pd.DataFrame:
    sample = observations.copy()
    sample = sample[sample["direction_sign"].ne(0)].copy()
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


def build_filter_specs() -> list[FilterSpec]:
    return [
        ("01", "A", "|delta|/vol > 0.50 + 60m + 15m", lambda df: df["is_high_delta_ratio"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        ("02", "A", "|delta|/vol < 0.10 + 60m + 15m", lambda df: df["is_low_delta_ratio"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        ("03", "A", "|delta|/vol < 0.05 + 60m + 15m", lambda df: df["is_very_low_delta_ratio"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        ("04", "A", "Delta opposing bar direction + 60m + 15m", lambda df: df["is_price_delta_divergence"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        ("05", "A", "Delta confirming bar direction + 60m + 15m", lambda df: df["is_price_delta_alignment"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        (
            "06",
            "B",
            "Volume > 2x EMA + narrow range + 60m + 15m",
            lambda df: df["is_volume_spike_2x"] & df["is_narrow_range"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"],
        ),
        ("07", "B", "Volume < 0.5x EMA + 60m + 15m", lambda df: df["is_low_participation"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        ("08", "B", "Volume in middle tercile + 60m + 15m", lambda df: df["is_middle_tercile_volume"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        ("09", "B", "Highest volume in last 10 bars + 60m + 15m", lambda df: df["is_climactic_volume"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        ("10", "B", "3-bar volume decline then spike + 60m + 15m", lambda df: df["is_release_pattern"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        ("11", "C", "Body > 80% of range + 60m + 15m", lambda df: df["is_full_body"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        ("12", "C", "Body < 20% of range + 60m + 15m", lambda df: df["is_doji_family"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        ("13", "C", "Upper wick > body and lower wick > body + 60m + 15m", lambda df: df["is_dual_rejection"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        ("14", "C", "One-sided wick only + 60m + 15m", lambda df: df["is_one_sided_wick"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        ("15", "D", "Current bar narrower than prior 2 + 60m + 15m", lambda df: df["is_compression"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        ("16", "D", "Current body reverses prior 2 bodies + 60m + 15m", lambda df: df["is_body_reversal_2bar"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        ("17", "D", "3 bars of shrinking |delta| + 60m + 15m", lambda df: df["is_shrinking_delta_3bar"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        ("18", "D", "Delta flip + volume spike + 60m + 15m", lambda df: df["is_delta_flip_volume_spike"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        (
            "19",
            "E",
            "Body < 20% + |delta|/vol < 0.10 + NOT killers + 60m + 15m + first_hour",
            lambda df: df["is_doji_family"]
            & df["is_low_delta_ratio"]
            & df["passes_not_all_killers"]
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["is_first_hour"],
        ),
        (
            "20",
            "E",
            "CVD divergence + body < 20% + 60m + 15m + NOT killers",
            lambda df: df["is_cvd_divergence"]
            & df["is_doji_family"]
            & df["passes_not_all_killers"]
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"],
        ),
    ]


def run_filters(df: pd.DataFrame) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for code, group, label, predicate in build_filter_specs():
        filtered = df.loc[predicate(df)].copy()
        results.append(summarize_filter(code, group, label, filtered))

    results.sort(
        key=lambda row: (
            float("-inf") if pd.isna(row["wr_30b"]) else float(row["wr_30b"]),
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
    observations = attach_timeframe_context(observations, timeframe_context)
    observations = compute_bar_features(observations)
    observations = compute_cvd_features(observations)
    thresholds = compute_thresholds(observations)
    observations = add_context_flags(observations, thresholds)
    observations = add_time_flags(observations)

    sample = build_trade_sample(observations)
    results = run_filters(sample)

    baseline_all = summarize_filter("00", "BASE", "All non-zero-delta signal bars", sample)
    baseline_core = summarize_filter(
        "00A",
        "BASE",
        "60m + 15m core sample",
        sample.loc[sample["is_60m_extreme"] & sample["is_15m_trend_aligned"]].copy(),
    )
    baseline_core_not_killers = summarize_filter(
        "00B",
        "BASE",
        "60m + 15m + NOT killers",
        sample.loc[
            sample["is_60m_extreme"] & sample["is_15m_trend_aligned"] & sample["passes_not_all_killers"]
        ].copy(),
    )
    baseline_cvd_doji = summarize_filter(
        "00C",
        "BASE",
        "CVD divergence + body < 20% + 60m + 15m + NOT killers",
        sample.loc[
            sample["is_cvd_divergence"]
            & sample["is_doji_family"]
            & sample["is_60m_extreme"]
            & sample["is_15m_trend_aligned"]
            & sample["passes_not_all_killers"]
        ].copy(),
    )

    lines = [
        "DEEP6 round12 bar microstructure analysis",
        "========================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index.",
        "Trade direction for all filters: sign(bar_delta). Zero-delta bars are excluded from scoring.",
        "15m / 60m context comes from OHLCV resamples of nq_1yr_1m.csv.",
        "delta_ratio = abs(bar_delta) / bar_volume. Volume EMA and range q25 both use the prior 20 bars within each session.",
        "KILLER_1 = trade-direction anchor in middle 40-60% of the active 60m range. KILLER_2 = bar_volume > 3x prior 20-bar EMA.",
        "CVD divergence = price makes a new session high/low while cumulative delta fails to confirm that new extreme.",
        "Volume middle tercile uses global grouped-bar volume quantiles over the non-zero-delta sample.",
        "Persistence: GROWING if WR_30b > WR_5b; STABLE if within 3 percentage points; DECAYING otherwise.",
        "",
        f"Raw event rows loaded:                 {len(events):,}",
        f"Grouped signal bars:                   {len(observations):,}",
        f"Tradable non-zero-delta bars:          {len(sample):,}",
        f"15m bars built:                        {len(timeframe_context[15]):,}",
        f"60m bars built:                        {len(timeframe_context[60]):,}",
        f"60m extreme bars:                      {int(sample['is_60m_extreme'].sum()):,}",
        f"15m trend-aligned bars:                {int(sample['is_15m_trend_aligned'].sum()):,}",
        f"Body < 20% bars:                       {int(sample['is_doji_family'].sum()):,}",
        f"CVD divergence bars:                   {int(sample['is_cvd_divergence'].sum()):,}",
        f"First-hour bars:                       {int(sample['is_first_hour'].sum()):,}",
        f"KILLER_1 hits:                         {int(sample['is_killer_1'].sum()):,}",
        f"KILLER_2 hits:                         {int(sample['is_killer_2'].sum()):,}",
        "",
        "Baselines",
        "---------",
        f"All non-zero-delta bars:                 {render_summary_line(baseline_all)}",
        f"60m + 15m core:                          {render_summary_line(baseline_core)}",
        f"60m + 15m + NOT killers:                 {render_summary_line(baseline_core_not_killers)}",
        f"CVD divergence + doji + core + NOT kill: {render_summary_line(baseline_cvd_doji)}",
        "",
        "20 bar microstructure filters ranked by 30b win rate",
        "-------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
