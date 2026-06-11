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
OUT_PATH = OUT_DIR / "round23_candle_combos_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
RTH_START_MINUTE = 9 * 60 + 30
FIRST_HOUR_MINUTES = 60

FilterSpec = tuple[str, str, Callable[[pd.DataFrame], pd.Series], Callable[[pd.DataFrame], int | pd.Series]]


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
    observations["direction"] = np.select(
        [observations["direction_sign"] > 0, observations["direction_sign"] < 0],
        ["BULLISH", "BEARISH"],
        default="FLAT",
    )
    for window in FORWARD_WINDOWS:
        observations[f"move_{window}b_ticks"] = (observations[f"fwd_close_{window}b"] - observations["bar_close"]) / TICK_SIZE
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

    return df


def compute_color_run_lengths(color_signs: pd.Series) -> pd.Series:
    values = pd.to_numeric(color_signs, errors="coerce").fillna(0).astype(int).to_numpy()
    run_lengths = np.zeros(len(values), dtype=np.int32)
    prev_sign = 0
    prev_length = 0

    for idx, sign in enumerate(values):
        if sign == 0:
            run_lengths[idx] = 0
            prev_sign = 0
            prev_length = 0
            continue

        if sign == prev_sign:
            prev_length += 1
        else:
            prev_sign = sign
            prev_length = 1
        run_lengths[idx] = prev_length

    return pd.Series(run_lengths, index=color_signs.index)


def compute_bar_features(observations: pd.DataFrame) -> pd.DataFrame:
    bars = observations.copy()
    by_session = bars.groupby("session_date", sort=False)

    bars["bar_range"] = bars["bar_high"] - bars["bar_low"]
    bars["body"] = (bars["bar_close"] - bars["bar_open"]).abs()
    bars["body_high"] = np.maximum(bars["bar_open"], bars["bar_close"])
    bars["body_low"] = np.minimum(bars["bar_open"], bars["bar_close"])
    bars["body_mid"] = (bars["bar_open"] + bars["bar_close"]) / 2.0
    bars["upper_wick"] = bars["bar_high"] - bars["body_high"]
    bars["lower_wick"] = bars["body_low"] - bars["bar_low"]
    bars["price_change"] = bars["bar_close"] - bars["bar_open"]
    bars["price_color_sign"] = np.sign(bars["price_change"].fillna(0.0)).astype(int)

    bars["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    bars["rolling_20_avg_range"] = by_session["bar_range"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).mean()
    )

    bars["is_doji"] = bars["bar_range"].gt(0) & bars["body"].lt(0.10 * bars["bar_range"])
    bars["is_volume_spike_2x"] = bars["rolling_20_ema_vol"].gt(0) & bars["bar_volume"].gt(2.0 * bars["rolling_20_ema_vol"])
    bars["is_volume_spike_3x"] = bars["rolling_20_ema_vol"].gt(0) & bars["bar_volume"].gt(3.0 * bars["rolling_20_ema_vol"])

    bars["is_hammer"] = (
        bars["body"].gt(0)
        & bars["lower_wick"].gt(2.0 * bars["body"])
        & bars["upper_wick"].lt(0.5 * bars["body"])
        & bars["bar_close"].gt(bars["bar_open"])
    )
    bars["is_shooting_star"] = (
        bars["body"].gt(0)
        & bars["upper_wick"].gt(2.0 * bars["body"])
        & bars["lower_wick"].lt(0.5 * bars["body"])
        & bars["bar_close"].lt(bars["bar_open"])
    )

    bars["prior_body_high"] = by_session["body_high"].shift(1)
    bars["prior_body_low"] = by_session["body_low"].shift(1)
    bars["is_engulfing"] = (
        bars["prior_body_high"].notna()
        & bars["body_high"].gt(bars["prior_body_high"])
        & bars["body_low"].lt(bars["prior_body_low"])
    )
    bars["is_bullish_engulf"] = bars["is_engulfing"] & bars["bar_close"].gt(bars["bar_open"])
    bars["is_bearish_engulf"] = bars["is_engulfing"] & bars["bar_close"].lt(bars["bar_open"])
    bars["engulf_direction_sign"] = np.select(
        [bars["is_bullish_engulf"], bars["is_bearish_engulf"]],
        [1, -1],
        default=0,
    ).astype(int)

    for shift in range(1, 5):
        bars[f"open_{shift}"] = by_session["bar_open"].shift(shift)
        bars[f"close_{shift}"] = by_session["bar_close"].shift(shift)
        bars[f"high_{shift}"] = by_session["bar_high"].shift(shift)
        bars[f"low_{shift}"] = by_session["bar_low"].shift(shift)
        bars[f"volume_{shift}"] = by_session["bar_volume"].shift(shift)
        bars[f"range_{shift}"] = by_session["bar_range"].shift(shift)
        bars[f"body_mid_{shift}"] = by_session["body_mid"].shift(shift)
        bars[f"price_color_sign_{shift}"] = by_session["price_color_sign"].shift(shift)
        bars[f"is_doji_{shift}"] = by_session["is_doji"].shift(shift).fillna(False).astype(bool)

    bars["ema_vol_1"] = by_session["rolling_20_ema_vol"].shift(1)
    bars["prior_bar_is_volume_spike_2x"] = bars["ema_vol_1"].gt(0) & bars["volume_1"].gt(2.0 * bars["ema_vol_1"])
    bars["engulf_direction_sign_1"] = pd.to_numeric(by_session["engulf_direction_sign"].shift(1), errors="coerce").fillna(0).astype(int)

    bars["color_run_length"] = (
        by_session["price_color_sign"].apply(compute_color_run_lengths).reset_index(level=0, drop=True)
    )
    bars["prior_color_run_length"] = by_session["color_run_length"].shift(1)
    return bars


