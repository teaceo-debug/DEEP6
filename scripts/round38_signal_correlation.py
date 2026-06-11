#!/usr/bin/env python3
from __future__ import annotations

import math
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data/backtests/signal_events.csv"
OHLCV_CSV = ROOT / "data/backtests/nq_1yr_1m.csv"
OUT_DIR = ROOT / "data/backtests/analysis"
OUT_PATH = OUT_DIR / "round38_signal_correlation_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
TICK_SIZE = 0.25
RTH_START_MINUTE = 9 * 60 + 30
FIRST_HOUR_MINUTES = 60
ROLLING_LOOKBACK = 20
ATR_WINDOW = 20
VOL_OF_VOL_WINDOW = 10
REDUNDANT_THRESHOLD = 0.70
INDEPENDENT_THRESHOLD = 0.30
TOP_INDEPENDENT_PAIRS = 5

SIGNAL_SPECS = [
    ("S01", "Doji", "is_doji"),
    ("S02", "CVD divergence", "is_cvd_divergence"),
    ("S03", "|delta|/vol < 0.05", "is_low_delta_vol"),
    ("S04", "3 narrowing ranges", "is_three_narrowing_ranges"),
    ("S05", "Hammer/shooting star", "is_hammer_or_star"),
    ("S06", "Engulfing", "is_engulfing"),
    ("S07", "Morning/evening star", "is_morning_evening_star"),
    ("S08", "Absorption (category)", "has_absorption"),
    ("S09", "Score >= 60", "score_ge_60"),
    ("S10", "Stable vol", "is_stable_vol"),
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


def render_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    def pad(cells: list[str]) -> str:
        return " | ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(cells))

    lines = [pad(headers), "-+-".join("-" * width for width in widths)]
    for row in rows:
        lines.append(pad(row))
    return lines


def stats_sort_key(row: dict[str, object]) -> tuple[float, float, float, int]:
    return (
        float("-inf") if pd.isna(row["wr_30b"]) else float(row["wr_30b"]),
        float("-inf") if pd.isna(row["wr_10b"]) else float(row["wr_10b"]),
        float("-inf") if pd.isna(row["wr_5b"]) else float(row["wr_5b"]),
        int(row["n"]),
    )


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
        "score_final",
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
        "score_final",
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
    working = events.copy()
    working["is_absorption"] = working["category"].eq("absorption")

    observations = (
        working.groupby("global_index", as_index=False, sort=False)
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
            max_score_final=("score_final", "max"),
            has_absorption=("is_absorption", "max"),
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
    observations["has_absorption"] = observations["has_absorption"].fillna(False).astype(bool)

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

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["body_high"] = np.maximum(out["bar_open"], out["bar_close"])
    out["body_low"] = np.minimum(out["bar_open"], out["bar_close"])
    out["body_mid"] = (out["bar_open"] + out["bar_close"]) / 2.0
    out["upper_wick"] = out["bar_high"] - out["body_high"]
    out["lower_wick"] = out["body_low"] - out["bar_low"]
    out["price_change"] = out["bar_close"] - out["bar_open"]
    out["price_color_sign"] = np.sign(out["price_change"].fillna(0.0)).astype(int)
    out["abs_delta"] = out["bar_delta"].abs()
    out["delta_ratio"] = np.where(out["bar_volume"] > 0, out["abs_delta"] / out["bar_volume"], np.nan)

    by_session = out.groupby("session_date", sort=False)
    out["prior_close"] = by_session["bar_close"].shift(1)
    out["prior_bar_range"] = by_session["bar_range"].shift(1)
    out["bar_range_2"] = by_session["bar_range"].shift(2)
    out["prior_body_high"] = by_session["body_high"].shift(1)
    out["prior_body_low"] = by_session["body_low"].shift(1)
    out["price_color_sign_1"] = by_session["price_color_sign"].shift(1)
    out["price_color_sign_2"] = by_session["price_color_sign"].shift(2)
    out["body_mid_2"] = by_session["body_mid"].shift(2)

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
        lambda s: s.rolling(ATR_WINDOW, min_periods=ATR_WINDOW).mean()
    )
    out["vol_of_vol"] = by_session["atr20"].transform(
        lambda s: s.rolling(VOL_OF_VOL_WINDOW, min_periods=VOL_OF_VOL_WINDOW).std()
    )
    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )

    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])
    out["is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.10 * out["bar_range"])
    out["is_low_delta_vol"] = out["delta_ratio"].lt(0.05)
    out["is_three_narrowing_ranges"] = (
        out["bar_range_2"].notna()
        & out["prior_bar_range"].lt(out["bar_range_2"])
        & out["bar_range"].lt(out["prior_bar_range"])
    )

    out["is_hammer"] = (
        out["body"].gt(0)
        & out["lower_wick"].gt(2.0 * out["body"])
        & out["upper_wick"].lt(0.5 * out["body"])
        & out["bar_close"].gt(out["bar_open"])
    )
    out["is_shooting_star"] = (
        out["body"].gt(0)
        & out["upper_wick"].gt(2.0 * out["body"])
        & out["lower_wick"].lt(0.5 * out["body"])
        & out["bar_close"].lt(out["bar_open"])
    )
    out["is_hammer_or_star"] = out["is_hammer"] | out["is_shooting_star"]

    out["is_engulfing"] = (
        out["prior_body_high"].notna()
        & out["body_high"].gt(out["prior_body_high"])
        & out["body_low"].lt(out["prior_body_low"])
    )

    by_session = out.groupby("session_date", sort=False)
    out["is_doji_1"] = by_session["is_doji"].shift(1).fillna(False).astype(bool)
    out["is_morning_star"] = (
        out["price_color_sign"].eq(1)
        & out["is_doji_1"]
        & out["price_color_sign_2"].eq(-1)
        & out["bar_close"].gt(out["body_mid_2"])
    )
    out["is_evening_star"] = (
        out["price_color_sign"].eq(-1)
        & out["is_doji_1"]
        & out["price_color_sign_2"].eq(1)
        & out["bar_close"].lt(out["body_mid_2"])
    )
    out["is_morning_evening_star"] = out["is_morning_star"] | out["is_evening_star"]

    bool_cols = [
        "has_absorption",
        "is_volume_spike_3x",
        "is_doji",
        "is_low_delta_vol",
        "is_three_narrowing_ranges",
        "is_hammer",
        "is_shooting_star",
        "is_hammer_or_star",
        "is_engulfing",
        "is_doji_1",
        "is_morning_star",
        "is_evening_star",
        "is_morning_evening_star",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)

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
    out["is_cvd_divergence"] = out["is_cvd_divergence"].fillna(False).astype(bool)
    return out


def add_time_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] * 60 + out["minute"]) - RTH_START_MINUTE
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(FIRST_HOUR_MINUTES)
    out["is_first_hour"] = out["is_first_hour"].fillna(False).astype(bool)
    return out


