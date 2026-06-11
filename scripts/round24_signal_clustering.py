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
OUT_PATH = OUT_DIR / "round24_signal_clustering_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
FIRST_HOUR_MINUTES = 60

FOMC_DATES = [
    "2025-01-29",
    "2025-03-19",
    "2025-05-07",
    "2025-06-18",
    "2025-07-30",
    "2025-09-17",
    "2025-10-29",
    "2025-12-17",
    "2026-01-28",
    "2026-03-18",
]

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
    df = pd.read_csv(EVENTS_CSV, usecols=cols, dtype=dtypes, low_memory=False)
    numeric_cols = [
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


def build_observations(events: pd.DataFrame) -> pd.DataFrame:
    observations = (
        events.groupby(["global_index", "direction_sign"], as_index=False, sort=False)
        .agg(
            session_date=("session_date", "first"),
            bar_ts=("bar_ts", "first"),
            bar_index=("bar_index", "first"),
            bar_open=("bar_open", "first"),
            bar_high=("bar_high", "first"),
            bar_low=("bar_low", "first"),
            bar_close=("bar_close", "first"),
            bar_volume=("bar_volume", "first"),
            fwd_close_5b=("fwd_close_5b", "first"),
            fwd_close_10b=("fwd_close_10b", "first"),
            fwd_close_30b=("fwd_close_30b", "first"),
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
            max_score_final=("score_final", "max"),
        )
        .sort_values(["global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    observations["direction"] = np.where(observations["direction_sign"] > 0, "BULLISH", "BEARISH")
    observations["session_date_ts"] = pd.to_datetime(observations["session_date"], errors="coerce").dt.normalize()

    for window in FORWARD_WINDOWS:
        observations[f"ret_{window}b_ticks"] = observations["direction_sign"] * (
            (observations[f"fwd_close_{window}b"] - observations["bar_close"]) / TICK_SIZE
        )

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

    for col in ["bar_high", "bar_low", "bar_close", "bar_volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.reset_index(drop=True)


def build_trading_calendar(bars_1m: pd.DataFrame) -> pd.DatetimeIndex:
    minute_of_day = bars_1m["ts_event"].dt.hour * 60 + bars_1m["ts_event"].dt.minute
    rth_mask = minute_of_day.ge(RTH_START_MINUTE) & minute_of_day.lt(RTH_END_MINUTE)
    sessions = (
        bars_1m.loc[rth_mask, "ts_event"]
        .dt.tz_localize(None)
        .dt.normalize()
        .drop_duplicates()
        .sort_values()
    )
    return pd.DatetimeIndex(sessions)


def build_session_calendar(bars_1m: pd.DataFrame) -> pd.DataFrame:
    session_dates = build_trading_calendar(bars_1m)
    calendar_df = pd.DataFrame({"session_date_ts": session_dates}).sort_values("session_date_ts").reset_index(drop=True)
    calendar_df["month"] = calendar_df["session_date_ts"].dt.month
    calendar_df["is_summer"] = calendar_df["month"].isin([6, 7, 8])
    calendar_df["is_not_summer"] = ~calendar_df["is_summer"]

    fomc_day_dates = {pd.Timestamp(raw_date).normalize() for raw_date in FOMC_DATES}
    calendar_df["is_fomc_day"] = calendar_df["session_date_ts"].isin(fomc_day_dates)
    calendar_df["is_not_fomc_day"] = ~calendar_df["is_fomc_day"]
    return calendar_df.drop(columns=["month"])


def attach_calendar_flags(observations: pd.DataFrame, calendar_df: pd.DataFrame) -> pd.DataFrame:
    out = observations.merge(calendar_df, on="session_date_ts", how="left", validate="many_to_one")
    for col in ["is_summer", "is_not_summer", "is_fomc_day", "is_not_fomc_day"]:
        out[col] = out[col].fillna(False).astype(bool)
    return out


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


def base_first_hour_mask(df: pd.DataFrame) -> pd.Series:
    return df["has_core_60m_15m_first_hour_gate"]


def base_first_hour_not_killers_mask(df: pd.DataFrame) -> pd.Series:
    return df["has_core_60m_15m_first_hour_gate"] & df["passes_not_all_killers"]


def build_filter_specs() -> list[FilterSpec]:
    return [
        ("01", "A", "3+ signals same direction + 60m + 15m + first_hour", lambda df: base_first_hour_mask(df) & df["signal_count"].ge(3)),
        ("02", "A", "5+ signals same direction + 60m + 15m + first_hour", lambda df: base_first_hour_mask(df) & df["signal_count"].ge(5)),
        ("03", "A", "7+ signals same direction + 60m + 15m + first_hour", lambda df: base_first_hour_mask(df) & df["signal_count"].ge(7)),
        ("04", "A", "10+ signals same direction + 60m + 15m + first_hour", lambda df: base_first_hour_mask(df) & df["signal_count"].ge(10)),
        ("05", "A", "15+ signals same direction + 60m + 15m + first_hour", lambda df: base_first_hour_mask(df) & df["signal_count"].ge(15)),
        ("06", "B", "2+ categories + 60m + 15m + first_hour", lambda df: base_first_hour_mask(df) & df["category_count"].ge(2)),
        ("07", "B", "3+ categories + 60m + 15m + first_hour", lambda df: base_first_hour_mask(df) & df["category_count"].ge(3)),
        ("08", "B", "4+ categories + 60m + 15m + first_hour", lambda df: base_first_hour_mask(df) & df["category_count"].ge(4)),
        ("09", "B", "5+ categories + 60m + 15m + first_hour", lambda df: base_first_hour_mask(df) & df["category_count"].ge(5)),
        ("10", "B", "6+ categories + 60m + 15m + first_hour", lambda df: base_first_hour_mask(df) & df["category_count"].ge(6)),
        ("11", "C", "score >= 50 + 60m + 15m + first_hour + NOT killers", lambda df: base_first_hour_not_killers_mask(df) & df["max_score_final"].ge(50)),
        ("12", "C", "score >= 60 + 60m + 15m + first_hour + NOT killers", lambda df: base_first_hour_not_killers_mask(df) & df["max_score_final"].ge(60)),
        ("13", "C", "score >= 70 + 60m + 15m + first_hour + NOT killers", lambda df: base_first_hour_not_killers_mask(df) & df["max_score_final"].ge(70)),
        ("14", "C", "score >= 80 + 60m + 15m + first_hour + NOT killers", lambda df: base_first_hour_not_killers_mask(df) & df["max_score_final"].ge(80)),
        ("15", "C", "score >= 90 + 60m + 15m + first_hour + NOT killers", lambda df: base_first_hour_not_killers_mask(df) & df["max_score_final"].ge(90)),
        ("16", "D", "5+ signals + score >= 60 + 60m + 15m + first_hour + NOT killers", lambda df: base_first_hour_not_killers_mask(df) & df["signal_count"].ge(5) & df["max_score_final"].ge(60)),
        ("17", "D", "7+ signals + score >= 70 + 60m + 15m + first_hour + NOT killers", lambda df: base_first_hour_not_killers_mask(df) & df["signal_count"].ge(7) & df["max_score_final"].ge(70)),
        ("18", "D", "3+ categories + score >= 60 + 60m + 15m + first_hour + NOT killers", lambda df: base_first_hour_not_killers_mask(df) & df["category_count"].ge(3) & df["max_score_final"].ge(60)),
        ("19", "D", "4+ categories + score >= 70 + 60m + 15m + first_hour + NOT killers", lambda df: base_first_hour_not_killers_mask(df) & df["category_count"].ge(4) & df["max_score_final"].ge(70)),
        (
            "20",
            "E",
            "5+ signals + 4+ categories + score >= 70 + 60m + 15m + first_hour + NOT killers + NOT FOMC + NOT summer",
            lambda df: base_first_hour_not_killers_mask(df)
            & df["signal_count"].ge(5)
            & df["category_count"].ge(4)
            & df["max_score_final"].ge(70)
            & df["is_not_fomc_day"]
            & df["is_not_summer"],
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


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events = load_events()
    bars_1m = load_ohlcv()
    observations = build_observations(events)
    context = build_timeframe_context(bars_1m)
    observations = attach_context(observations, context)
    observations = add_context_flags(observations)
    calendar_df = build_session_calendar(bars_1m)
    observations = attach_calendar_flags(observations, calendar_df)

    baseline_all = summarize_filter("00", "BASE", "All grouped same-direction observations", observations)
    baseline_core = summarize_filter(
        "BASE",
        "BASE",
        "60m + 15m + first_hour grouped observations",
        observations.loc[base_first_hour_mask(observations)].copy(),
    )
    baseline_core_not_killers = summarize_filter(
        "BASE+NK",
        "BASE",
        "60m + 15m + first_hour + NOT killers grouped observations",
        observations.loc[base_first_hour_not_killers_mask(observations)].copy(),
    )
    results = run_filters(observations)

    lines = [
        "DEEP6 round24 signal clustering analysis",
        "=======================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique same-bar, same-direction grouped signal observation (global_index, direction_sign).",
        "signal_count = grouped unique signal_id count; category_count = grouped unique category count; score = grouped max score_final.",
        "Base gate = 60m_extreme + 15m_trend_aligned + first_hour.",
        "60m_extreme = bullish bar_low in bottom 20% of 60m range / bearish bar_high in top 20%.",
        "15m_trend_aligned = signal direction matches 15m open-close sign. first_hour = 09:30-10:29 ET.",
        "NOT killers = NOT killer_1 (60m position between 40%-60%) AND NOT killer_2 (bar_volume > 3x prior 20-bar EMA within session).",
        "NOT FOMC uses the exact round13 FOMC day list. NOT summer excludes Jun-Aug sessions.",
        "N uses rows with complete 5b/10b/30b forward closes so all WR windows compare the same sample.",
        "PF and Avg Ticks are based on 5b returns. Persistence compares WR_30b versus WR_5b.",
        "Sorted by 30b WR descending.",
        "",
        f"Raw event rows loaded:                     {len(events):,}",
        f"Grouped observations:                      {len(observations):,}",
        f"15m bars built:                            {len(context[15]):,}",
        f"60m bars built:                            {len(context[60]):,}",
        f"Trading sessions in calendar:              {len(calendar_df):,}",
        f"15m trend aligned observations:            {int(observations['is_15m_trend_aligned'].sum()):,}",
        f"60m extreme observations:                  {int(observations['is_60m_extreme'].sum()):,}",
        f"60m + 15m + first_hour observations:       {int(observations['has_core_60m_15m_first_hour_gate'].sum()):,}",
        f"NOT-killers observations:                  {int(observations['passes_not_all_killers'].sum()):,}",
        f"FOMC-day observations:                     {int(observations['is_fomc_day'].sum()):,}",
        f"Summer observations:                       {int(observations['is_summer'].sum()):,}",
        "",
        f"Baseline all bars: N={baseline_all['n']:,} | WR5={fmt_pct(float(baseline_all['wr_5b']))} | WR10={fmt_pct(float(baseline_all['wr_10b']))} | WR30={fmt_pct(float(baseline_all['wr_30b']))} | PF5={fmt_float(float(baseline_all['pf_5b']))} | Avg5={fmt_float(float(baseline_all['avg_ticks_5b']))}t | CI5={fmt_ci(float(baseline_all['ci_low']), float(baseline_all['ci_high']))} | Persistence={baseline_all['persistence']}",
        f"Baseline 60m + 15m + first_hour: N={baseline_core['n']:,} | WR5={fmt_pct(float(baseline_core['wr_5b']))} | WR10={fmt_pct(float(baseline_core['wr_10b']))} | WR30={fmt_pct(float(baseline_core['wr_30b']))} | PF5={fmt_float(float(baseline_core['pf_5b']))} | Avg5={fmt_float(float(baseline_core['avg_ticks_5b']))}t | CI5={fmt_ci(float(baseline_core['ci_low']), float(baseline_core['ci_high']))} | Persistence={baseline_core['persistence']}",
        f"Baseline 60m + 15m + first_hour + NOT killers: N={baseline_core_not_killers['n']:,} | WR5={fmt_pct(float(baseline_core_not_killers['wr_5b']))} | WR10={fmt_pct(float(baseline_core_not_killers['wr_10b']))} | WR30={fmt_pct(float(baseline_core_not_killers['wr_30b']))} | PF5={fmt_float(float(baseline_core_not_killers['pf_5b']))} | Avg5={fmt_float(float(baseline_core_not_killers['avg_ticks_5b']))}t | CI5={fmt_ci(float(baseline_core_not_killers['ci_low']), float(baseline_core_not_killers['ci_high']))} | Persistence={baseline_core_not_killers['persistence']}",
        "",
        "20 signal-density / diversity / score filters ranked by 30b WR",
        "-------------------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
