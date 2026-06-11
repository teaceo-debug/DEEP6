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
OUT_PATH = OUT_DIR / "round25_momentum_exhaustion_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
FIRST_HOUR_MINUTES = 60
MOVE_FROM_OPEN_100 = 100
MOVE_FROM_OPEN_200 = 200
MOVE_FROM_OPEN_30 = 30
FAST_MOVE_10B = 50
STALL_MOVE_10B = 10
SESSION_LEVEL_TICKS = 10

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


def filter_rth_bars(bars_1m: pd.DataFrame) -> pd.DataFrame:
    bars = bars_1m.copy()
    minute_of_day = bars["ts_event"].dt.hour * 60 + bars["ts_event"].dt.minute
    bars = bars.loc[(minute_of_day >= RTH_START_MINUTE) & (minute_of_day < RTH_END_MINUTE)].copy()
    bars["session_date"] = bars["ts_event"].dt.strftime("%Y-%m-%d")
    bars["minutes_since_930"] = minute_of_day.loc[bars.index] - RTH_START_MINUTE
    bars["bar_index"] = bars.groupby("session_date", sort=False).cumcount().astype("int32")
    return bars.reset_index(drop=True)


def build_rth_momentum_context(rth_bars: pd.DataFrame) -> pd.DataFrame:
    bars = rth_bars.copy()
    by_session = bars.groupby("session_date", sort=False)

    bars["bar_range"] = bars["high"] - bars["low"]
    bars["body"] = (bars["close"] - bars["open"]).abs()
    bars["is_doji"] = bars["bar_range"].gt(0) & bars["body"].lt(0.10 * bars["bar_range"])

    bars["rolling_20_ema_vol"] = by_session["volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    bars["is_volume_spike_3x"] = bars["rolling_20_ema_vol"].gt(0) & bars["volume"].gt(3.0 * bars["rolling_20_ema_vol"])

    bars["session_open"] = by_session["open"].transform("first")
    bars["move_from_open_ticks"] = (bars["close"] - bars["session_open"]) / TICK_SIZE
    bars["abs_move_from_open_ticks"] = bars["move_from_open_ticks"].abs()
    bars["move_from_open_sign"] = np.sign(bars["move_from_open_ticks"].fillna(0.0)).astype(int)
    bars["reversal_from_open_sign"] = -bars["move_from_open_sign"]

    bars["running_abs_move_max"] = by_session["abs_move_from_open_ticks"].cummax()
    bars["prior_running_abs_move_max"] = by_session["running_abs_move_max"].shift(1)
    bars["is_new_session_move_extreme"] = (
        bars["prior_running_abs_move_max"].notna()
        & bars["abs_move_from_open_ticks"].gt(bars["prior_running_abs_move_max"])
    )

    bars["running_high"] = by_session["high"].cummax()
    bars["running_low"] = by_session["low"].cummin()
    bars["distance_to_session_high_ticks"] = (bars["running_high"] - bars["close"]) / TICK_SIZE
    bars["distance_to_session_low_ticks"] = (bars["close"] - bars["running_low"]) / TICK_SIZE
    bars["is_within_10_ticks_session_high"] = bars["distance_to_session_high_ticks"].le(SESSION_LEVEL_TICKS)
    bars["is_within_10_ticks_session_low"] = bars["distance_to_session_low_ticks"].le(SESSION_LEVEL_TICKS)

    bars["prior_close_10"] = by_session["close"].shift(10)
    bars["lookback_move_10b_ticks"] = ((bars["close"] - bars["prior_close_10"]).abs()) / TICK_SIZE
    bars["is_fast_move_10b"] = bars["lookback_move_10b_ticks"].gt(FAST_MOVE_10B)
    bars["is_stalled_move_10b"] = bars["lookback_move_10b_ticks"].lt(STALL_MOVE_10B)

    bars["close_5"] = by_session["close"].shift(5)
    bars["close_10"] = by_session["close"].shift(10)
    bars["move_5b_signed"] = bars["close"] - bars["close_5"]
    bars["prior_move_5b_signed"] = bars["close_5"] - bars["close_10"]
    same_5b_direction = (
        np.sign(bars["move_5b_signed"]).ne(0)
        & np.sign(bars["move_5b_signed"]).eq(np.sign(bars["prior_move_5b_signed"]))
    )
    bars["is_acceleration"] = same_5b_direction & bars["move_5b_signed"].abs().gt(bars["prior_move_5b_signed"].abs())
    bars["is_deceleration"] = same_5b_direction & bars["move_5b_signed"].abs().lt(bars["prior_move_5b_signed"].abs())

    bars["prior_9_max_range"] = by_session["bar_range"].transform(lambda s: s.shift(1).rolling(9, min_periods=9).max())
    bars["is_fastest_bar_last_10"] = bars["prior_9_max_range"].notna() & bars["bar_range"].gt(bars["prior_9_max_range"])

    bars["higher_lows_5"] = (
        bars["low"].gt(by_session["low"].shift(1))
        & by_session["low"].shift(1).gt(by_session["low"].shift(2))
        & by_session["low"].shift(2).gt(by_session["low"].shift(3))
        & by_session["low"].shift(3).gt(by_session["low"].shift(4))
    )
    bars["lower_highs_5"] = (
        bars["high"].lt(by_session["high"].shift(1))
        & by_session["high"].shift(1).lt(by_session["high"].shift(2))
        & by_session["high"].shift(2).lt(by_session["high"].shift(3))
        & by_session["high"].shift(3).lt(by_session["high"].shift(4))
    )
    bars["is_higher_high_higher_low"] = bars["high"].gt(by_session["high"].shift(1)) & bars["low"].gt(by_session["low"].shift(1))

    bars["prior_5_bar_high"] = by_session["high"].transform(lambda s: s.shift(1).rolling(5, min_periods=5).max())
    bars["prior_5_bar_low"] = by_session["low"].transform(lambda s: s.shift(1).rolling(5, min_periods=5).min())
    bars["broke_prior_5_bar_high_then_reversed"] = (
        bars["prior_5_bar_high"].notna()
        & bars["high"].gt(bars["prior_5_bar_high"])
        & bars["close"].lt(bars["prior_5_bar_high"])
    )
    bars["broke_prior_5_bar_low_then_reversed"] = (
        bars["prior_5_bar_low"].notna()
        & bars["low"].lt(bars["prior_5_bar_low"])
        & bars["close"].gt(bars["prior_5_bar_low"])
    )

    bars["session_pv"] = bars["close"] * bars["volume"]
    bars["cum_session_pv"] = by_session["session_pv"].cumsum()
    bars["cum_session_volume"] = by_session["volume"].cumsum()
    bars["session_vwap"] = np.where(
        bars["cum_session_volume"] > 0,
        bars["cum_session_pv"] / bars["cum_session_volume"],
        np.nan,
    )
    bars["distance_to_session_vwap_ticks"] = (bars["close"] - bars["session_vwap"]).abs() / TICK_SIZE
    bars["is_near_session_vwap"] = bars["distance_to_session_vwap_ticks"].le(SESSION_LEVEL_TICKS)
    bars["prev_close"] = by_session["close"].shift(1)
    bars["prev_session_vwap"] = by_session["session_vwap"].shift(1)
    bars["crossed_above_session_vwap_from_below"] = (
        bars["prev_close"].notna()
        & bars["prev_session_vwap"].notna()
        & bars["prev_close"].lt(bars["prev_session_vwap"])
        & bars["close"].gt(bars["session_vwap"])
    )

    bars["peak_move_up_ticks"] = (bars["running_high"] - bars["session_open"]) / TICK_SIZE
    bars["pullback_from_peak_ticks"] = (bars["running_high"] - bars["close"]) / TICK_SIZE
    bars["peak_move_down_ticks"] = (bars["session_open"] - bars["running_low"]) / TICK_SIZE
    bars["bounce_from_trough_ticks"] = (bars["close"] - bars["running_low"]) / TICK_SIZE
    bars["is_retraced_gt_50pct"] = (
        (
            bars["move_from_open_sign"].gt(0)
            & bars["peak_move_up_ticks"].gt(0)
            & bars["pullback_from_peak_ticks"].ge(0.50 * bars["peak_move_up_ticks"])
        )
        | (
            bars["move_from_open_sign"].lt(0)
            & bars["peak_move_down_ticks"].gt(0)
            & bars["bounce_from_trough_ticks"].ge(0.50 * bars["peak_move_down_ticks"])
        )
    )

    bars["is_first_hour"] = bars["minutes_since_930"].ge(0) & bars["minutes_since_930"].lt(FIRST_HOUR_MINUTES)

    bool_cols = [
        "is_doji",
        "is_volume_spike_3x",
        "is_new_session_move_extreme",
        "is_within_10_ticks_session_high",
        "is_within_10_ticks_session_low",
        "is_fast_move_10b",
        "is_stalled_move_10b",
        "is_acceleration",
        "is_deceleration",
        "is_fastest_bar_last_10",
        "higher_lows_5",
        "lower_highs_5",
        "is_higher_high_higher_low",
        "broke_prior_5_bar_high_then_reversed",
        "broke_prior_5_bar_low_then_reversed",
        "is_near_session_vwap",
        "crossed_above_session_vwap_from_below",
        "is_retraced_gt_50pct",
        "is_first_hour",
    ]
    for col in bool_cols:
        bars[col] = bars[col].fillna(False).astype(bool)

    return bars[
        [
            "ts_event",
            "session_date",
            "bar_index",
            "minutes_since_930",
            "session_open",
            "move_from_open_ticks",
            "abs_move_from_open_ticks",
            "move_from_open_sign",
            "reversal_from_open_sign",
            "is_new_session_move_extreme",
            "is_retraced_gt_50pct",
            "lookback_move_10b_ticks",
            "is_fast_move_10b",
            "is_stalled_move_10b",
            "is_acceleration",
            "is_deceleration",
            "is_fastest_bar_last_10",
            "higher_lows_5",
            "lower_highs_5",
            "is_higher_high_higher_low",
            "broke_prior_5_bar_high_then_reversed",
            "broke_prior_5_bar_low_then_reversed",
            "distance_to_session_high_ticks",
            "distance_to_session_low_ticks",
            "is_within_10_ticks_session_high",
            "is_within_10_ticks_session_low",
            "session_vwap",
            "is_near_session_vwap",
            "crossed_above_session_vwap_from_below",
            "is_doji",
            "is_volume_spike_3x",
            "is_first_hour",
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
        "is_new_session_move_extreme",
        "is_retraced_gt_50pct",
        "is_fast_move_10b",
        "is_stalled_move_10b",
        "is_acceleration",
        "is_deceleration",
        "is_fastest_bar_last_10",
        "higher_lows_5",
        "lower_highs_5",
        "is_higher_high_higher_low",
        "broke_prior_5_bar_high_then_reversed",
        "broke_prior_5_bar_low_then_reversed",
        "is_within_10_ticks_session_high",
        "is_within_10_ticks_session_low",
        "is_near_session_vwap",
        "crossed_above_session_vwap_from_below",
        "is_doji",
        "is_volume_spike_3x",
        "is_first_hour",
    ]
    for col in bool_cols:
        if col in out.columns:
            out[col] = out[col].fillna(False).astype(bool)

    int_cols = ["move_from_open_sign", "reversal_from_open_sign", "minutes_since_930"]
    for col in int_cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    out["move_from_open_sign"] = out["move_from_open_sign"].fillna(0).astype(int)
    out["reversal_from_open_sign"] = out["reversal_from_open_sign"].fillna(0).astype(int)
    out["minutes_since_930"] = out["minutes_since_930"].fillna(-1).astype(int)
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


def build_trade_sample(source_df: pd.DataFrame, trade_sign: int | pd.Series | np.ndarray) -> pd.DataFrame:
    sample = source_df.copy()
    sample["trade_sign"] = coerce_trade_sign(trade_sign, sample.index)
    sample = sample[sample["trade_sign"].ne(0)].copy()

    sample["pos_in_60m_anchor"] = anchor_pos_in_range(sample, sample["trade_sign"], 60)
    sample["pos_in_15m_anchor"] = anchor_pos_in_range(sample, sample["trade_sign"], 15)
    sample["is_60m_extreme"] = (
        ((sample["trade_sign"] > 0) & sample["pos_in_60m_anchor"].le(0.20))
        | ((sample["trade_sign"] < 0) & sample["pos_in_60m_anchor"].ge(0.80))
    )
    sample["is_15m_trend_aligned"] = sample["trade_sign"].eq(sample["trend_sign_15m"])
    sample["has_core_60m_15m_gate"] = sample["is_60m_extreme"] & sample["is_15m_trend_aligned"]

    for window in FORWARD_WINDOWS:
        sample[f"ret_{window}b_ticks"] = sample["trade_sign"] * sample[f"move_{window}b_ticks"]

    sample["is_killer_1"] = sample["pos_in_60m_anchor"].between(0.40, 0.60, inclusive="both")
    sample["is_killer_2"] = sample["is_volume_spike_3x"]
    sample["passes_not_all_killers"] = (~sample["is_killer_1"]) & (~sample["is_killer_2"])
    sample["signal_matches_trade_sign"] = sample["direction_sign"].eq(sample["trade_sign"])
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
            "Move from open > 100 ticks + reversal signal + 60m + 15m",
            "reversal",
            lambda df: df["signal_matches_trade_sign"]
            & df["abs_move_from_open_ticks"].gt(MOVE_FROM_OPEN_100)
            & df["has_core_60m_15m_gate"],
        ),
        (
            "02",
            "A",
            "Move from open > 200 ticks + reversal signal + 60m + 15m",
            "reversal",
            lambda df: df["signal_matches_trade_sign"]
            & df["abs_move_from_open_ticks"].gt(MOVE_FROM_OPEN_200)
            & df["has_core_60m_15m_gate"],
        ),
        (
            "03",
            "A",
            "Move from open < 30 ticks + reversal signal + 60m + 15m",
            "reversal",
            lambda df: df["signal_matches_trade_sign"]
            & df["abs_move_from_open_ticks"].lt(MOVE_FROM_OPEN_30)
            & df["has_core_60m_15m_gate"],
        ),
        (
            "04",
            "A",
            "Largest move of session so far + reversal signal + 60m + 15m",
            "reversal",
            lambda df: df["signal_matches_trade_sign"]
            & df["is_new_session_move_extreme"]
            & df["has_core_60m_15m_gate"],
        ),
        (
            "05",
            "A",
            "Retraced > 50% of prior move + reversal signal + 60m + 15m",
            "reversal",
            lambda df: df["signal_matches_trade_sign"]
            & df["is_retraced_gt_50pct"]
            & df["has_core_60m_15m_gate"],
        ),
        (
            "06",
            "B",
            "10-bar move > 50 ticks + 60m + 15m",
            "bar",
            lambda df: df["is_fast_move_10b"] & df["has_core_60m_15m_gate"],
        ),
        (
            "07",
            "B",
            "10-bar move < 10 ticks + 60m + 15m",
            "bar",
            lambda df: df["is_stalled_move_10b"] & df["has_core_60m_15m_gate"],
        ),
        (
            "08",
            "B",
            "5-bar acceleration + 60m + 15m",
            "bar",
            lambda df: df["is_acceleration"] & df["has_core_60m_15m_gate"],
        ),
        (
            "09",
            "B",
            "5-bar deceleration + 60m + 15m",
            "bar",
            lambda df: df["is_deceleration"] & df["has_core_60m_15m_gate"],
        ),
        (
            "10",
            "B",
            "Current bar is fastest range in last 10 + 60m + 15m",
            "bar",
            lambda df: df["is_fastest_bar_last_10"] & df["has_core_60m_15m_gate"],
        ),
        (
            "11",
            "C",
            "5 higher lows + bearish signal + 60m + 15m",
            "bear",
            lambda df: df["signal_matches_trade_sign"] & df["higher_lows_5"] & df["has_core_60m_15m_gate"],
        ),
        (
            "12",
            "C",
            "5 lower highs + bullish signal + 60m + 15m",
            "bull",
            lambda df: df["signal_matches_trade_sign"] & df["lower_highs_5"] & df["has_core_60m_15m_gate"],
        ),
        (
            "13",
            "C",
            "Higher high + higher low then bearish reversal signal + 60m + 15m",
            "bear",
            lambda df: df["signal_matches_trade_sign"]
            & df["is_higher_high_higher_low"]
            & df["has_core_60m_15m_gate"],
        ),
        (
            "14",
            "C",
            "Broke prior 5-bar high then reversed bearish + 60m + 15m",
            "bear",
            lambda df: df["signal_matches_trade_sign"]
            & df["broke_prior_5_bar_high_then_reversed"]
            & df["has_core_60m_15m_gate"],
        ),
        (
            "15",
            "C",
            "Broke prior 5-bar low then reversed bullish + 60m + 15m",
            "bull",
            lambda df: df["signal_matches_trade_sign"]
            & df["broke_prior_5_bar_low_then_reversed"]
            & df["has_core_60m_15m_gate"],
        ),
        (
            "16",
            "D",
            "Within 10 ticks of session high + bearish signal + 60m + 15m",
            "bear",
            lambda df: df["signal_matches_trade_sign"]
            & df["is_within_10_ticks_session_high"]
            & df["has_core_60m_15m_gate"],
        ),
        (
            "17",
            "D",
            "Within 10 ticks of session low + bullish signal + 60m + 15m",
            "bull",
            lambda df: df["signal_matches_trade_sign"]
            & df["is_within_10_ticks_session_low"]
            & df["has_core_60m_15m_gate"],
        ),
        (
            "18",
            "D",
            "Near session VWAP (within 10 ticks) + 60m + 15m",
            "bar",
            lambda df: df["is_near_session_vwap"] & df["has_core_60m_15m_gate"],
        ),
        (
            "19",
            "D",
            "Crossed above session VWAP from below + bullish signal + 60m + 15m",
            "bull",
            lambda df: df["signal_matches_trade_sign"]
            & df["crossed_above_session_vwap_from_below"]
            & df["has_core_60m_15m_gate"],
        ),
        (
            "20",
            "E",
            "Overextended > 100 + deceleration + doji + 60m + 15m + NOT killers + first_hour",
            "reversal",
            lambda df: df["signal_matches_trade_sign"]
            & df["abs_move_from_open_ticks"].gt(MOVE_FROM_OPEN_100)
            & df["is_deceleration"]
            & df["is_doji"]
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
    grouped_signal_bars = len(observations)
    timeframe_context = build_timeframe_context(bars_1m)
    observations = attach_timeframe_context(observations, timeframe_context)

    rth_bars = filter_rth_bars(bars_1m)
    rth_context = build_rth_momentum_context(rth_bars)
    observations = merge_rth_context(observations, rth_context)
    observations = observations.loc[observations["session_open"].notna()].copy().reset_index(drop=True)

    bar_sample = build_trade_sample(observations, observations["direction_sign"])
    reversal_sample = build_trade_sample(observations, observations["reversal_from_open_sign"])
    bear_sample = build_trade_sample(observations, -1)
    bull_sample = build_trade_sample(observations, 1)

    samples = {
        "bar": bar_sample,
        "reversal": reversal_sample,
        "bear": bear_sample,
        "bull": bull_sample,
    }
    results = run_filters(samples)

    base_bar = summarize_filter("00A", "BASE", "All non-zero-delta signal bars (bar_delta direction)", bar_sample)
    base_bar_core = summarize_filter(
        "00B",
        "BASE",
        "Bar-direction sample + 60m + 15m",
        bar_sample.loc[bar_sample["has_core_60m_15m_gate"]].copy(),
    )
    base_reversal = summarize_filter(
        "00C",
        "BASE",
        "Move-from-open reversal sign + matching signal",
        reversal_sample.loc[reversal_sample["signal_matches_trade_sign"]].copy(),
    )
    base_reversal_core = summarize_filter(
        "00D",
        "BASE",
        "Move-from-open reversal sign + matching signal + 60m + 15m",
        reversal_sample.loc[
            reversal_sample["signal_matches_trade_sign"] & reversal_sample["has_core_60m_15m_gate"]
        ].copy(),
    )

    lines = [
        "DEEP6 round25 momentum exhaustion",
        "================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index, then merged to 1m RTH context at bar_ts.",
        "Core gate: 60m_extreme = trade-direction anchor in bottom 20% / top 20% of the active 60m bar; 15m gate = trade_sign aligned with the active 15m trend.",
        "Bar-direction filters use sign(bar_delta). Reversal-from-open filters use the opposite sign of close vs session open and require the signal bar to match that reversal sign.",
        "Explicit bullish/bearish filters use fixed trade_sign (+1 / -1) and require the signal bar to match that direction.",
        "Move from open = (bar_close - session_open) / tick. Largest move so far = new high in absolute close-vs-open distance. Retracement > 50% compares current close to the running session high/low relative to the session open.",
        "10-bar / 5-bar momentum features, higher-lows / lower-highs, false breakouts, running session high/low, and running VWAP all come from 1m RTH bars.",
        "Session VWAP = cumulative sum(close * volume) / cumulative sum(volume) per RTH session.",
        "KILLER_1 = trade-direction anchor in middle 40-60% of the active 60m range. KILLER_2 = bar_volume > 3x prior 20-bar EMA volume.",
        "N uses rows with complete 5b/10b/30b forward closes so every WR window and persistence flag uses the same sample.",
        "Persistence: GROWING if WR_30b > WR_5b; STABLE if WR_30b is within 3 percentage points of WR_5b without growth; DECAYING otherwise.",
        "",
        f"Raw event rows loaded:                        {len(events):,}",
        f"Grouped signal bars:                          {grouped_signal_bars:,}",
        f"Signal bars with merged RTH context:          {len(observations):,}",
        f"15m bars built:                               {len(timeframe_context[15]):,}",
        f"60m bars built:                               {len(timeframe_context[60]):,}",
        f"Move-from-open > 100 ticks bars:              {int(observations['abs_move_from_open_ticks'].gt(MOVE_FROM_OPEN_100).sum()):,}",
        f"Move-from-open > 200 ticks bars:              {int(observations['abs_move_from_open_ticks'].gt(MOVE_FROM_OPEN_200).sum()):,}",
        f"Move-from-open < 30 ticks bars:               {int(observations['abs_move_from_open_ticks'].lt(MOVE_FROM_OPEN_30).sum()):,}",
        f"New session move extremes:                    {int(observations['is_new_session_move_extreme'].sum()):,}",
        f">50% retracement bars:                        {int(observations['is_retraced_gt_50pct'].sum()):,}",
        f"Fast 10-bar move bars:                        {int(observations['is_fast_move_10b'].sum()):,}",
        f"Stalled 10-bar move bars:                     {int(observations['is_stalled_move_10b'].sum()):,}",
        f"5-bar acceleration bars:                      {int(observations['is_acceleration'].sum()):,}",
        f"5-bar deceleration bars:                      {int(observations['is_deceleration'].sum()):,}",
        f"Fastest-bar-of-last-10 hits:                  {int(observations['is_fastest_bar_last_10'].sum()):,}",
        f"Higher-lows x5 hits:                          {int(observations['higher_lows_5'].sum()):,}",
        f"Lower-highs x5 hits:                          {int(observations['lower_highs_5'].sum()):,}",
        f"Higher-high + higher-low hits:                {int(observations['is_higher_high_higher_low'].sum()):,}",
        f"False breaks above prior 5-bar high:          {int(observations['broke_prior_5_bar_high_then_reversed'].sum()):,}",
        f"False breaks below prior 5-bar low:           {int(observations['broke_prior_5_bar_low_then_reversed'].sum()):,}",
        f"Within 10 ticks of running session high:      {int(observations['is_within_10_ticks_session_high'].sum()):,}",
        f"Within 10 ticks of running session low:       {int(observations['is_within_10_ticks_session_low'].sum()):,}",
        f"Near running session VWAP:                    {int(observations['is_near_session_vwap'].sum()):,}",
        f"Crossed above session VWAP from below:        {int(observations['crossed_above_session_vwap_from_below'].sum()):,}",
        f"Doji bars:                                    {int(observations['is_doji'].sum()):,}",
        f"KILLER_1 hits (reversal sample):              {int(reversal_sample['is_killer_1'].sum()):,}",
        f"KILLER_2 hits (reversal sample):              {int(reversal_sample['is_killer_2'].sum()):,}",
        "",
        "Baselines",
        "---------",
        f"Bar-direction all bars:                 {render_summary_line(base_bar)}",
        f"Bar-direction 60m + 15m:                {render_summary_line(base_bar_core)}",
        f"Reversal sign + matching signal:        {render_summary_line(base_reversal)}",
        f"Reversal sign + matching signal + core: {render_summary_line(base_reversal_core)}",
        "",
        "20 momentum exhaustion filters ranked by 30b win rate",
        "---------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