def anchor_pos_60m(df: pd.DataFrame, trade_sign: pd.Series) -> pd.Series:
    rng_60m = df["range_60m"].replace(0, np.nan)
    anchor = np.where(trade_sign > 0, df["bar_low"], np.where(trade_sign < 0, df["bar_high"], np.nan))
    return pd.Series((anchor - df["low_60m"]) / rng_60m, index=df.index)


def build_trade_sample(observations: pd.DataFrame) -> pd.DataFrame:
    sample = observations.loc[observations["direction_sign"].ne(0)].copy()
    sample["trade_sign"] = sample["direction_sign"]
    sample["pos_in_60m"] = anchor_pos_60m(sample, sample["trade_sign"])
    sample["is_60m_extreme"] = (
        ((sample["trade_sign"] > 0) & sample["pos_in_60m"].le(0.20))
        | ((sample["trade_sign"] < 0) & sample["pos_in_60m"].ge(0.80))
    )
    sample["is_15m_trend_aligned"] = sample["trade_sign"].eq(sample["trend_sign_15m"])
    sample["has_core_60m_15m_gate"] = sample["is_60m_extreme"] & sample["is_15m_trend_aligned"]

    for window in FORWARD_WINDOWS:
        sample[f"ret_{window}b_ticks"] = sample["trade_sign"] * sample[f"move_{window}b_ticks"]

    sample["is_killer_1"] = sample["pos_in_60m"].between(0.40, 0.60, inclusive="both")
    sample["is_killer_2"] = sample["is_volume_spike_3x"]
    sample["passes_not_all_killers"] = (~sample["is_killer_1"]) & (~sample["is_killer_2"])
    sample["score_ge_60"] = sample["max_score_final"].ge(60)

    bool_cols = [
        "has_absorption",
        "is_60m_extreme",
        "is_15m_trend_aligned",
        "has_core_60m_15m_gate",
        "is_killer_1",
        "is_killer_2",
        "passes_not_all_killers",
        "score_ge_60",
    ]
    for col in bool_cols:
        sample[col] = sample[col].fillna(False).astype(bool)

    return sample.reset_index(drop=True)


