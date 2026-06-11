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
OUT_PATH = OUT_DIR / "round18_weekly_relative_strength_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOW = 5
TICK_SIZE = 0.25
RTH_START_MINUTE = 9 * 60 + 30
FIRST_HOUR_MINUTES = 60
ROLLING_LOOKBACK = 20

FilterSpec = tuple[str, str, Callable[[pd.DataFrame], pd.Series], str]


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


def fmt_ticks(value: float) -> str:
    if pd.isna(value):
        return "nan"
    if np.isinf(value):
        return "inf"
    return f"{value:+,.2f}"


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


def render_summary_line(row: dict[str, object]) -> str:
    suffix = f" [{row['flag']}]" if row["flag"] else ""
    return (
        f"N={row['n']:,} | WR={fmt_pct(row['win_rate'])} | PF={fmt_float(row['profit_factor'])} | "
        f"Avg={fmt_ticks(row['avg_return_5b_ticks'])} | CI={fmt_ci(row['ci_low'], row['ci_high'])}{suffix}"
    )


def anchor_pos_in_range(df: pd.DataFrame, trade_sign: pd.Series, tf: int) -> pd.Series:
    sign = pd.to_numeric(trade_sign, errors="coerce").fillna(0).astype(int)
    rng = df[f"range_{tf}m"].replace(0, np.nan)
    anchor = np.where(sign > 0, df["bar_low"], np.where(sign < 0, df["bar_high"], np.nan))
    return pd.Series((anchor - df[f"low_{tf}m"]) / rng, index=df.index)


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
    df["direction_sign"] = np.sign(df["bar_delta"].fillna(0.0)).astype(int)
    return df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)


def build_unique_bars(events: pd.DataFrame) -> pd.DataFrame:
    bars = (
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
        .sort_values(["session_date", "bar_ts", "global_index"], kind="stable")
        .reset_index(drop=True)
    )
    bars["direction_sign"] = np.sign(bars["bar_delta"].fillna(0.0)).astype(int)
    bars["move_5b_ticks"] = (bars["fwd_close_5b"] - bars["bar_close"]) / TICK_SIZE
    return bars


