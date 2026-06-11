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
OUT_PATH = OUT_DIR / "round20_ultra_stack_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
VOL_OF_VOL_WINDOW = 10
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
FIRST_HOUR_MINUTES = 60
OPENING_RANGE_BARS = 15
SMALL_OVERNIGHT_MOVE_TICKS = 20

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

FilterSpec = tuple[str, str, str, str, Callable[[pd.DataFrame], pd.Series]]


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


def build_session_summary(observations: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    summary = (
        observations.groupby("session_date", as_index=False, sort=False)
        .agg(
            session_start_ts=("bar_ts", "first"),
            session_open=("bar_open", "first"),
            session_high=("bar_high", "max"),
            session_low=("bar_low", "min"),
            session_close=("bar_close", "last"),
        )
        .sort_values("session_start_ts", kind="stable")
        .reset_index(drop=True)
    )
    summary["session_range"] = summary["session_high"] - summary["session_low"]
    summary["prior_session_range"] = summary["session_range"].shift(1)
    thresholds = {
        "range_q75": float(summary["session_range"].dropna().quantile(0.75)),
    }
    return summary, thresholds


def attach_session_features(
    observations: pd.DataFrame,
    session_summary: pd.DataFrame,
    thresholds: dict[str, float],
) -> pd.DataFrame:
    out = observations.merge(
        session_summary[["session_date", "prior_session_range"]],
        on="session_date",
        how="left",
        validate="many_to_one",
    )
    out["prior_session_is_wide_range"] = out["prior_session_range"].ge(thresholds["range_q75"])
    out["prior_session_is_wide_range"] = out["prior_session_is_wide_range"].fillna(False).astype(bool)
    return out


def filter_rth_bars(bars_1m: pd.DataFrame) -> pd.DataFrame:
    bars = bars_1m.copy()
    minute_of_day = bars["ts_event"].dt.hour * 60 + bars["ts_event"].dt.minute
    bars = bars.loc[(minute_of_day >= RTH_START_MINUTE) & (minute_of_day < RTH_END_MINUTE)].copy()
    bars["session_date"] = bars["ts_event"].dt.strftime("%Y-%m-%d")
    bars["minutes_since_930"] = minute_of_day.loc[bars.index] - RTH_START_MINUTE
    bars["bar_index"] = bars.groupby("session_date", sort=False).cumcount().astype("int32")
    return bars.reset_index(drop=True)


def build_overnight_context(rth_bars: pd.DataFrame) -> pd.DataFrame:
    summary = (
        rth_bars.groupby("session_date", as_index=False, sort=False)
        .agg(
            session_start_ts=("ts_event", "first"),
            rth_open=("open", "first"),
            rth_close=("close", "last"),
        )
        .sort_values("session_start_ts", kind="stable")
        .reset_index(drop=True)
    )
    summary["prior_rth_close"] = summary["rth_close"].shift(1)
    summary["overnight_move_ticks"] = (summary["rth_open"] - summary["prior_rth_close"]) / TICK_SIZE
    summary["abs_overnight_move_ticks"] = summary["overnight_move_ticks"].abs()
    return summary[
        [
            "session_date",
            "rth_open",
            "prior_rth_close",
            "overnight_move_ticks",
            "abs_overnight_move_ticks",
        ]
    ].copy()


def attach_overnight_context(observations: pd.DataFrame, overnight_context: pd.DataFrame) -> pd.DataFrame:
    out = observations.merge(overnight_context, on="session_date", how="left", validate="many_to_one")
    for col in ["rth_open", "prior_rth_close", "overnight_move_ticks", "abs_overnight_move_ticks"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


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
    out["body_high"] = np.maximum(out["bar_open"], out["bar_close"])
    out["body_low"] = np.minimum(out["bar_open"], out["bar_close"])
    out["delta_ratio"] = np.where(out["bar_volume"] > 0, out["bar_delta"].abs() / out["bar_volume"], np.nan)

    out["prior_close"] = by_session["bar_close"].shift(1)
    out["prior_bar_range"] = by_session["bar_range"].shift(1)
    out["bar_range_2"] = by_session["bar_range"].shift(2)
    out["prior_body_high"] = by_session["body_high"].shift(1)
    out["prior_body_low"] = by_session["body_low"].shift(1)

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
    out["vol_of_vol"] = by_session["atr20"].transform(
        lambda s: s.rolling(VOL_OF_VOL_WINDOW, min_periods=VOL_OF_VOL_WINDOW).std()
    )
    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )

    out["is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.10 * out["bar_range"])
    out["is_three_narrowing_ranges"] = (
        out["bar_range_2"].notna()
        & out["prior_bar_range"].lt(out["bar_range_2"])
        & out["bar_range"].lt(out["prior_bar_range"])
    )
    out["is_three_contracting_ranges"] = out["is_three_narrowing_ranges"]
    out["is_very_low_delta_ratio"] = out["delta_ratio"].lt(0.05)
    out["is_low_delta_ratio"] = out["delta_ratio"].lt(0.10)
    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])

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
    out["is_engulfing"] = (
        out["prior_body_high"].notna()
        & out["body_high"].gt(out["prior_body_high"])
        & out["body_low"].lt(out["prior_body_low"])
    )

    bool_cols = [
        "is_doji",
        "is_three_narrowing_ranges",
        "is_three_contracting_ranges",
        "is_very_low_delta_ratio",
        "is_low_delta_ratio",
        "is_volume_spike_3x",
        "is_hammer",
        "is_shooting_star",
        "is_engulfing",
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

    out["is_bearish_cvd_divergence"] = (
        out["is_price_new_session_high"]
        & out["prior_cvd_high"].notna()
        & out["cvd"].lt(out["prior_cvd_high"])
    )
    out["is_bullish_cvd_divergence"] = (
        out["is_price_new_session_low"]
        & out["prior_cvd_low"].notna()
        & out["cvd"].gt(out["prior_cvd_low"])
    )
    out["divergence_sign"] = np.select(
        [out["is_bullish_cvd_divergence"], out["is_bearish_cvd_divergence"]],
        [1, -1],
        default=0,
    ).astype(int)
    out["is_cvd_divergence"] = out["divergence_sign"].ne(0)
    return out


def add_time_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] * 60 + out["minute"]) - RTH_START_MINUTE
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(FIRST_HOUR_MINUTES)
    out["is_first_hour"] = out["is_first_hour"].fillna(False).astype(bool)
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
    calendar_df["month"] = calendar_df["session_date_ts"].dt.month
    calendar_df["is_summer"] = calendar_df["month"].isin([6, 7, 8])
    calendar_df["is_not_summer"] = ~calendar_df["is_summer"]

    fomc_day_dates = expand_session_offsets(session_dates, FOMC_DATES, (0,))
    calendar_df["is_fomc_day"] = calendar_df["session_date_ts"].isin(fomc_day_dates)
    calendar_df["is_not_fomc_day"] = ~calendar_df["is_fomc_day"]

    return calendar_df[
        [
            "session_date_ts",
            "is_summer",
            "is_not_summer",
            "is_fomc_day",
            "is_not_fomc_day",
        ]
    ].copy()


