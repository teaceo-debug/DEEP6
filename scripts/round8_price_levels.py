#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data/backtests/signal_events.csv"
OHLCV_CSV = ROOT / "data/backtests/nq_1yr_1m.csv"
OUT_DIR = ROOT / "data/backtests/analysis"
OUT_PATH = OUT_DIR / "round8_price_levels_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOW = 5
TICK_SIZE = 0.25
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
FIRST_HOUR_MINUTES = 60


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
    return df


def filter_rth_bars(bars_1m: pd.DataFrame) -> pd.DataFrame:
    bars = bars_1m.copy()
    minute_of_day = bars["ts_event"].dt.hour * 60 + bars["ts_event"].dt.minute
    bars = bars.loc[(minute_of_day >= RTH_START_MINUTE) & (minute_of_day < RTH_END_MINUTE)].copy()
    bars["session_date"] = bars["ts_event"].dt.strftime("%Y-%m-%d")
    bars["minute_of_day"] = minute_of_day.loc[bars.index]
    bars["minutes_since_930"] = bars["minute_of_day"] - RTH_START_MINUTE
    return bars.reset_index(drop=True)


def build_session_context(bars_1m: pd.DataFrame) -> pd.DataFrame:
    bars = filter_rth_bars(bars_1m)
    by_session = bars.groupby("session_date", sort=False)

    bars["session_open"] = by_session["open"].transform("first")
    bars["session_high"] = by_session["high"].cummax()
    bars["session_low"] = by_session["low"].cummin()
    bars["cum_pv"] = ((bars["close"] * bars["volume"]).groupby(bars["session_date"], sort=False).cumsum())
    bars["cum_vol"] = by_session["volume"].cumsum()
    bars["session_vwap"] = np.where(bars["cum_vol"] > 0, bars["cum_pv"] / bars["cum_vol"], np.nan)
    bars["prev_close"] = by_session["close"].shift(1)
    bars["prev_vwap"] = bars.groupby("session_date", sort=False)["session_vwap"].shift(1)
    bars["is_first_hour"] = bars["minutes_since_930"].ge(0) & bars["minutes_since_930"].lt(FIRST_HOUR_MINUTES)
    bars["has_completed_ib"] = bars["minutes_since_930"].ge(FIRST_HOUR_MINUTES)

    ib_levels = (
        bars.loc[bars["is_first_hour"]]
        .groupby("session_date", sort=False)
        .agg(
            ib_high=("high", "max"),
            ib_low=("low", "min"),
        )
        .reset_index()
    )
    bars = bars.merge(ib_levels, on="session_date", how="left", validate="many_to_one")

    daily = (
        bars.groupby("session_date", sort=False)
        .agg(
            day_open=("open", "first"),
            day_high=("high", "max"),
            day_low=("low", "min"),
            day_close=("close", "last"),
        )
        .reset_index()
        .sort_values("session_date", kind="stable")
        .reset_index(drop=True)
    )
    daily["prior_day_open"] = daily["day_open"].shift(1)
    daily["prior_day_high"] = daily["day_high"].shift(1)
    daily["prior_day_low"] = daily["day_low"].shift(1)
    daily["prior_day_close"] = daily["day_close"].shift(1)

    bars = bars.merge(
        daily[
            [
                "session_date",
                "prior_day_open",
                "prior_day_high",
                "prior_day_low",
                "prior_day_close",
            ]
        ],
        on="session_date",
        how="left",
        validate="many_to_one",
    )

    return bars[
        [
            "ts_event",
            "session_open",
            "session_high",
            "session_low",
            "session_vwap",
            "prev_close",
            "prev_vwap",
            "ib_high",
            "ib_low",
            "has_completed_ib",
            "prior_day_open",
            "prior_day_high",
            "prior_day_low",
            "prior_day_close",
        ]
    ].copy()


