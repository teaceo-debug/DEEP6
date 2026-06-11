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
OUT_PATH = OUT_DIR / "round10_stack_winners_exclude_killers_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
FIRST_HOUR_MINUTES = 60
OPENING_RANGE_BARS = 15
SEQUENCE_DIRECTIONS = (-1, 1)

FilterSpec = tuple[str, str, str, str, Callable[[pd.DataFrame], pd.Series]]


def direction_to_sign(series: pd.Series) -> pd.Series:
    return series.map({"1": 1, "-1": -1, "BULLISH": 1, "BEARISH": -1, 1: 1, -1: -1}).fillna(0).astype(int)


def direction_suffix(direction: int) -> str:
    return "pos" if direction > 0 else "neg"


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


def attach_directional_event_features(observations: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    working = events.copy()
    working["event_direction_sign"] = direction_to_sign(working["direction"])
    working = working[working["event_direction_sign"].ne(0)].copy()
    working["is_absorption"] = working["category"].eq("absorption")
    working["is_TRAP_05"] = working["signal_id"].eq("TRAP_05")

    grouped = (
        working.groupby(["global_index", "event_direction_sign"], as_index=False, sort=False)
        .agg(
            has_absorption=("is_absorption", "max"),
            has_TRAP_05=("is_TRAP_05", "max"),
        )
        .sort_values(["global_index", "event_direction_sign"], kind="stable")
        .reset_index(drop=True)
    )

    out = observations.copy()
    for direction in SEQUENCE_DIRECTIONS:
        suffix = direction_suffix(direction)
        subset = grouped.loc[grouped["event_direction_sign"].eq(direction)].drop(columns="event_direction_sign")
        subset = subset.rename(
            columns={
                "has_absorption": f"has_absorption_{suffix}",
                "has_TRAP_05": f"has_TRAP_05_{suffix}",
            }
        )
        out = out.merge(subset, on="global_index", how="left", validate="one_to_one")
        out[f"has_absorption_{suffix}"] = out[f"has_absorption_{suffix}"].fillna(False).astype(bool)
        out[f"has_TRAP_05_{suffix}"] = out[f"has_TRAP_05_{suffix}"].fillna(False).astype(bool)

    return out


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


def attach_session_features(
    observations: pd.DataFrame,
    session_summary: pd.DataFrame,
    thresholds: dict[str, float],
) -> pd.DataFrame:
    session_cols = ["session_date", "session_open", "prior_session_low", "prior_session_range"]
    out = observations.merge(session_summary[session_cols], on="session_date", how="left", validate="many_to_one")
    out["prior_session_is_wide_range"] = out["prior_session_range"].ge(thresholds["range_q75"])
    out["gap_down_session"] = out["session_open"] < out["prior_session_low"]
    out["prior_session_is_wide_range"] = out["prior_session_is_wide_range"].fillna(False).astype(bool)
    out["gap_down_session"] = out["gap_down_session"].fillna(False).astype(bool)
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
    out["body_high"] = np.maximum(out["bar_open"], out["bar_close"])
    out["body_low"] = np.minimum(out["bar_open"], out["bar_close"])
    out["abs_delta"] = out["bar_delta"].abs()

    out["prior_bar_range"] = by_session["bar_range"].shift(1)
    out["bar_range_2"] = by_session["bar_range"].shift(2)
    out["prior_body_high"] = by_session["body_high"].shift(1)
    out["prior_body_low"] = by_session["body_low"].shift(1)

    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )

    out["is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.10 * out["bar_range"])
    out["is_three_narrowing_ranges"] = (
        out["bar_range_2"].notna()
        & out["prior_bar_range"].lt(out["bar_range_2"])
        & out["bar_range"].lt(out["prior_bar_range"])
    )
    out["is_engulfing"] = (
        out["prior_body_high"].notna()
        & out["body_high"].gt(out["prior_body_high"])
        & out["body_low"].lt(out["prior_body_low"])
    )
    out["is_bullish_engulf"] = out["is_engulfing"] & out["bar_close"].gt(out["bar_open"])
    out["is_bearish_engulf"] = out["is_engulfing"] & out["bar_close"].lt(out["bar_open"])
    out["engulf_direction_sign"] = np.select(
        [out["is_bullish_engulf"], out["is_bearish_engulf"]],
        [1, -1],
        default=0,
    ).astype(int)
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
    lunch_mask = out["minutes_since_930"].ge(150) & out["minutes_since_930"].lt(270)
    out["is_not_lunch"] = ~lunch_mask
    return out


def filter_rth_bars(bars_1m: pd.DataFrame) -> pd.DataFrame:
    bars = bars_1m.copy()
    minute_of_day = bars["ts_event"].dt.hour * 60 + bars["ts_event"].dt.minute
    bars = bars.loc[(minute_of_day >= RTH_START_MINUTE) & (minute_of_day < RTH_END_MINUTE)].copy()
    bars["session_date"] = bars["ts_event"].dt.strftime("%Y-%m-%d")
    bars["minutes_since_930"] = minute_of_day.loc[bars.index] - RTH_START_MINUTE
    bars["bar_index"] = bars.groupby("session_date", sort=False).cumcount().astype("int32")
    return bars.reset_index(drop=True)


def build_rth_context(bars_1m: pd.DataFrame) -> pd.DataFrame:
    bars = filter_rth_bars(bars_1m)
    by_session = bars.groupby("session_date", sort=False)

    bars["cum_pv"] = ((bars["close"] * bars["volume"]).groupby(bars["session_date"], sort=False).cumsum())
    bars["cum_vol"] = by_session["volume"].cumsum()
    bars["session_vwap"] = np.where(bars["cum_vol"] > 0, bars["cum_pv"] / bars["cum_vol"], np.nan)
    bars["prev_close"] = by_session["close"].shift(1)
    bars["prev_vwap"] = bars.groupby("session_date", sort=False)["session_vwap"].shift(1)
    bars["is_vwap_cross"] = (
        bars["prev_close"].notna()
        & bars["prev_vwap"].notna()
        & (
            ((bars["prev_close"] < bars["prev_vwap"]) & (bars["close"] > bars["session_vwap"]))
            | ((bars["prev_close"] > bars["prev_vwap"]) & (bars["close"] < bars["session_vwap"]))
        )
    )

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

    bool_cols = [
        "is_vwap_cross",
        "inside_or",
        "broke_above_or_now",
        "broke_below_or_now",
        "has_broken_above_or",
        "has_broken_below_or",
        "has_failed_breakout",
        "has_failed_breakdown",
    ]
    for col in bool_cols:
        bars[col] = bars[col].fillna(False).astype(bool)

    return bars[
        [
            "ts_event",
            "session_date",
            "bar_index",
            "session_vwap",
            "prev_close",
            "prev_vwap",
            "is_vwap_cross",
            "has_failed_breakout",
            "has_failed_breakdown",
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
        "is_vwap_cross",
        "has_failed_breakout",
        "has_failed_breakdown",
    ]
    for col in bool_cols:
        if col in out.columns:
            out[col] = out[col].fillna(False).astype(bool)

    out["has_failed_breakout"] = out["has_failed_breakout"].fillna(False).astype(bool)
    out["has_failed_breakdown"] = out["has_failed_breakdown"].fillna(False).astype(bool)
    out["is_vwap_cross"] = out["is_vwap_cross"].fillna(False).astype(bool)
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

    for window in FORWARD_WINDOWS:
        sample[f"ret_{window}b_ticks"] = sample["trade_sign"] * sample[f"move_{window}b_ticks"]

    sample["is_killer_1"] = sample["pos_in_60m"].between(0.40, 0.60, inclusive="both")
    sample["is_killer_2"] = sample["is_volume_spike_3x"]
    sample["passes_not_killer_1"] = ~sample["is_killer_1"]
    sample["passes_not_killer_2"] = ~sample["is_killer_2"]
    sample["passes_not_all_killers"] = (~sample["is_killer_1"]) & (~sample["is_killer_2"])
    sample["is_failed_or_reversal"] = (
        ((sample["trade_sign"] > 0) & sample["has_failed_breakdown"])
        | ((sample["trade_sign"] < 0) & sample["has_failed_breakout"])
    )
    return sample.reset_index(drop=True)


def build_condition_cache(df: pd.DataFrame) -> dict[tuple[str, int], np.ndarray]:
    cache: dict[tuple[str, int], np.ndarray] = {}
    for direction in SEQUENCE_DIRECTIONS:
        suffix = direction_suffix(direction)
        cache[("doji", direction)] = (df["is_doji"] & df["direction_sign"].eq(direction)).to_numpy(dtype=bool)
        cache[("engulfing", direction)] = df["engulf_direction_sign"].eq(direction).to_numpy(dtype=bool)
        cache[("category_absorption", direction)] = df[f"has_absorption_{suffix}"].to_numpy(dtype=bool)
        cache[("signal_TRAP_05", direction)] = df[f"has_TRAP_05_{suffix}"].to_numpy(dtype=bool)
    return cache


def match_sequence(
    df: pd.DataFrame,
    first_name: str,
    second_name: str,
    lookahead: int,
    relation: str,
) -> pd.DataFrame:
    cache = build_condition_cache(df)
    session_positions = [group.index.to_numpy() for _, group in df.groupby("session_date", sort=False)]
    trade_directions = df["direction_sign"].to_numpy(dtype=int)

    matched_indices: list[int] = []
    matched_trade_signs: list[int] = []

    for positions in session_positions:
        session_len = len(positions)
        for start_offset, start_idx in enumerate(positions):
            for first_direction in SEQUENCE_DIRECTIONS:
                if not cache[(first_name, first_direction)][start_idx]:
                    continue

                second_direction = first_direction if relation == "same" else -first_direction
                max_step = min(lookahead, session_len - start_offset - 1)

                for step in range(1, max_step + 1):
                    end_idx = positions[start_offset + step]
                    if not cache[(second_name, second_direction)][end_idx]:
                        continue

                    trade_sign = int(trade_directions[end_idx])
                    if trade_sign == 0:
                        continue

                    matched_indices.append(int(end_idx))
                    matched_trade_signs.append(trade_sign)
                    break

    if not matched_indices:
        empty = df.head(0).copy().reset_index(drop=True)
        empty["trade_sign"] = pd.Series(dtype="int64")
        return empty

    matched = df.iloc[matched_indices].copy().reset_index(drop=True)
    matched["trade_sign"] = matched_trade_signs
    return matched


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
            "CVD divergence + 60m + 15m_trend + NOT killer_1",
            "div",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["passes_not_killer_1"],
        ),
        (
            "02",
            "A",
            "CVD divergence + 60m + 15m_trend + NOT killer_2",
            "div",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["passes_not_killer_2"],
        ),
        (
            "03",
            "A",
            "CVD divergence + 60m + 15m_trend + NOT all_killers",
            "div",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["passes_not_all_killers"],
        ),
        (
            "04",
            "A",
            "CVD divergence + 60m + 15m_trend + NOT all_killers + first_hour",
            "div",
            lambda df: df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
        (
            "05",
            "A",
            "CVD divergence + 60m + 15m_trend + NOT all_killers + NOT lunch",
            "div",
            lambda df: df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["passes_not_all_killers"]
            & df["is_not_lunch"],
        ),
        (
            "06",
            "B",
            "60m + 15m + NOT all_killers",
            "bar",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["passes_not_all_killers"],
        ),
        (
            "07",
            "B",
            "60m + 15m + NOT all_killers + first_hour",
            "bar",
            lambda df: df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
        (
            "08",
            "B",
            "60m + 15m + NOT all_killers + NOT lunch",
            "bar",
            lambda df: df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["passes_not_all_killers"]
            & df["is_not_lunch"],
        ),
        (
            "09",
            "B",
            "60m + 15m + NOT all_killers + prior_wide_range_day",
            "bar",
            lambda df: df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["passes_not_all_killers"]
            & df["prior_session_is_wide_range"],
        ),
        (
            "10",
            "B",
            "60m + 15m + NOT all_killers + gap_down (bearish signal)",
            "bar",
            lambda df: df["trade_sign"].lt(0)
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["passes_not_all_killers"]
            & df["gap_down_session"],
        ),
        (
            "11",
            "C",
            "Doji + 60m + 15m + NOT all_killers",
            "bar",
            lambda df: df["is_doji"]
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["passes_not_all_killers"],
        ),
        (
            "12",
            "C",
            "Doji + 60m + 15m + NOT all_killers + first_hour",
            "bar",
            lambda df: df["is_doji"]
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
        (
            "13",
            "C",
            "Doji + 60m + 15m + NOT all_killers + NOT lunch",
            "bar",
            lambda df: df["is_doji"]
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["passes_not_all_killers"]
            & df["is_not_lunch"],
        ),
        (
            "14",
            "D",
            "doji -> engulfing within 2 bars + 60m + 15m + NOT all_killers",
            "seq_doji_engulf",
            lambda df: df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["passes_not_all_killers"],
        ),
        (
            "15",
            "D",
            "absorption -> TRAP_05 within 3 bars + 60m + NOT all_killers",
            "seq_abs_trap",
            lambda df: df["is_60m_extreme"] & df["passes_not_all_killers"],
        ),
        (
            "16",
            "E",
            "CVD divergence + doji + 60m + 15m",
            "div",
            lambda df: df["is_doji"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"],
        ),
        (
            "17",
            "E",
            "CVD divergence + 3 narrowing ranges + 60m",
            "div",
            lambda df: df["is_three_narrowing_ranges"] & df["is_60m_extreme"],
        ),
        (
            "18",
            "E",
            "CVD divergence + prior_wide_range_day + 60m + 15m",
            "div",
            lambda df: df["prior_session_is_wide_range"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"],
        ),
        (
            "19",
            "E",
            "CVD divergence + VWAP cross + 60m",
            "div",
            lambda df: df["is_vwap_cross"] & df["is_60m_extreme"],
        ),
        (
            "20",
            "E",
            "CVD divergence + failed OR breakout + 60m",
            "div",
            lambda df: df["is_failed_or_reversal"] & df["is_60m_extreme"],
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
    observations = attach_directional_event_features(observations, events)

    session_summary, session_thresholds = build_session_summary(observations)
    observations = attach_session_features(observations, session_summary, session_thresholds)

    timeframe_context = build_timeframe_context(bars_1m)
    observations = attach_timeframe_context(observations, timeframe_context)
    observations = compute_bar_features(observations)
    observations = compute_cvd_features(observations)
    observations = add_time_flags(observations)

    rth_context = build_rth_context(bars_1m)
    observations = merge_rth_context(observations, rth_context)

    bar_sample = build_trade_sample(observations, observations["direction_sign"])

    div_source = observations.loc[observations["is_cvd_divergence"]].copy()
    div_sample = build_trade_sample(div_source, div_source["divergence_sign"])

    seq_doji_engulf_matches = match_sequence(observations, "doji", "engulfing", lookahead=2, relation="same")
    seq_doji_engulf_sample = build_trade_sample(seq_doji_engulf_matches, seq_doji_engulf_matches.get("trade_sign", 0))

    seq_abs_trap_matches = match_sequence(observations, "category_absorption", "signal_TRAP_05", lookahead=3, relation="same")
    seq_abs_trap_sample = build_trade_sample(seq_abs_trap_matches, seq_abs_trap_matches.get("trade_sign", 0))

    samples = {
        "bar": bar_sample,
        "div": div_sample,
        "seq_doji_engulf": seq_doji_engulf_sample,
        "seq_abs_trap": seq_abs_trap_sample,
    }
    results = run_filters(samples)

    base_bar = summarize_filter("00", "BASE", "All non-zero-delta signal bars", bar_sample)
    base_bar_core = summarize_filter(
        "00A",
        "BASE",
        "60m + 15m (bar_delta direction)",
        bar_sample.loc[bar_sample["is_60m_extreme"] & bar_sample["is_15m_trend_aligned"]].copy(),
    )
    base_div = summarize_filter("00B", "BASE", "All CVD divergence bars", div_sample)
    base_div_core = summarize_filter(
        "00C",
        "BASE",
        "CVD divergence + 60m + 15m",
        div_sample.loc[div_sample["is_60m_extreme"] & div_sample["is_15m_trend_aligned"]].copy(),
    )
    base_seq_doji = summarize_filter("00D", "BASE", "doji -> engulfing matches", seq_doji_engulf_sample)
    base_seq_abs = summarize_filter("00E", "BASE", "absorption -> TRAP_05 matches", seq_abs_trap_sample)

    failed_or_reversal_count = int(
        (
            ((observations["direction_sign"] < 0) & observations["has_failed_breakout"])
            | ((observations["direction_sign"] > 0) & observations["has_failed_breakdown"])
        ).sum()
    )

    lines = [
        "DEEP6 round10 stacked winners excluding killers",
        "=============================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index; sequential filters count matched sequence occurrences and score the SECOND bar.",
        "Trade direction: sign(bar_delta) for base/doji stacks, divergence_sign for CVD stacks, second-bar sign(bar_delta) for sequential stacks.",
        "KILLER_1 = trade-direction anchor in middle 40-60% of the active 60m range. KILLER_2 = bar_volume > 3x prior 20-bar EMA volume.",
        "NOT all_killers = NOT killer_1 AND NOT killer_2. 60m / 15m gates are always re-evaluated against the active trade direction.",
        "Prior wide-range day and gap_down follow the round6 multi-session unique-signal-bar session summary.",
        "VWAP cross and failed OR breakout use RTH 1m context merged on bar_ts; failed OR breakout is direction-aware (bearish=failed breakout, bullish=failed breakdown).",
        "N uses rows with complete 5b/10b/30b forward closes so every WR window and persistence flag uses the same sample.",
        "Persistence: GROWING if WR_30b > WR_5b; STABLE if WR_30b is within 3 percentage points of WR_5b without growth; DECAYING otherwise.",
        "",
        f"Raw event rows loaded:               {len(events):,}",
        f"Grouped signal bars:                 {len(observations):,}",
        f"15m bars built:                      {len(timeframe_context[15]):,}",
        f"60m bars built:                      {len(timeframe_context[60]):,}",
        f"Bars with CVD divergence:            {int(observations['is_cvd_divergence'].sum()):,}",
        f"Bars with prior wide-range day:      {int(observations['prior_session_is_wide_range'].sum()):,}",
        f"Bars in gap-down sessions:           {int(observations['gap_down_session'].sum()):,}",
        f"Bars with VWAP cross:                {int(observations['is_vwap_cross'].sum()):,}",
        f"Bars with failed OR reversal setup:  {failed_or_reversal_count:,}",
        f"KILLER_1 hits (bar-direction sample): {int(bar_sample['is_killer_1'].sum()):,}",
        f"KILLER_2 hits (bar-direction sample): {int(bar_sample['is_killer_2'].sum()):,}",
        "",
        "Baselines",
        "---------",
        f"Bar-direction all bars:        {render_summary_line(base_bar)}",
        f"Bar-direction 60m + 15m:       {render_summary_line(base_bar_core)}",
        f"CVD divergence all bars:       {render_summary_line(base_div)}",
        f"CVD divergence + 60m + 15m:    {render_summary_line(base_div_core)}",
        f"doji -> engulfing matches:     {render_summary_line(base_seq_doji)}",
        f"absorption -> TRAP_05 matches: {render_summary_line(base_seq_abs)}",
        "",
        "20 stacked winner / anti-killer filters ranked by 30b win rate",
        "-------------------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
