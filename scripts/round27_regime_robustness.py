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
OUT_PATH = OUT_DIR / "round27_regime_robustness_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
RTH_START_MINUTE = 9 * 60 + 30
FIRST_HOUR_MINUTES = 60

PERIODS = [
    ("Q1-Q2 2025", pd.Timestamp("2025-01-01"), pd.Timestamp("2025-06-30")),
    ("Q3-Q4 2025", pd.Timestamp("2025-07-01"), pd.Timestamp("2025-12-31")),
    ("Q1 2026", pd.Timestamp("2026-01-01"), pd.Timestamp("2026-03-31")),
    ("Q2 2026", pd.Timestamp("2026-04-01"), pd.Timestamp("2026-04-30")),
]

SetupSpec = tuple[str, str, str, Callable[[pd.DataFrame], pd.Series], Callable[[pd.DataFrame], int | pd.Series]]


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


def fmt_ci(low: float, high: float) -> str:
    return f"[{low * 100:.1f}%, {high * 100:.1f}%]"


def fmt_pp(value: float) -> str:
    if pd.isna(value):
        return "nan"
    return f"{value:.1f}pp"


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
    ]
    events = pd.read_csv(EVENTS_CSV, usecols=cols, dtype=dtypes, low_memory=False)
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
        events[col] = pd.to_numeric(events[col], errors="coerce")
    events["bar_ts"] = pd.to_datetime(events["bar_ts"], utc=True, errors="coerce").dt.tz_convert(EASTERN)
    events["event_direction_sign"] = direction_to_sign(events["direction"])
    return events.sort_values(["session_date", "bar_ts", "global_index", "signal_id"], kind="stable").reset_index(drop=True)


def add_session_date_fields(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["session_date_dt"] = pd.to_datetime(out["session_date"], errors="coerce")
    return out


def build_bar_observations(events: pd.DataFrame) -> pd.DataFrame:
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
        .sort_values(["session_date", "bar_ts", "global_index"], kind="stable")
        .reset_index(drop=True)
    )
    observations["direction_sign"] = np.sign(observations["bar_delta"].fillna(0.0)).astype(int)
    observations["move_5b_ticks"] = (observations["fwd_close_5b"] - observations["bar_close"]) / TICK_SIZE
    return add_session_date_fields(observations)