def add_context_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["is_15m_trend_aligned"] = out["direction_sign"] == out["trend_sign_15m"]

    rng_60m = out["range_60m"].replace(0, np.nan)
    anchor = np.where(out["direction_sign"] > 0, out["bar_low"], out["bar_high"])
    out["pos_60m"] = (anchor - out["low_60m"]) / rng_60m
    out["is_60m_extreme"] = (
        ((out["direction_sign"] > 0) & (out["pos_60m"] <= 0.20))
        | ((out["direction_sign"] < 0) & (out["pos_60m"] >= 0.80))
    )
    return out


def add_time_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] * 60 + out["minute"]) - RTH_START_MINUTE
    lunch_mask = out["minutes_since_930"].ge(150) & out["minutes_since_930"].lt(270)
    out["is_not_lunch"] = ~lunch_mask
    return out


def distance_to_grid(series: pd.Series, spacing: float, offset: float = 0.0) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    distance = np.full(len(values), np.nan, dtype=float)
    valid = ~np.isnan(values)
    remainder = np.mod(values[valid] - offset, spacing)
    distance[valid] = np.minimum(remainder, spacing - remainder)
    return pd.Series(distance, index=series.index)


def price_distance_ticks(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a - b).abs() / TICK_SIZE


def add_price_level_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["signal_price"] = np.where(out["direction_sign"] > 0, out["bar_low"], out["bar_high"])

    out["major_round_dist_ticks"] = distance_to_grid(out["signal_price"], 100.0) / TICK_SIZE
    out["minor_round_dist_ticks"] = distance_to_grid(out["signal_price"], 100.0, offset=50.0) / TICK_SIZE
    out["any_round_dist_ticks"] = out[["major_round_dist_ticks", "minor_round_dist_ticks"]].min(axis=1)

    out["dist_prior_high_ticks"] = price_distance_ticks(out["signal_price"], out["prior_day_high"])
    out["dist_prior_low_ticks"] = price_distance_ticks(out["signal_price"], out["prior_day_low"])
    out["dist_prior_close_ticks"] = price_distance_ticks(out["signal_price"], out["prior_day_close"])
    out["nearest_prior_level_ticks"] = out[
        ["dist_prior_high_ticks", "dist_prior_low_ticks", "dist_prior_close_ticks"]
    ].min(axis=1)

    out["inside_prior_range"] = (
        out["prior_day_low"].notna()
        & out["prior_day_high"].notna()
        & out["signal_price"].ge(out["prior_day_low"])
        & out["signal_price"].le(out["prior_day_high"])
    )
    out["outside_prior_range"] = (
        out["prior_day_low"].notna()
        & out["prior_day_high"].notna()
        & ((out["signal_price"] < out["prior_day_low"]) | (out["signal_price"] > out["prior_day_high"]))
    )

    out["vwap_dist_ticks"] = price_distance_ticks(out["bar_close"], out["session_vwap"])
    out["close_vs_vwap_ticks"] = (out["bar_close"] - out["session_vwap"]) / TICK_SIZE
    out["is_vwap_cross"] = (
        out["prev_close"].notna()
        & out["prev_vwap"].notna()
        & (
            ((out["prev_close"] < out["prev_vwap"]) & (out["bar_close"] > out["session_vwap"]))
            | ((out["prev_close"] > out["prev_vwap"]) & (out["bar_close"] < out["session_vwap"]))
        )
    )

    out["dist_ib_high_ticks"] = price_distance_ticks(out["signal_price"], out["ib_high"])
    out["dist_ib_low_ticks"] = price_distance_ticks(out["signal_price"], out["ib_low"])
    out["failed_ib_high_breakout"] = (
        out["has_completed_ib"].fillna(False)
        & out["ib_high"].notna()
        & out["bar_high"].gt(out["ib_high"])
        & out["bar_close"].lt(out["ib_high"])
    )
    out["failed_ib_low_breakout"] = (
        out["has_completed_ib"].fillna(False)
        & out["ib_low"].notna()
        & out["bar_low"].lt(out["ib_low"])
        & out["bar_close"].gt(out["ib_low"])
    )

    return out


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


