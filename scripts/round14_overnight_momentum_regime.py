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
OUT_PATH = OUT_DIR / "round14_overnight_momentum_regime_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (5, 15, 60)
FORWARD_WINDOWS = (5, 10, 30)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
FIRST_HOUR_MINUTES = 60
LARGE_OVERNIGHT_MOVE_TICKS = 100
SMALL_OVERNIGHT_MOVE_TICKS = 20
REALIZED_VOL_WINDOW = 10

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
        "direction": "string",
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
    observations["direction"] = np.select(
        [observations["direction_sign"] > 0, observations["direction_sign"] < 0],
        ["BULLISH", "BEARISH"],
        default="FLAT",
    )
    for window in FORWARD_WINDOWS:
        observations[f"move_{window}b_ticks"] = (
            observations[f"fwd_close_{window}b"] - observations["bar_close"]
        ) / TICK_SIZE
    return observations


def build_session_summary(observations: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    working = observations.sort_values(["session_date", "bar_ts", "global_index"], kind="stable").copy()
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
    summary["overnight_move_sign"] = np.sign(summary["overnight_move_ticks"].fillna(0.0)).astype(int)
    return summary[
        [
            "session_date",
            "rth_open",
            "rth_close",
            "prior_rth_close",
            "overnight_move_ticks",
            "abs_overnight_move_ticks",
            "overnight_move_sign",
        ]
    ].copy()


def attach_session_features(
    observations: pd.DataFrame,
    session_summary: pd.DataFrame,
    thresholds: dict[str, float],
    overnight_context: pd.DataFrame,
) -> pd.DataFrame:
    session_cols = ["session_date", "prior_session_range"]
    out = observations.merge(session_summary[session_cols], on="session_date", how="left", validate="many_to_one")
    out["prior_session_is_wide_range"] = out["prior_session_range"].ge(thresholds["range_q75"])
    out["prior_session_is_wide_range"] = out["prior_session_is_wide_range"].fillna(False).astype(bool)
    out = out.merge(overnight_context, on="session_date", how="left", validate="many_to_one")
    out["overnight_move_sign"] = pd.to_numeric(out["overnight_move_sign"], errors="coerce").fillna(0).astype(int)
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

    df["bar_open"] = pd.to_numeric(df["bar_open"], errors="coerce")
    df["bar_high"] = pd.to_numeric(df["bar_high"], errors="coerce")
    df["bar_low"] = pd.to_numeric(df["bar_low"], errors="coerce")
    df["bar_close"] = pd.to_numeric(df["bar_close"], errors="coerce")
    return df.reset_index(drop=True)


def compute_bar_features(observations: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["prior_bar_range"] = by_session["bar_range"].shift(1)
    out["bar_range_2"] = by_session["bar_range"].shift(2)

    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )

    out["is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.10 * out["bar_range"])
    out["is_three_narrowing_ranges"] = (
        out["bar_range_2"].notna()
        & out["prior_bar_range"].lt(out["bar_range_2"])
        & out["bar_range"].lt(out["prior_bar_range"])
    )
    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])
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
    return out