def compute_thresholds(sample: pd.DataFrame) -> dict[str, float]:
    vol_of_vol = sample["vol_of_vol"].dropna()
    return {
        "vol_of_vol_q25": float(vol_of_vol.quantile(0.25)) if not vol_of_vol.empty else float("nan"),
    }


def apply_signal_flags(df: pd.DataFrame, thresholds: dict[str, float]) -> pd.DataFrame:
    out = df.copy()
    out["score_ge_60"] = out["max_score_final"].ge(60)
    out["is_stable_vol"] = out["vol_of_vol"].lt(thresholds["vol_of_vol_q25"])

    bool_cols = [
        "has_absorption",
        "is_doji",
        "is_cvd_divergence",
        "is_low_delta_vol",
        "is_three_narrowing_ranges",
        "is_hammer_or_star",
        "is_engulfing",
        "is_morning_evening_star",
        "score_ge_60",
        "is_stable_vol",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)

    return out


def summarize_sample(label: str, df: pd.DataFrame) -> dict[str, object]:
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


def compute_pairwise_metrics(observations: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, object]], dict[str, int]]:
    arrays = {
        code: observations[col].fillna(False).to_numpy(dtype=bool)
        for code, _, col in SIGNAL_SPECS
    }
    counts = {code: int(arr.sum()) for code, arr in arrays.items()}

    codes = [code for code, _, _ in SIGNAL_SPECS]
    matrix = pd.DataFrame(index=codes, columns=codes, dtype=float)
    pair_rows: list[dict[str, object]] = []

    for code in codes:
        matrix.loc[code, code] = 1.0

    for (code_a, label_a, _), (code_b, label_b, _) in combinations(SIGNAL_SPECS, 2):
        arr_a = arrays[code_a]
        arr_b = arrays[code_b]
        intersection = int(np.logical_and(arr_a, arr_b).sum())
        union = int(np.logical_or(arr_a, arr_b).sum())
        jaccard = float(intersection / union) if union else 0.0
        p_a_given_b = float(intersection / counts[code_b]) if counts[code_b] else np.nan
        p_b_given_a = float(intersection / counts[code_a]) if counts[code_a] else np.nan
        relationship = "REDUNDANT" if jaccard > REDUNDANT_THRESHOLD else "INDEPENDENT" if jaccard < INDEPENDENT_THRESHOLD else "PARTIAL"

        matrix.loc[code_a, code_b] = jaccard
        matrix.loc[code_b, code_a] = jaccard
        pair_rows.append(
            {
                "code_a": code_a,
                "label_a": label_a,
                "code_b": code_b,
                "label_b": label_b,
                "count_a": counts[code_a],
                "count_b": counts[code_b],
                "intersection": intersection,
                "union": union,
                "jaccard": jaccard,
                "p_a_given_b": p_a_given_b,
                "p_b_given_a": p_b_given_a,
                "relationship": relationship,
            }
        )

    return matrix, pair_rows, counts


def compute_solo_signal_stats(sample: pd.DataFrame) -> dict[str, dict[str, object]]:
    stats: dict[str, dict[str, object]] = {}
    base_gate = sample["has_core_60m_15m_gate"] & sample["passes_not_all_killers"]

    for code, label, col in SIGNAL_SPECS:
        filtered = sample.loc[base_gate & sample[col]].copy()
        stats[code] = summarize_sample(label, filtered)

    return stats