def build_filter_specs() -> list[tuple[str, str, object]]:
    return [
        ("01", "Within 10t of xx00 major round + 60m_extreme", lambda df: df["is_60m_extreme"] & df["major_round_dist_ticks"].le(10)),
        ("02", "Within 10t of xx50 minor round + 60m_extreme", lambda df: df["is_60m_extreme"] & df["minor_round_dist_ticks"].le(10)),
        ("03", "Within 5t of any xx00/xx50 round + 60m_extreme", lambda df: df["is_60m_extreme"] & df["any_round_dist_ticks"].le(5)),
        ("04", "NOT near any round (>25t) + 60m_extreme", lambda df: df["is_60m_extreme"] & df["any_round_dist_ticks"].gt(25)),
        ("05", "Major round + 60m_extreme + 15m_trend", lambda df: df["is_60m_extreme"] & df["major_round_dist_ticks"].le(10) & df["is_15m_trend_aligned"]),
        ("06", "Within 15t of prior day high + 60m_extreme", lambda df: df["is_60m_extreme"] & df["direction_sign"].lt(0) & df["dist_prior_high_ticks"].le(15)),
        ("07", "Within 15t of prior day low + 60m_extreme", lambda df: df["is_60m_extreme"] & df["direction_sign"].gt(0) & df["dist_prior_low_ticks"].le(15)),
        ("08", "Within 15t of prior day close + 60m_extreme", lambda df: df["is_60m_extreme"] & df["dist_prior_close_ticks"].le(15)),
        ("09", "Inside prior day range + 60m_extreme", lambda df: df["is_60m_extreme"] & df["inside_prior_range"]),
        ("10", "Outside prior day range + 60m_extreme", lambda df: df["is_60m_extreme"] & df["outside_prior_range"]),
        ("11", "Within 10t of session VWAP + 60m_extreme", lambda df: df["is_60m_extreme"] & df["vwap_dist_ticks"].le(10)),
        ("12", ">50t above VWAP + 60m_extreme", lambda df: df["is_60m_extreme"] & df["direction_sign"].lt(0) & df["close_vs_vwap_ticks"].gt(50)),
        ("13", ">50t below VWAP + 60m_extreme", lambda df: df["is_60m_extreme"] & df["direction_sign"].gt(0) & df["close_vs_vwap_ticks"].lt(-50)),
        ("14", "VWAP cross + 60m_extreme", lambda df: df["is_60m_extreme"] & df["is_vwap_cross"]),
        ("15", "At IB high (±10t) + 60m_extreme", lambda df: df["is_60m_extreme"] & df["has_completed_ib"].fillna(False) & df["direction_sign"].lt(0) & df["dist_ib_high_ticks"].le(10)),
        ("16", "At IB low (±10t) + 60m_extreme", lambda df: df["is_60m_extreme"] & df["has_completed_ib"].fillna(False) & df["direction_sign"].gt(0) & df["dist_ib_low_ticks"].le(10)),
        ("17", "Failed IB high breakout + 60m_extreme", lambda df: df["is_60m_extreme"] & df["direction_sign"].lt(0) & df["failed_ib_high_breakout"]),
        ("18", "Failed IB low breakout + 60m_extreme", lambda df: df["is_60m_extreme"] & df["direction_sign"].gt(0) & df["failed_ib_low_breakout"]),
        ("19", "Within 15t of BOTH round number and prior day level + 60m_extreme", lambda df: df["is_60m_extreme"] & df["any_round_dist_ticks"].le(15) & df["nearest_prior_level_ticks"].le(15)),
        ("20", "Prior day level + 60m_extreme + 15m_trend + NOT lunch", lambda df: df["is_60m_extreme"] & df["nearest_prior_level_ticks"].le(15) & df["is_15m_trend_aligned"] & df["is_not_lunch"]),
    ]