def build_signal_observations(events: pd.DataFrame) -> pd.DataFrame:
    working = events.loc[events["event_direction_sign"].ne(0)].copy()
    working["is_DELT_04"] = working["signal_id"].eq("DELT_04")
    working["is_TRAP_04"] = working["signal_id"].eq("TRAP_04")

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
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
            has_DELT_04=("is_DELT_04", "max"),
            has_TRAP_04=("is_TRAP_04", "max"),
        )
        .rename(columns={"event_direction_sign": "direction_sign"})
        .sort_values(["session_date", "bar_ts", "global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    observations["move_5b_ticks"] = (observations["fwd_close_5b"] - observations["bar_close"]) / TICK_SIZE
    return add_session_date_fields(observations)


def build_absorption_observations(events: pd.DataFrame) -> pd.DataFrame:
    absorption = events.loc[events["category"].eq("absorption") & events["event_direction_sign"].ne(0)].copy()
    observations = (
        absorption.groupby(["global_index", "event_direction_sign"], as_index=False, sort=False)
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
        )
        .rename(columns={"event_direction_sign": "direction_sign"})
        .sort_values(["session_date", "bar_ts", "global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    observations["move_5b_ticks"] = (observations["fwd_close_5b"] - observations["bar_close"]) / TICK_SIZE
    return add_session_date_fields(observations)


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


def compute_common_bar_features(observations: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["body_high"] = np.maximum(out["bar_open"], out["bar_close"])
    out["body_low"] = np.minimum(out["bar_open"], out["bar_close"])
    out["body_mid"] = (out["body_high"] + out["body_low"]) / 2.0
    out["upper_wick"] = out["bar_high"] - out["body_high"]
    out["lower_wick"] = out["body_low"] - out["bar_low"]
    out["abs_delta"] = out["bar_delta"].abs()
    out["delta_ratio"] = np.where(out["bar_volume"] > 0, out["abs_delta"] / out["bar_volume"], np.nan)
    out["price_change"] = out["bar_close"] - out["bar_open"]
    out["price_sign"] = np.sign(out["price_change"]).astype(int)
    out["price_color_sign"] = out["price_sign"]

    out["prior_high"] = by_session["bar_high"].shift(1)
    out["prior_low"] = by_session["bar_low"].shift(1)
    out["prior_bar_range"] = by_session["bar_range"].shift(1)
    out["bar_range_2"] = by_session["bar_range"].shift(2)
    out["prior_price_sign"] = by_session["price_sign"].shift(1)
    out["prior_direction_sign"] = by_session["direction_sign"].shift(1)
    out["prior_body_high"] = by_session["body_high"].shift(1)
    out["prior_body_low"] = by_session["body_low"].shift(1)

    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    out["range_q25"] = by_session["bar_range"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.25)
    )
    out["rolling_20_avg_range"] = by_session["bar_range"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).mean()
    )

    out["is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.10 * out["bar_range"])
    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])
    out["is_three_narrowing_ranges"] = (
        out["bar_range_2"].notna()
        & out["prior_bar_range"].lt(out["bar_range_2"])
        & out["bar_range"].lt(out["prior_bar_range"])
    )
    out["is_price_delta_divergence"] = (
        out["price_sign"].ne(0)
        & out["direction_sign"].ne(0)
        & out["price_sign"].eq(-out["direction_sign"])
    )
    out["is_delta_divergence_2bar"] = (
        out["is_price_delta_divergence"]
        & out["prior_price_sign"].notna()
        & out["prior_direction_sign"].notna()
        & pd.Series(out["prior_price_sign"], index=out.index).ne(0)
        & pd.Series(out["prior_direction_sign"], index=out.index).ne(0)
        & pd.Series(out["prior_price_sign"], index=out.index).eq(-pd.Series(out["prior_direction_sign"], index=out.index))
    )
    out["is_very_low_delta_ratio"] = out["delta_ratio"].lt(0.05)

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

    by_session = out.groupby("session_date", sort=False)
    out["is_doji_1"] = by_session["is_doji"].shift(1).fillna(False).astype(bool)
    out["price_color_sign_2"] = by_session["price_color_sign"].shift(2)
    out["body_mid_2"] = by_session["body_mid"].shift(2)

    out["is_morning_star"] = (
        out["price_color_sign"].eq(1)
        & out["is_doji_1"]
        & out["price_color_sign_2"].eq(-1)
        & out["bar_close"].gt(out["body_mid_2"])
    )
    out["is_evening_star"] = (
        out["price_color_sign"].eq(-1)
        & out["is_doji_1"]
        & out["price_color_sign_2"].eq(1)
        & out["bar_close"].lt(out["body_mid_2"])
    )
    out["star_direction_sign"] = np.select(
        [out["is_morning_star"], out["is_evening_star"]],
        [1, -1],
        default=0,
    ).astype(int)
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
    sample["trade_sign"] = normalize_direction(direction, sample)
    sample = sample.loc[sample["trade_sign"].ne(0)].copy()
    sample["ret_5b_ticks"] = sample["trade_sign"] * sample["move_5b_ticks"]
    return sample.reset_index(drop=True)


def summarize_period(sample: pd.DataFrame, period_name: str, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, object]:
    period_df = sample.loc[sample["session_date_dt"].between(start, end, inclusive="both")].copy()
    returns = period_df["ret_5b_ticks"].dropna()
    n = int(len(returns))
    wins = int((returns > 0).sum())
    ci_low, ci_high, win_rate = wilson_ci(n, wins)
    return {
        "period": period_name,
        "start": start,
        "end": end,
        "n": n,
        "win_rate": win_rate if n else np.nan,
        "profit_factor": profit_factor(returns) if n else np.nan,
        "avg_ticks": float(returns.mean()) if n else np.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
    }


def summarize_total(sample: pd.DataFrame) -> dict[str, object]:
    returns = sample["ret_5b_ticks"].dropna()
    n = int(len(returns))
    wins = int((returns > 0).sum())
    ci_low, ci_high, win_rate = wilson_ci(n, wins)
    return {
        "n": n,
        "win_rate": win_rate if n else np.nan,
        "profit_factor": profit_factor(returns) if n else np.nan,
        "avg_ticks": float(returns.mean()) if n else np.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
    }


def classify_setup(period_rows: list[dict[str, object]]) -> dict[str, object]:
    valid_rows = [row for row in period_rows if int(row["n"]) > 0]
    full_coverage = len(valid_rows) == len(period_rows)
    wr_values = [float(row["win_rate"]) for row in valid_rows]
    wr_spread_pp = (max(wr_values) - min(wr_values)) * 100 if wr_values else np.nan

    robust = (
        full_coverage
        and all(float(row["win_rate"]) > 0.55 for row in period_rows)
        and all(float(row["profit_factor"]) >= 1.0 for row in period_rows)
        and wr_spread_pp < 20.0
    )
    fragile = any(
        (int(row["n"]) > 0 and float(row["win_rate"]) < 0.45)
        or (int(row["n"]) > 0 and float(row["profit_factor"]) < 0.5)
        for row in period_rows
    )

    notes: list[str] = []
    if not full_coverage:
        notes.append(f"coverage {len(valid_rows)}/{len(period_rows)}")
    if not robust:
        if full_coverage and any(float(row["win_rate"]) <= 0.55 for row in period_rows):
            notes.append("WR<=55% in at least one period")
        if full_coverage and any(float(row["profit_factor"]) < 1.0 for row in period_rows):
            notes.append("PF<1.0 in at least one period")
        if full_coverage and not pd.isna(wr_spread_pp) and wr_spread_pp >= 20.0:
            notes.append("WR spread>=20pp")
    if fragile:
        if any(int(row["n"]) > 0 and float(row["win_rate"]) < 0.45 for row in period_rows):
            notes.append("WR<45% in at least one period")
        if any(int(row["n"]) > 0 and float(row["profit_factor"]) < 0.5 for row in period_rows):
            notes.append("PF<0.5 in at least one period")

    status = "ROBUST" if robust else "FRAGILE" if fragile else "NEITHER"
    return {
        "status": status,
        "robust": robust,
        "fragile": fragile,
        "coverage": f"{len(valid_rows)}/{len(period_rows)}",
        "wr_spread_pp": wr_spread_pp,
        "notes": "; ".join(dict.fromkeys(notes)) if notes else "",
    }


def build_setup_specs() -> list[SetupSpec]:
    return [
        (
            "01",
            "60m + 15m (base)",
            "bar",
            lambda df: has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "02",
            "60m + 15m + NOT killers + first_hour",
            "bar",
            lambda df: has_core_60m_15m_gate_for(df, df["direction_sign"])
            & passes_not_all_killers_for(df, df["direction_sign"])
            & df["is_first_hour"],
            lambda df: df["direction_sign"],
        ),
        (
            "03",
            "Doji + 60m + 15m",
            "bar",
            lambda df: df["is_doji"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "04",
            "CVD divergence + 60m + 15m",
            "bar",
            lambda df: df["is_cvd_divergence"] & has_core_60m_15m_gate_for(df, df["divergence_sign"]),
            lambda df: df["divergence_sign"],
        ),
        (
            "05",
            "|delta|/vol < 0.05 + 60m + 15m",
            "bar",
            lambda df: df["is_very_low_delta_ratio"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "06",
            "3 narrowing ranges + 60m + 15m",
            "bar",
            lambda df: df["is_three_narrowing_ranges"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "07",
            "Morning/evening star + 60m + 15m",
            "bar",
            lambda df: df["star_direction_sign"].ne(0) & has_core_60m_15m_gate_for(df, df["star_direction_sign"]),
            lambda df: df["star_direction_sign"],
        ),
        (
            "08",
            "absorption + 60m + 15m",
            "absorption",
            lambda df: has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "09",
            "DELT_04 + TRAP_04 + 15m_trend",
            "signal",
            lambda df: df["has_DELT_04"] & df["has_TRAP_04"] & is_15m_trend_aligned_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "10",
            "Engulfing + 60m + 15m",
            "bar",
            lambda df: df["engulf_direction_sign"].ne(0) & has_core_60m_15m_gate_for(df, df["engulf_direction_sign"]),
            lambda df: df["engulf_direction_sign"],
        ),
    ]


def evaluate_setup(setup: SetupSpec, datasets: dict[str, pd.DataFrame]) -> dict[str, object]:
    code, label, dataset_key, predicate, direction_fn = setup
    source = datasets[dataset_key]
    mask = predicate(source).fillna(False)
    filtered = source.loc[mask].copy()

    direction = direction_fn(source)
    if isinstance(direction, pd.Series):
        direction = direction.loc[mask]
    sample = build_trade_sample(filtered, direction)

    total = summarize_total(sample)
    period_rows = [summarize_period(sample, period_name, start, end) for period_name, start, end in PERIODS]
    regime = classify_setup(period_rows)

    return {
        "code": code,
        "label": label,
        "dataset_key": dataset_key,
        "total": total,
        "periods": period_rows,
        "regime": regime,
    }


def render_summary_table(results: list[dict[str, object]]) -> list[str]:
    headers = ["Setup", "Total N", "WR 5b", "PF", "Avg", "Status", "Coverage", "WR Spread", "Notes"]
    rows = [headers]

    for result in results:
        total = result["total"]
        regime = result["regime"]
        rows.append(
            [
                f"{result['code']}. {result['label']}",
                f"{int(total['n']):,}",
                fmt_pct(float(total["win_rate"])),
                fmt_float(float(total["profit_factor"])),
                f"{fmt_float(float(total['avg_ticks']))}t",
                str(regime["status"]),
                str(regime["coverage"]),
                fmt_pp(float(regime["wr_spread_pp"])),
                str(regime["notes"]),
            ]
        )

    widths = [max(len(str(row[idx])) for row in rows) for idx in range(len(headers))]
    lines = []
    header = " | ".join(str(value).ljust(widths[idx]) for idx, value in enumerate(rows[0]))
    divider = "-+-".join("-" * width for width in widths)
    lines.append(header)
    lines.append(divider)
    for row in rows[1:]:
        lines.append(" | ".join(str(value).ljust(widths[idx]) for idx, value in enumerate(row)))
    return lines


def render_period_table(period_rows: list[dict[str, object]]) -> list[str]:
    headers = ["Period", "N", "WR 5b", "PF", "Avg Ticks", "Wilson 95% CI"]
    rows = [headers]
    for row in period_rows:
        rows.append(
            [
                str(row["period"]),
                f"{int(row['n']):,}",
                fmt_pct(float(row["win_rate"])),
                fmt_float(float(row["profit_factor"])),
                f"{fmt_float(float(row['avg_ticks']))}t",
                fmt_ci(float(row["ci_low"]), float(row["ci_high"])),
            ]
        )

    widths = [max(len(str(row[idx])) for row in rows) for idx in range(len(headers))]
    lines = []
    header = " | ".join(str(value).ljust(widths[idx]) for idx, value in enumerate(rows[0]))
    divider = "-+-".join("-" * width for width in widths)
    lines.append(header)
    lines.append(divider)
    for row in rows[1:]:
        lines.append(" | ".join(str(value).ljust(widths[idx]) for idx, value in enumerate(row)))
    return lines


def build_report(results: list[dict[str, object]], events: pd.DataFrame, datasets: dict[str, pd.DataFrame], context: dict[int, pd.DataFrame]) -> str:
    lines = [
        "DEEP6 round27 regime robustness analysis",
        "========================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "",
        "Requested regime periods:",
        "- Q1-Q2 2025 = 2025-01-01 through 2025-06-30",
        "- Q3-Q4 2025 = 2025-07-01 through 2025-12-31",
        "- Q1 2026    = 2026-01-01 through 2026-03-31",
        "- Q2 2026    = 2026-04-01 through 2026-04-30",
        "",
        "Flag rules:",
        "- ROBUST if WR > 55% in all 4 periods, no period has PF < 1.0, and max WR spread < 20pp.",
        "- FRAGILE if any period has WR < 45% or any period has PF < 0.5.",
        "- NEITHER otherwise. Coverage below 4/4 automatically blocks ROBUST.",
        "",
        "Implementation notes:",
        "- 60m + 15m uses the established core gate: trade-direction 60m extreme plus 15m trend alignment.",
        "- NOT killers = NOT killer_1 (trade anchor in middle 40%-60% of 60m range) AND NOT killer_2 (bar_volume > 3x prior 20-bar EMA).",
        "- Doji / 3 narrowing ranges / 2-bar price-delta divergence / 60m context follow round2_novel_bar_patterns.py.",
        "- Morning/evening star and engulfing follow the round23 / round3 candlestick workflow.",
        "- Absorption uses unique same-bar, same-direction absorption observations.",
        "- DELT_04 + TRAP_04 + 15m_trend uses unique same-bar, same-direction grouped signal observations.",
        "",
        f"Raw event rows loaded:              {len(events):,}",
        f"Grouped bar observations:           {len(datasets['bar']):,}",
        f"Grouped signal-direction obs:       {len(datasets['signal']):,}",
        f"Grouped absorption observations:    {len(datasets['absorption']):,}",
        f"15m bars built:                     {len(context[15]):,}",
        f"60m bars built:                     {len(context[60]):,}",
        "",
        "Setup summary",
        "-------------",
        *render_summary_table(results),
        "",
        "Detailed setup-by-period metrics",
        "------------------------------",
    ]

    for result in results:
        total = result["total"]
        regime = result["regime"]
        lines.extend(
            [
                "",
                f"{result['code']}. {result['label']}",
                f"Status: {regime['status']} | Coverage: {regime['coverage']} | WR spread: {fmt_pp(float(regime['wr_spread_pp']))}",
                (
                    f"Full sample: N={int(total['n']):,} | WR 5b={fmt_pct(float(total['win_rate']))} | "
                    f"PF={fmt_float(float(total['profit_factor']))} | Avg={fmt_float(float(total['avg_ticks']))}t | "
                    f"CI={fmt_ci(float(total['ci_low']), float(total['ci_high']))}"
                ),
            ]
        )
        if regime["notes"]:
            lines.append(f"Notes: {regime['notes']}")
        lines.extend(render_period_table(result["periods"]))

    return "\n".join(lines) + "\n"


def prepare_datasets() -> tuple[pd.DataFrame, dict[str, pd.DataFrame], dict[int, pd.DataFrame]]:
    events = load_events()
    bars_1m = load_ohlcv()
    context = build_timeframe_context(bars_1m)

    bar_obs = build_bar_observations(events)
    bar_obs = attach_context(bar_obs, context)
    bar_obs = compute_common_bar_features(bar_obs)
    bar_obs = compute_cvd_features(bar_obs)
    bar_obs = add_time_flags(bar_obs)

    signal_obs = build_signal_observations(events)
    signal_obs = attach_context(signal_obs, context)

    absorption_obs = build_absorption_observations(events)
    absorption_obs = attach_context(absorption_obs, context)

    datasets = {
        "bar": bar_obs,
        "signal": signal_obs,
        "absorption": absorption_obs,
    }
    return events, datasets, context


def main() -> None:
    events, datasets, context = prepare_datasets()
    results = [evaluate_setup(setup, datasets) for setup in build_setup_specs()]
    report = build_report(results, events, datasets, context)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