def compute_combo_features(observations: pd.DataFrame) -> pd.DataFrame:
    bars = observations.copy()

    bars["three_red_then_green_direction_sign"] = np.where(
        bars["price_color_sign"].eq(1)
        & bars["price_color_sign_1"].eq(-1)
        & bars["price_color_sign_2"].eq(-1)
        & bars["price_color_sign_3"].eq(-1),
        1,
        0,
    ).astype(int)
    bars["three_green_then_red_direction_sign"] = np.where(
        bars["price_color_sign"].eq(-1)
        & bars["price_color_sign_1"].eq(1)
        & bars["price_color_sign_2"].eq(1)
        & bars["price_color_sign_3"].eq(1),
        -1,
        0,
    ).astype(int)

    bull_run_reversal = (
        bars["price_color_sign"].eq(1)
        & bars["price_color_sign_1"].eq(-1)
        & bars["prior_color_run_length"].ge(4)
    )
    bear_run_reversal = (
        bars["price_color_sign"].eq(-1)
        & bars["price_color_sign_1"].eq(1)
        & bars["prior_color_run_length"].ge(4)
    )
    bars["extended_run_reversal_direction_sign"] = np.select(
        [bull_run_reversal, bear_run_reversal],
        [1, -1],
        default=0,
    ).astype(int)

    bull_alternating = (
        bars["price_color_sign"].eq(1)
        & bars["price_color_sign_1"].eq(-1)
        & bars["price_color_sign_2"].eq(1)
    )
    bear_alternating = (
        bars["price_color_sign"].eq(-1)
        & bars["price_color_sign_1"].eq(1)
        & bars["price_color_sign_2"].eq(-1)
    )
    bars["alternating_direction_sign"] = np.select(
        [bull_alternating, bear_alternating],
        [1, -1],
        default=0,
    ).astype(int)

    bars["selling_climax_direction_sign"] = np.where(
        bars["price_color_sign"].eq(1)
        & bars["price_color_sign_1"].eq(-1)
        & bars["price_color_sign_2"].eq(-1)
        & bars["range_1"].gt(bars["range_2"]),
        1,
        0,
    ).astype(int)

    bars["is_morning_star"] = (
        bars["price_color_sign"].eq(1)
        & bars["is_doji_1"]
        & bars["price_color_sign_2"].eq(-1)
        & bars["bar_close"].gt(bars["body_mid_2"])
    )
    bars["is_evening_star"] = (
        bars["price_color_sign"].eq(-1)
        & bars["is_doji_1"]
        & bars["price_color_sign_2"].eq(1)
        & bars["bar_close"].lt(bars["body_mid_2"])
    )
    bars["star_direction_sign"] = np.select(
        [bars["is_morning_star"], bars["is_evening_star"]],
        [1, -1],
        default=0,
    ).astype(int)

    bars["is_tweezer_bottom"] = bars["price_color_sign"].eq(1) & (bars["bar_low"] - bars["low_1"]).abs().le(TICK_SIZE)
    bars["is_tweezer_top"] = bars["price_color_sign"].eq(-1) & (bars["bar_high"] - bars["high_1"]).abs().le(TICK_SIZE)
    bars["is_piercing_line"] = (
        bars["price_color_sign"].eq(1)
        & bars["price_color_sign_1"].eq(-1)
        & bars["bar_open"].lt(bars["close_1"])
        & bars["bar_close"].gt(bars["body_mid_1"])
    )

    bars["hammer_after_red_run_direction_sign"] = np.where(
        bars["is_hammer"]
        & bars["price_color_sign_1"].eq(-1)
        & bars["prior_color_run_length"].ge(2),
        1,
        0,
    ).astype(int)
    bars["shooting_star_after_green_run_direction_sign"] = np.where(
        bars["is_shooting_star"]
        & bars["price_color_sign_1"].eq(1)
        & bars["prior_color_run_length"].ge(2),
        -1,
        0,
    ).astype(int)

    bars["engulf_after_doji_direction_sign"] = np.where(
        bars["is_doji_1"] & bars["engulf_direction_sign"].ne(0),
        bars["engulf_direction_sign"],
        0,
    ).astype(int)
    bars["doji_after_engulf_direction_sign"] = np.where(
        bars["is_doji"] & bars["engulf_direction_sign_1"].ne(0),
        bars["engulf_direction_sign_1"],
        0,
    ).astype(int)

    prior_two_high = np.maximum(bars["high_1"], bars["high_2"])
    prior_two_low = np.minimum(bars["low_1"], bars["low_2"])
    bull_double_doji_breakout = (
        bars["price_color_sign"].eq(1)
        & bars["is_doji_1"]
        & bars["is_doji_2"]
        & bars["rolling_20_avg_range"].gt(0)
        & bars["bar_range"].gt(1.5 * bars["rolling_20_avg_range"])
        & bars["bar_close"].gt(prior_two_high)
    )
    bear_double_doji_breakout = (
        bars["price_color_sign"].eq(-1)
        & bars["is_doji_1"]
        & bars["is_doji_2"]
        & bars["rolling_20_avg_range"].gt(0)
        & bars["bar_range"].gt(1.5 * bars["rolling_20_avg_range"])
        & bars["bar_close"].lt(prior_two_low)
    )
    bars["double_doji_breakout_direction_sign"] = np.select(
        [bull_double_doji_breakout, bear_double_doji_breakout],
        [1, -1],
        default=0,
    ).astype(int)

    bars["star_with_volume_direction_sign"] = np.where(
        bars["star_direction_sign"].ne(0) & bars["prior_bar_is_volume_spike_2x"],
        bars["star_direction_sign"],
        0,
    ).astype(int)
    bars["hammer_volume_direction_sign"] = np.where(
        bars["is_hammer"] & bars["is_volume_spike_2x"],
        1,
        0,
    ).astype(int)
    bars["engulf_volume_direction_sign"] = np.where(
        bars["engulf_direction_sign"].ne(0) & bars["bar_volume"].gt(bars["volume_1"]),
        bars["engulf_direction_sign"],
        0,
    ).astype(int)
    return bars