def run_filters(df: pd.DataFrame) -> list[dict]:
    results: list[dict] = []
    for code, label, predicate in build_filter_specs():
        mask = predicate(df)
        results.append(summarize_filter(code, label, df[mask].copy()))
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
    session_context = build_session_context(bars_1m)

    observations = attach_context(observations, context)
    observations = observations.merge(
        session_context,
        left_on="bar_ts",
        right_on="ts_event",
        how="left",
        validate="many_to_one",
    ).drop(columns=["ts_event"])
    observations = add_context_flags(observations)
    observations = add_time_flags(observations)
    observations = add_price_level_flags(observations)

    baseline_all = summarize_filter("00", "All non-zero-delta signal bars", observations)
    baseline_60m = summarize_filter(
        "00A",
        "All non-zero-delta bars at 60m extreme",
        observations[observations["is_60m_extreme"]].copy(),
    )
    results = run_filters(observations)

    lines = [
        "DEEP6 round8 price-level confluence analysis",
        "============================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index.",
        "Trade direction for P&L: sign(bar_delta). Zero-delta bars are skipped.",
        "60m_extreme = bullish bar_low in bottom 20% of 60m range / bearish bar_high in top 20%.",
        "15m_trend = signal direction matches 15m open-close sign.",
        "Signal price anchor for fixed levels = bullish bar_low / bearish bar_high.",
        "Session VWAP distance uses bar_close vs cumulative same-session close*volume / volume VWAP.",
        "Prior day OHLC is built from prior RTH session aggregates. IB = first hour (09:30-10:29 ET) high/low.",
        "Distance thresholds use true NQ ticks at 0.25 points (10t=2.50 pts, 15t=3.75 pts, 50t=12.50 pts).",
        "Time filters use America/New_York. lunch = 12:00-14:00 ET, so NOT lunch excludes that window.",
        "Status flags: VALIDATED = N>=30 and Wilson lower bound >50%; PROMISING = N>=15 and Wilson lower bound >45%; LOW_N = N<15.",
        "Sorted by 5-bar average return descending.",
        "",
        f"Raw event rows loaded:             {len(events):,}",
        f"Grouped observations:              {len(observations):,}",
        f"15m bars built:                    {len(context[15]):,}",
        f"60m bars built:                    {len(context[60]):,}",
        f"RTH bars with session context:     {len(session_context):,}",
        f"Observations with prior-day OHLC:  {int(observations['prior_day_high'].notna().sum()):,}",
        f"Observations with completed IB:    {int(observations['has_completed_ib'].fillna(False).sum()):,}",
        f"60m extreme observations:          {int(observations['is_60m_extreme'].sum()):,}",
        f"15m trend aligned observations:    {int(observations['is_15m_trend_aligned'].sum()):,}",
        "",
        f"Baseline ({FORWARD_WINDOW}-bar window)",
        "-----------------------",
        f"All bars: N={baseline_all['n']:,} | WR={fmt_pct(baseline_all['win_rate'])} | PF={fmt_float(baseline_all['profit_factor'])} | Avg={fmt_float(baseline_all['avg_return_5b_ticks'])}t | CI={fmt_ci(baseline_all['ci_low'], baseline_all['ci_high'])} | Flag={baseline_all['flag'] or '-'}",
        f"60m extreme: N={baseline_60m['n']:,} | WR={fmt_pct(baseline_60m['win_rate'])} | PF={fmt_float(baseline_60m['profit_factor'])} | Avg={fmt_float(baseline_60m['avg_return_5b_ticks'])}t | CI={fmt_ci(baseline_60m['ci_low'], baseline_60m['ci_high'])} | Flag={baseline_60m['flag'] or '-'}",
        "",
        "20 requested price-level filters ranked by 5-bar average return",
        "---------------------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