def build_observations(events: pd.DataFrame) -> pd.DataFrame:
    observations = (
        events.loc[events["direction_sign"].ne(0)]
        .groupby(["global_index", "direction_sign"], as_index=False, sort=False)
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
        .sort_values(["session_date", "bar_ts", "global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    observations["direction"] = np.where(observations["direction_sign"] > 0, "BULLISH", "BEARISH")
    observations["move_5b_ticks"] = (observations["fwd_close_5b"] - observations["bar_close"]) / TICK_SIZE
    return observations


def build_session_summary(bars: pd.DataFrame) -> pd.DataFrame:
    working = bars.sort_values(["session_date", "bar_ts", "global_index"], kind="stable").copy()
    working["bar_pv"] = working["bar_close"] * working["bar_volume"]

    summary = (
        working.groupby("session_date", as_index=False, sort=False)
        .agg(
            session_start_ts=("bar_ts", "first"),
            session_open=("bar_open", "first"),
            session_high=("bar_high", "max"),
            session_low=("bar_low", "min"),
            session_close=("bar_close", "last"),
            session_delta=("bar_delta", "sum"),
            session_volume=("bar_volume", "sum"),
            session_pv=("bar_pv", "sum"),
            session_bar_count=("global_index", "count"),
        )
        .sort_values("session_start_ts", kind="stable")
        .reset_index(drop=True)
    )

    summary["session_range"] = summary["session_high"] - summary["session_low"]
    summary["session_vwap"] = np.where(
        summary["session_volume"] > 0,
        summary["session_pv"] / summary["session_volume"],
        np.nan,
    )
    summary["session_delta_sign"] = np.sign(summary["session_delta"].fillna(0.0)).astype(int)

    session_date_dt = pd.to_datetime(summary["session_date"], errors="coerce")
    summary["session_date_dt"] = session_date_dt
    iso = session_date_dt.dt.isocalendar()
    summary["iso_year"] = iso.year.astype("Int64")
    summary["iso_week"] = iso.week.astype("Int64")
    summary["day_of_week"] = session_date_dt.dt.dayofweek.astype("Int64")

    shift_cols = [
        "session_open",
        "session_high",
        "session_low",
        "session_close",
        "session_range",
        "session_delta",
        "session_volume",
        "session_vwap",
        "session_delta_sign",
        "session_bar_count",
    ]
    for col in shift_cols:
        summary[f"prior_{col}"] = summary[col].shift(1)

    summary["prior_2_session_range"] = summary["session_range"].shift(2)
    summary["prior_3_session_range"] = summary["session_range"].shift(3)
    summary["prior_3_session_high_max"] = summary["session_high"].shift(1).rolling(3, min_periods=3).max()
    summary["prior_3_session_low_min"] = summary["session_low"].shift(1).rolling(3, min_periods=3).min()

    summary["session_is_inside_day"] = (
        summary["prior_session_high"].notna()
        & summary["session_high"].lt(summary["prior_session_high"])
        & summary["session_low"].gt(summary["prior_session_low"])
    )
    summary["prior_session_is_inside_day"] = summary["session_is_inside_day"].shift(1)
    return summary


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

    for col in ["bar_open", "bar_high", "bar_low", "bar_close", "bar_volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def attach_session_weekly_context(observations: pd.DataFrame, bars: pd.DataFrame, session_summary: pd.DataFrame) -> pd.DataFrame:
    running = bars.sort_values(["session_date", "bar_ts", "global_index"], kind="stable").copy()
    session_date_dt = pd.to_datetime(running["session_date"], errors="coerce")
    running["session_date_dt"] = session_date_dt
    iso = session_date_dt.dt.isocalendar()
    running["iso_year"] = iso.year.astype("Int64")
    running["iso_week"] = iso.week.astype("Int64")

    by_session = running.groupby("session_date", sort=False)
    running["developing_session_high"] = by_session["bar_high"].cummax()
    running["developing_session_low"] = by_session["bar_low"].cummin()
    running["developing_session_range"] = running["developing_session_high"] - running["developing_session_low"]
    running["developing_session_delta"] = by_session["bar_delta"].cumsum()
    running["developing_session_delta_sign"] = np.sign(running["developing_session_delta"].fillna(0.0)).astype(int)

    by_week = running.groupby(["iso_year", "iso_week"], sort=False)
    running["developing_weekly_high"] = by_week["bar_high"].cummax()
    running["developing_weekly_low"] = by_week["bar_low"].cummin()
    running["developing_weekly_range"] = running["developing_weekly_high"] - running["developing_weekly_low"]
    running["weekly_pos_in_range"] = np.where(
        running["developing_weekly_range"] > 0,
        (running["bar_close"] - running["developing_weekly_low"]) / running["developing_weekly_range"],
        np.nan,
    )
    running["prior_weekly_high"] = by_week["bar_high"].transform(lambda s: s.cummax().shift(1))
    running["prior_weekly_low"] = by_week["bar_low"].transform(lambda s: s.cummin().shift(1))
    running["broke_weekly_high"] = running["prior_weekly_high"].notna() & running["bar_high"].gt(running["prior_weekly_high"])
    running["broke_weekly_low"] = running["prior_weekly_low"].notna() & running["bar_low"].lt(running["prior_weekly_low"])

    session_cols = [
        "session_date",
        "session_open",
        "session_high",
        "session_low",
        "session_close",
        "session_range",
        "session_delta",
        "session_volume",
        "session_vwap",
        "prior_session_open",
        "prior_session_high",
        "prior_session_low",
        "prior_session_close",
        "prior_session_range",
        "prior_session_delta",
        "prior_session_volume",
        "prior_session_vwap",
        "prior_session_delta_sign",
        "prior_2_session_range",
        "prior_3_session_range",
        "prior_3_session_high_max",
        "prior_3_session_low_min",
        "day_of_week",
        "iso_year",
        "iso_week",
        "prior_session_is_inside_day",
    ]
    running_cols = [
        "global_index",
        "developing_session_high",
        "developing_session_low",
        "developing_session_range",
        "developing_session_delta",
        "developing_session_delta_sign",
        "developing_weekly_high",
        "developing_weekly_low",
        "developing_weekly_range",
        "weekly_pos_in_range",
        "prior_weekly_high",
        "prior_weekly_low",
        "broke_weekly_high",
        "broke_weekly_low",
    ]

    df = observations.merge(session_summary[session_cols], on="session_date", how="left", validate="many_to_one")
    df = df.merge(running[running_cols], on="global_index", how="left", validate="many_to_one")

    df["is_bottom_20_weekly"] = df["weekly_pos_in_range"].le(0.20)
    df["is_top_20_weekly"] = df["weekly_pos_in_range"].ge(0.80)
    df["is_mid_40_60_weekly"] = df["weekly_pos_in_range"].between(0.40, 0.60, inclusive="both")
    df["is_weekly_extreme_by_direction"] = (
        ((df["direction_sign"] > 0) & df["is_bottom_20_weekly"])
        | ((df["direction_sign"] < 0) & df["is_top_20_weekly"])
    )

    df["is_stronger_day"] = df["prior_session_range"].notna() & df["developing_session_range"].gt(df["prior_session_range"])
    df["is_weaker_day"] = df["prior_session_range"].notna() & df["developing_session_range"].lt(df["prior_session_range"])
    df["makes_new_multiday_high"] = df["prior_3_session_high_max"].notna() & df["developing_session_high"].gt(
        df["prior_3_session_high_max"]
    )
    df["makes_new_multiday_low"] = df["prior_3_session_low_min"].notna() & df["developing_session_low"].lt(
        df["prior_3_session_low_min"]
    )

    prior_delta_sign = pd.to_numeric(df["prior_session_delta_sign"], errors="coerce").fillna(0).astype(int)
    df["prior_session_delta_sign"] = prior_delta_sign
    df["is_delta_continuation"] = (
        prior_delta_sign.ne(0)
        & df["developing_session_delta_sign"].ne(0)
        & df["developing_session_delta_sign"].eq(prior_delta_sign)
    )

    df["is_inside_day"] = (
        df["prior_session_high"].notna()
        & df["developing_session_high"].lt(df["prior_session_high"])
        & df["developing_session_low"].gt(df["prior_session_low"])
    )
    df["is_consecutive_inside_day"] = df["is_inside_day"] & df["prior_session_is_inside_day"].fillna(False)

    df["has_two_consecutive_shrinking_ranges"] = (
        df["prior_2_session_range"].notna()
        & df["developing_session_range"].lt(df["prior_session_range"])
        & df["prior_session_range"].lt(df["prior_2_session_range"])
    )
    df["has_three_consecutive_shrinking_ranges"] = (
        df["prior_3_session_range"].notna()
        & df["developing_session_range"].lt(df["prior_session_range"])
        & df["prior_session_range"].lt(df["prior_2_session_range"])
        & df["prior_2_session_range"].lt(df["prior_3_session_range"])
    )
    df["prior_two_sessions_shrinking"] = (
        df["prior_3_session_range"].notna()
        & df["prior_session_range"].lt(df["prior_2_session_range"])
        & df["prior_2_session_range"].lt(df["prior_3_session_range"])
    )
    df["is_range_expansion_after_shrink"] = df["prior_two_sessions_shrinking"] & df["developing_session_range"].gt(
        df["prior_session_range"]
    )

    df["is_monday"] = df["day_of_week"].eq(0)
    df["is_wednesday"] = df["day_of_week"].eq(2)
    df["is_friday"] = df["day_of_week"].eq(4)

    bool_cols = [
        "is_bottom_20_weekly",
        "is_top_20_weekly",
        "is_mid_40_60_weekly",
        "is_weekly_extreme_by_direction",
        "is_stronger_day",
        "is_weaker_day",
        "makes_new_multiday_high",
        "makes_new_multiday_low",
        "is_delta_continuation",
        "is_inside_day",
        "is_consecutive_inside_day",
        "has_two_consecutive_shrinking_ranges",
        "has_three_consecutive_shrinking_ranges",
        "prior_two_sessions_shrinking",
        "is_range_expansion_after_shrink",
        "is_monday",
        "is_wednesday",
        "is_friday",
        "broke_weekly_high",
        "broke_weekly_low",
    ]
    for col in bool_cols:
        df[col] = df[col].fillna(False).astype(bool)

    return df


def add_base_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["is_15m_trend_aligned"] = out["direction_sign"].eq(out["trend_sign_15m"])
    out["pos_60m"] = anchor_pos_in_range(out, out["direction_sign"], 60)
    out["is_60m_extreme"] = (
        ((out["direction_sign"] > 0) & out["pos_60m"].le(0.20))
        | ((out["direction_sign"] < 0) & out["pos_60m"].ge(0.80))
    )
    out["has_core_60m_15m_gate"] = out["is_60m_extreme"] & out["is_15m_trend_aligned"]

    minute_of_day = out["bar_ts"].dt.hour * 60 + out["bar_ts"].dt.minute
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

    bool_cols = [
        "is_15m_trend_aligned",
        "is_60m_extreme",
        "has_core_60m_15m_gate",
        "is_first_hour",
        "is_volume_spike_3x",
        "is_killer_1",
        "is_killer_2",
        "passes_not_all_killers",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def compute_cvd_features(observations: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    by_session = out.groupby("session_date", sort=False)

    out["cvd"] = by_session["bar_delta"].cumsum()
    out["prior_session_price_high"] = by_session["bar_high"].transform(lambda s: s.cummax().shift(1))
    out["prior_session_price_low"] = by_session["bar_low"].transform(lambda s: s.cummin().shift(1))
    out["prior_cvd_high"] = by_session["cvd"].transform(lambda s: s.cummax().shift(1))
    out["prior_cvd_low"] = by_session["cvd"].transform(lambda s: s.cummin().shift(1))

    out["is_price_new_session_high"] = out["prior_session_price_high"].notna() & out["bar_high"].gt(
        out["prior_session_price_high"]
    )
    out["is_price_new_session_low"] = out["prior_session_price_low"].notna() & out["bar_low"].lt(
        out["prior_session_price_low"]
    )
    out["is_bearish_cvd_divergence"] = (
        out["is_price_new_session_high"] & out["prior_cvd_high"].notna() & out["cvd"].lt(out["prior_cvd_high"])
    )
    out["is_bullish_cvd_divergence"] = (
        out["is_price_new_session_low"] & out["prior_cvd_low"].notna() & out["cvd"].gt(out["prior_cvd_low"])
    )
    out["divergence_sign"] = np.select(
        [out["is_bullish_cvd_divergence"], out["is_bearish_cvd_divergence"]],
        [1, -1],
        default=0,
    ).astype(int)
    out["is_cvd_divergence"] = out["divergence_sign"].ne(0)

    out["pos_60m_divergence"] = anchor_pos_in_range(out, out["divergence_sign"], 60)
    out["is_60m_extreme_divergence"] = (
        ((out["divergence_sign"] > 0) & out["pos_60m_divergence"].le(0.20))
        | ((out["divergence_sign"] < 0) & out["pos_60m_divergence"].ge(0.80))
    )
    out["is_15m_trend_aligned_divergence"] = out["divergence_sign"].ne(0) & out["divergence_sign"].eq(
        out["trend_sign_15m"]
    )
    out["has_core_divergence_gate"] = out["is_60m_extreme_divergence"] & out["is_15m_trend_aligned_divergence"]
    out["is_killer_1_divergence"] = out["pos_60m_divergence"].between(0.40, 0.60, inclusive="both")
    out["passes_not_all_killers_divergence"] = (~out["is_killer_1_divergence"]) & (~out["is_killer_2"])

    bool_cols = [
        "is_price_new_session_high",
        "is_price_new_session_low",
        "is_bearish_cvd_divergence",
        "is_bullish_cvd_divergence",
        "is_cvd_divergence",
        "is_60m_extreme_divergence",
        "is_15m_trend_aligned_divergence",
        "has_core_divergence_gate",
        "is_killer_1_divergence",
        "passes_not_all_killers_divergence",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def summarize_filter(code: str, label: str, df: pd.DataFrame, trade_sign_col: str) -> dict[str, object]:
    trade_sign = pd.to_numeric(df[trade_sign_col], errors="coerce").fillna(0).astype(int)
    returns = (trade_sign * df["move_5b_ticks"]).where(trade_sign.ne(0)).dropna()
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
        (
            "01",
            "Bottom 20% weekly range + bullish signal + 60m + 15m",
            lambda df: df["direction_sign"].gt(0) & df["is_bottom_20_weekly"] & df["has_core_60m_15m_gate"],
            "direction_sign",
        ),
        (
            "02",
            "Top 20% weekly range + bearish signal + 60m + 15m",
            lambda df: df["direction_sign"].lt(0) & df["is_top_20_weekly"] & df["has_core_60m_15m_gate"],
            "direction_sign",
        ),
        (
            "03",
            "Middle 40-60% weekly range + 60m + 15m",
            lambda df: df["is_mid_40_60_weekly"] & df["has_core_60m_15m_gate"],
            "direction_sign",
        ),
        (
            "04",
            "New weekly high this bar + 60m + 15m",
            lambda df: df["broke_weekly_high"] & df["has_core_60m_15m_gate"],
            "direction_sign",
        ),
        (
            "05",
            "New weekly low this bar + 60m + 15m",
            lambda df: df["broke_weekly_low"] & df["has_core_60m_15m_gate"],
            "direction_sign",
        ),
        (
            "06",
            "Developing today range > prior session range + 60m + 15m",
            lambda df: df["is_stronger_day"] & df["has_core_60m_15m_gate"],
            "direction_sign",
        ),
        (
            "07",
            "Developing today range < prior session range + 60m + 15m",
            lambda df: df["is_weaker_day"] & df["has_core_60m_15m_gate"],
            "direction_sign",
        ),
        (
            "08",
            "Developing today makes new 3-session high + 60m + 15m",
            lambda df: df["makes_new_multiday_high"] & df["has_core_60m_15m_gate"],
            "direction_sign",
        ),
        (
            "09",
            "Developing today makes new 3-session low + 60m + 15m",
            lambda df: df["makes_new_multiday_low"] & df["has_core_60m_15m_gate"],
            "direction_sign",
        ),
        (
            "10",
            "Developing today delta sign matches prior session delta + 60m + 15m",
            lambda df: df["is_delta_continuation"] & df["has_core_60m_15m_gate"],
            "direction_sign",
        ),
        (
            "11",
            "Monday + bottom 20% weekly range + bullish signal + 60m + 15m",
            lambda df: df["is_monday"]
            & df["direction_sign"].gt(0)
            & df["is_bottom_20_weekly"]
            & df["has_core_60m_15m_gate"],
            "direction_sign",
        ),
        (
            "12",
            "Friday + top 20% weekly range + bearish signal + 60m + 15m",
            lambda df: df["is_friday"]
            & df["direction_sign"].lt(0)
            & df["is_top_20_weekly"]
            & df["has_core_60m_15m_gate"],
            "direction_sign",
        ),
        (
            "13",
            "Wednesday + weekly extreme by direction + 60m + 15m",
            lambda df: df["is_wednesday"] & df["is_weekly_extreme_by_direction"] & df["has_core_60m_15m_gate"],
            "direction_sign",
        ),
        (
            "14",
            "Consecutive inside days + 60m + 15m",
            lambda df: df["is_consecutive_inside_day"] & df["has_core_60m_15m_gate"],
            "direction_sign",
        ),
        (
            "15",
            "2 consecutive shrinking session ranges + 60m + 15m",
            lambda df: df["has_two_consecutive_shrinking_ranges"] & df["has_core_60m_15m_gate"],
            "direction_sign",
        ),
        (
            "16",
            "3 consecutive shrinking session ranges + 60m + 15m",
            lambda df: df["has_three_consecutive_shrinking_ranges"] & df["has_core_60m_15m_gate"],
            "direction_sign",
        ),
        (
            "17",
            "Range expansion after 2 prior shrinking sessions + 60m + 15m",
            lambda df: df["is_range_expansion_after_shrink"] & df["has_core_60m_15m_gate"],
            "direction_sign",
        ),
        (
            "18",
            "Inside day + 60m + 15m",
            lambda df: df["is_inside_day"] & df["has_core_60m_15m_gate"],
            "direction_sign",
        ),
        (
            "19",
            "Bottom 20% weekly + stronger day + 60m + 15m + NOT killers + first_hour",
            lambda df: df["direction_sign"].gt(0)
            & df["is_bottom_20_weekly"]
            & df["is_stronger_day"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
            "direction_sign",
        ),
        (
            "20",
            "New weekly high + bearish CVD divergence + 60m + 15m + NOT killers",
            lambda df: df["broke_weekly_high"]
            & df["is_bearish_cvd_divergence"]
            & df["has_core_divergence_gate"]
            & df["passes_not_all_killers_divergence"],
            "divergence_sign",
        ),
    ]


def run_filters(df: pd.DataFrame) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for code, label, predicate, trade_sign_col in build_filter_specs():
        mask = predicate(df)
        results.append(summarize_filter(code, label, df[mask].copy(), trade_sign_col))

    results.sort(
        key=lambda row: (
            float("-inf") if pd.isna(row["avg_return_5b_ticks"]) else float(row["avg_return_5b_ticks"]),
            float("-inf") if pd.isna(row["win_rate"]) else float(row["win_rate"]),
            int(row["n"]),
        ),
        reverse=True,
    )
    return results


def render_table(rows: list[dict[str, object]]) -> list[str]:
    headers = ["Filter", "N", "WR 5b", "PF", "Avg Ticks", "Wilson 95% CI"]
    data_rows: list[list[str]] = []
    for row in rows:
        filter_name = f"{row['code']}. {row['label']}"
        if row["flag"]:
            filter_name = f"{filter_name} [{row['flag']}]"
        data_rows.append(
            [
                filter_name,
                f"{row['n']:,}",
                fmt_pct(row["win_rate"]),
                fmt_float(row["profit_factor"]),
                fmt_ticks(row["avg_return_5b_ticks"]),
                fmt_ci(row["ci_low"], row["ci_high"]),
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
    unique_bars = build_unique_bars(events)
    observations = build_observations(events)
    session_summary = build_session_summary(unique_bars)
    timeframe_context = build_timeframe_context(bars_1m)

    observations = attach_timeframe_context(observations, timeframe_context)
    observations = attach_session_weekly_context(observations, unique_bars, session_summary)
    observations = add_base_flags(observations)
    observations = compute_cvd_features(observations)

    baseline_all = summarize_filter("00", "All non-zero-delta grouped signal bars", observations, "direction_sign")
    baseline_core = summarize_filter(
        "00A",
        "Core 60m + 15m gate",
        observations[observations["has_core_60m_15m_gate"]].copy(),
        "direction_sign",
    )
    baseline_weekly_extreme = summarize_filter(
        "00B",
        "Weekly extreme by direction + 60m + 15m",
        observations[observations["is_weekly_extreme_by_direction"] & observations["has_core_60m_15m_gate"]].copy(),
        "direction_sign",
    )
    baseline_divergence = summarize_filter(
        "00C",
        "All CVD divergence bars",
        observations[observations["is_cvd_divergence"]].copy(),
        "divergence_sign",
    )
    baseline_divergence_core = summarize_filter(
        "00D",
        "CVD divergence + 60m + 15m",
        observations[observations["has_core_divergence_gate"]].copy(),
        "divergence_sign",
    )
    results = run_filters(observations)

    lines = [
        "DEEP6 round 18 weekly relative strength analysis",
        "===========================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: grouped signal bar by (global_index, direction_sign from bar_delta).",
        "Forward P&L window: 5 bars, signed by bar_delta direction for 19 filters and by divergence_sign for weekly-breakout CVD divergence.",
        "Session summaries come from unique signal bars deduplicated by global_index before daily aggregation, following the round6 pattern.",
        "Current-day comparisons use developing session high/low/range/delta through the signal bar. Prior-session comparisons use completed prior sessions.",
        "Weekly context uses cumulative Mon-Fri developing high/low within each ISO week. Weekly position = bar_close within the developing weekly range.",
        "60m + 15m core gate = direction-specific 60m extreme plus 15m trend alignment. Weekly breakout = current bar makes a new developing weekly high/low.",
        "Inside day uses developing_session_high < prior_session_high AND developing_session_low > prior_session_low.",
        "NOT killers = NOT killer_1 (trade-direction 60m position in middle 40%-60%) AND NOT killer_2 (bar_volume > 3x prior 20-bar EMA).",
        "CVD divergence matches round8: price makes a new session high/low while cumulative delta fails to confirm that new extreme.",
        "Status flags: VALIDATED = N>=30 and Wilson lower bound >50%; PROMISING = N>=15 and Wilson lower bound >45%; LOW_N = N<15.",
        "",
        f"Raw event rows loaded:                 {len(events):,}",
        f"Unique bars loaded:                    {len(unique_bars):,}",
        f"Grouped observations:                  {len(observations):,}",
        f"Sessions summarized:                   {len(session_summary):,}",
        f"15m bars built:                        {len(timeframe_context[15]):,}",
        f"60m bars built:                        {len(timeframe_context[60]):,}",
        f"Core 60m + 15m observations:           {int(observations['has_core_60m_15m_gate'].sum()):,}",
        f"Weekly bottom-20 observations:         {int(observations['is_bottom_20_weekly'].sum()):,}",
        f"Weekly top-20 observations:            {int(observations['is_top_20_weekly'].sum()):,}",
        f"Weekly breakout-high observations:     {int(observations['broke_weekly_high'].sum()):,}",
        f"Weekly breakout-low observations:      {int(observations['broke_weekly_low'].sum()):,}",
        f"Stronger-day observations:             {int(observations['is_stronger_day'].sum()):,}",
        f"Inside-day observations:               {int(observations['is_inside_day'].sum()):,}",
        f"First-hour observations:               {int(observations['is_first_hour'].sum()):,}",
        f"NOT-killers observations:              {int(observations['passes_not_all_killers'].sum()):,}",
        f"CVD divergence observations:           {int(observations['is_cvd_divergence'].sum()):,}",
        "",
        f"Baselines ({FORWARD_WINDOW}-bar window)",
        "--------------------------",
        f"All grouped bars:               {render_summary_line(baseline_all)}",
        f"Core 60m + 15m:                {render_summary_line(baseline_core)}",
        f"Weekly extreme + core:         {render_summary_line(baseline_weekly_extreme)}",
        f"All CVD divergence bars:       {render_summary_line(baseline_divergence)}",
        f"CVD divergence + 60m + 15m:    {render_summary_line(baseline_divergence_core)}",
        "",
        "All 20 weekly-relative-strength filters ranked by 5-bar average return",
        "------------------------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
