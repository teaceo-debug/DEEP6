#!/usr/bin/env python3
from __future__ import annotations

import calendar
import math
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data/backtests/signal_events.csv"
OHLCV_CSV = ROOT / "data/backtests/nq_1yr_1m.csv"
OUT_DIR = ROOT / "data/backtests/analysis"
OUT_PATH = OUT_DIR / "round13_macro_calendar_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOW = 5
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
FIRST_HOUR_MINUTES = 60
LUNCH_START_MINUTE = 12 * 60
LUNCH_END_MINUTE = 14 * 60
LAST_WEEK_SESSION_COUNT = 5

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

ROLLOVER_WEEKS = [
    "2025-03-10",
    "2025-06-09",
    "2025-09-08",
    "2025-12-08",
    "2026-03-09",
]

FilterSpec = tuple[str, str, Callable[[pd.DataFrame], pd.Series]]


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


def third_friday(year: int, month: int) -> pd.Timestamp:
    cal = calendar.monthcalendar(year, month)
    friday = calendar.FRIDAY
    fridays = [week[friday] for week in cal if week[friday] != 0]
    return pd.Timestamp(year=year, month=month, day=fridays[2]).normalize()


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
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
        )
        .sort_values("global_index", kind="stable")
        .reset_index(drop=True)
    )
    observations["direction_sign"] = np.sign(observations["bar_delta"].fillna(0.0)).astype(int)
    observations = observations[observations["direction_sign"] != 0].copy()
    observations["direction"] = np.where(observations["direction_sign"] > 0, "BULLISH", "BEARISH")
    observations["ret_5b_ticks"] = observations["direction_sign"] * (
        (observations["fwd_close_5b"] - observations["bar_close"]) / TICK_SIZE
    )
    observations["session_date_ts"] = pd.to_datetime(observations["session_date"], errors="coerce").dt.normalize()
    return observations.reset_index(drop=True)


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
    df["bar_volume"] = pd.to_numeric(df["bar_volume"], errors="coerce")
    return df.reset_index(drop=True)


def add_base_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["is_15m_trend_aligned"] = out["direction_sign"] == out["trend_sign_15m"]

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
    lunch_mask = minute_of_day.ge(LUNCH_START_MINUTE) & minute_of_day.lt(LUNCH_END_MINUTE)
    out["is_not_lunch"] = ~lunch_mask

    by_session = out.groupby("session_date", sort=False)
    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])
    out["is_killer_1"] = out["pos_60m"].between(0.40, 0.60, inclusive="both")
    out["is_killer_2"] = out["is_volume_spike_3x"]
    out["passes_not_all_killers"] = (~out["is_killer_1"]) & (~out["is_killer_2"])
    return out


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


def expand_session_offsets(
    session_dates: pd.DatetimeIndex,
    anchor_dates: list[str],
    offsets: tuple[int, ...],
) -> set[pd.Timestamp]:
    index_by_date = {session_date: idx for idx, session_date in enumerate(session_dates)}
    selected: set[pd.Timestamp] = set()

    for raw_date in anchor_dates:
        anchor = pd.Timestamp(raw_date).normalize()
        anchor_idx = index_by_date.get(anchor)
        if anchor_idx is None:
            continue
        for offset in offsets:
            target_idx = anchor_idx + offset
            if 0 <= target_idx < len(session_dates):
                selected.add(session_dates[target_idx])
    return selected


