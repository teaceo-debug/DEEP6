#!/usr/bin/env python3
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data/backtests/signal_events.csv"
OHLCV_CSV = ROOT / "data/backtests/nq_1yr_1m.csv"
OUT_DIR = ROOT / "data/backtests/analysis"
OUT_PATH = OUT_DIR / "round36_walkforward_r29_r35_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
VALIDATION_MONTHS = pd.period_range("2025-01", "2026-04", freq="M")
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
ADAPTIVE_LOOKBACK = 50
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
FIRST_HOUR_MINUTES = 60
BETA_PRIOR_ALPHA = 10
BETA_PRIOR_BETA = 10

FilterPredicate = Callable[[pd.DataFrame], pd.Series]


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


def win_rate(returns: pd.Series) -> float:
    if returns.empty:
        return float("nan")
    return float((returns > 0).mean())


def wilson_ci(n: int, k: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return 0.0, 0.0, 0.0
    p_hat = k / n
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, center - margin), min(1.0, center + margin), p_hat


def beta_credible_interval(alpha: float, beta_value: float, level: float = 0.95) -> tuple[float, float]:
    tail = (1.0 - level) / 2.0
    try:
        from scipy.stats import beta as scipy_beta

        low = float(scipy_beta.ppf(tail, alpha, beta_value))
        high = float(scipy_beta.ppf(1.0 - tail, alpha, beta_value))
        return low, high
    except Exception:
        mean = alpha / (alpha + beta_value)
        var = (alpha * beta_value) / (((alpha + beta_value) ** 2) * (alpha + beta_value + 1.0))
        z = 1.959963984540054
        margin = z * math.sqrt(var)
        return max(0.0, mean - margin), min(1.0, mean + margin)


def month_period(value: str) -> pd.Period:
    return pd.Period(value, freq="M")


def month_label(period_value: pd.Period) -> str:
    return period_value.to_timestamp().strftime("%b %Y")


def month_short_label(period_value: pd.Period) -> str:
    return period_value.to_timestamp().strftime("%b-%y")


def format_is_label(is_months: list[pd.Period]) -> str:
    if len(is_months) == 1:
        return month_label(is_months[0])
    first = is_months[0].to_timestamp()
    last = is_months[-1].to_timestamp()
    if first.year == last.year:
        return f"{first.strftime('%b')}-{last.strftime('%b %Y')}"
    return f"{first.strftime('%b %Y')}-{last.strftime('%b %Y')}"


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
        "direction",
        "strength",
        "score_final",
        "score_tier",
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
        "strength",
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
    df["category"] = df["category"].astype("string").str.lower()
    df["signal_id"] = df["signal_id"].astype("string").str.upper()
    df["event_direction_sign"] = direction_to_sign(df["direction"])
    df["bar_direction_sign"] = np.sign(df["bar_delta"].fillna(0.0)).astype(int)
    return df.sort_values(["session_date", "bar_ts", "global_index", "signal_id"], kind="stable").reset_index(drop=True)