def compute_independent_pair_tests(
    sample: pd.DataFrame,
    pair_rows: list[dict[str, object]],
    solo_stats: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    code_to_col = {code: col for code, _, col in SIGNAL_SPECS}
    independent_rows: list[dict[str, object]] = []
    base_gate = sample["has_core_60m_15m_gate"] & sample["passes_not_all_killers"]

    for row in pair_rows:
        if float(row["jaccard"]) >= INDEPENDENT_THRESHOLD:
            continue

        code_a = str(row["code_a"])
        code_b = str(row["code_b"])
        combined = sample.loc[base_gate & sample[code_to_col[code_a]] & sample[code_to_col[code_b]]].copy()
        combined_stats = summarize_sample(f"{row['label_a']} + {row['label_b']}", combined)
        best_solo_wr30 = max(
            float("-inf") if pd.isna(solo_stats[code_a]["wr_30b"]) else float(solo_stats[code_a]["wr_30b"]),
            float("-inf") if pd.isna(solo_stats[code_b]["wr_30b"]) else float(solo_stats[code_b]["wr_30b"]),
        )

        independent_rows.append(
            {
                **row,
                "combined_n": combined_stats["n"],
                "combined_wr_5b": combined_stats["wr_5b"],
                "combined_wr_10b": combined_stats["wr_10b"],
                "combined_wr_30b": combined_stats["wr_30b"],
                "combined_pf_5b": combined_stats["pf_5b"],
                "combined_avg_ticks_5b": combined_stats["avg_ticks_5b"],
                "solo_a_wr_30b": solo_stats[code_a]["wr_30b"],
                "solo_b_wr_30b": solo_stats[code_b]["wr_30b"],
                "synergy": "SYNERGY"
                if combined_stats["n"] > 0
                and not pd.isna(combined_stats["wr_30b"])
                and float(combined_stats["wr_30b"]) > best_solo_wr30
                else "NO_DATA"
                if combined_stats["n"] == 0
                else "NO",
            }
        )

    independent_rows.sort(key=stats_sort_key_pair, reverse=True)
    return independent_rows[:TOP_INDEPENDENT_PAIRS]


def stats_sort_key_pair(row: dict[str, object]) -> tuple[float, float, float, int]:
    return (
        float("-inf") if pd.isna(row["combined_wr_30b"]) else float(row["combined_wr_30b"]),
        float("-inf") if pd.isna(row["combined_wr_10b"]) else float(row["combined_wr_10b"]),
        float("-inf") if pd.isna(row["combined_wr_5b"]) else float(row["combined_wr_5b"]),
        int(row["combined_n"]),
    )


def build_redundancy_clusters(
    pair_rows: list[dict[str, object]],
    solo_stats: dict[str, dict[str, object]],
) -> tuple[list[dict[str, object]], list[str]]:
    codes = [code for code, _, _ in SIGNAL_SPECS]
    code_to_name = {code: label for code, label, _ in SIGNAL_SPECS}
    adjacency = {code: set() for code in codes}
    pair_lookup: dict[frozenset[str], dict[str, object]] = {}

    for row in pair_rows:
        code_a = str(row["code_a"])
        code_b = str(row["code_b"])
        pair_lookup[frozenset([code_a, code_b])] = row
        if float(row["jaccard"]) > REDUNDANT_THRESHOLD:
            adjacency[code_a].add(code_b)
            adjacency[code_b].add(code_a)

    clusters: list[dict[str, object]] = []
    visited: set[str] = set()

    for code in codes:
        if code in visited:
            continue

        stack = [code]
        members: list[str] = []
        visited.add(code)

        while stack:
            current = stack.pop()
            members.append(current)
            for neighbor in sorted(adjacency[current]):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                stack.append(neighbor)

        members.sort(key=codes.index)
        representative = max(members, key=lambda member: stats_sort_key(solo_stats[member]))
        edges: list[str] = []
        for code_a, code_b in combinations(members, 2):
            row = pair_lookup[frozenset([code_a, code_b])]
            if float(row["jaccard"]) > REDUNDANT_THRESHOLD:
                edges.append(f"{code_a}/{code_b}={float(row['jaccard']):.3f}")

        clusters.append(
            {
                "members": members,
                "member_names": [code_to_name[member] for member in members],
                "representative": representative,
                "edges": edges,
            }
        )

    non_redundant = [str(cluster["representative"]) for cluster in clusters]
    return clusters, non_redundant


def intersection_stats(sample: pd.DataFrame, codes: list[str], first_hour: bool) -> dict[str, object]:
    code_to_col = {code: col for code, _, col in SIGNAL_SPECS}
    mask = sample["has_core_60m_15m_gate"] & sample["passes_not_all_killers"]
    if first_hour:
        mask &= sample["is_first_hour"]
    for code in codes:
        mask &= sample[code_to_col[code]]
    return summarize_sample(" + ".join(codes), sample.loc[mask].copy())


def render_signal_overview(observations: pd.DataFrame, sample: pd.DataFrame, solo_stats: dict[str, dict[str, object]]) -> list[str]:
    rows: list[list[str]] = []
    base_gate = sample["has_core_60m_15m_gate"] & sample["passes_not_all_killers"]
    for code, label, col in SIGNAL_SPECS:
        raw_n = int(observations[col].sum())
        gated_n = int((base_gate & sample[col]).sum())
        rows.append(
            [
                code,
                label,
                f"{raw_n:,}",
                f"{gated_n:,}",
                fmt_pct(float(solo_stats[code]["wr_30b"])),
            ]
        )
    return render_table(["Code", "Signal", "Raw Bars", "Core+NOT Killers Bars", "Solo WR30"], rows)


def render_jaccard_matrix(matrix: pd.DataFrame) -> list[str]:
    headers = ["Signal", *matrix.columns.tolist()]
    rows: list[list[str]] = []
    for code in matrix.index.tolist():
        rows.append([code, *[f"{float(matrix.loc[code, other]):.3f}" for other in matrix.columns.tolist()]])
    return render_table(headers, rows)


def render_pairwise_table(pair_rows: list[dict[str, object]]) -> list[str]:
    rows: list[list[str]] = []
    ordered = sorted(
        pair_rows,
        key=lambda row: (
            float(row["jaccard"]),
            float(row["p_a_given_b"]) if not pd.isna(row["p_a_given_b"]) else float("-inf"),
            float(row["p_b_given_a"]) if not pd.isna(row["p_b_given_a"]) else float("-inf"),
        ),
        reverse=True,
    )
    for row in ordered:
        rows.append(
            [
                f"{row['code_a']}+{row['code_b']}",
                f"{row['count_a']:,}",
                f"{row['count_b']:,}",
                f"{row['intersection']:,}",
                f"{row['union']:,}",
                f"{float(row['jaccard']):.3f}",
                fmt_pct(float(row["p_a_given_b"])),
                fmt_pct(float(row["p_b_given_a"])),
                str(row["relationship"]),
            ]
        )
    return render_table(
        ["Pair", "A Bars", "B Bars", "Both", "Union", "Jaccard", "P(A|B)", "P(B|A)", "Flag"],
        rows,
    )


def render_synergy_table(rows_in: list[dict[str, object]]) -> list[str]:
    rows: list[list[str]] = []
    for row in rows_in:
        rows.append(
            [
                f"{row['code_a']}+{row['code_b']}",
                f"{float(row['jaccard']):.3f}",
                f"{int(row['combined_n']):,}",
                fmt_pct(float(row["solo_a_wr_30b"])),
                fmt_pct(float(row["solo_b_wr_30b"])),
                fmt_pct(float(row["combined_wr_30b"])),
                fmt_float(float(row["combined_pf_5b"])),
                fmt_float(float(row["combined_avg_ticks_5b"])),
                str(row["synergy"]),
            ]
        )
    return render_table(
        ["Pair", "Jaccard", "Combined N", "Solo A WR30", "Solo B WR30", "Combined WR30", "PF5", "Avg5", "Synergy"],
        rows,
    )


def render_cluster_table(
    clusters: list[dict[str, object]],
    solo_stats: dict[str, dict[str, object]],
) -> list[str]:
    code_to_name = {code: label for code, label, _ in SIGNAL_SPECS}
    rows: list[list[str]] = []
    for idx, cluster in enumerate(clusters, start=1):
        representative = str(cluster["representative"])
        stats = solo_stats[representative]
        member_codes = [str(member) for member in cluster["members"]]
        members_text = ", ".join(f"{member}:{code_to_name[member]}" for member in member_codes)
        edges_text = "; ".join(cluster["edges"]) if cluster["edges"] else "singleton"
        rows.append(
            [
                f"C{idx:02d}",
                members_text,
                edges_text,
                f"{representative}:{code_to_name[representative]}",
                f"{int(stats['n']):,}",
                fmt_pct(float(stats["wr_30b"])),
            ]
        )
    return render_table(["Cluster", "Members", "Redundant Edges", "Representative", "Rep N", "Rep WR30"], rows)


def render_set_table(rows_in: list[tuple[str, list[str], dict[str, object]]]) -> list[str]:
    rows: list[list[str]] = []
    for label, codes, stats in rows_in:
        rows.append(
            [
                label,
                ", ".join(codes),
                f"{int(stats['n']):,}",
                fmt_pct(float(stats["wr_5b"])),
                fmt_pct(float(stats["wr_10b"])),
                fmt_pct(float(stats["wr_30b"])),
                fmt_float(float(stats["pf_5b"])),
                fmt_float(float(stats["avg_ticks_5b"])),
                str(stats["persistence"]),
            ]
        )
    return render_table(["Set", "Signals", "N", "WR5", "WR10", "WR30", "PF5", "Avg5", "Persistence"], rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events = load_events()
    bars_1m = load_ohlcv()

    observations = build_observations(events)
    timeframe_context = build_timeframe_context(bars_1m)
    observations = attach_timeframe_context(observations, timeframe_context)
    observations = compute_bar_features(observations)
    observations = compute_cvd_features(observations)
    observations = add_time_flags(observations)

    sample = build_trade_sample(observations)
    thresholds = compute_thresholds(sample)
    observations = apply_signal_flags(observations, thresholds)
    sample = apply_signal_flags(sample, thresholds)

    jaccard_matrix, pair_rows, _raw_counts = compute_pairwise_metrics(observations)
    solo_stats = compute_solo_signal_stats(sample)
    synergy_rows = compute_independent_pair_tests(sample, pair_rows, solo_stats)
    clusters, non_redundant_codes = build_redundancy_clusters(pair_rows, solo_stats)

    full_codes = [code for code, _, _ in SIGNAL_SPECS]
    full_set_stats = intersection_stats(sample, full_codes, first_hour=True)
    non_redundant_set_stats = intersection_stats(sample, non_redundant_codes, first_hour=True)

    baseline_all = summarize_sample("All non-zero-delta bars", sample)
    baseline_core = summarize_sample(
        "60m + 15m core",
        sample.loc[sample["has_core_60m_15m_gate"]].copy(),
    )
    baseline_core_not_killers = summarize_sample(
        "60m + 15m + NOT killers",
        sample.loc[sample["has_core_60m_15m_gate"] & sample["passes_not_all_killers"]].copy(),
    )
    baseline_core_not_killers_first_hour = summarize_sample(
        "60m + 15m + NOT killers + first_hour",
        sample.loc[sample["has_core_60m_15m_gate"] & sample["passes_not_all_killers"] & sample["is_first_hour"]].copy(),
    )

    code_to_name = {code: label for code, label, _ in SIGNAL_SPECS}
    signal_legend_rows = [f"{code} = {label}" for code, label, _ in SIGNAL_SPECS]

    lines = [
        "DEEP6 round38 signal correlation analysis",
        "========================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index.",
        "Trade direction for P&L: sign(bar_delta). Zero-delta bars are skipped for WR/PF/Avg stats.",
        "Bar-feature formulas are aligned to the existing round2, round12, round17, and round23 definitions.",
        "Co-occurrence / redundancy uses raw deduped signal bars. Synergy and representative selection use signal + 60m + 15m + NOT killers.",
        "Section 4 adds first_hour to both the full-set and non-redundant-set tests.",
        "60m gate = bullish bar_low in bottom 20% of active 60m range / bearish bar_high in top 20%. 15m gate = trade direction matches 15m trend sign.",
        "NOT killers = NOT killer_1 (trade anchor in middle 40%-60% of the active 60m range) AND NOT killer_2 (bar_volume > 3x prior 20-bar EMA).",
        "Stable vol = rolling 10-bar std of ATR20 below the 25th percentile of vol_of_vol across the non-zero-delta sample.",
        "Synergy uses WR30 as the primary comparison. PF and Avg are reported on the 5-bar horizon.",
        "",
        f"Raw event rows loaded:                   {len(events):,}",
        f"Grouped signal bars:                     {len(observations):,}",
        f"Non-zero-delta trade sample:             {len(sample):,}",
        f"15m bars built:                          {len(timeframe_context[15]):,}",
        f"60m bars built:                          {len(timeframe_context[60]):,}",
        f"60m + 15m core bars:                     {int(sample['has_core_60m_15m_gate'].sum()):,}",
        f"60m + 15m + NOT killers bars:            {int((sample['has_core_60m_15m_gate'] & sample['passes_not_all_killers']).sum()):,}",
        f"60m + 15m + NOT killers + first_hour:    {int((sample['has_core_60m_15m_gate'] & sample['passes_not_all_killers'] & sample['is_first_hour']).sum()):,}",
        f"Stable-vol threshold (25th pct vol_of_vol): {fmt_float(thresholds['vol_of_vol_q25'])}",
        "",
        "Baselines",
        "---------",
        f"All non-zero-delta bars:               {render_summary_line(baseline_all)}",
        f"60m + 15m core:                        {render_summary_line(baseline_core)}",
        f"60m + 15m + NOT killers:               {render_summary_line(baseline_core_not_killers)}",
        f"60m + 15m + NOT killers + first_hour:  {render_summary_line(baseline_core_not_killers_first_hour)}",
        "",
        "Section 1: 10x10 Jaccard co-occurrence matrix",
        "-----------------------------------------------",
        "Signal legend:",
        *[f"- {row}" for row in signal_legend_rows],
        "",
        "Signal overview",
        "---------------",
    ]
    lines.extend(render_signal_overview(observations, sample, solo_stats))
    lines.extend(
        [
            "",
            "Jaccard matrix",
            "--------------",
        ]
    )
    lines.extend(render_jaccard_matrix(jaccard_matrix))
    lines.extend(
        [
            "",
            "Pairwise overlap / conditional table",
            "------------------------------------",
        ]
    )
    lines.extend(render_pairwise_table(pair_rows))

    lines.extend(
        [
            "",
            "Section 2: Top 5 independent pairs with synergy tests",
            "------------------------------------------------------",
            "Independent = Jaccard < 0.30. Table sorted by combined WR30 descending.",
        ]
    )
    lines.extend(render_synergy_table(synergy_rows))

    lines.extend(
        [
            "",
            "Section 3: Redundancy clusters and best representatives",
            "-------------------------------------------------------",
            f"Redundant edge threshold: Jaccard > {REDUNDANT_THRESHOLD:.2f}",
        ]
    )
    lines.extend(render_cluster_table(clusters, solo_stats))
    lines.extend(
        [
            "",
            f"Non-redundant signal set ({len(non_redundant_codes)} reps): "
            + ", ".join(f"{code}:{code_to_name[code]}" for code in non_redundant_codes),
        ]
    )

    lines.extend(
        [
            "",
            "Section 4: Non-redundant signal set performance",
            "-----------------------------------------------",
            "Both rows below require every listed signal + 60m + 15m + NOT killers + first_hour.",
        ]
    )
    lines.extend(
        render_set_table(
            [
                ("Full 10-signal set", full_codes, full_set_stats),
                ("Non-redundant set", non_redundant_codes, non_redundant_set_stats),
            ]
        )
    )

    full_wr30 = float(full_set_stats["wr_30b"])
    nr_wr30 = float(non_redundant_set_stats["wr_30b"])
    lines.append("")
    if int(full_set_stats["n"]) == 0 and int(non_redundant_set_stats["n"]) == 0:
        lines.append("Comparison: neither the full set nor the non-redundant set produced a tradable first-hour intersection sample.")
    elif int(full_set_stats["n"]) == 0:
        lines.append(
            "Comparison: removing redundancy increased usable first-hour sample size from 0 to "
            f"{int(non_redundant_set_stats['n']):,} bars."
        )
    elif int(non_redundant_set_stats["n"]) == 0:
        lines.append("Comparison: the full set has sample, but the non-redundant first-hour intersection does not.")
    else:
        lines.append(
            f"Comparison: non-redundant WR30 delta vs full set = {fmt_pct(nr_wr30 - full_wr30)} "
            f"({fmt_pct(nr_wr30)} vs {fmt_pct(full_wr30)}), sample delta = "
            f"{int(non_redundant_set_stats['n']) - int(full_set_stats['n']):,} bars."
        )

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