def add_time_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] * 60 + out["minute"]) - RTH_START_MINUTE
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(FIRST_HOUR_MINUTES)
    out["is_first_hour"] = out["is_first_hour"].fillna(False).astype(bool)
    return out


def normalize_direction(direction: int | pd.Series, df: pd.DataFrame) -> pd.Series:
    if isinstance(direction, pd.Series):
        series = direction.reindex(df.index)
    else:
        series = pd.Series(direction, index=df.index)
    series = pd.to_numeric(series, errors="coerce").fillna(0.0)
    return np.sign(series).astype(int)


def anchor_pos_60m(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    rng_60m = df["range_60m"].replace(0, np.nan)
    anchor = np.where(direction_sign > 0, df["bar_low"], np.where(direction_sign < 0, df["bar_high"], np.nan))
    return pd.Series((anchor - df["low_60m"]) / rng_60m, index=df.index)


def is_60m_extreme_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    pos_60m = anchor_pos_60m(df, direction_sign)
    return ((direction_sign > 0) & pos_60m.le(0.20)) | ((direction_sign < 0) & pos_60m.ge(0.80))


def is_15m_trend_aligned_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    return direction_sign.ne(0) & direction_sign.eq(df["trend_sign_15m"])


def has_core_60m_15m_gate_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    return is_60m_extreme_for(df, direction) & is_15m_trend_aligned_for(df, direction)


def passes_not_all_killers_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    pos_60m = anchor_pos_60m(df, direction_sign)
    not_middle_60m = ~pos_60m.between(0.40, 0.60, inclusive="both")
    return direction_sign.ne(0) & not_middle_60m & (~df["is_volume_spike_3x"])


def build_trade_sample(source_df: pd.DataFrame, direction: int | pd.Series) -> pd.DataFrame:
    sample = source_df.copy()
    sample["trade_direction_sign"] = normalize_direction(direction, sample)
    sample = sample.loc[sample["trade_direction_sign"].ne(0)].copy()

    sample["pos_in_60m"] = anchor_pos_60m(sample, sample["trade_direction_sign"])
    sample["is_60m_extreme"] = is_60m_extreme_for(sample, sample["trade_direction_sign"])
    sample["is_15m_trend_aligned"] = is_15m_trend_aligned_for(sample, sample["trade_direction_sign"])
    sample["is_killer_1"] = sample["pos_in_60m"].between(0.40, 0.60, inclusive="both")
    sample["is_killer_2"] = sample["is_volume_spike_3x"]
    sample["passes_not_all_killers"] = (~sample["is_killer_1"]) & (~sample["is_killer_2"])

    for window in FORWARD_WINDOWS:
        sample[f"ret_{window}b_ticks"] = sample["trade_direction_sign"] * sample[f"move_{window}b_ticks"]
    return sample.reset_index(drop=True)


def summarize_filter(code: str, label: str, sample: pd.DataFrame) -> dict[str, object]:
    required_cols = [f"ret_{window}b_ticks" for window in FORWARD_WINDOWS]
    clean = sample.dropna(subset=required_cols).copy()
    n = int(len(clean))
    win_rates: dict[int, float] = {}

    for window in FORWARD_WINDOWS:
        returns = clean[f"ret_{window}b_ticks"]
        win_rates[window] = float((returns > 0).mean()) if n else np.nan

    returns_5b = clean["ret_5b_ticks"]
    wins_5b = int((returns_5b > 0).sum())
    ci_low, ci_high, win_rate_5b = wilson_ci(n, wins_5b)

    return {
        "code": code,
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


def build_filter_specs() -> list[FilterSpec]:
    return [
        (
            "01",
            "3 red bars -> green bar + 60m + 15m",
            lambda df: df["three_red_then_green_direction_sign"].eq(1) & has_core_60m_15m_gate_for(df, 1),
            lambda df: 1,
        ),
        (
            "02",
            "3 green bars -> red bar + 60m + 15m",
            lambda df: df["three_green_then_red_direction_sign"].eq(-1) & has_core_60m_15m_gate_for(df, -1),
            lambda df: -1,
        ),
        (
            "03",
            "4+ same-color bars -> opposite color + 60m + 15m",
            lambda df: df["extended_run_reversal_direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["extended_run_reversal_direction_sign"]),
            lambda df: df["extended_run_reversal_direction_sign"],
        ),
        (
            "04",
            "Alternating colors last 3 bars + 60m + 15m",
            lambda df: df["alternating_direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["alternating_direction_sign"]),
            lambda df: df["alternating_direction_sign"],
        ),
        (
            "05",
            "2 red bars with increasing range -> green bar + 60m + 15m",
            lambda df: df["selling_climax_direction_sign"].eq(1) & has_core_60m_15m_gate_for(df, 1),
            lambda df: 1,
        ),
        (
            "06",
            "Morning star + 60m + 15m",
            lambda df: df["is_morning_star"] & has_core_60m_15m_gate_for(df, 1),
            lambda df: 1,
        ),
        (
            "07",
            "Evening star + 60m + 15m",
            lambda df: df["is_evening_star"] & has_core_60m_15m_gate_for(df, -1),
            lambda df: -1,
        ),
        (
            "08",
            "Tweezer bottom + 60m + 15m",
            lambda df: df["is_tweezer_bottom"] & has_core_60m_15m_gate_for(df, 1),
            lambda df: 1,
        ),
        (
            "09",
            "Tweezer top + 60m + 15m",
            lambda df: df["is_tweezer_top"] & has_core_60m_15m_gate_for(df, -1),
            lambda df: -1,
        ),
        (
            "10",
            "Piercing line + 60m + 15m",
            lambda df: df["is_piercing_line"] & has_core_60m_15m_gate_for(df, 1),
            lambda df: 1,
        ),
        (
            "11",
            "Hammer after 2+ red bars + 60m + 15m",
            lambda df: df["hammer_after_red_run_direction_sign"].eq(1) & has_core_60m_15m_gate_for(df, 1),
            lambda df: 1,
        ),
        (
            "12",
            "Shooting star after 2+ green bars + 60m + 15m",
            lambda df: df["shooting_star_after_green_run_direction_sign"].eq(-1) & has_core_60m_15m_gate_for(df, -1),
            lambda df: -1,
        ),
        (
            "13",
            "Engulfing after doji + 60m + 15m",
            lambda df: df["engulf_after_doji_direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["engulf_after_doji_direction_sign"]),
            lambda df: df["engulf_after_doji_direction_sign"],
        ),
        (
            "14",
            "Doji after engulfing + 60m + 15m",
            lambda df: df["doji_after_engulf_direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["doji_after_engulf_direction_sign"]),
            lambda df: df["doji_after_engulf_direction_sign"],
        ),
        (
            "15",
            "Double doji -> breakout bar + 60m + 15m",
            lambda df: df["double_doji_breakout_direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["double_doji_breakout_direction_sign"]),
            lambda df: df["double_doji_breakout_direction_sign"],
        ),
        (
            "16",
            "Morning/evening star + volume spike on star bar + 60m + 15m",
            lambda df: df["star_with_volume_direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["star_with_volume_direction_sign"]),
            lambda df: df["star_with_volume_direction_sign"],
        ),
        (
            "17",
            "Hammer with volume > 2x EMA + 60m + 15m",
            lambda df: df["hammer_volume_direction_sign"].eq(1) & has_core_60m_15m_gate_for(df, 1),
            lambda df: 1,
        ),
        (
            "18",
            "Engulfing with volume > prior bar volume + 60m + 15m",
            lambda df: df["engulf_volume_direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["engulf_volume_direction_sign"]),
            lambda df: df["engulf_volume_direction_sign"],
        ),
        (
            "19",
            "Morning/evening star + NOT killers + first_hour + 60m + 15m",
            lambda df: df["star_direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["star_direction_sign"])
            & passes_not_all_killers_for(df, df["star_direction_sign"])
            & df["is_first_hour"],
            lambda df: df["star_direction_sign"],
        ),
        (
            "20",
            "Hammer/shooting star after 2+ same-color bars + NOT killers + first_hour + 60m + 15m",
            lambda df: (
                df["hammer_after_red_run_direction_sign"].ne(0)
                | df["shooting_star_after_green_run_direction_sign"].ne(0)
            )
            & has_core_60m_15m_gate_for(
                df,
                df["hammer_after_red_run_direction_sign"] + df["shooting_star_after_green_run_direction_sign"],
            )
            & passes_not_all_killers_for(
                df,
                df["hammer_after_red_run_direction_sign"] + df["shooting_star_after_green_run_direction_sign"],
            )
            & df["is_first_hour"],
            lambda df: df["hammer_after_red_run_direction_sign"] + df["shooting_star_after_green_run_direction_sign"],
        ),
    ]


def run_filters(df: pd.DataFrame) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for code, label, predicate, direction_fn in build_filter_specs():
        mask = predicate(df).fillna(False)
        filtered = df.loc[mask].copy()
        direction = direction_fn(df)
        if isinstance(direction, pd.Series):
            direction = direction.loc[mask]
        sample = build_trade_sample(filtered, direction)
        results.append(summarize_filter(code, label, sample))

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
    headers = ["Filter", "N", "WR 5b", "WR 10b", "WR 30b", "PF 5b", "Avg Ticks 5b", "Wilson 95% CI (5b)", "Persistence"]
    data_rows: list[list[str]] = []

    for row in rows:
        data_rows.append(
            [
                f"{row['code']}. {row['label']}",
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


def render_summary_line(row: dict[str, object]) -> str:
    return (
        f"N={int(row['n']):,} | WR5={fmt_pct(float(row['wr_5b']))} | WR10={fmt_pct(float(row['wr_10b']))} | "
        f"WR30={fmt_pct(float(row['wr_30b']))} | PF5={fmt_float(float(row['pf_5b']))} | "
        f"Avg5={fmt_float(float(row['avg_ticks_5b']))}t | CI5={fmt_ci(float(row['ci_low']), float(row['ci_high']))} | "
        f"Persistence={row['persistence']}"
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events = load_events()
    bars_1m = load_ohlcv()
    observations = build_observations(events)
    context = build_timeframe_context(bars_1m)
    observations = attach_context(observations, context)
    observations = compute_bar_features(observations)
    observations = compute_combo_features(observations)
    observations = add_time_flags(observations)

    all_color_bars = build_trade_sample(observations, observations["price_color_sign"])
    core_color_bars = all_color_bars.loc[
        all_color_bars["is_60m_extreme"] & all_color_bars["is_15m_trend_aligned"]
    ].copy()
    core_not_killers_first_hour = core_color_bars.loc[
        core_color_bars["passes_not_all_killers"] & core_color_bars["is_first_hour"]
    ].copy()

    baseline_all = summarize_filter("00", "All non-doji price-color signal bars", all_color_bars)
    baseline_core = summarize_filter("00A", "All non-doji price-color bars + 60m + 15m", core_color_bars)
    baseline_core_first = summarize_filter(
        "00B",
        "All non-doji price-color bars + NOT killers + first_hour + 60m + 15m",
        core_not_killers_first_hour,
    )
    results = run_filters(observations)

    lines = [
        "DEEP6 round 23 candlestick combo analysis",
        "==========================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index.",
        "Pattern direction drives the 60m extreme gate, 15m trend gate, killer exclusion, and signed forward returns.",
        "Bar color = green when close > open, red when close < open. Doji = body / range < 0.10.",
        "Morning/evening star, hammer, shooting star, and engulfing definitions follow the round3 candlestick workflow.",
        "60m + 15m = trade-direction 60m extreme (bull anchor in bottom 20%, bear anchor in top 20%) plus 15m open-close alignment.",
        "NOT killers = NOT killer_1 (trade anchor in middle 40%-60% of 60m range) AND NOT killer_2 (bar_volume > 3x prior 20-bar EMA).",
        "first_hour = 09:30-10:29 ET.",
        "Pattern 15 breakout implementation: current close must break outside the prior two-doji range and current range must exceed 1.5x the prior 20-bar average range.",
        "Pattern 16 volume spike implementation: the star/doji bar (bar[-1]) volume must be > 2x its own prior 20-bar EMA.",
        "PF, Avg Ticks, and Wilson CI are reported on the 5-bar horizon; WR columns show 5b / 10b / 30b as requested.",
        "Rows are sorted by 30b WR, then 10b WR, then 5b WR, then N.",
        "",
        f"Raw event rows loaded:                             {len(events):,}",
        f"Grouped observations:                              {len(observations):,}",
        f"15m bars built:                                    {len(context[15]):,}",
        f"60m bars built:                                    {len(context[60]):,}",
        f"Non-doji price-color observations:                 {len(all_color_bars):,}",
        f"Core 60m + 15m observations:                       {len(core_color_bars):,}",
        f"Core 60m + 15m + NOT killers + first_hour sample: {len(core_not_killers_first_hour):,}",
        "",
        "Baselines",
        "---------",
        f"All non-doji price-color bars:                       {render_summary_line(baseline_all)}",
        f"60m + 15m core gate:                                 {render_summary_line(baseline_core)}",
        f"60m + 15m + NOT killers + first_hour core baseline: {render_summary_line(baseline_core_first)}",
        "",
        "20 requested candlestick-combo filters sorted by 30b WR",
        "-----------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