def attach_calendar_flags(observations: pd.DataFrame, calendar_df: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    out["session_date_ts"] = pd.to_datetime(out["session_date"], errors="coerce")
    out = out.merge(calendar_df, on="session_date_ts", how="left", validate="many_to_one")
    for col in ["is_summer", "is_not_summer", "is_fomc_day", "is_not_fomc_day"]:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def build_rth_context(rth_bars: pd.DataFrame) -> pd.DataFrame:
    bars = rth_bars.copy()

    opening_range = (
        bars.loc[bars["bar_index"] < OPENING_RANGE_BARS]
        .groupby("session_date", as_index=False, sort=False)
        .agg(
            or_high=("high", "max"),
            or_low=("low", "min"),
        )
    )
    bars = bars.merge(opening_range, on="session_date", how="left", validate="many_to_one")

    by_session = bars.groupby("session_date", sort=False)
    bars["inside_or"] = bars["close"].le(bars["or_high"]) & bars["close"].ge(bars["or_low"])
    bars["broke_above_or_now"] = bars["bar_index"].ge(OPENING_RANGE_BARS) & bars["high"].gt(bars["or_high"])
    bars["broke_below_or_now"] = bars["bar_index"].ge(OPENING_RANGE_BARS) & bars["low"].lt(bars["or_low"])
    bars["has_broken_above_or"] = by_session["broke_above_or_now"].cummax()
    bars["has_broken_below_or"] = by_session["broke_below_or_now"].cummax()
    bars["has_failed_breakout"] = bars["has_broken_above_or"] & bars["inside_or"] & bars["bar_index"].ge(OPENING_RANGE_BARS)
    bars["has_failed_breakdown"] = bars["has_broken_below_or"] & bars["inside_or"] & bars["bar_index"].ge(OPENING_RANGE_BARS)

    for col in [
        "inside_or",
        "broke_above_or_now",
        "broke_below_or_now",
        "has_broken_above_or",
        "has_broken_below_or",
        "has_failed_breakout",
        "has_failed_breakdown",
    ]:
        bars[col] = bars[col].fillna(False).astype(bool)

    return bars[
        [
            "ts_event",
            "session_date",
            "bar_index",
            "has_failed_breakout",
            "has_failed_breakdown",
        ]
    ].copy()


def merge_rth_context(observations: pd.DataFrame, rth_context: pd.DataFrame) -> pd.DataFrame:
    out = observations.merge(
        rth_context.rename(columns={"session_date": "rth_session_date", "bar_index": "rth_bar_index"}),
        left_on="bar_ts",
        right_on="ts_event",
        how="left",
        validate="many_to_one",
    ).drop(columns=["ts_event"])

    for col in ["has_failed_breakout", "has_failed_breakdown"]:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def coerce_trade_sign(trade_sign: int | pd.Series | np.ndarray, index: pd.Index) -> pd.Series:
    if isinstance(trade_sign, pd.Series):
        series = trade_sign.reindex(index)
    else:
        series = pd.Series(trade_sign, index=index)
    return pd.to_numeric(series, errors="coerce").fillna(0).astype(int)


def anchor_pos_60m(df: pd.DataFrame, trade_sign: pd.Series) -> pd.Series:
    rng_60m = df["range_60m"].replace(0, np.nan)
    anchor = np.where(trade_sign > 0, df["bar_low"], np.where(trade_sign < 0, df["bar_high"], np.nan))
    return pd.Series((anchor - df["low_60m"]) / rng_60m, index=df.index)


def build_trade_sample(source_df: pd.DataFrame, trade_sign: int | pd.Series | np.ndarray) -> pd.DataFrame:
    sample = source_df.copy()
    sample["trade_sign"] = coerce_trade_sign(trade_sign, sample.index)
    sample = sample[sample["trade_sign"].ne(0)].copy()

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
    sample["is_failed_or_reversal"] = (
        ((sample["trade_sign"] > 0) & sample["has_failed_breakdown"])
        | ((sample["trade_sign"] < 0) & sample["has_failed_breakout"])
    )

    bool_cols = [
        "is_60m_extreme",
        "is_15m_trend_aligned",
        "has_core_60m_15m_gate",
        "is_killer_1",
        "is_killer_2",
        "passes_not_all_killers",
        "is_failed_or_reversal",
    ]
    for col in bool_cols:
        sample[col] = sample[col].fillna(False).astype(bool)
    return sample.reset_index(drop=True)


def compute_thresholds(sample: pd.DataFrame) -> dict[str, float]:
    vol_of_vol = sample["vol_of_vol"].dropna()
    return {
        "vol_of_vol_q25": float(vol_of_vol.quantile(0.25)) if not vol_of_vol.empty else float("nan"),
    }


def annotate_sample_context(sample: pd.DataFrame, thresholds: dict[str, float]) -> pd.DataFrame:
    out = sample.copy()
    out["is_stable_vol"] = out["vol_of_vol"].lt(thresholds["vol_of_vol_q25"])
    out["is_small_overnight"] = out["abs_overnight_move_ticks"].lt(SMALL_OVERNIGHT_MOVE_TICKS)
    out["is_stable_vol"] = out["is_stable_vol"].fillna(False).astype(bool)
    out["is_small_overnight"] = out["is_small_overnight"].fillna(False).astype(bool)
    return out


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
        (
            "01",
            "A",
            "CVD div + doji + stable vol + 60m + 15m + NOT killers + first_hour",
            "div",
            lambda df: df["is_doji"]
            & df["is_stable_vol"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
        (
            "02",
            "A",
            "CVD div + doji + small overnight + 60m + 15m + NOT killers + first_hour",
            "div",
            lambda df: df["is_doji"]
            & df["is_small_overnight"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
        (
            "03",
            "A",
            "CVD div + 3 narrowing ranges + stable vol + 60m + 15m + NOT killers",
            "div",
            lambda df: df["is_three_narrowing_ranges"]
            & df["is_stable_vol"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
        ),
        (
            "04",
            "A",
            "CVD div + |delta|/vol < 0.05 + 60m + 15m + NOT killers + first_hour",
            "div",
            lambda df: df["is_very_low_delta_ratio"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
        (
            "05",
            "A",
            "CVD div + prior wide-range day + 60m + 15m + NOT killers",
            "div",
            lambda df: df["prior_session_is_wide_range"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
        ),
        (
            "06",
            "B",
            "Doji + stable vol + small overnight + 60m + 15m + NOT killers + first_hour",
            "bar",
            lambda df: df["is_doji"]
            & df["is_stable_vol"]
            & df["is_small_overnight"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
        (
            "07",
            "B",
            "Doji + 3 narrowing ranges + 60m + 15m + NOT killers + first_hour",
            "bar",
            lambda df: df["is_doji"]
            & df["is_three_narrowing_ranges"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
        (
            "08",
            "B",
            "Doji + |delta|/vol < 0.05 + stable vol + 60m + 15m + NOT killers",
            "bar",
            lambda df: df["is_doji"]
            & df["is_very_low_delta_ratio"]
            & df["is_stable_vol"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
        ),
        (
            "09",
            "B",
            "Doji + failed OR breakout + 60m + 15m + NOT killers",
            "bar",
            lambda df: df["is_doji"]
            & df["is_failed_or_reversal"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
        ),
        (
            "10",
            "B",
            "Doji + NOT FOMC + NOT summer + 60m + 15m + NOT killers + first_hour",
            "bar",
            lambda df: df["is_doji"]
            & df["is_not_fomc_day"]
            & df["is_not_summer"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
        (
            "11",
            "C",
            "|delta|/vol < 0.05 + stable vol + 60m + 15m + NOT killers + first_hour",
            "bar",
            lambda df: df["is_very_low_delta_ratio"]
            & df["is_stable_vol"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
        (
            "12",
            "C",
            "|delta|/vol < 0.05 + small overnight + 60m + 15m + NOT killers + first_hour",
            "bar",
            lambda df: df["is_very_low_delta_ratio"]
            & df["is_small_overnight"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
        (
            "13",
            "C",
            "|delta|/vol < 0.05 + 3 contracting ranges + 60m + 15m + NOT killers",
            "bar",
            lambda df: df["is_very_low_delta_ratio"]
            & df["is_three_contracting_ranges"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
        ),
        (
            "14",
            "C",
            "|delta|/vol < 0.05 + NOT FOMC + NOT summer + 60m + 15m + NOT killers + first_hour",
            "bar",
            lambda df: df["is_very_low_delta_ratio"]
            & df["is_not_fomc_day"]
            & df["is_not_summer"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
        (
            "15",
            "D",
            "Hammer/shooting star + stable vol + 60m + 15m + NOT killers + first_hour",
            "bar",
            lambda df: (df["is_hammer"] | df["is_shooting_star"])
            & df["is_stable_vol"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
        (
            "16",
            "D",
            "Engulfing + |delta|/vol < 0.10 + 60m + 15m + NOT killers + first_hour",
            "bar",
            lambda df: df["is_engulfing"]
            & df["is_low_delta_ratio"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
        (
            "17",
            "D",
            "3 narrowing ranges + stable vol + small overnight + 60m + 15m + NOT killers",
            "bar",
            lambda df: df["is_three_narrowing_ranges"]
            & df["is_stable_vol"]
            & df["is_small_overnight"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
        ),
        (
            "18",
            "D",
            "Failed OR breakout + CVD div + 60m + 15m + NOT killers",
            "div",
            lambda df: df["is_failed_or_reversal"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
        ),
        (
            "19",
            "E",
            "CVD div + doji + stable vol + small overnight + NOT FOMC + 60m + 15m + NOT killers + first_hour",
            "div",
            lambda df: df["is_doji"]
            & df["is_stable_vol"]
            & df["is_small_overnight"]
            & df["is_not_fomc_day"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
        (
            "20",
            "E",
            "|delta|/vol < 0.05 + stable vol + small overnight + NOT FOMC + 3 contracting ranges + 60m + 15m + NOT killers + first_hour",
            "bar",
            lambda df: df["is_very_low_delta_ratio"]
            & df["is_stable_vol"]
            & df["is_small_overnight"]
            & df["is_not_fomc_day"]
            & df["is_three_contracting_ranges"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
    ]


def run_filters(samples: dict[str, pd.DataFrame]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for code, group, label, sample_key, predicate in build_filter_specs():
        sample = samples[sample_key]
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


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events = load_events()
    bars_1m = load_ohlcv()

    observations = build_observations(events)

    session_summary, session_thresholds = build_session_summary(observations)
    observations = attach_session_features(observations, session_summary, session_thresholds)

    rth_bars = filter_rth_bars(bars_1m)
    overnight_context = build_overnight_context(rth_bars)
    observations = attach_overnight_context(observations, overnight_context)

    timeframe_context = build_timeframe_context(bars_1m)
    observations = attach_timeframe_context(observations, timeframe_context)
    observations = compute_bar_features(observations)
    observations = compute_cvd_features(observations)
    observations = add_time_flags(observations)
    observations = attach_calendar_flags(observations, build_session_calendar(bars_1m))

    rth_context = build_rth_context(rth_bars)
    observations = merge_rth_context(observations, rth_context)

    bar_sample = build_trade_sample(observations, observations["direction_sign"])

    div_source = observations.loc[observations["is_cvd_divergence"]].copy()
    div_sample = build_trade_sample(div_source, div_source["divergence_sign"])

    thresholds = compute_thresholds(bar_sample)
    bar_sample = annotate_sample_context(bar_sample, thresholds)
    div_sample = annotate_sample_context(div_sample, thresholds)

    samples = {
        "bar": bar_sample,
        "div": div_sample,
    }
    results = run_filters(samples)

    base_bar = summarize_filter("00", "BASE", "All non-zero-delta signal bars", bar_sample)
    base_bar_core = summarize_filter(
        "00A",
        "BASE",
        "60m + 15m core gate",
        bar_sample.loc[bar_sample["has_core_60m_15m_gate"]].copy(),
    )
    base_bar_core_not_killers = summarize_filter(
        "00B",
        "BASE",
        "60m + 15m + NOT killers",
        bar_sample.loc[bar_sample["has_core_60m_15m_gate"] & bar_sample["passes_not_all_killers"]].copy(),
    )
    base_div = summarize_filter("00C", "BASE", "All CVD divergence bars", div_sample)
    base_div_core = summarize_filter(
        "00D",
        "BASE",
        "CVD divergence + 60m + 15m + NOT killers",
        div_sample.loc[div_sample["has_core_60m_15m_gate"] & div_sample["passes_not_all_killers"]].copy(),
    )

    lines = [
        "DEEP6 round20 ultra-stacked filter analysis",
        "============================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index.",
        "Trade direction: sign(bar_delta) for bar filters; divergence_sign for CVD-divergence filters.",
        "Core gate: bullish bar_low in the bottom 20% of the active 60m range / bearish bar_high in the top 20%, plus 15m trend alignment.",
        "CVD divergence = price makes a new session high/low while cumulative delta fails to confirm.",
        "Doji = body/range < 0.10. Hammer, shooting star, and engulfing use the same wick/body/body-containment rules as round3.",
        "Stable vol = rolling 10-bar std of ATR20 below the 25th percentile of vol_of_vol across the full non-zero-delta bar sample.",
        f"Stable-vol threshold (25th pct vol_of_vol): {fmt_float(thresholds['vol_of_vol_q25'])}",
        f"Small overnight = |09:30 RTH open - prior RTH close| < {SMALL_OVERNIGHT_MOVE_TICKS} ticks.",
        "|delta|/vol = abs(bar_delta) / bar_volume. 3 narrowing/contracting ranges = current range < prior range < range two bars ago.",
        "Failed OR breakout is direction-aware: bullish trades require failed breakdown, bearish trades require failed breakout.",
        "NOT FOMC uses the exact supplied FOMC session dates. NOT summer = month not in [6, 7, 8].",
        "NOT killers = NOT killer_1 (trade anchor in the middle 40-60% of the active 60m range) AND NOT killer_2 (bar_volume > 3x prior 20-bar EMA).",
        "N uses rows with complete 5b/10b/30b forward closes so every WR window and persistence flag uses the same sample.",
        "Persistence: GROWING if WR_30b > WR_5b; STABLE if WR_30b is within 3 percentage points of WR_5b without growth; DECAYING otherwise.",
        "",
        f"Raw event rows loaded:                 {len(events):,}",
        f"Grouped signal bars:                   {len(observations):,}",
        f"Tradable bar-direction sample:         {len(bar_sample):,}",
        f"Tradable CVD-divergence sample:        {len(div_sample):,}",
        f"15m bars built:                        {len(timeframe_context[15]):,}",
        f"60m bars built:                        {len(timeframe_context[60]):,}",
        f"Strict doji bars:                      {int(bar_sample['is_doji'].sum()):,}",
        f"Very-low delta-ratio bars (<0.05):     {int(bar_sample['is_very_low_delta_ratio'].sum()):,}",
        f"Stable-vol bar observations:           {int(bar_sample['is_stable_vol'].sum()):,}",
        f"Stable-vol divergence observations:    {int(div_sample['is_stable_vol'].sum()):,}",
        f"Small-overnight observations:          {int(bar_sample['is_small_overnight'].sum()):,}",
        f"3 narrowing/contracting bars:          {int(bar_sample['is_three_narrowing_ranges'].sum()):,}",
        f"Prior wide-range-day observations:     {int(bar_sample['prior_session_is_wide_range'].sum()):,}",
        f"Failed OR reversal observations:       {int(bar_sample['is_failed_or_reversal'].sum()):,}",
        f"Hammer/shooting-star observations:     {int((bar_sample['is_hammer'] | bar_sample['is_shooting_star']).sum()):,}",
        f"Engulfing observations:                {int(bar_sample['is_engulfing'].sum()):,}",
        "",
        "Baselines",
        "---------",
        f"All non-zero-delta bars:              {render_summary_line(base_bar)}",
        f"60m + 15m core gate:                 {render_summary_line(base_bar_core)}",
        f"60m + 15m + NOT killers:             {render_summary_line(base_bar_core_not_killers)}",
        f"All CVD divergence bars:             {render_summary_line(base_div)}",
        f"CVD divergence + 60m + 15m + NOT killers:{render_summary_line(base_div_core)}",
        "",
        "20 ultra-stacked filters ranked by 30b win rate",
        "----------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