def build_session_calendar(bars_1m: pd.DataFrame) -> pd.DataFrame:
    session_dates = build_trading_calendar(bars_1m)
    calendar_df = pd.DataFrame({"session_date_ts": session_dates}).sort_values("session_date_ts").reset_index(drop=True)
    calendar_df["year"] = calendar_df["session_date_ts"].dt.year
    calendar_df["month"] = calendar_df["session_date_ts"].dt.month
    calendar_df["day"] = calendar_df["session_date_ts"].dt.day
    calendar_df["month_period"] = calendar_df["session_date_ts"].dt.to_period("M")

    calendar_df["is_january"] = calendar_df["month"].eq(1)
    calendar_df["is_sep_oct"] = calendar_df["month"].isin([9, 10])
    calendar_df["is_december"] = calendar_df["month"].eq(12)
    calendar_df["is_summer"] = calendar_df["month"].isin([6, 7, 8])
    calendar_df["is_not_summer"] = ~calendar_df["is_summer"]
    calendar_df["is_first_week_of_month"] = calendar_df["day"].le(7)
    calendar_df["is_last_week_of_month"] = False
    calendar_df["is_month_end_pm1"] = False
    calendar_df["is_opex_week"] = False

    index_by_date = {session_date: idx for idx, session_date in enumerate(session_dates)}
    month_end_dates: set[pd.Timestamp] = set()

    for _, month_slice in calendar_df.groupby("month_period", sort=False):
        calendar_df.loc[month_slice.tail(LAST_WEEK_SESSION_COUNT).index, "is_last_week_of_month"] = True

        last_session = pd.Timestamp(month_slice["session_date_ts"].iloc[-1])
        last_idx = index_by_date[last_session]
        for offset in (-1, 0, 1):
            target_idx = last_idx + offset
            if 0 <= target_idx < len(session_dates):
                month_end_dates.add(session_dates[target_idx])

    for year, month in calendar_df[["year", "month"]].drop_duplicates().itertuples(index=False):
        third_fri = third_friday(int(year), int(month))
        monday = third_fri - pd.Timedelta(days=third_fri.weekday())
        friday = monday + pd.Timedelta(days=4)
        opex_mask = calendar_df["session_date_ts"].between(monday, friday)
        calendar_df.loc[opex_mask, "is_opex_week"] = True

    fomc_day_dates = expand_session_offsets(session_dates, FOMC_DATES, (0,))
    fomc_day_after_dates = expand_session_offsets(session_dates, FOMC_DATES, (1,))
    fomc_two_days_after_dates = expand_session_offsets(session_dates, FOMC_DATES, (2,))
    fomc_week_dates = expand_session_offsets(session_dates, FOMC_DATES, (-2, -1, 0, 1, 2))
    rollover_week_dates = expand_session_offsets(session_dates, ROLLOVER_WEEKS, (-2, -1, 0, 1, 2))

    calendar_df["is_fomc_day"] = calendar_df["session_date_ts"].isin(fomc_day_dates)
    calendar_df["is_day_after_fomc"] = calendar_df["session_date_ts"].isin(fomc_day_after_dates)
    calendar_df["is_two_days_after_fomc"] = calendar_df["session_date_ts"].isin(fomc_two_days_after_dates)
    calendar_df["is_fomc_week"] = calendar_df["session_date_ts"].isin(fomc_week_dates)
    calendar_df["is_not_fomc_week"] = ~calendar_df["is_fomc_week"]
    calendar_df["is_not_fomc_day"] = ~calendar_df["is_fomc_day"]
    calendar_df["is_rollover_week"] = calendar_df["session_date_ts"].isin(rollover_week_dates)
    calendar_df["is_not_rollover_week"] = ~calendar_df["is_rollover_week"]
    calendar_df["is_month_end_pm1"] = calendar_df["session_date_ts"].isin(month_end_dates)
    return calendar_df.drop(columns=["year", "month_period"])