def consecutive_run_length(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(0).astype(int).to_numpy()
    out = np.zeros(len(values), dtype="int32")
    current_sign = 0
    current_length = 0

    for idx, sign in enumerate(values):
        if sign == 0:
            current_sign = 0
            current_length = 0
            out[idx] = 0
            continue
        if sign == current_sign:
            current_length += 1
        else:
            current_sign = sign
            current_length = 1
        out[idx] = current_length

    return pd.Series(out, index=series.index)


def build_rth_context(rth_bars: pd.DataFrame) -> pd.DataFrame:
    bars = rth_bars.copy()
    by_session = bars.groupby("session_date", sort=False)

    bars["bar_range"] = bars["high"] - bars["low"]
    bars["running_high"] = by_session["high"].cummax()
    bars["running_low"] = by_session["low"].cummin()
    bars["prior_running_high"] = bars.groupby("session_date", sort=False)["running_high"].shift(1)
    bars["prior_running_low"] = bars.groupby("session_date", sort=False)["running_low"].shift(1)
    bars["session_range_so_far"] = bars["running_high"] - bars["running_low"]
    bars["close_pos_in_session"] = (bars["close"] - bars["running_low"]) / bars["session_range_so_far"].replace(0, np.nan)

    bars["is_near_session_high"] = bars["close_pos_in_session"].ge(0.80)
    bars["is_near_session_low"] = bars["close_pos_in_session"].le(0.20)
    bars["made_new_session_high"] = bars["prior_running_high"].notna() & bars["high"].gt(bars["prior_running_high"])
    bars["made_new_session_low"] = bars["prior_running_low"].notna() & bars["low"].lt(bars["prior_running_low"])

    bars["session_midpoint"] = (bars["running_high"] + bars["running_low"]) / 2.0
    bars["prior_session_midpoint"] = bars.groupby("session_date", sort=False)["session_midpoint"].shift(1)
    bars["prev_close"] = by_session["close"].shift(1)
    bars["crossed_session_midpoint"] = (
        bars["prev_close"].notna()
        & bars["prior_session_midpoint"].notna()
        & (
            ((bars["prev_close"] > bars["prior_session_midpoint"]) & (bars["close"] < bars["session_midpoint"]))
            | ((bars["prev_close"] < bars["prior_session_midpoint"]) & (bars["close"] > bars["session_midpoint"]))
        )
    )

    bars["close_change"] = bars["close"] - bars["prev_close"]
    bars["close_sign"] = np.sign(bars["close_change"].fillna(0.0)).astype(int)
    bars["close_run_length"] = by_session["close_sign"].transform(consecutive_run_length)
    bars["prior_close_sign"] = by_session["close_sign"].shift(1).fillna(0).astype(int)
    bars["prior_close_run_length"] = by_session["close_run_length"].shift(1).fillna(0).astype(int)

    bars["return_1m"] = by_session["close"].pct_change()
    bars["realized_vol_10"] = by_session["return_1m"].transform(
        lambda s: s.rolling(REALIZED_VOL_WINDOW, min_periods=REALIZED_VOL_WINDOW).std()
    )
    bars["prior_realized_vol_10"] = bars.groupby("session_date", sort=False)["realized_vol_10"].shift(REALIZED_VOL_WINDOW)

    for lookback in range(1, 6):
        bars[f"realized_vol_10_lag_{lookback}"] = bars.groupby("session_date", sort=False)["realized_vol_10"].shift(lookback)

    bars["is_vol_expanding"] = bars["prior_realized_vol_10"].notna() & bars["realized_vol_10"].gt(bars["prior_realized_vol_10"])
    bars["is_vol_contracting"] = bars["prior_realized_vol_10"].notna() & bars["realized_vol_10"].lt(bars["prior_realized_vol_10"])
    bars["is_vol_breakout"] = (
        bars["realized_vol_10_lag_5"].notna()
        & bars["realized_vol_10_lag_5"].gt(bars["realized_vol_10_lag_4"])
        & bars["realized_vol_10_lag_4"].gt(bars["realized_vol_10_lag_3"])
        & bars["realized_vol_10_lag_3"].gt(bars["realized_vol_10_lag_2"])
        & bars["realized_vol_10_lag_2"].gt(bars["realized_vol_10_lag_1"])
        & bars["realized_vol_10"].gt(bars["realized_vol_10_lag_1"])
    )

    bars["range_1"] = by_session["bar_range"].shift(1)
    bars["range_2"] = by_session["bar_range"].shift(2)
    bars["range_3"] = by_session["bar_range"].shift(3)
    bars["is_range_compression_release"] = (
        bars["range_3"].notna()
        & bars["range_3"].gt(bars["range_2"])
        & bars["range_2"].gt(bars["range_1"])
        & bars["range_1"].gt(0)
        & bars["bar_range"].gt(bars["range_1"])
    )

    bool_cols = [
        "is_near_session_high",
        "is_near_session_low",
        "made_new_session_high",
        "made_new_session_low",
        "crossed_session_midpoint",
        "is_vol_expanding",
        "is_vol_contracting",
        "is_vol_breakout",
        "is_range_compression_release",
    ]
    for col in bool_cols:
        bars[col] = bars[col].fillna(False).astype(bool)

    return bars[
        [
            "ts_event",
            "session_date",
            "bar_index",
            "is_near_session_high",
            "is_near_session_low",
            "made_new_session_high",
            "made_new_session_low",
            "crossed_session_midpoint",
            "prior_close_sign",
            "prior_close_run_length",
            "realized_vol_10",
            "prior_realized_vol_10",
            "is_vol_expanding",
            "is_vol_contracting",
            "is_vol_breakout",
            "is_range_compression_release",
        ]
    ].copy()


def merge_rth_context(observations: pd.DataFrame, rth_context: pd.DataFrame) -> pd.DataFrame:
    renamed_context = rth_context.rename(
        columns={
            "session_date": "rth_session_date",
            "bar_index": "rth_bar_index",
        }
    )
    out = observations.merge(
        renamed_context,
        left_on="bar_ts",
        right_on="ts_event",
        how="left",
        validate="many_to_one",
    ).drop(columns=["ts_event"])

    bool_cols = [
        "is_near_session_high",
        "is_near_session_low",
        "made_new_session_high",
        "made_new_session_low",
        "crossed_session_midpoint",
        "is_vol_expanding",
        "is_vol_contracting",
        "is_vol_breakout",
        "is_range_compression_release",
    ]
    for col in bool_cols:
        if col in out.columns:
            out[col] = out[col].fillna(False).astype(bool)

    out["prior_close_sign"] = pd.to_numeric(out["prior_close_sign"], errors="coerce").fillna(0).astype(int)
    out["prior_close_run_length"] = pd.to_numeric(out["prior_close_run_length"], errors="coerce").fillna(0).astype(int)
    return out


def coerce_trade_sign(trade_sign: int | pd.Series | np.ndarray, index: pd.Index) -> pd.Series:
    if isinstance(trade_sign, pd.Series):
        series = trade_sign.reindex(index)
    else:
        series = pd.Series(trade_sign, index=index)
    return pd.to_numeric(series, errors="coerce").fillna(0).astype(int)


def anchor_pos_in_range(df: pd.DataFrame, trade_sign: pd.Series, tf: int) -> pd.Series:
    rng = df[f"range_{tf}m"].replace(0, np.nan)
    anchor = np.where(trade_sign > 0, df["bar_low"], np.where(trade_sign < 0, df["bar_high"], np.nan))
    return pd.Series((anchor - df[f"low_{tf}m"]) / rng, index=df.index)


def low_pos_in_range(df: pd.DataFrame, tf: int) -> pd.Series:
    rng = df[f"range_{tf}m"].replace(0, np.nan)
    return pd.Series((df["bar_low"] - df[f"low_{tf}m"]) / rng, index=df.index)


def high_pos_in_range(df: pd.DataFrame, tf: int) -> pd.Series:
    rng = df[f"range_{tf}m"].replace(0, np.nan)
    return pd.Series((df["bar_high"] - df[f"low_{tf}m"]) / rng, index=df.index)


def build_trade_sample(source_df: pd.DataFrame, trade_sign: int | pd.Series | np.ndarray) -> pd.DataFrame:
    sample = source_df.copy()
    sample["trade_sign"] = coerce_trade_sign(trade_sign, sample.index)
    sample = sample[sample["trade_sign"].ne(0)].copy()

    sample["pos_in_60m_anchor"] = anchor_pos_in_range(sample, sample["trade_sign"], 60)
    sample["pos_in_60m_low"] = low_pos_in_range(sample, 60)
    sample["pos_in_60m_high"] = high_pos_in_range(sample, 60)
    sample["pos_in_15m_low"] = low_pos_in_range(sample, 15)
    sample["pos_in_15m_high"] = high_pos_in_range(sample, 15)

    sample["is_60m_extreme"] = (
        ((sample["trade_sign"] > 0) & sample["pos_in_60m_low"].le(0.20))
        | ((sample["trade_sign"] < 0) & sample["pos_in_60m_high"].ge(0.80))
    )
    sample["is_15m_trend_aligned"] = sample["trade_sign"].eq(sample["trend_sign_15m"])
    sample["is_5m_trend_aligned"] = sample["trade_sign"].eq(sample["trend_sign_5m"])
    sample["has_core_60m_15m_gate"] = sample["is_60m_extreme"] & sample["is_15m_trend_aligned"]
    sample["is_reversal_timing_setup"] = sample["is_5m_trend_aligned"] & sample["trend_sign_15m"].eq(-sample["trade_sign"])
    sample["is_multi_tf_bottom_extreme"] = (
        sample["trade_sign"].gt(0)
        & sample["is_15m_trend_aligned"]
        & sample["pos_in_60m_low"].le(0.20)
        & sample["pos_in_15m_low"].le(0.20)
    )

    for window in FORWARD_WINDOWS:
        sample[f"ret_{window}b_ticks"] = sample["trade_sign"] * sample[f"move_{window}b_ticks"]

    sample["is_killer_1"] = sample["pos_in_60m_anchor"].between(0.40, 0.60, inclusive="both")
    sample["is_killer_2"] = sample["is_volume_spike_3x"]
    sample["passes_not_all_killers"] = (~sample["is_killer_1"]) & (~sample["is_killer_2"])
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
        (
            "01",
            "A",
            "Large overnight move > 100 ticks + 60m + 15m",
            "bar",
            lambda df: df["abs_overnight_move_ticks"].gt(LARGE_OVERNIGHT_MOVE_TICKS) & df["has_core_60m_15m_gate"],
        ),
        (
            "02",
            "A",
            "Small overnight move < 20 ticks + 60m + 15m",
            "bar",
            lambda df: df["abs_overnight_move_ticks"].lt(SMALL_OVERNIGHT_MOVE_TICKS) & df["has_core_60m_15m_gate"],
        ),
        (
            "03",
            "A",
            "Overnight move opposite signal direction + 60m + 15m",
            "bar",
            lambda df: df["overnight_move_sign"].ne(0)
            & df["overnight_move_sign"].eq(-df["trade_sign"])
            & df["has_core_60m_15m_gate"],
        ),
        (
            "04",
            "A",
            "Overnight move same as signal direction + 60m + 15m",
            "bar",
            lambda df: df["overnight_move_sign"].ne(0)
            & df["overnight_move_sign"].eq(df["trade_sign"])
            & df["has_core_60m_15m_gate"],
        ),
        (
            "05",
            "B",
            "Near session high + bearish signal + 60m + 15m",
            "bar",
            lambda df: df["is_near_session_high"] & df["trade_sign"].lt(0) & df["has_core_60m_15m_gate"],
        ),
        (
            "06",
            "B",
            "Near session low + bullish signal + 60m + 15m",
            "bar",
            lambda df: df["is_near_session_low"] & df["trade_sign"].gt(0) & df["has_core_60m_15m_gate"],
        ),
        (
            "07",
            "B",
            "Crossed running session midpoint + 60m + 15m",
            "bar",
            lambda df: df["crossed_session_midpoint"] & df["has_core_60m_15m_gate"],
        ),
        (
            "08",
            "B",
            "New session high then bearish reversal + 60m + 15m",
            "bar",
            lambda df: df["made_new_session_high"] & df["trade_sign"].lt(0) & df["has_core_60m_15m_gate"],
        ),
        (
            "09",
            "B",
            "New session low then bullish reversal + 60m + 15m",
            "bar",
            lambda df: df["made_new_session_low"] & df["trade_sign"].gt(0) & df["has_core_60m_15m_gate"],
        ),
        (
            "10",
            "B",
            "5+ bars same direction then opposite signal + 60m + 15m",
            "bar",
            lambda df: df["prior_close_run_length"].ge(5)
            & df["prior_close_sign"].ne(0)
            & df["trade_sign"].eq(-df["prior_close_sign"])
            & df["has_core_60m_15m_gate"],
        ),
        (
            "11",
            "C",
            "Current 10-bar realized vol > prior 10-bar vol + 60m + 15m",
            "bar",
            lambda df: df["is_vol_expanding"] & df["has_core_60m_15m_gate"],
        ),
        (
            "12",
            "C",
            "Current 10-bar realized vol < prior 10-bar vol + 60m + 15m",
            "bar",
            lambda df: df["is_vol_contracting"] & df["has_core_60m_15m_gate"],
        ),
        (
            "13",
            "C",
            "Vol expansion after 5 bars of contraction + 60m + 15m",
            "bar",
            lambda df: df["is_vol_breakout"] & df["has_core_60m_15m_gate"],
        ),
        (
            "14",
            "C",
            "3 shrinking ranges then expanding bar + 60m + 15m",
            "bar",
            lambda df: df["is_range_compression_release"] & df["has_core_60m_15m_gate"],
        ),
        (
            "15",
            "D",
            "5m trend aligned + 15m trend aligned + 60m_extreme",
            "bar",
            lambda df: df["is_5m_trend_aligned"] & df["has_core_60m_15m_gate"],
        ),
        (
            "16",
            "D",
            "5m trend aligned while 15m trend opposite + 60m_extreme",
            "bar",
            lambda df: df["is_reversal_timing_setup"] & df["is_60m_extreme"],
        ),
        (
            "17",
            "D",
            "Bottom 20% of 60m and 15m + 15m trend + 60m_extreme",
            "bar",
            lambda df: df["is_multi_tf_bottom_extreme"],
        ),
        (
            "18",
            "E",
            "CVD divergence + doji + 60m + 15m + NOT killers + first_hour",
            "div",
            lambda df: df["is_doji"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
        (
            "19",
            "E",
            "Prior wide-range day + overnight reversal + 60m + 15m + NOT killers",
            "bar",
            lambda df: df["prior_session_is_wide_range"]
            & df["overnight_move_sign"].ne(0)
            & df["overnight_move_sign"].eq(-df["trade_sign"])
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
        ),
        (
            "20",
            "E",
            "3 narrowing ranges + CVD divergence + 60m + 15m + NOT killers",
            "div",
            lambda df: df["is_three_narrowing_ranges"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
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

    rth_bars = filter_rth_bars(bars_1m)
    overnight_context = build_overnight_context(rth_bars)
    observations = attach_session_features(observations, session_summary, session_thresholds, overnight_context)

    timeframe_context = build_timeframe_context(bars_1m)
    observations = attach_timeframe_context(observations, timeframe_context)
    observations = compute_bar_features(observations)
    observations = compute_cvd_features(observations)
    observations = add_time_flags(observations)

    rth_context = build_rth_context(rth_bars)
    observations = merge_rth_context(observations, rth_context)

    bar_sample = build_trade_sample(observations, observations["direction_sign"])

    div_source = observations.loc[observations["is_cvd_divergence"]].copy()
    div_sample = build_trade_sample(div_source, div_source["divergence_sign"])

    samples = {
        "bar": bar_sample,
        "div": div_sample,
    }
    results = run_filters(samples)

    base_bar = summarize_filter("00", "BASE", "All non-zero-delta signal bars", bar_sample)
    base_bar_core = summarize_filter(
        "00A",
        "BASE",
        "60m + 15m (bar_delta direction)",
        bar_sample.loc[bar_sample["has_core_60m_15m_gate"]].copy(),
    )
    base_div = summarize_filter("00B", "BASE", "All CVD divergence bars", div_sample)
    base_div_core = summarize_filter(
        "00C",
        "BASE",
        "CVD divergence + 60m + 15m",
        div_sample.loc[div_sample["has_core_60m_15m_gate"]].copy(),
    )

    lines = [
        "DEEP6 round14 overnight momentum regime",
        "========================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index.",
        "Trade direction: sign(bar_delta) for all baseline / regime filters; divergence_sign for the CVD-divergence stack filters.",
        "Core gate: 60m_extreme = trade-direction anchor in bottom 20% / top 20% of the active 60m bar; 15m gate = trade_sign aligned with the active 15m trend.",
        "KILLER_1 = trade-direction anchor in middle 40-60% of the active 60m range. KILLER_2 = bar_volume > 3x prior 20-bar EMA volume.",
        "Overnight move = current 09:30 RTH open minus prior RTH close, in ticks. Large/small overnight filters use 100-tick and 20-tick cutoffs from the brief.",
        "Session-high/low, midpoint-cross, streak exhaustion, 10-bar realized vol, and range-compression release all come from merged RTH 1m context at bar_ts.",
        "Realized vol = rolling std of 1m close-to-close pct returns over 10 bars; prior vol = the same series shifted 10 bars (non-overlapping comparison window).",
        "Filter 16 scores the 5m-aligned reversal case where the 15m trend is still opposite. Filter 17 follows the literal brief and is bullish-only (bottom 20% of both 60m and 15m).",
        "N uses rows with complete 5b/10b/30b forward closes so every WR window and persistence flag uses the same sample.",
        "Persistence: GROWING if WR_30b > WR_5b; STABLE if WR_30b is within 3 percentage points of WR_5b without growth; DECAYING otherwise.",
        "",
        f"Raw event rows loaded:                  {len(events):,}",
        f"Grouped signal bars:                    {len(observations):,}",
        f"5m bars built:                          {len(timeframe_context[5]):,}",
        f"15m bars built:                         {len(timeframe_context[15]):,}",
        f"60m bars built:                         {len(timeframe_context[60]):,}",
        f"Bars in large overnight-move sessions:  {int(observations['abs_overnight_move_ticks'].gt(LARGE_OVERNIGHT_MOVE_TICKS).sum()):,}",
        f"Bars in small overnight-move sessions:  {int(observations['abs_overnight_move_ticks'].lt(SMALL_OVERNIGHT_MOVE_TICKS).sum()):,}",
        f"Bars near running session high:         {int(observations['is_near_session_high'].sum()):,}",
        f"Bars near running session low:          {int(observations['is_near_session_low'].sum()):,}",
        f"Bars crossing session midpoint:         {int(observations['crossed_session_midpoint'].sum()):,}",
        f"Bars with vol expansion:                {int(observations['is_vol_expanding'].sum()):,}",
        f"Bars with vol contraction:              {int(observations['is_vol_contracting'].sum()):,}",
        f"Bars with vol breakout:                 {int(observations['is_vol_breakout'].sum()):,}",
        f"Bars with compression release:          {int(observations['is_range_compression_release'].sum()):,}",
        f"Bars with CVD divergence:               {int(observations['is_cvd_divergence'].sum()):,}",
        f"KILLER_1 hits (bar-direction sample):   {int(bar_sample['is_killer_1'].sum()):,}",
        f"KILLER_2 hits (bar-direction sample):   {int(bar_sample['is_killer_2'].sum()):,}",
        "",
        "Baselines",
        "---------",
        f"Bar-direction all bars:     {render_summary_line(base_bar)}",
        f"Bar-direction 60m + 15m:    {render_summary_line(base_bar_core)}",
        f"CVD divergence all bars:    {render_summary_line(base_div)}",
        f"CVD divergence + 60m + 15m: {render_summary_line(base_div_core)}",
        "",
        "20 overnight / momentum / regime filters ranked by 30b win rate",
        "-------------------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