def add_session_month(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["session_month"] = pd.to_datetime(out["session_date"], errors="coerce").dt.to_period("M")
    return out


def add_trade_returns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for window in FORWARD_WINDOWS:
        out[f"trade_ret_{window}b_ticks"] = out["direction_sign"] * (
            (out[f"fwd_close_{window}b"] - out["bar_close"]) / TICK_SIZE
        )
    return out


def build_bar_frame(events: pd.DataFrame) -> pd.DataFrame:
    return (
        events.drop_duplicates(subset=["global_index"])
        .sort_values(["session_date", "bar_ts", "global_index"], kind="stable")
        .loc[
            :,
            [
                "global_index",
                "session_date",
                "bar_ts",
                "bar_index",
                "bar_open",
                "bar_high",
                "bar_low",
                "bar_close",
                "bar_delta",
                "bar_volume",
                "fwd_close_5b",
                "fwd_close_10b",
                "fwd_close_30b",
            ],
        ]
        .copy()
        .reset_index(drop=True)
    )


def build_signal_directional_observations(events: pd.DataFrame) -> pd.DataFrame:
    working = events.loc[events["event_direction_sign"].ne(0)].copy()
    working["is_absorption"] = working["category"].eq("absorption")
    working["is_trap_family"] = working["category"].eq("trap")
    working["is_exhaustion_family"] = working["category"].eq("exhaustion")

    observations = (
        working.groupby(["global_index", "event_direction_sign"], as_index=False, sort=False)
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
            other_category_count=("category", lambda s: s[s != "absorption"].nunique()),
            max_strength=("strength", "max"),
            max_score_final=("score_final", "max"),
            has_absorption=("is_absorption", "max"),
            has_trap_family=("is_trap_family", "max"),
            has_exhaustion_family=("is_exhaustion_family", "max"),
        )
        .rename(columns={"event_direction_sign": "direction_sign"})
        .sort_values(["session_date", "bar_ts", "global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    observations = add_trade_returns(observations)
    return add_session_month(observations)


def build_absorption_observations(events: pd.DataFrame) -> pd.DataFrame:
    absorption_events = events.loc[events["category"].eq("absorption") & events["event_direction_sign"].ne(0)].copy()
    observations = (
        absorption_events.groupby(["global_index", "event_direction_sign"], as_index=False, sort=False)
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
            absorption_strength=("strength", "max"),
            absorption_score_final=("score_final", "max"),
            absorption_variants=("signal_id", "nunique"),
        )
        .rename(columns={"event_direction_sign": "direction_sign"})
        .sort_values(["session_date", "bar_ts", "global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    observations = add_trade_returns(observations)
    return add_session_month(observations)


def build_bar_observations(events: pd.DataFrame) -> pd.DataFrame:
    working = events.loc[events["bar_direction_sign"].ne(0)].copy()
    working["is_absorption"] = working["category"].eq("absorption")
    working["is_trap_family"] = working["category"].eq("trap")
    working["is_exhaustion_family"] = working["category"].eq("exhaustion")

    observations = (
        working.groupby(["global_index", "bar_direction_sign"], as_index=False, sort=False)
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
            max_strength=("strength", "max"),
            max_score_final=("score_final", "max"),
            has_absorption=("is_absorption", "max"),
            has_trap_family=("is_trap_family", "max"),
            has_exhaustion_family=("is_exhaustion_family", "max"),
        )
        .rename(columns={"bar_direction_sign": "direction_sign"})
        .sort_values(["session_date", "bar_ts", "global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    observations = add_trade_returns(observations)
    return add_session_month(observations)


def compute_bar_features(bars: pd.DataFrame) -> pd.DataFrame:
    out = bars.sort_values(["session_date", "bar_ts", "global_index"], kind="stable").copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["abs_delta"] = out["bar_delta"].abs()
    out["delta_ratio"] = np.where(out["bar_volume"] > 0, out["abs_delta"] / out["bar_volume"], np.nan)
    out["prior_bar_range"] = by_session["bar_range"].shift(1)
    out["bar_range_2"] = by_session["bar_range"].shift(2)

    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    out["range_q25"] = by_session["bar_range"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.25)
    )
    out["range_q10"] = by_session["bar_range"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.10)
    )
    out["volume_q75"] = by_session["bar_volume"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.75)
    )
    out["delta_ratio_q10_50"] = by_session["delta_ratio"].transform(
        lambda s: s.shift(1).rolling(ADAPTIVE_LOOKBACK, min_periods=ADAPTIVE_LOOKBACK).quantile(0.10)
    )
    out["volume_q90_50"] = by_session["bar_volume"].transform(
        lambda s: s.shift(1).rolling(ADAPTIVE_LOOKBACK, min_periods=ADAPTIVE_LOOKBACK).quantile(0.90)
    )

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
        lambda s: s.rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).mean()
    )
    out["session_cumulative_delta"] = by_session["bar_delta"].cumsum()

    out["is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.10 * out["bar_range"])
    out["is_narrow_range"] = out["range_q25"].notna() & out["bar_range"].lt(out["range_q25"])
    out["is_very_narrow_range"] = out["range_q10"].notna() & out["bar_range"].lt(out["range_q10"])
    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])
    out["is_adaptive_low_delta_vol"] = out["delta_ratio_q10_50"].notna() & out["delta_ratio"].lt(out["delta_ratio_q10_50"])
    out["is_tight_vs_atr20"] = out["atr20"].gt(0) & out["bar_range"].lt(0.5 * out["atr20"])
    out["is_triple_adaptive"] = (
        out["volume_q90_50"].notna()
        & out["bar_volume"].gt(out["volume_q90_50"])
        & out["is_tight_vs_atr20"]
        & out["is_adaptive_low_delta_vol"]
    )

    bool_cols = [
        "is_doji",
        "is_narrow_range",
        "is_very_narrow_range",
        "is_volume_spike_3x",
        "is_adaptive_low_delta_vol",
        "is_tight_vs_atr20",
        "is_triple_adaptive",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out.reset_index(drop=True)


def build_session_summary(bars: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
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

    shift_cols = [
        "session_open",
        "session_high",
        "session_low",
        "session_close",
        "session_range",
        "session_delta",
        "session_volume",
        "session_vwap",
        "session_bar_count",
    ]
    for col in shift_cols:
        summary[f"prior_{col}"] = summary[col].shift(1)

    thresholds = {
        "range_q75": float(summary["session_range"].dropna().quantile(0.75)),
    }
    return summary, thresholds


def filter_rth_bars(bars_1m: pd.DataFrame) -> pd.DataFrame:
    bars = bars_1m.copy()
    minute_of_day = bars["ts_event"].dt.hour * 60 + bars["ts_event"].dt.minute
    bars = bars.loc[(minute_of_day >= RTH_START_MINUTE) & (minute_of_day < RTH_END_MINUTE)].copy()
    bars["session_date"] = bars["ts_event"].dt.strftime("%Y-%m-%d")
    bars["minutes_since_930"] = minute_of_day.loc[bars.index] - RTH_START_MINUTE
    bars["bar_index"] = bars.groupby("session_date", sort=False).cumcount().astype("int32")
    return bars.reset_index(drop=True)


def build_rth_context(rth_bars: pd.DataFrame) -> pd.DataFrame:
    bars = rth_bars.sort_values(["session_date", "ts_event"], kind="stable").copy()
    bars["is_first_hour"] = bars["minutes_since_930"].ge(0) & bars["minutes_since_930"].lt(FIRST_HOUR_MINUTES)

    ib_summary = (
        bars.loc[bars["is_first_hour"]]
        .groupby("session_date", as_index=False, sort=False)
        .agg(
            ib_high=("high", "max"),
            ib_low=("low", "min"),
        )
    )

    bars = bars.merge(ib_summary, on="session_date", how="left", validate="many_to_one")
    bars["is_after_ib"] = bars["minutes_since_930"].ge(FIRST_HOUR_MINUTES)
    bars["is_within_ib"] = (
        bars["is_after_ib"] & bars["ib_high"].notna() & bars["ib_low"].notna() & bars["high"].le(bars["ib_high"]) & bars["low"].ge(bars["ib_low"])
    )
    bars["is_ib_extension"] = (
        bars["is_after_ib"]
        & bars["ib_high"].notna()
        & bars["ib_low"].notna()
        & ((bars["high"] > bars["ib_high"]) | (bars["low"] < bars["ib_low"]))
    )

    bool_cols = ["is_first_hour", "is_after_ib", "is_within_ib", "is_ib_extension"]
    for col in bool_cols:
        bars[col] = bars[col].fillna(False).astype(bool)

    return bars[
        [
            "ts_event",
            "session_date",
            "bar_index",
            "minutes_since_930",
            "is_first_hour",
            "ib_high",
            "ib_low",
            "is_after_ib",
            "is_within_ib",
            "is_ib_extension",
        ]
    ].copy()


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


def count_events_in_bar_window(df: pd.DataFrame, window: int) -> pd.Series:
    counts = pd.Series(index=df.index, dtype="int64")
    for _, group in df.groupby(["session_date", "direction_sign"], sort=False):
        bar_numbers = group["bar_index"].to_numpy(dtype=int)
        left = np.searchsorted(bar_numbers, bar_numbers - window + 1, side="left")
        values = np.arange(len(group)) - left + 1
        counts.loc[group.index] = values
    return counts.fillna(0).astype("int32")


def nearby_reference_flag(
    current: pd.DataFrame,
    reference: pd.DataFrame,
    max_gap: int,
    direction: str,
) -> pd.Series:
    flags = pd.Series(False, index=current.index, dtype=bool)
    if current.empty or reference.empty:
        return flags

    reference_map = {
        key: np.unique(group["bar_index"].to_numpy(dtype=int))
        for key, group in reference.groupby(["session_date", "direction_sign"], sort=False)
    }

    for key, group in current.groupby(["session_date", "direction_sign"], sort=False):
        ref_bars = reference_map.get(key)
        if ref_bars is None or len(ref_bars) == 0:
            continue

        cur_bars = group["bar_index"].to_numpy(dtype=int)
        if direction == "future":
            positions = np.searchsorted(ref_bars, cur_bars + 1, side="left")
            valid = positions < len(ref_bars)
            group_flags = np.zeros(len(group), dtype=bool)
            if valid.any():
                gap = ref_bars[positions[valid]] - cur_bars[valid]
                group_flags[valid] = (gap >= 1) & (gap <= max_gap)
        else:
            positions = np.searchsorted(ref_bars, cur_bars, side="left") - 1
            valid = positions >= 0
            group_flags = np.zeros(len(group), dtype=bool)
            if valid.any():
                gap = cur_bars[valid] - ref_bars[positions[valid]]
                group_flags[valid] = (gap >= 1) & (gap <= max_gap)

        flags.loc[group.index] = group_flags

    return flags


def add_absorption_sequence_flags(absorption: pd.DataFrame, directional: pd.DataFrame) -> pd.DataFrame:
    out = absorption.sort_values(["session_date", "direction_sign", "bar_index", "global_index"], kind="stable").copy()
    out["abs_count_last_3"] = count_events_in_bar_window(out, 3)
    out["abs_count_last_5"] = count_events_in_bar_window(out, 5)
    out["abs_count_last_10"] = count_events_in_bar_window(out, 10)

    prev_bar_index = out.groupby(["session_date", "direction_sign"], sort=False)["bar_index"].shift(1)
    out["prev_abs_gap_bars"] = out["bar_index"] - prev_bar_index
    out["has_prior_abs_gap_3plus"] = out["prev_abs_gap_bars"].ge(4)

    exhaustion_reference = directional.loc[directional["has_exhaustion_family"]].copy()
    out["has_future_exhaustion_within_3"] = nearby_reference_flag(
        out,
        exhaustion_reference,
        max_gap=3,
        direction="future",
    )

    bool_cols = ["has_prior_abs_gap_3plus", "has_future_exhaustion_within_3"]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out.reset_index(drop=True)


def attach_common_context(
    observations: pd.DataFrame,
    bar_features: pd.DataFrame,
    session_summary: pd.DataFrame,
    session_thresholds: dict[str, float],
    rth_context: pd.DataFrame,
    timeframe_context: dict[int, pd.DataFrame],
) -> pd.DataFrame:
    feature_cols = [
        "global_index",
        "bar_range",
        "body",
        "abs_delta",
        "delta_ratio",
        "prior_bar_range",
        "bar_range_2",
        "range_q25",
        "range_q10",
        "volume_q75",
        "delta_ratio_q10_50",
        "volume_q90_50",
        "rolling_20_ema_vol",
        "atr20",
        "session_cumulative_delta",
        "is_doji",
        "is_narrow_range",
        "is_very_narrow_range",
        "is_volume_spike_3x",
        "is_adaptive_low_delta_vol",
        "is_tight_vs_atr20",
        "is_triple_adaptive",
    ]
    session_cols = ["session_date", "prior_session_range"]

    out = observations.merge(bar_features[feature_cols], on="global_index", how="left", validate="many_to_one")
    out = out.merge(session_summary[session_cols], on="session_date", how="left", validate="many_to_one")
    out = out.merge(
        rth_context.rename(columns={"session_date": "rth_session_date", "bar_index": "rth_bar_index"}),
        left_on="bar_ts",
        right_on="ts_event",
        how="left",
        validate="many_to_one",
    ).drop(columns=["ts_event"])
    out = attach_timeframe_context(out, timeframe_context)

    rng_60m = out["range_60m"].replace(0, np.nan)
    anchor = np.where(out["direction_sign"] > 0, out["bar_low"], np.where(out["direction_sign"] < 0, out["bar_high"], np.nan))
    out["pos_in_60m"] = (anchor - out["low_60m"]) / rng_60m
    out["is_60m_extreme"] = (
        ((out["direction_sign"] > 0) & out["pos_in_60m"].le(0.20))
        | ((out["direction_sign"] < 0) & out["pos_in_60m"].ge(0.80))
    )
    out["is_15m_trend_aligned"] = out["direction_sign"].eq(out["trend_sign_15m"])
    out["has_core_60m_15m_gate"] = out["is_60m_extreme"] & out["is_15m_trend_aligned"]
    out["prior_session_is_wide_range"] = out["prior_session_range"].ge(session_thresholds["range_q75"])

    session_delta_sign = np.sign(out["session_cumulative_delta"].fillna(0.0)).astype(int)
    out["is_session_delta_opposing"] = session_delta_sign.ne(0) & session_delta_sign.eq(-out["direction_sign"])
    out["score_65_80"] = out["max_score_final"].ge(65) & out["max_score_final"].le(80)

    out["is_killer_1"] = out["pos_in_60m"].between(0.40, 0.60, inclusive="both")
    out["is_killer_2"] = out["is_volume_spike_3x"]
    out["passes_not_all_killers"] = (~out["is_killer_1"]) & (~out["is_killer_2"])

    bool_cols = [
        "is_first_hour",
        "is_after_ib",
        "is_within_ib",
        "is_ib_extension",
        "is_doji",
        "is_narrow_range",
        "is_very_narrow_range",
        "is_volume_spike_3x",
        "is_adaptive_low_delta_vol",
        "is_tight_vs_atr20",
        "is_triple_adaptive",
        "is_60m_extreme",
        "is_15m_trend_aligned",
        "has_core_60m_15m_gate",
        "prior_session_is_wide_range",
        "is_session_delta_opposing",
        "score_65_80",
        "is_killer_1",
        "is_killer_2",
        "passes_not_all_killers",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out.reset_index(drop=True)


def build_walk_forward_windows() -> list[dict[str, object]]:
    raw_specs = [
        (1, ["2025-01", "2025-02"], "2025-03"),
        (2, ["2025-04", "2025-05"], "2025-06"),
        (3, ["2025-06", "2025-07"], "2025-08"),
        (4, ["2025-09", "2025-10"], "2025-11"),
        (5, ["2025-11", "2025-12"], "2026-01"),
        (6, ["2026-02", "2026-03"], "2026-04"),
    ]
    windows: list[dict[str, object]] = []
    for window_num, is_labels, oos_label in raw_specs:
        is_months = [month_period(label) for label in is_labels]
        oos_month = month_period(oos_label)
        windows.append(
            {
                "window_num": window_num,
                "is_months": is_months,
                "oos_month": oos_month,
                "label": f"{format_is_label(is_months)} IS → {month_label(oos_month)} OOS",
            }
        )
    return windows


def sample_stats(df: pd.DataFrame, eval_window: int) -> dict[str, float | int]:
    ret_col = f"trade_ret_{eval_window}b_ticks"
    returns = df[ret_col].dropna()
    n = int(len(returns))
    wins = int((returns > 0).sum())
    ci_low, ci_high, wr_hat = wilson_ci(n, wins)
    return {
        "n": n,
        "wins": wins,
        "wr": win_rate(returns),
        "pf": profit_factor(returns) if n else float("nan"),
        "avg_ticks": float(returns.mean()) if n else float("nan"),
        "ci_low": ci_low,
        "ci_high": ci_high,
        "wr_hat": wr_hat,
    }


def walk_forward_analysis(df: pd.DataFrame, windows: list[dict[str, object]], eval_window: int) -> dict[str, object]:
    ret_col = f"trade_ret_{eval_window}b_ticks"
    oos_frames: list[pd.DataFrame] = []
    rows: list[dict[str, object]] = []
    weak_windows: list[str] = []

    for window in windows:
        is_months = list(window["is_months"])
        oos_month = window["oos_month"]

        is_df = df.loc[df["session_month"].isin(is_months)].copy()
        oos_df = df.loc[df["session_month"].eq(oos_month)].copy()

        is_ret = is_df[ret_col].dropna()
        oos_ret = oos_df[ret_col].dropna()
        oos_n = int(len(oos_ret))
        oos_wins = int((oos_ret > 0).sum())
        oos_wr = win_rate(oos_ret)
        oos_avg_ticks = float(oos_ret.mean()) if oos_n else float("nan")

        rows.append(
            {
                "window_num": int(window["window_num"]),
                "label": str(window["label"]),
                "is_n": int(len(is_ret)),
                "is_wr": win_rate(is_ret),
                "oos_month": oos_month,
                "oos_n": oos_n,
                "oos_wins": oos_wins,
                "oos_wr": oos_wr,
                "oos_avg_ticks": oos_avg_ticks,
            }
        )
        if oos_n and oos_wr < 0.40:
            weak_windows.append(str(window["label"]))
        if oos_n:
            oos_frames.append(oos_df.loc[oos_df[ret_col].notna()].copy())

    oos_trade_df = pd.concat(oos_frames, ignore_index=True) if oos_frames else df.iloc[0:0].copy()
    oos_ret = oos_trade_df[ret_col].dropna()
    oos_n = int(len(oos_ret))
    oos_wins = int((oos_ret > 0).sum())
    oos_ci_low, oos_ci_high, oos_wr_hat = wilson_ci(oos_n, oos_wins)
    oos_wr = win_rate(oos_ret)
    oos_avg = float(oos_ret.mean()) if oos_n else float("nan")

    if oos_n == 0:
        status = "FAIL"
        reason = "no out-of-sample trades"
    elif weak_windows:
        status = "FAIL"
        reason = f"{len(weak_windows)} OOS window(s) below 40% WR"
    else:
        status = "PASS"
        reason = "no OOS window below 40% WR"

    return {
        "rows": rows,
        "oos_trade_df": oos_trade_df,
        "oos_n": oos_n,
        "oos_wins": oos_wins,
        "oos_wr": oos_wr,
        "oos_avg_ticks": oos_avg,
        "oos_ci_low": oos_ci_low,
        "oos_ci_high": oos_ci_high,
        "oos_wr_hat": oos_wr_hat,
        "weak_windows": weak_windows,
        "status": status,
        "reason": reason,
    }


def longest_losing_trade_streak(df: pd.DataFrame, eval_window: int) -> int:
    ret_col = f"trade_ret_{eval_window}b_ticks"
    returns = df.sort_values(["bar_ts", "global_index", "direction_sign"], kind="stable")[ret_col].dropna()
    longest = 0
    current = 0
    for value in returns:
        if value <= 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def monthly_stability(df: pd.DataFrame, months: list[pd.Period], eval_window: int) -> dict[str, object]:
    ret_col = f"trade_ret_{eval_window}b_ticks"
    rows: list[dict[str, object]] = []
    for month in months:
        month_df = df.loc[df["session_month"].eq(month)].copy()
        ret = month_df[ret_col].dropna()
        n = int(len(ret))
        rows.append(
            {
                "month": month,
                "label": month_short_label(month),
                "n": n,
                "wr": win_rate(ret),
                "avg_ticks": float(ret.mean()) if n else float("nan"),
            }
        )

    active_rows = [row for row in rows if row["n"] > 0]
    good_months = sum(1 for row in active_rows if row["wr"] > 0.50)
    flagged_bad_months: list[str] = []
    longest_bad_month_streak = 0
    current_bad_month_streak = 0

    for row in active_rows:
        if row["wr"] < 0.50:
            current_bad_month_streak += 1
            longest_bad_month_streak = max(longest_bad_month_streak, current_bad_month_streak)
        else:
            current_bad_month_streak = 0
        if row["n"] >= 3 and row["wr"] < 0.35:
            flagged_bad_months.append(row["label"])

    if not active_rows:
        status = "FAIL"
        reason = "no monthly OOS trades"
    elif flagged_bad_months:
        status = "FAIL"
        reason = f"month(s) below 35% WR with N>=3: {', '.join(flagged_bad_months)}"
    else:
        status = "PASS"
        reason = "no OOS month below 35% WR with N>=3"

    return {
        "rows": rows,
        "active_months": len(active_rows),
        "good_months": good_months,
        "flagged_bad_months": flagged_bad_months,
        "longest_bad_month_streak": longest_bad_month_streak,
        "longest_losing_trade_streak": longest_losing_trade_streak(df, eval_window),
        "status": status,
        "reason": reason,
    }


def bayesian_analysis(df: pd.DataFrame, eval_window: int) -> dict[str, object]:
    ret_col = f"trade_ret_{eval_window}b_ticks"
    ret = df[ret_col].dropna()
    n = int(len(ret))
    wins = int((ret > 0).sum())
    losses = n - wins
    posterior_alpha = BETA_PRIOR_ALPHA + wins
    posterior_beta = BETA_PRIOR_BETA + losses
    observed_wr = win_rate(ret)
    posterior_mean = posterior_alpha / (posterior_alpha + posterior_beta)
    ci_low, ci_high = beta_credible_interval(posterior_alpha, posterior_beta)
    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "observed_wr": observed_wr,
        "posterior_alpha": posterior_alpha,
        "posterior_beta": posterior_beta,
        "posterior_mean": float(posterior_mean),
        "ci_low": ci_low,
        "ci_high": ci_high,
    }


def overall_verdict(walk_forward: dict[str, object], monthly: dict[str, object], bayes: dict[str, object]) -> str:
    oos_wr = float(walk_forward["oos_wr"])
    posterior_mean = float(bayes["posterior_mean"])
    has_bad_month = bool(monthly["flagged_bad_months"])
    if not pd.isna(oos_wr) and oos_wr > 0.55 and not has_bad_month and posterior_mean > 0.55:
        return "DEPLOY"
    if not pd.isna(oos_wr) and oos_wr > 0.50 and posterior_mean > 0.50:
        return "PAPER TRADE"
    return "INSUFFICIENT"


def sample_label(sample_key: str) -> str:
    labels = {
        "bar": "grouped signal-bar sample / sign(bar_delta)",
        "absorption": "absorption observation sample / event direction_sign",
    }
    return labels[sample_key]


def build_filter_specs() -> list[dict[str, object]]:
    return [
        {
            "code": "01",
            "source_round": "R29",
            "label": "absorption + 60m + 15m + prior wide-range day + NOT killers",
            "sample_key": "absorption",
            "eval_window": 30,
            "predicate": lambda df: df["has_core_60m_15m_gate"] & df["prior_session_is_wide_range"] & df["passes_not_all_killers"],
            "reference": "R29: 100% WR, N=10.",
        },
        {
            "code": "02",
            "source_round": "R30",
            "label": "Gap absorption (3+ bar gap then re-absorption) + 60m + 15m",
            "sample_key": "absorption",
            "eval_window": 30,
            "predicate": lambda df: df["has_core_60m_15m_gate"] & df["has_prior_abs_gap_3plus"],
            "reference": "R30: 100.0% WR30, N=20.",
        },
        {
            "code": "03",
            "source_round": "R30",
            "label": "absorption -> exhaustion within 3 bars + 60m + 15m",
            "sample_key": "absorption",
            "eval_window": 30,
            "predicate": lambda df: df["has_core_60m_15m_gate"] & df["has_future_exhaustion_within_3"],
            "reference": "R30: 91.7% WR30, N=36.",
        },
        {
            "code": "04",
            "source_round": "R33",
            "label": "Adaptive low delta/vol (rolling q10) + doji + 60m + 15m + NOT killers",
            "sample_key": "bar",
            "eval_window": 30,
            "predicate": lambda df: df["is_adaptive_low_delta_vol"] & df["is_doji"] & df["has_core_60m_15m_gate"] & df["passes_not_all_killers"],
        },
        {
            "code": "05",
            "source_round": "R33",
            "label": "Triple adaptive absorption: high vol + low range + low delta/vol + 60m + 15m + NOT killers",
            "sample_key": "absorption",
            "eval_window": 30,
            "predicate": lambda df: df["is_triple_adaptive"] & df["has_core_60m_15m_gate"] & df["passes_not_all_killers"],
        },
        {
            "code": "06",
            "source_round": "R34",
            "label": "Score 65-80 + 60m + 15m + first_hour + NOT killers",
            "sample_key": "bar",
            "eval_window": 30,
            "predicate": lambda df: df["score_65_80"] & df["has_core_60m_15m_gate"] & df["is_first_hour"] & df["passes_not_all_killers"],
        },
        {
            "code": "07",
            "source_round": "R34",
            "label": "max_strength >= 0.7 + score >= 60 + 60m + 15m + first_hour + NOT killers",
            "sample_key": "bar",
            "eval_window": 30,
            "predicate": lambda df: df["max_strength"].ge(0.70) & df["max_score_final"].ge(60) & df["has_core_60m_15m_gate"] & df["is_first_hour"] & df["passes_not_all_killers"],
        },
        {
            "code": "08",
            "source_round": "R34",
            "label": "absorption + exhaustion + trapped same bar + 60m + 15m + NOT killers",
            "sample_key": "absorption",
            "eval_window": 30,
            "predicate": lambda df: df["has_exhaustion_family"] & df["has_trap_family"] & df["has_core_60m_15m_gate"] & df["passes_not_all_killers"],
        },
        {
            "code": "09",
            "source_round": "R35",
            "label": "Within IB + session delta opposing + 60m + 15m + NOT killers",
            "sample_key": "bar",
            "eval_window": 30,
            "predicate": lambda df: df["is_within_ib"] & df["is_session_delta_opposing"] & df["has_core_60m_15m_gate"] & df["passes_not_all_killers"],
        },
        {
            "code": "10",
            "source_round": "R35",
            "label": "IB extension + wide day + 60m + 15m + NOT killers + first_hour",
            "sample_key": "bar",
            "eval_window": 30,
            "predicate": lambda df: df["is_ib_extension"] & df["prior_session_is_wide_range"] & df["has_core_60m_15m_gate"] & df["passes_not_all_killers"] & df["is_first_hour"],
            "note": "Implemented literally from the brief. With first_hour defined as 09:30-10:29 ET and IB extension locked only after the first hour, this filter is structurally expected to be empty.",
        },
        {
            "code": "11",
            "source_round": "R33",
            "label": "Range < 0.5x ATR20 + doji + 60m + 15m + NOT killers",
            "sample_key": "bar",
            "eval_window": 30,
            "predicate": lambda df: df["is_tight_vs_atr20"] & df["is_doji"] & df["has_core_60m_15m_gate"] & df["passes_not_all_killers"],
            "reference": "R33: tight + doji family.",
        },
        {
            "code": "12",
            "source_round": "R35",
            "label": "Session delta opposing signal + 60m + 15m",
            "sample_key": "bar",
            "eval_window": 30,
            "predicate": lambda df: df["is_session_delta_opposing"] & df["has_core_60m_15m_gate"],
            "reference": "R35: counter-delta reversal.",
        },
    ]


def validate_filter(
    sample_df: pd.DataFrame,
    filter_spec: dict[str, object],
    windows: list[dict[str, object]],
    oos_months: list[pd.Period],
) -> dict[str, object]:
    filtered = sample_df.loc[filter_spec["predicate"](sample_df)].copy()
    eval_window = int(filter_spec["eval_window"])
    stats = sample_stats(filtered, eval_window)
    walk_forward = walk_forward_analysis(filtered, windows, eval_window)
    oos_trade_df = walk_forward["oos_trade_df"]
    monthly = monthly_stability(oos_trade_df, oos_months, eval_window)
    bayes = bayesian_analysis(oos_trade_df, eval_window)

    return {
        "filter_code": str(filter_spec["code"]),
        "source_round": str(filter_spec["source_round"]),
        "label": str(filter_spec["label"]),
        "sample_key": str(filter_spec["sample_key"]),
        "eval_window": eval_window,
        "reference": filter_spec.get("reference"),
        "note": filter_spec.get("note"),
        "n": int(stats["n"]),
        "wr": float(stats["wr"]),
        "pf": float(stats["pf"]),
        "avg_ticks": float(stats["avg_ticks"]),
        "walk_forward": walk_forward,
        "monthly": monthly,
        "bayes": bayes,
        "verdict": overall_verdict(walk_forward, monthly, bayes),
    }


def render_reference_line(result: dict[str, object]) -> str | None:
    reference = result.get("reference")
    if not reference:
        return None
    return f"Discovery reference: {reference}"


def render_summary_table(results: list[dict[str, object]]) -> list[str]:
    headers = ["Rank", "Round", "Eval", "Filter", "N", "WR%", "OOS N", "OOS WR%", "OOS Wilson 95% CI", "OOS Bayes", "Verdict"]
    data_rows: list[list[str]] = []

    for idx, row in enumerate(results, start=1):
        walk_forward = row["walk_forward"]
        bayes = row["bayes"]
        data_rows.append(
            [
                str(idx),
                str(row["source_round"]),
                f"{int(row['eval_window'])}b",
                f"{row['filter_code']}. {row['label']}",
                f"{int(row['n']):,}",
                fmt_pct(float(row["wr"])),
                f"{int(walk_forward['oos_n']):,}",
                fmt_pct(float(walk_forward["oos_wr"])),
                fmt_ci(float(walk_forward["oos_ci_low"]), float(walk_forward["oos_ci_high"])),
                fmt_pct(float(bayes["posterior_mean"])),
                str(row["verdict"]),
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


def render_baseline_line(label: str, df: pd.DataFrame, eval_window: int) -> str:
    stats = sample_stats(df, eval_window)
    return (
        f"{label}: N={int(stats['n']):,} | WR={fmt_pct(float(stats['wr']))} | PF={fmt_float(float(stats['pf']))} | "
        f"Avg={fmt_ticks(float(stats['avg_ticks']))} ticks | CI={fmt_ci(float(stats['ci_low']), float(stats['ci_high']))}"
    )


def render_filter_report(result: dict[str, object]) -> list[str]:
    walk_forward = result["walk_forward"]
    monthly = result["monthly"]
    bayes = result["bayes"]
    weak_windows = walk_forward["weak_windows"]
    reference_line = render_reference_line(result)

    lines = [
        f"FILTER {result['filter_code']}: {result['label']}",
        "-" * (8 + len(result["filter_code"]) + len(result["label"])),
        f"Source round: {result['source_round']}",
        f"Observation frame: {sample_label(str(result['sample_key']))}",
        f"Evaluation horizon: {int(result['eval_window'])} bars forward",
        f"Discovery sample: N={result['n']:,}, WR={fmt_pct(float(result['wr']))}, PF={fmt_float(float(result['pf']))}, Avg={fmt_ticks(float(result['avg_ticks']))} ticks",
    ]
    if reference_line is not None:
        lines.append(reference_line)
    if result["note"]:
        lines.append(f"Note: {result['note']}")

    lines.extend(
        [
            "",
            f"A) Walk-Forward ({len(walk_forward['rows'])} fixed windows, 2mo IS / 1mo OOS):",
        ]
    )
    for row in walk_forward["rows"]:
        lines.append(
            f"  Window {int(row['window_num'])} ({row['label']}): IS N={int(row['is_n'])}, IS WR={fmt_pct(float(row['is_wr']))} | "
            f"OOS N={int(row['oos_n'])}, Wins={int(row['oos_wins'])}, WR={fmt_pct(float(row['oos_wr']))}, Avg={fmt_ticks(float(row['oos_avg_ticks']))} ticks"
        )
    lines.extend(
        [
            f"  Composite OOS: N={int(walk_forward['oos_n'])}, Wins={int(walk_forward['oos_wins'])}, WR={fmt_pct(float(walk_forward['oos_wr']))}, Avg={fmt_ticks(float(walk_forward['oos_avg_ticks']))} ticks",
            f"  OOS Wilson 95% CI: {fmt_ci(float(walk_forward['oos_ci_low']), float(walk_forward['oos_ci_high']))}",
            f"  Any OOS window < 40% WR: {'YES' if weak_windows else 'NO'}",
            f"  [{walk_forward['status']}]: {walk_forward['reason']}",
            "",
            "B) Monthly Stability (OOS months only):",
        ]
    )
    for row in monthly["rows"]:
        lines.append(
            f"  {row['label']}: N={int(row['n'])}, WR={fmt_pct(float(row['wr']))}, Avg={fmt_ticks(float(row['avg_ticks']))} ticks"
        )
    lines.extend(
        [
            f"  Months > 50% WR: {int(monthly['good_months'])}/{int(monthly['active_months'])}",
            f"  Longest bad-month streak (<50% WR): {int(monthly['longest_bad_month_streak'])}",
            f"  Longest losing trade streak (composite OOS): {int(monthly['longest_losing_trade_streak'])}",
            f"  [{monthly['status']}]: {monthly['reason']}",
            "",
            "C) Bayesian (Composite OOS):",
            f"  Prior: Beta({BETA_PRIOR_ALPHA}, {BETA_PRIOR_BETA}), mean=50.0%",
            f"  Posterior: Beta({int(bayes['posterior_alpha'])}, {int(bayes['posterior_beta'])}), mean={fmt_pct(float(bayes['posterior_mean']))}",
            f"  95% Credible Interval: {fmt_ci(float(bayes['ci_low']), float(bayes['ci_high']))}",
            f"  Shrinkage: {fmt_pct(float(bayes['observed_wr']))} → {fmt_pct(float(bayes['posterior_mean']))}",
            "",
            f"OVERALL VERDICT: {result['verdict']}",
            "- DEPLOY: composite OOS WR > 55%, no OOS month below 35% WR (N>=3), posterior > 55%",
            "- PAPER TRADE: composite OOS WR > 50% and posterior > 50%",
            "- INSUFFICIENT: otherwise",
            "",
        ]
    )
    return lines


def build_validation_samples() -> tuple[pd.DataFrame, pd.DataFrame, dict[int, pd.DataFrame], pd.DataFrame, dict[str, float], int]:
    events = load_events()
    bars_1m = load_ohlcv()
    all_bars = build_bar_frame(events)
    bar_features = compute_bar_features(all_bars)
    session_summary, session_thresholds = build_session_summary(all_bars)
    rth_context = build_rth_context(filter_rth_bars(bars_1m))
    timeframe_context = build_timeframe_context(bars_1m)

    signal_directional = build_signal_directional_observations(events)
    absorption_sample = build_absorption_observations(events)
    bar_sample = build_bar_observations(events)

    directional_cols = [
        "global_index",
        "direction_sign",
        "signal_count",
        "category_count",
        "other_category_count",
        "max_strength",
        "max_score_final",
        "has_absorption",
        "has_trap_family",
        "has_exhaustion_family",
    ]
    absorption_sample = absorption_sample.merge(
        signal_directional[directional_cols],
        on=["global_index", "direction_sign"],
        how="left",
        validate="one_to_one",
    )
    absorption_sample = add_absorption_sequence_flags(absorption_sample, signal_directional)

    absorption_sample = attach_common_context(
        absorption_sample,
        bar_features,
        session_summary,
        session_thresholds,
        rth_context,
        timeframe_context,
    )
    bar_sample = attach_common_context(
        bar_sample,
        bar_features,
        session_summary,
        session_thresholds,
        rth_context,
        timeframe_context,
    )

    absorption_sample = absorption_sample.loc[absorption_sample["session_month"].isin(VALIDATION_MONTHS)].copy()
    bar_sample = bar_sample.loc[bar_sample["session_month"].isin(VALIDATION_MONTHS)].copy()

    absorption_sample = absorption_sample.sort_values(["bar_ts", "global_index", "direction_sign"], kind="stable").reset_index(drop=True)
    bar_sample = bar_sample.sort_values(["bar_ts", "global_index", "direction_sign"], kind="stable").reset_index(drop=True)

    metadata = pd.DataFrame(
        {
            "metric": [
                "raw_event_rows",
                "raw_absorption_event_rows",
                "unique_all_signal_bars",
                "signal_directional_observations",
                "bar_sample_observations",
                "absorption_sample_observations",
                "core_bar_sample",
                "core_absorption_sample",
                "adaptive_low_delta_vol_bar_sample",
                "triple_adaptive_absorption_sample",
                "session_delta_opposing_bar_sample",
                "within_ib_bar_sample",
                "ib_extension_bar_sample",
            ],
            "value": [
                len(events),
                int(events["category"].eq("absorption").sum()),
                len(all_bars),
                len(signal_directional),
                len(bar_sample),
                len(absorption_sample),
                int(bar_sample["has_core_60m_15m_gate"].sum()),
                int(absorption_sample["has_core_60m_15m_gate"].sum()),
                int(bar_sample["is_adaptive_low_delta_vol"].sum()),
                int(absorption_sample["is_triple_adaptive"].sum()),
                int(bar_sample["is_session_delta_opposing"].sum()),
                int(bar_sample["is_within_ib"].sum()),
                int(bar_sample["is_ib_extension"].sum()),
            ],
        }
    )
    return absorption_sample, bar_sample, timeframe_context, metadata, session_thresholds, len(events)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    absorption_sample, bar_sample, timeframe_context, metadata, session_thresholds, raw_event_count = build_validation_samples()
    windows = build_walk_forward_windows()
    oos_months = [window["oos_month"] for window in windows]

    samples = {
        "absorption": absorption_sample,
        "bar": bar_sample,
    }

    results: list[dict[str, object]] = []
    for filter_spec in build_filter_specs():
        sample_df = samples[str(filter_spec["sample_key"])]
        results.append(validate_filter(sample_df, filter_spec, windows, oos_months))

    results.sort(
        key=lambda row: (
            float("-inf") if pd.isna(row["walk_forward"]["oos_wr"]) else float(row["walk_forward"]["oos_wr"]),
            int(row["walk_forward"]["oos_n"]),
            float("-inf") if pd.isna(row["bayes"]["posterior_mean"]) else float(row["bayes"]["posterior_mean"]),
            float("-inf") if pd.isna(row["wr"]) else float(row["wr"]),
            int(row["n"]),
        ),
        reverse=True,
    )

    meta = metadata.set_index("metric")["value"]

    lines = [
        "ROUND 36 WALK-FORWARD VALIDATION (R29-R35 TOP 12)",
        "=================================================",
        "",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation frames: (1) grouped signal bars using sign(bar_delta) for non-absorption filters, and (2) grouped absorption observations using event direction_sign.",
        "Core gate carries forward from prior rounds: 60m_extreme = trade anchor in bottom 20% / top 20% of the active 60m bar; 15m gate = trade direction aligned with the active 15m trend.",
        "Killers carry forward from prior rounds: killer_1 = 60m position in the middle 40%-60%; killer_2 = bar_volume > 3x prior 20-bar EMA volume; NOT killers = neither killer fired.",
        "Adaptive low delta/vol = abs(bar_delta) / bar_volume below the prior 50 grouped-bar rolling 10th percentile within the same session.",
        "Triple adaptive = bar_volume above the prior 50 grouped-bar rolling 90th percentile AND bar_range < 0.5 * ATR20 AND adaptive low delta/vol.",
        "Wide day carries forward from prior rounds as prior_session_is_wide_range = prior session range >= validation-period session-range q75 built from unique signal bars.",
        "IB context is reconstructed directly from nq_1yr_1m.csv: IB high/low = 09:30-10:29 ET; within-IB and extension states are evaluated only after that first hour to avoid look-ahead.",
        "Session delta opposing = sign(session_cumulative_delta) opposite the filter trade direction. Session cumulative delta is built from unique signal bars because nq_1yr_1m.csv does not contain delta.",
        "All 12 requested filters are evaluated on 30-bar forward returns because the supplied R29-R35 leader notes were framed as top findings and the explicit references pointed to WR30 leaders.",
        "round35_session_structure.py was not present under scripts/, and round33/round34 source scripts were also absent, so those filters were rebuilt directly from the task brief plus existing round11/24/29/30 primitives.",
        "Walk-forward windows: Jan-Feb→Mar 2025, Apr-May→Jun 2025, Jun-Jul→Aug 2025, Sep-Oct→Nov 2025, Nov-Dec 2025→Jan 2026, Feb-Mar→Apr 2026.",
        "Monthly stability and Bayesian metrics use only composite OOS trades.",
        "",
        f"Raw event rows loaded:                   {raw_event_count:,}",
        f"Raw absorption event rows:               {int(meta['raw_absorption_event_rows']):,}",
        f"Unique all-signal bars:                  {int(meta['unique_all_signal_bars']):,}",
        f"Signal-direction observations:           {int(meta['signal_directional_observations']):,}",
        f"Bar-sample observations:                 {int(meta['bar_sample_observations']):,}",
        f"Absorption observations:                 {int(meta['absorption_sample_observations']):,}",
        f"15m bars built:                          {len(timeframe_context[15]):,}",
        f"60m bars built:                          {len(timeframe_context[60]):,}",
        f"Prior wide-range threshold (range q75):  {fmt_float(float(session_thresholds['range_q75']))}",
        f"Core bar observations:                   {int(meta['core_bar_sample']):,}",
        f"Core absorption observations:            {int(meta['core_absorption_sample']):,}",
        f"Adaptive low delta/vol bar observations: {int(meta['adaptive_low_delta_vol_bar_sample']):,}",
        f"Triple adaptive absorption obs:          {int(meta['triple_adaptive_absorption_sample']):,}",
        f"Session-delta-opposing bar obs:          {int(meta['session_delta_opposing_bar_sample']):,}",
        f"Within-IB bar observations:              {int(meta['within_ib_bar_sample']):,}",
        f"IB-extension bar observations:           {int(meta['ib_extension_bar_sample']):,}",
        "",
        "Baselines",
        "---------",
        render_baseline_line("Bar sample core 30b", bar_sample.loc[bar_sample['has_core_60m_15m_gate']].copy(), 30),
        render_baseline_line(
            "Bar sample core 30b + NOT killers",
            bar_sample.loc[bar_sample['has_core_60m_15m_gate'] & bar_sample['passes_not_all_killers']].copy(),
            30,
        ),
        render_baseline_line("Absorption sample core 30b", absorption_sample.loc[absorption_sample['has_core_60m_15m_gate']].copy(), 30),
        render_baseline_line(
            "Absorption sample core 30b + NOT killers",
            absorption_sample.loc[absorption_sample['has_core_60m_15m_gate'] & absorption_sample['passes_not_all_killers']].copy(),
            30,
        ),
        "",
        "Summary ranking by composite OOS WR",
        "-----------------------------------",
    ]
    lines.extend(render_summary_table(results))
    lines.append("")

    for result in results:
        lines.extend(render_filter_report(result))

    report = "\n".join(lines).rstrip() + "\n"
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report, end="")
    print(f"Saved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