def attach_calendar_flags(observations: pd.DataFrame, calendar_df: pd.DataFrame) -> pd.DataFrame:
    out = observations.merge(calendar_df, on="session_date_ts", how="left", validate="many_to_one")
    bool_cols = [
        "is_january",
        "is_sep_oct",
        "is_december",
        "is_summer",
        "is_not_summer",
        "is_first_week_of_month",
        "is_last_week_of_month",
        "is_month_end_pm1",
        "is_opex_week",
        "is_fomc_day",
        "is_day_after_fomc",
        "is_two_days_after_fomc",
        "is_fomc_week",
        "is_not_fomc_week",
        "is_not_fomc_day",
        "is_rollover_week",
        "is_not_rollover_week",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def base_mask(df: pd.DataFrame) -> pd.Series:
    return df["is_60m_extreme"] & df["is_15m_trend_aligned"]


def summarize_filter(code: str, label: str, df: pd.DataFrame) -> dict:
    returns = df["ret_5b_ticks"].dropna()
    n = int(len(returns))
    wins = int((returns > 0).sum())
    ci_low, ci_high, win_rate = wilson_ci(n, wins)
    return {
        "code": code,
        "label": label,
        "n": n,
        "win_rate": win_rate,
        "wins": wins,
        "profit_factor": profit_factor(returns) if n else np.nan,
        "avg_return_5b_ticks": float(returns.mean()) if n else np.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "flag": status_flag(n, ci_low),
    }


def build_filter_specs() -> list[FilterSpec]:
    return [
        ("01", "FOMC day + 60m + 15m", lambda df: base_mask(df) & df["is_fomc_day"]),
        ("02", "Day after FOMC + 60m + 15m", lambda df: base_mask(df) & df["is_day_after_fomc"]),
        ("03", "2 days after FOMC + 60m + 15m", lambda df: base_mask(df) & df["is_two_days_after_fomc"]),
        ("04", "NOT FOMC week + 60m + 15m", lambda df: base_mask(df) & df["is_not_fomc_week"]),
        ("05", "FOMC day + 60m + 15m + first_hour", lambda df: base_mask(df) & df["is_fomc_day"] & df["is_first_hour"]),
        ("06", "Rollover week + 60m + 15m", lambda df: base_mask(df) & df["is_rollover_week"]),
        ("07", "NOT rollover week + 60m + 15m", lambda df: base_mask(df) & df["is_not_rollover_week"]),
        ("08", "Rollover week + 60m + 15m + NOT lunch", lambda df: base_mask(df) & df["is_rollover_week"] & df["is_not_lunch"]),
        ("09", "First week of month + 60m + 15m", lambda df: base_mask(df) & df["is_first_week_of_month"]),
        ("10", "OpEx week + 60m + 15m", lambda df: base_mask(df) & df["is_opex_week"]),
        ("11", "Last week of month + 60m + 15m", lambda df: base_mask(df) & df["is_last_week_of_month"]),
        ("12", "Month-end day ±1 + 60m + 15m", lambda df: base_mask(df) & df["is_month_end_pm1"]),
        ("13", "January + 60m + 15m", lambda df: base_mask(df) & df["is_january"]),
        ("14", "September-October + 60m + 15m", lambda df: base_mask(df) & df["is_sep_oct"]),
        ("15", "December + 60m + 15m", lambda df: base_mask(df) & df["is_december"]),
        ("16", "Summer (Jun-Aug) + 60m + 15m", lambda df: base_mask(df) & df["is_summer"]),
        (
            "17",
            "NOT FOMC week + NOT rollover + OpEx week + 60m + 15m",
            lambda df: base_mask(df) & df["is_not_fomc_week"] & df["is_not_rollover_week"] & df["is_opex_week"],
        ),
        (
            "18",
            "NOT FOMC + NOT rollover + first_hour + 60m + 15m + NOT killers",
            lambda df: base_mask(df)
            & df["is_not_fomc_day"]
            & df["is_not_rollover_week"]
            & df["is_first_hour"]
            & df["passes_not_all_killers"],
        ),
        (
            "19",
            "December + OpEx week + 60m + 15m",
            lambda df: base_mask(df) & df["is_december"] & df["is_opex_week"],
        ),
        (
            "20",
            "NOT summer + NOT FOMC + 60m + 15m + NOT killers + first_hour",
            lambda df: base_mask(df)
            & df["is_not_summer"]
            & df["is_not_fomc_day"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
    ]


def run_filters(df: pd.DataFrame) -> list[dict]:
    results: list[dict] = []
    for code, label, predicate in build_filter_specs():
        mask = predicate(df)
        results.append(summarize_filter(code, label, df.loc[mask].copy()))

    results.sort(
        key=lambda row: (
            float("-inf") if pd.isna(row["avg_return_5b_ticks"]) else float(row["avg_return_5b_ticks"]),
            float("-inf") if pd.isna(row["win_rate"]) else float(row["win_rate"]),
            int(row["n"]),
        ),
        reverse=True,
    )
    return results


def render_table(rows: list[dict]) -> list[str]:
    headers = ["Filter", "N", "WR 5b", "PF", "Avg Ticks", "Wilson 95% CI", "Flag"]
    data_rows: list[list[str]] = []

    for row in rows:
        data_rows.append(
            [
                f"{row['code']}. {row['label']}",
                f"{row['n']:,}",
                fmt_pct(row["win_rate"]),
                fmt_float(row["profit_factor"]),
                fmt_float(row["avg_return_5b_ticks"]),
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


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events = load_events()
    bars_1m = load_ohlcv()
    observations = build_observations(events)
    context = build_timeframe_context(bars_1m)
    observations = attach_context(observations, context)
    observations = add_base_flags(observations)
    calendar_df = build_session_calendar(bars_1m)
    observations = attach_calendar_flags(observations, calendar_df)

    baseline_all = summarize_filter("00", "All non-zero-delta grouped bars", observations)
    baseline_base = summarize_filter(
        "BASE",
        "All non-zero-delta grouped bars at 60m + 15m base",
        observations.loc[base_mask(observations)].copy(),
    )
    results = run_filters(observations)

    lines = [
        "DEEP6 round 13 macro/calendar analysis",
        "=====================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index.",
        "Trade direction for P&L: sign(bar_delta). Zero-delta bars are skipped.",
        "Base gate for all 20 tests = 60m_extreme + 15m_trend_aligned.",
        "60m_extreme = bullish bar_low in bottom 20% of 60m range / bearish bar_high in top 20%.",
        "15m_trend = sign(bar_delta) matches 15m open-close sign.",
        "FOMC proximity uses the exact supplied FOMC dates projected onto the trading-session calendar.",
        "FOMC week = FOMC session ±2 trading sessions. Filters 18 and 20 use NOT FOMC day only.",
        "Rollover week = supplied rollover anchor date ±2 trading sessions.",
        "First week = calendar day 1-7. Last week = final 5 trading sessions of the month.",
        "Month-end ±1 = last trading session of each month plus one trading session before/after.",
        "first_hour = 09:30-10:29 ET. NOT lunch excludes 12:00-13:59 ET.",
        "NOT killers = NOT killer_1 (mid-60m position 40%-60%) AND NOT killer_2 (bar_volume > 3x prior 20-bar EMA).",
        "Status flags: VALIDATED = N>=30 and Wilson lower bound >50%; PROMISING = N>=15 and Wilson lower bound >45%; LOW_N = N<15.",
        "Final ranking is sorted by Avg Ticks descending.",
        "",
        f"Raw event rows loaded:               {len(events):,}",
        f"Grouped observations:                {len(observations):,}",
        f"15m bars built:                      {len(context[15]):,}",
        f"60m bars built:                      {len(context[60]):,}",
        f"Trading sessions in calendar:        {len(calendar_df):,}",
        f"60m + 15m base observations:         {int(base_mask(observations).sum()):,}",
        f"FOMC-day observations:               {int(observations['is_fomc_day'].sum()):,}",
        f"FOMC-week observations:              {int(observations['is_fomc_week'].sum()):,}",
        f"Rollover-week observations:          {int(observations['is_rollover_week'].sum()):,}",
        f"OpEx-week observations:              {int(observations['is_opex_week'].sum()):,}",
        f"Month-end ±1 observations:           {int(observations['is_month_end_pm1'].sum()):,}",
        "",
        f"Baseline all bars: N={baseline_all['n']:,} | WR5={fmt_pct(baseline_all['win_rate'])} | PF={fmt_float(baseline_all['profit_factor'])} | Avg={fmt_float(baseline_all['avg_return_5b_ticks'])}t | CI={fmt_ci(baseline_all['ci_low'], baseline_all['ci_high'])}",
        f"Baseline 60m + 15m: N={baseline_base['n']:,} | WR5={fmt_pct(baseline_base['win_rate'])} | PF={fmt_float(baseline_base['profit_factor'])} | Avg={fmt_float(baseline_base['avg_return_5b_ticks'])}t | CI={fmt_ci(baseline_base['ci_low'], baseline_base['ci_high'])}",
        "",
        "All 20 macro/calendar filters ranked by Avg Ticks",
        "-----------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
