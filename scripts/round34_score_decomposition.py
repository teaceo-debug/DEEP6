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
OUT_PATH = OUT_DIR / "round34_score_decomposition_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
RTH_START_MINUTE = 9 * 60 + 30
FIRST_HOUR_MINUTES = 60
SCALABLE_MIN_N = 100
SCORE_TIER_ORDER = {"QUIET": 0, "TYPE_C": 1, "TYPE_B": 2, "TYPE_A": 3}
SCORE_TIER_RANK_TO_NAME = {rank: name for name, rank in SCORE_TIER_ORDER.items()}

FilterSpec = tuple[str, str, str, Callable[[pd.DataFrame], pd.Series]]


def direction_to_sign(series: pd.Series) -> pd.Series:
    return series.map({"1": 1, "-1": -1, "BULLISH": 1, "BEARISH": -1, 1: 1, -1: -1}).fillna(0).astype(int)


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


def score_bucket_mask(series: pd.Series, low: float, high: float, *, include_high: bool = False) -> pd.Series:
    if include_high:
        return series.ge(low) & series.le(high)
    return series.ge(low) & series.lt(high)


def strength_bucket_mask(series: pd.Series, low: float, high: float | None = None) -> pd.Series:
    if high is None:
        return series.ge(low)
    return series.ge(low) & series.lt(high)


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
        "direction": "string",
        "score_tier": "string",
        "bar_index": "int32",
        "global_index": "int32",
        "bar_volume": "float64",
    }
    cols = [
        "session_date",
        "bar_ts",
        "bar_index",
        "global_index",
        "signal_id",
        "category",
        "direction",
        "strength",
        "score_final",
        "score_tier",
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_volume",
        "fwd_close_5b",
        "fwd_close_10b",
        "fwd_close_30b",
    ]
    df = pd.read_csv(EVENTS_CSV, usecols=cols, dtype=dtypes, low_memory=False)
    numeric_cols = [
        "strength",
        "score_final",
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_volume",
        "fwd_close_5b",
        "fwd_close_10b",
        "fwd_close_30b",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["bar_ts"] = pd.to_datetime(df["bar_ts"], utc=True, errors="coerce").dt.tz_convert(EASTERN)
    df["direction_sign"] = direction_to_sign(df["direction"])
    df = df[df["direction_sign"] != 0].copy()
    return df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)


