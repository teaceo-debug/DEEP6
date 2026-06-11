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
OUT_PATH = OUT_DIR / "round7_signal_sequences_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
SIGNAL_IDS = ("TRAP_04", "TRAP_05", "EXH_03", "DELT_04")
SEQUENCE_DIRECTIONS = (-1, 1)


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
        "score_final",
        "score_tier",
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
        "score_final",
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
    df["event_direction_sign"] = direction_to_sign(df["direction"])
    return df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)


def build_bars(events: pd.DataFrame) -> pd.DataFrame:
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
            raw_signal_count=("signal_id", "nunique"),
            raw_category_count=("category", "nunique"),
        )
        .sort_values("global_index", kind="stable")
        .reset_index(drop=True)
    )
    bars["direction_sign"] = np.sign(bars["bar_delta"].fillna(0.0)).astype(int)
    bars["move_5b_ticks"] = (bars["fwd_close_5b"] - bars["bar_close"]) / TICK_SIZE
    bars["ret_5b_ticks"] = np.where(
        bars["direction_sign"].ne(0),
        bars["direction_sign"] * bars["move_5b_ticks"],
        np.nan,
    )
    return bars


def attach_directional_event_features(bars: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    working = events.loc[events["event_direction_sign"].ne(0)].copy()
    working["is_absorption"] = working["category"].eq("absorption")
    working["is_TRAP_04"] = working["signal_id"].eq("TRAP_04")
    working["is_TRAP_05"] = working["signal_id"].eq("TRAP_05")
    working["is_EXH_03"] = working["signal_id"].eq("EXH_03")
    working["is_DELT_04"] = working["signal_id"].eq("DELT_04")
    working["is_TYPE_B"] = working["score_tier"].eq("TYPE_B")
    working["is_score_ge_60"] = working["score_final"].ge(60)

    grouped = (
        working.groupby(["global_index", "event_direction_sign"], as_index=False, sort=False)
        .agg(
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
            max_score_final=("score_final", "max"),
            has_absorption=("is_absorption", "max"),
            has_TRAP_04=("is_TRAP_04", "max"),
            has_TRAP_05=("is_TRAP_05", "max"),
            has_EXH_03=("is_EXH_03", "max"),
            has_DELT_04=("is_DELT_04", "max"),
            has_TYPE_B=("is_TYPE_B", "max"),
            has_score_ge_60=("is_score_ge_60", "max"),
        )
        .sort_values(["global_index", "event_direction_sign"], kind="stable")
        .reset_index(drop=True)
    )

    numeric_cols = ["signal_count", "category_count", "max_score_final"]
    bool_cols = [
        "has_absorption",
        "has_TRAP_04",
        "has_TRAP_05",
        "has_EXH_03",
        "has_DELT_04",
        "has_TYPE_B",
        "has_score_ge_60",
    ]

    out = bars.copy()
    for direction in SEQUENCE_DIRECTIONS:
        suffix = direction_suffix(direction)
        subset = grouped.loc[grouped["event_direction_sign"].eq(direction)].drop(columns="event_direction_sign")
        renamed = subset.rename(columns={col: f"{col}_{suffix}" for col in subset.columns if col != "global_index"})
        out = out.merge(renamed, on="global_index", how="left", validate="one_to_one")

        for col in numeric_cols:
            out[f"{col}_{suffix}"] = pd.to_numeric(out[f"{col}_{suffix}"], errors="coerce").fillna(0.0)
        for col in bool_cols:
            out[f"{col}_{suffix}"] = out[f"{col}_{suffix}"].fillna(False).astype(bool)

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


def attach_context(bars: pd.DataFrame, context: dict[int, pd.DataFrame]) -> pd.DataFrame:
    df = bars.copy()
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


def compute_bar_features(bars: pd.DataFrame) -> pd.DataFrame:
    out = bars.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["body_high"] = np.maximum(out["bar_open"], out["bar_close"])
    out["body_low"] = np.minimum(out["bar_open"], out["bar_close"])
    out["upper_wick"] = out["bar_high"] - out["body_high"]
    out["lower_wick"] = out["body_low"] - out["bar_low"]
    out["abs_delta"] = out["bar_delta"].abs()

    out["prior_bar_delta"] = by_session["bar_delta"].shift(1)
    out["prior_direction_sign_1"] = by_session["direction_sign"].shift(1)
    out["prior_direction_sign_2"] = by_session["direction_sign"].shift(2)
    out["prior_abs_delta_1"] = by_session["abs_delta"].shift(1)
    out["prior_abs_delta_2"] = by_session["abs_delta"].shift(2)
    out["prior_high"] = by_session["bar_high"].shift(1)
    out["prior_bar_range"] = by_session["bar_range"].shift(1)
    out["prior_body_high"] = by_session["body_high"].shift(1)
    out["prior_body_low"] = by_session["body_low"].shift(1)

    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    out["range_q75"] = by_session["bar_range"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.75)
    )
    out["range_q25"] = by_session["bar_range"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.25)
    )

    out["is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.10 * out["bar_range"])
    out["is_narrow_range"] = out["bar_range"].lt(out["range_q25"])
    out["is_wide_range"] = out["bar_range"].gt(out["range_q75"])
    out["is_volume_spike"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(2.0 * out["rolling_20_ema_vol"])
    out["is_delta_reversal"] = (
        out["prior_bar_delta"].notna()
        & out["prior_bar_delta"].ne(0)
        & out["direction_sign"].ne(0)
        & np.sign(out["bar_delta"]).ne(np.sign(out["prior_bar_delta"]))
    )

    same_direction_run = (
        out["direction_sign"].ne(0)
        & out["direction_sign"].eq(out["prior_direction_sign_1"])
        & out["direction_sign"].eq(out["prior_direction_sign_2"])
    )
    out["run3_direction_sign"] = np.where(same_direction_run, out["direction_sign"], 0)

    out["prior_is_wide_range"] = by_session["is_wide_range"].shift(1).fillna(False).astype(bool)
    out["two_wide_range_direction_sign"] = np.where(
        out["is_wide_range"]
        & out["prior_is_wide_range"]
        & out["direction_sign"].ne(0)
        & out["direction_sign"].eq(out["prior_direction_sign_1"]),
        out["direction_sign"],
        0,
    )

    out["delta_acceleration_direction_sign"] = np.where(
        out["direction_sign"].ne(0)
        & out["direction_sign"].eq(out["prior_direction_sign_1"])
        & out["direction_sign"].eq(out["prior_direction_sign_2"])
        & out["prior_abs_delta_2"].gt(0)
        & out["prior_abs_delta_2"].lt(out["prior_abs_delta_1"])
        & out["prior_abs_delta_1"].lt(out["abs_delta"]),
        out["direction_sign"],
        0,
    )

    out["is_hammer"] = (
        out["body"].gt(0)
        & out["lower_wick"].gt(2.0 * out["body"])
        & out["upper_wick"].lt(0.5 * out["body"])
        & out["bar_close"].gt(out["bar_open"])
    )
    out["is_bullish_follow_through"] = (
        out["direction_sign"].eq(1)
        & out["bar_close"].gt(out["bar_open"])
        & out["prior_high"].notna()
        & out["bar_close"].gt(out["prior_high"])
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
    )

    return out


def add_context_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    rng_60m = out["range_60m"].replace(0, np.nan)
    out["pos_60m_low"] = (out["bar_low"] - out["low_60m"]) / rng_60m
    out["pos_60m_high"] = (out["bar_high"] - out["low_60m"]) / rng_60m
    out["is_60m_extreme_bullish"] = out["pos_60m_low"].le(0.20)
    out["is_60m_extreme_bearish"] = out["pos_60m_high"].ge(0.80)
    out["is_15m_trend_bullish"] = out["trend_sign_15m"].eq(1)
    out["is_15m_trend_bearish"] = out["trend_sign_15m"].eq(-1)
    return out


def build_condition_cache(df: pd.DataFrame) -> dict[tuple[str, int], np.ndarray]:
    cache: dict[tuple[str, int], np.ndarray] = {}
    false_array = np.zeros(len(df), dtype=bool)

    for direction in SEQUENCE_DIRECTIONS:
        suffix = direction_suffix(direction)
        cache[("signal_TRAP_04", direction)] = df[f"has_TRAP_04_{suffix}"].to_numpy(dtype=bool)
        cache[("signal_TRAP_05", direction)] = df[f"has_TRAP_05_{suffix}"].to_numpy(dtype=bool)
        cache[("signal_EXH_03", direction)] = df[f"has_EXH_03_{suffix}"].to_numpy(dtype=bool)
        cache[("signal_DELT_04", direction)] = df[f"has_DELT_04_{suffix}"].to_numpy(dtype=bool)
        cache[("category_absorption", direction)] = df[f"has_absorption_{suffix}"].to_numpy(dtype=bool)
        cache[("any_signal", direction)] = df[f"signal_count_{suffix}"].ge(1).to_numpy(dtype=bool)
        cache[("three_plus_categories", direction)] = df[f"category_count_{suffix}"].ge(3).to_numpy(dtype=bool)
        cache[("two_plus_signals", direction)] = df[f"signal_count_{suffix}"].ge(2).to_numpy(dtype=bool)
        cache[("type_b_bar", direction)] = df[f"has_TYPE_B_{suffix}"].to_numpy(dtype=bool)
        cache[("score_ge_60_bar", direction)] = df[f"has_score_ge_60_{suffix}"].to_numpy(dtype=bool)
        cache[("doji", direction)] = (df["is_doji"] & df["direction_sign"].eq(direction)).to_numpy(dtype=bool)
        cache[("narrow_range", direction)] = (df["is_narrow_range"] & df["direction_sign"].eq(direction)).to_numpy(dtype=bool)
        cache[("run3", direction)] = df["run3_direction_sign"].eq(direction).to_numpy(dtype=bool)
        cache[("volume_spike", direction)] = (df["is_volume_spike"] & df["direction_sign"].eq(direction)).to_numpy(dtype=bool)
        cache[("two_wide_range", direction)] = df["two_wide_range_direction_sign"].eq(direction).to_numpy(dtype=bool)
        cache[("delta_acceleration", direction)] = df["delta_acceleration_direction_sign"].eq(direction).to_numpy(dtype=bool)
        cache[("delta_reversal", direction)] = df["is_delta_reversal"] & df["direction_sign"].eq(direction)
        cache[("delta_reversal", direction)] = cache[("delta_reversal", direction)].to_numpy(dtype=bool)
        cache[("engulfing", direction)] = df["engulf_direction_sign"].eq(direction).to_numpy(dtype=bool)

        if direction > 0:
            cache[("hammer", direction)] = df["is_hammer"].to_numpy(dtype=bool)
            cache[("bullish_follow_through", direction)] = df["is_bullish_follow_through"].to_numpy(dtype=bool)
        else:
            cache[("hammer", direction)] = false_array.copy()
            cache[("bullish_follow_through", direction)] = false_array.copy()

    return cache


def build_sequence_specs() -> list[dict[str, object]]:
    return [
        {
            "code": "01",
            "group": "A",
            "label": "TRAP_04 -> absorption within 3 bars + 60m_extreme",
            "lookahead": 3,
            "first": "signal_TRAP_04",
            "second": "category_absorption",
            "relation": "same",
            "require_15m": False,
        },
        {
            "code": "02",
            "group": "A",
            "label": "EXH_03 -> absorption within 3 bars + 60m_extreme",
            "lookahead": 3,
            "first": "signal_EXH_03",
            "second": "category_absorption",
            "relation": "same",
            "require_15m": False,
        },
        {
            "code": "03",
            "group": "A",
            "label": "DELT_04 -> absorption within 5 bars + 60m_extreme",
            "lookahead": 5,
            "first": "signal_DELT_04",
            "second": "category_absorption",
            "relation": "same",
            "require_15m": False,
        },
        {
            "code": "04",
            "group": "A",
            "label": "Doji -> absorption within 3 bars + 60m_extreme",
            "lookahead": 3,
            "first": "doji",
            "second": "category_absorption",
            "relation": "same",
            "require_15m": False,
        },
        {
            "code": "05",
            "group": "A",
            "label": "absorption -> absorption within 5 bars + 60m_extreme",
            "lookahead": 5,
            "first": "category_absorption",
            "second": "category_absorption",
            "relation": "same",
            "require_15m": False,
        },
        {
            "code": "06",
            "group": "B",
            "label": "EXH_03 -> TRAP_04 within 3 bars + 60m_extreme",
            "lookahead": 3,
            "first": "signal_EXH_03",
            "second": "signal_TRAP_04",
            "relation": "same",
            "require_15m": False,
        },
        {
            "code": "07",
            "group": "B",
            "label": "EXH_03 -> doji within 3 bars + 60m_extreme",
            "lookahead": 3,
            "first": "signal_EXH_03",
            "second": "doji",
            "relation": "same",
            "require_15m": False,
        },
        {
            "code": "08",
            "group": "B",
            "label": "DELT_04 -> EXH_03 within 5 bars + 60m_extreme",
            "lookahead": 5,
            "first": "signal_DELT_04",
            "second": "signal_EXH_03",
            "relation": "same",
            "require_15m": False,
        },
        {
            "code": "09",
            "group": "B",
            "label": "3+ categories -> EXH_03 within 3 bars + 60m_extreme",
            "lookahead": 3,
            "first": "three_plus_categories",
            "second": "signal_EXH_03",
            "relation": "same",
            "require_15m": False,
        },
        {
            "code": "10",
            "group": "C",
            "label": "3 same-direction bars -> opposite doji within 3 bars + 60m_extreme",
            "lookahead": 3,
            "first": "run3",
            "second": "doji",
            "relation": "opposite",
            "require_15m": False,
        },
        {
            "code": "11",
            "group": "C",
            "label": "Volume spike -> narrow range bar within 3 bars + 60m_extreme",
            "lookahead": 3,
            "first": "volume_spike",
            "second": "narrow_range",
            "relation": "same",
            "require_15m": False,
        },
        {
            "code": "12",
            "group": "C",
            "label": "2 wide range bars -> narrow range bar within 3 bars + 60m_extreme",
            "lookahead": 3,
            "first": "two_wide_range",
            "second": "narrow_range",
            "relation": "same",
            "require_15m": False,
        },
        {
            "code": "13",
            "group": "C",
            "label": "Delta acceleration -> delta reversal within 3 bars + 60m_extreme",
            "lookahead": 3,
            "first": "delta_acceleration",
            "second": "delta_reversal",
            "relation": "opposite",
            "require_15m": False,
        },
        {
            "code": "14",
            "group": "D",
            "label": "Any signal -> confirming signal within 2 bars + 60m_extreme + 15m_trend",
            "lookahead": 2,
            "first": "any_signal",
            "second": "any_signal",
            "relation": "same",
            "require_15m": True,
        },
        {
            "code": "15",
            "group": "D",
            "label": "absorption -> TRAP_05 within 3 bars + 60m_extreme + 15m_trend",
            "lookahead": 3,
            "first": "category_absorption",
            "second": "signal_TRAP_05",
            "relation": "same",
            "require_15m": True,
        },
        {
            "code": "16",
            "group": "D",
            "label": "doji -> engulfing within 2 bars + 60m_extreme + 15m_trend",
            "lookahead": 2,
            "first": "doji",
            "second": "engulfing",
            "relation": "same",
            "require_15m": True,
        },
        {
            "code": "17",
            "group": "D",
            "label": "hammer -> bullish follow-through within 2 bars + 60m_extreme + 15m_trend",
            "lookahead": 2,
            "first": "hammer",
            "second": "bullish_follow_through",
            "relation": "same",
            "require_15m": True,
        },
        {
            "code": "18",
            "group": "E",
            "label": "2+ signals -> 2+ signals on next bar + 60m_extreme",
            "lookahead": 1,
            "first": "two_plus_signals",
            "second": "two_plus_signals",
            "relation": "same",
            "require_15m": False,
        },
        {
            "code": "19",
            "group": "E",
            "label": "TYPE_B bar -> TYPE_B bar within 3 bars + 60m_extreme",
            "lookahead": 3,
            "first": "type_b_bar",
            "second": "type_b_bar",
            "relation": "same",
            "require_15m": False,
        },
        {
            "code": "20",
            "group": "E",
            "label": "score >= 60 bar -> score >= 60 bar within 3 bars + 60m_extreme",
            "lookahead": 3,
            "first": "score_ge_60_bar",
            "second": "score_ge_60_bar",
            "relation": "same",
            "require_15m": False,
        },
    ]


def summarize_returns(code: str, group: str, label: str, returns: list[float] | pd.Series) -> dict[str, object]:
    series = pd.Series(returns, dtype="float64").dropna()
    n = int(len(series))
    wins = int((series > 0).sum())
    ci_low, ci_high, win_rate = wilson_ci(n, wins)
    return {
        "code": code,
        "group": group,
        "label": label,
        "n": n,
        "wr_5b": win_rate,
        "pf_5b": profit_factor(series) if n else np.nan,
        "avg_ticks_5b": float(series.mean()) if n else np.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "flag": status_flag(n, ci_low),
    }


def run_sequences(df: pd.DataFrame) -> list[dict[str, object]]:
    specs = build_sequence_specs()
    cache = build_condition_cache(df)
    session_positions = [group.index.to_numpy() for _, group in df.groupby("session_date", sort=False)]

    trade_directions = df["direction_sign"].to_numpy(dtype=int)
    returns_5b = df["ret_5b_ticks"].to_numpy(dtype=float)
    is_60m_extreme_bullish = df["is_60m_extreme_bullish"].fillna(False).to_numpy(dtype=bool)
    is_60m_extreme_bearish = df["is_60m_extreme_bearish"].fillna(False).to_numpy(dtype=bool)
    is_15m_trend_bullish = df["is_15m_trend_bullish"].fillna(False).to_numpy(dtype=bool)
    is_15m_trend_bearish = df["is_15m_trend_bearish"].fillna(False).to_numpy(dtype=bool)

    results: list[dict[str, object]] = []
    for spec in specs:
        matched_returns: list[float] = []
        first_name = str(spec["first"])
        second_name = str(spec["second"])
        relation = str(spec["relation"])
        lookahead = int(spec["lookahead"])
        require_15m = bool(spec["require_15m"])

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

                        trade_direction = int(trade_directions[end_idx])
                        if trade_direction == 0:
                            continue

                        if trade_direction > 0 and not is_60m_extreme_bullish[end_idx]:
                            continue
                        if trade_direction < 0 and not is_60m_extreme_bearish[end_idx]:
                            continue

                        if require_15m:
                            if trade_direction > 0 and not is_15m_trend_bullish[end_idx]:
                                continue
                            if trade_direction < 0 and not is_15m_trend_bearish[end_idx]:
                                continue

                        ret_5b = returns_5b[end_idx]
                        if not np.isnan(ret_5b):
                            matched_returns.append(float(ret_5b))
                        break

        results.append(summarize_returns(str(spec["code"]), str(spec["group"]), str(spec["label"]), matched_returns))

    results.sort(
        key=lambda row: (
            float("-inf") if pd.isna(row["avg_ticks_5b"]) else float(row["avg_ticks_5b"]),
            float("-inf") if pd.isna(row["wr_5b"]) else float(row["wr_5b"]),
            int(row["n"]),
        ),
        reverse=True,
    )
    return results


def render_table(rows: list[dict[str, object]]) -> list[str]:
    headers = ["Filter", "N", "WR 5b", "PF", "Avg Ticks", "Wilson 95% CI", "Flag"]
    data_rows: list[list[str]] = []

    for row in rows:
        data_rows.append(
            [
                f"{row['code']}. [{row['group']}] {row['label']}",
                f"{row['n']:,}",
                fmt_pct(float(row["wr_5b"])),
                fmt_float(float(row["pf_5b"])),
                fmt_float(float(row["avg_ticks_5b"])),
                fmt_ci(float(row["ci_low"]), float(row["ci_high"])),
                str(row["flag"]),
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
        f"N={int(row['n']):,} | WR5={fmt_pct(float(row['wr_5b']))} | PF5={fmt_float(float(row['pf_5b']))} | "
        f"Avg5={fmt_float(float(row['avg_ticks_5b']))}t | CI5={fmt_ci(float(row['ci_low']), float(row['ci_high']))}"
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events = load_events()
    bars_1m = load_ohlcv()
    bars = build_bars(events)
    bars = attach_directional_event_features(bars, events)
    context = build_timeframe_context(bars_1m)
    bars = attach_context(bars, context)
    bars = compute_bar_features(bars)
    bars = add_context_flags(bars)

    non_zero = bars[bars["direction_sign"].ne(0)].copy()
    baseline_all = summarize_returns("00", "BASE", "All non-zero-delta signal bars", non_zero["ret_5b_ticks"])
    extreme_mask = (
        (non_zero["direction_sign"].gt(0) & non_zero["is_60m_extreme_bullish"])
        | (non_zero["direction_sign"].lt(0) & non_zero["is_60m_extreme_bearish"])
    )
    baseline_60m = summarize_returns(
        "00A",
        "BASE",
        "All non-zero-delta bars at 60m extreme",
        non_zero.loc[extreme_mask, "ret_5b_ticks"],
    )
    results = run_sequences(bars)

    lines = [
        "DEEP6 round 7 sequential signal-sequence analysis",
        "===============================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index.",
        "Sequence scan runs chronologically inside each session and looks forward 1..X bars for the second condition.",
        "Signal-based sequence matching uses signal direction from signal_events.csv; bar-pattern sequence matching uses the pattern direction defined below.",
        "P&L and regime gates always use sign(bar_delta) on the SECOND bar, per request.",
        "60m_extreme = bullish second-bar low in the bottom 20% of its 60m range / bearish second-bar high in the top 20%.",
        "15m_trend = second-bar bar_delta sign matches the 15m open-close sign.",
        f"Rolling range / volume thresholds use the prior {ROLLING_LOOKBACK} deduped signal bars inside each session.",
        "Doji = body/range < 0.10 using the deduped signal-bar stream.",
        "Hammer = bullish body with lower wick >2x body and upper wick <0.5x body.",
        "Bullish follow-through = positive-delta bullish bar that closes above the prior bar high.",
        "Engulfing = current body fully engulfs the prior body; direction is bullish/bearish by close vs open.",
        "3 same-direction bars = three consecutive deduped signal bars with the same non-zero bar_delta sign.",
        "2 wide range bars = two consecutive wide-range bars with the same non-zero bar_delta sign.",
        "Delta acceleration = three consecutive bars with the same non-zero bar_delta sign and strictly increasing |bar_delta|.",
        "Delta reversal = current bar_delta sign flips versus the prior bar_delta sign.",
        "Sequences 10 and 13 are intentionally opposite-direction A->B transitions; all others require same-direction A->B matching.",
        "Unspecified build-up windows (filters 10-13) default to a 3-bar lookahead.",
        "Status flags: VALIDATED = N>=30 and Wilson lower bound >50%; PROMISING = N>=15 and Wilson lower bound >45%; LOW_N = N<15.",
        "Final ranking is sorted by 5-bar average ticks descending.",
        "",
        f"Raw event rows loaded:         {len(events):,}",
        f"Deduped signal bars:          {len(bars):,}",
        f"15m bars built:               {len(context[15]):,}",
        f"60m bars built:               {len(context[60]):,}",
        f"Non-zero-delta bars:          {len(non_zero):,}",
        f"60m extreme non-zero bars:    {int(extreme_mask.sum()):,}",
        f"TRAP_04 rows loaded:          {int(events['signal_id'].eq('TRAP_04').sum()):,}",
        f"TRAP_05 rows loaded:          {int(events['signal_id'].eq('TRAP_05').sum()):,}",
        f"EXH_03 rows loaded:           {int(events['signal_id'].eq('EXH_03').sum()):,}",
        f"DELT_04 rows loaded:          {int(events['signal_id'].eq('DELT_04').sum()):,}",
        f"Absorption rows loaded:       {int(events['category'].eq('absorption').sum()):,}",
        "",
        "Baselines",
        "---------",
        f"All non-zero-delta bars: {render_summary_line(baseline_all)}",
        f"60m extreme only:        {render_summary_line(baseline_60m)}",
        "",
        "20 requested sequential filters",
        "------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