def build_observations(events: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    working = events.copy()
    working["score_tier_rank"] = working["score_tier"].map(SCORE_TIER_ORDER).fillna(-1).astype(int)

    categories = sorted(working["category"].dropna().unique().tolist())
    for category in categories:
        working[f"cat_{category}"] = working["category"].eq(category)

    agg_spec: dict[str, tuple[str, str]] = {
        "session_date": ("session_date", "first"),
        "bar_ts": ("bar_ts", "first"),
        "bar_index": ("bar_index", "first"),
        "bar_open": ("bar_open", "first"),
        "bar_high": ("bar_high", "first"),
        "bar_low": ("bar_low", "first"),
        "bar_close": ("bar_close", "first"),
        "bar_volume": ("bar_volume", "first"),
        "fwd_close_5b": ("fwd_close_5b", "first"),
        "fwd_close_10b": ("fwd_close_10b", "first"),
        "fwd_close_30b": ("fwd_close_30b", "first"),
        "signal_count": ("signal_id", "nunique"),
        "category_count": ("category", "nunique"),
        "max_score_final": ("score_final", "max"),
        "max_strength": ("strength", "max"),
        "best_score_tier_rank": ("score_tier_rank", "max"),
    }
    for category in categories:
        agg_spec[f"has_{category}"] = (f"cat_{category}", "max")

    observations = (
        working.groupby(["global_index", "direction_sign"], as_index=False, sort=False)
        .agg(**agg_spec)
        .sort_values(["global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    observations["direction"] = np.where(observations["direction_sign"] > 0, "BULLISH", "BEARISH")
    observations["best_score_tier"] = observations["best_score_tier_rank"].map(SCORE_TIER_RANK_TO_NAME).fillna("UNKNOWN")
    observations["category_set"] = observations.apply(
        lambda row: tuple(category for category in categories if bool(row[f"has_{category}"])),
        axis=1,
    )
    observations["category_set_text"] = observations["category_set"].apply(lambda items: ",".join(items) if items else "none")

    for window in FORWARD_WINDOWS:
        observations[f"ret_{window}b_ticks"] = observations["direction_sign"] * (
            (observations[f"fwd_close_{window}b"] - observations["bar_close"]) / TICK_SIZE
        )

    return observations, categories


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

    for col in ["bar_high", "bar_low", "bar_close", "bar_volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.reset_index(drop=True)


def add_context_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["is_15m_trend_aligned"] = out["direction_sign"].eq(out["trend_sign_15m"])

    rng_60m = out["range_60m"].replace(0, np.nan)
    anchor = np.where(out["direction_sign"] > 0, out["bar_low"], out["bar_high"])
    out["pos_60m"] = (anchor - out["low_60m"]) / rng_60m
    out["is_60m_extreme"] = (
        ((out["direction_sign"] > 0) & out["pos_60m"].le(0.20))
        | ((out["direction_sign"] < 0) & out["pos_60m"].ge(0.80))
    )

    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    minute_of_day = out["hour"] * 60 + out["minute"]
    out["minutes_since_930"] = minute_of_day - RTH_START_MINUTE
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(FIRST_HOUR_MINUTES)

    by_session = out.groupby("session_date", sort=False)
    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])

    out["is_killer_1"] = out["pos_60m"].between(0.40, 0.60, inclusive="both")
    out["is_killer_2"] = out["is_volume_spike_3x"]
    out["passes_not_all_killers"] = (~out["is_killer_1"]) & (~out["is_killer_2"])

    out["has_core_60m_15m_gate"] = out["is_60m_extreme"] & out["is_15m_trend_aligned"]
    out["has_core_60m_15m_first_hour_gate"] = out["has_core_60m_15m_gate"] & out["is_first_hour"]

    bool_cols = [
        "is_15m_trend_aligned",
        "is_60m_extreme",
        "is_first_hour",
        "is_volume_spike_3x",
        "is_killer_1",
        "is_killer_2",
        "passes_not_all_killers",
        "has_core_60m_15m_gate",
        "has_core_60m_15m_first_hour_gate",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out.reset_index(drop=True)


def base_core_mask(df: pd.DataFrame) -> pd.Series:
    return df["has_core_60m_15m_gate"]


def base_first_hour_mask(df: pd.DataFrame) -> pd.Series:
    return df["has_core_60m_15m_first_hour_gate"]


def base_first_hour_not_killers_mask(df: pd.DataFrame) -> pd.Series:
    return df["has_core_60m_15m_first_hour_gate"] & df["passes_not_all_killers"]


def build_filter_specs() -> list[FilterSpec]:
    return [
        ("01", "A", "TYPE_A only bars + 60m + 15m + first_hour", lambda df: base_first_hour_mask(df) & df["best_score_tier"].eq("TYPE_A")),
        ("02", "A", "TYPE_B only bars + 60m + 15m + first_hour", lambda df: base_first_hour_mask(df) & df["best_score_tier"].eq("TYPE_B")),
        ("03", "A", "TYPE_C only bars + 60m + 15m + first_hour", lambda df: base_first_hour_mask(df) & df["best_score_tier"].eq("TYPE_C")),
        ("04", "A", "QUIET bars + 60m + 15m + first_hour", lambda df: base_first_hour_mask(df) & df["best_score_tier"].eq("QUIET")),
        ("05", "A", "TYPE_A OR TYPE_B bars + 60m + 15m + first_hour", lambda df: base_first_hour_mask(df) & df["best_score_tier"].isin(["TYPE_A", "TYPE_B"])),
        ("06", "B", "score 0-30 + 60m + 15m + first_hour + NOT killers", lambda df: base_first_hour_not_killers_mask(df) & score_bucket_mask(df["max_score_final"], 0, 30)),
        ("07", "B", "score 30-50 + 60m + 15m + first_hour + NOT killers", lambda df: base_first_hour_not_killers_mask(df) & score_bucket_mask(df["max_score_final"], 30, 50)),
        ("08", "B", "score 50-65 + 60m + 15m + first_hour + NOT killers", lambda df: base_first_hour_not_killers_mask(df) & score_bucket_mask(df["max_score_final"], 50, 65)),
        ("09", "B", "score 65-80 + 60m + 15m + first_hour + NOT killers", lambda df: base_first_hour_not_killers_mask(df) & score_bucket_mask(df["max_score_final"], 65, 80)),
        ("10", "B", "score 80-100 + 60m + 15m + first_hour + NOT killers", lambda df: base_first_hour_not_killers_mask(df) & score_bucket_mask(df["max_score_final"], 80, 100, include_high=True)),
        ("11", "C", "max_strength < 0.3 + 60m + 15m", lambda df: base_core_mask(df) & df["max_strength"].lt(0.3)),
        ("12", "C", "max_strength 0.3-0.6 + 60m + 15m", lambda df: base_core_mask(df) & strength_bucket_mask(df["max_strength"], 0.3, 0.6)),
        ("13", "C", "max_strength 0.6-0.9 + 60m + 15m", lambda df: base_core_mask(df) & strength_bucket_mask(df["max_strength"], 0.6, 0.9)),
        ("14", "C", "max_strength >= 0.9 + 60m + 15m", lambda df: base_core_mask(df) & strength_bucket_mask(df["max_strength"], 0.9)),
        (
            "15",
            "C",
            "max_strength >= 0.7 + score >= 60 + 60m + 15m + first_hour + NOT killers",
            lambda df: base_first_hour_not_killers_mask(df) & df["max_strength"].ge(0.7) & df["max_score_final"].ge(60),
        ),
        ("16", "D", "has absorption + has exhaustion same bar + 60m + 15m", lambda df: base_core_mask(df) & df["has_absorption"] & df["has_exhaustion"]),
        ("17", "D", "has absorption + has trapped same bar + 60m + 15m", lambda df: base_core_mask(df) & df["has_absorption"] & df["has_trapped"]),
        ("18", "D", "has delta + has imbalance same bar + 60m + 15m", lambda df: base_core_mask(df) & df["has_delta"] & df["has_imbalance"]),
        ("19", "D", "has 4+ distinct categories same bar + 60m + 15m", lambda df: base_core_mask(df) & df["category_count"].ge(4)),
        (
            "20",
            "D",
            "has absorption + has delta + has exhaustion same bar + 60m + 15m + NOT killers + first_hour",
            lambda df: base_first_hour_not_killers_mask(df) & df["has_absorption"] & df["has_delta"] & df["has_exhaustion"],
        ),
    ]


def summarize_filter(code: str, group: str, label: str, df: pd.DataFrame) -> dict[str, object]:
    required_cols = [f"ret_{window}b_ticks" for window in FORWARD_WINDOWS]
    sample = df.dropna(subset=required_cols).copy()
    n = int(len(sample))
    win_rates: dict[int, float] = {window: np.nan for window in FORWARD_WINDOWS}

    for window in FORWARD_WINDOWS:
        returns = sample[f"ret_{window}b_ticks"]
        wins = int((returns > 0).sum())
        win_rates[window] = (wins / n) if n else np.nan

    returns_5b = sample["ret_5b_ticks"]
    wins_5b = int((returns_5b > 0).sum())
    ci_low, ci_high, win_rate_5b = wilson_ci(n, wins_5b)

    return {
        "code": code,
        "group": group,
        "label": label,
        "n": n,
        "wr_5b": win_rate_5b if n else np.nan,
        "wr_10b": win_rates[10],
        "wr_30b": win_rates[30],
        "pf_5b": profit_factor(returns_5b) if n else np.nan,
        "avg_ticks_5b": float(returns_5b.mean()) if n else np.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "persistence": classify_persistence(win_rate_5b if n else np.nan, win_rates[30]),
    }


def run_filters(df: pd.DataFrame) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for code, group, label, predicate in build_filter_specs():
        mask = predicate(df)
        results.append(summarize_filter(code, group, label, df.loc[mask].copy()))

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


def build_category_presence_rows(df: pd.DataFrame, categories: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, category in enumerate(categories, start=1):
        rows.append(
            summarize_filter(
                f"CAT{index:02d}",
                "CAT",
                f"has {category}",
                df.loc[df[f"has_{category}"]].copy(),
            )
        )

    rows.sort(
        key=lambda row: (
            float("-inf") if pd.isna(row["wr_30b"]) else float(row["wr_30b"]),
            int(row["n"]),
        ),
        reverse=True,
    )
    return rows


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
                f"{row['code']}[{row['group']}]. {row['label']}",
                f"{row['n']:,}",
                fmt_pct(float(row["wr_5b"])) if not pd.isna(row["wr_5b"]) else "nan",
                fmt_pct(float(row["wr_10b"])) if not pd.isna(row["wr_10b"]) else "nan",
                fmt_pct(float(row["wr_30b"])) if not pd.isna(row["wr_30b"]) else "nan",
                fmt_float(float(row["pf_5b"])) if not pd.isna(row["pf_5b"]) else "nan",
                fmt_float(float(row["avg_ticks_5b"])) if not pd.isna(row["avg_ticks_5b"]) else "nan",
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


def render_summary_line(row: dict[str, object]) -> str:
    return (
        f"N={row['n']:,} | WR5={fmt_pct(float(row['wr_5b']))} | WR10={fmt_pct(float(row['wr_10b']))} | "
        f"WR30={fmt_pct(float(row['wr_30b']))} | PF5={fmt_float(float(row['pf_5b']))} | "
        f"Avg5={fmt_float(float(row['avg_ticks_5b']))}t | CI5={fmt_ci(float(row['ci_low']), float(row['ci_high']))} | "
        f"Persistence={row['persistence']}"
    )


def best_row_for_group(rows: list[dict[str, object]], group: str, *, min_n: int = 0) -> dict[str, object]:
    return next(row for row in rows if row["group"] == group and int(row["n"]) >= min_n)


def best_overall_row(rows: list[dict[str, object]], *, min_n: int = 0) -> dict[str, object]:
    return next(row for row in rows if int(row["n"]) >= min_n)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events = load_events()
    bars_1m = load_ohlcv()
    observations, categories = build_observations(events)
    context = build_timeframe_context(bars_1m)
    observations = attach_context(observations, context)
    observations = add_context_flags(observations)

    baseline_all = summarize_filter("00", "BASE", "All grouped same-direction observations", observations)
    baseline_core = summarize_filter(
        "BASE60",
        "BASE",
        "60m + 15m grouped observations",
        observations.loc[base_core_mask(observations)].copy(),
    )
    baseline_first_hour = summarize_filter(
        "BASEFH",
        "BASE",
        "60m + 15m + first_hour grouped observations",
        observations.loc[base_first_hour_mask(observations)].copy(),
    )
    baseline_first_hour_not_killers = summarize_filter(
        "BASEFHNK",
        "BASE",
        "60m + 15m + first_hour + NOT killers grouped observations",
        observations.loc[base_first_hour_not_killers_mask(observations)].copy(),
    )
    known_score60 = summarize_filter(
        "KNOWN60",
        "BASE",
        "score >= 60 + 60m + 15m + first_hour + NOT killers",
        observations.loc[base_first_hour_not_killers_mask(observations) & observations["max_score_final"].ge(60)].copy(),
    )

    results = run_filters(observations)
    category_presence_rows = build_category_presence_rows(
        observations.loc[base_first_hour_not_killers_mask(observations) & observations["max_score_final"].ge(60)].copy(),
        categories,
    )

    best_overall = results[0]
    best_tier = best_row_for_group(results, "A")
    best_score_bucket = best_row_for_group(results, "B")
    best_strength = best_row_for_group(results, "C")
    best_category = best_row_for_group(results, "D")
    best_overall_scalable = best_overall_row(results, min_n=SCALABLE_MIN_N)
    best_tier_scalable = best_row_for_group(results, "A", min_n=SCALABLE_MIN_N)
    best_score_bucket_scalable = best_row_for_group(results, "B", min_n=SCALABLE_MIN_N)
    best_strength_scalable = best_row_for_group(results, "C", min_n=SCALABLE_MIN_N)
    best_category_scalable = best_row_for_group(results, "D", min_n=SCALABLE_MIN_N)

    lines = [
        "DEEP6 round34 score decomposition analysis",
        "========================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique same-bar, same-direction grouped signal observation (global_index, direction_sign).",
        "Grouped fields: max_score_final, best_score_tier, max_strength, category_set, signal_count, category_count.",
        "best_score_tier uses hierarchy TYPE_A > TYPE_B > TYPE_C > QUIET inside each grouped observation.",
        "Base 60m gate = bullish bar_low in bottom 20% of 60m range / bearish bar_high in top 20%.",
        "Base 15m gate = signal direction matches 15m open-close sign. first_hour = 09:30-10:29 ET.",
        "NOT killers = NOT killer_1 (60m position between 40%-60%) AND NOT killer_2 (bar_volume > 3x prior 20-observation EMA within session).",
        "Score brackets use lower-inclusive / upper-exclusive bins: [0,30), [30,50), [50,65), [65,80), [80,100].",
        "Strength brackets use <0.3, [0.3,0.6), [0.6,0.9), and >=0.9.",
        "N uses rows with complete 5b/10b/30b forward closes so all WR windows compare the same sample.",
        "PF and Avg Ticks are based on 5b returns. Tables are sorted by 30b WR descending.",
        "",
        f"Raw event rows loaded:                             {len(events):,}",
        f"Grouped observations:                              {len(observations):,}",
        f"15m bars built:                                    {len(context[15]):,}",
        f"60m bars built:                                    {len(context[60]):,}",
        f"15m trend aligned observations:                    {int(observations['is_15m_trend_aligned'].sum()):,}",
        f"60m extreme observations:                          {int(observations['is_60m_extreme'].sum()):,}",
        f"60m + 15m observations:                            {int(observations['has_core_60m_15m_gate'].sum()):,}",
        f"60m + 15m + first_hour observations:               {int(observations['has_core_60m_15m_first_hour_gate'].sum()):,}",
        f"NOT-killers observations:                          {int(observations['passes_not_all_killers'].sum()):,}",
        "",
        f"Baseline all bars: {render_summary_line(baseline_all)}",
        f"Baseline 60m + 15m: {render_summary_line(baseline_core)}",
        f"Baseline 60m + 15m + first_hour: {render_summary_line(baseline_first_hour)}",
        f"Baseline 60m + 15m + first_hour + NOT killers: {render_summary_line(baseline_first_hour_not_killers)}",
        f"Known working stack (score >= 60 + 60m + 15m + first_hour + NOT killers): {render_summary_line(known_score60)}",
        "",
        "Category presence inside the known working stack (overlapping families)",
        "------------------------------------------------------------------",
        f"Interpret with N discipline: rows below {SCALABLE_MIN_N:,} are descriptive, not stable by themselves.",
    ]
    lines.extend(render_table(category_presence_rows))
    lines.extend(
        [
            "",
            "20 score decomposition filters ranked by 30b WR",
            "---------------------------------------------",
        ]
    )
    lines.extend(render_table(results))
    lines.extend(
        [
            "",
            "Group winners",
            "-------------",
            f"Group A best score-tier rule: {best_tier['code']}[{best_tier['group']}]. {best_tier['label']} | {render_summary_line(best_tier)}",
            f"Group B best score-bracket rule: {best_score_bucket['code']}[{best_score_bucket['group']}]. {best_score_bucket['label']} | {render_summary_line(best_score_bucket)}",
            f"Group C best strength rule: {best_strength['code']}[{best_strength['group']}]. {best_strength['label']} | {render_summary_line(best_strength)}",
            f"Group D best category rule: {best_category['code']}[{best_category['group']}]. {best_category['label']} | {render_summary_line(best_category)}",
            f"Best overall tested filter: {best_overall['code']}[{best_overall['group']}]. {best_overall['label']} | {render_summary_line(best_overall)}",
            "",
            f"Scalable winners (N >= {SCALABLE_MIN_N:,})",
            "---------------------------",
            f"Group A scalable score-tier rule: {best_tier_scalable['code']}[{best_tier_scalable['group']}]. {best_tier_scalable['label']} | {render_summary_line(best_tier_scalable)}",
            f"Group B scalable score-bracket rule: {best_score_bucket_scalable['code']}[{best_score_bucket_scalable['group']}]. {best_score_bucket_scalable['label']} | {render_summary_line(best_score_bucket_scalable)}",
            f"Group C scalable strength rule: {best_strength_scalable['code']}[{best_strength_scalable['group']}]. {best_strength_scalable['label']} | {render_summary_line(best_strength_scalable)}",
            f"Group D scalable category rule: {best_category_scalable['code']}[{best_category_scalable['group']}]. {best_category_scalable['label']} | {render_summary_line(best_category_scalable)}",
            f"Best overall scalable filter: {best_overall_scalable['code']}[{best_overall_scalable['group']}]. {best_overall_scalable['label']} | {render_summary_line(best_overall_scalable)}",
            "",
            "Derived optimal scoring rules",
            "-----------------------------",
            "1. Keep the structural gate first: 60m_extreme + 15m_trend_aligned is still the non-negotiable base.",
            f"2. Pure-edge winners are: tier={best_tier['label']}; score={best_score_bucket['label']}; strength={best_strength['label']}; category={best_category['label']}.",
            f"3. Stability-biased winners (N >= {SCALABLE_MIN_N:,}) are: tier={best_tier_scalable['label']}; score={best_score_bucket_scalable['label']}; strength={best_strength_scalable['label']}; category={best_category_scalable['label']}.",
            f"4. If you want one robust tested rule instead of component stacking, start from: {best_overall_scalable['label']}.",
            "5. Treat those as component winners; only filters 15 and 20 explicitly test multi-component stacking inside this round.",
        ]
    )

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
