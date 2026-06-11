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
OUT_PATH = OUT_DIR / "round17_vol_of_vol_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
ATR_MA_WINDOW = 50
VOL_OF_VOL_WINDOW = 10
RANGE_LOOKBACK = 5
RTH_START_MINUTE = 9 * 60 + 30
FIRST_HOUR_MINUTES = 60
RANGE_EXPANSION_MULTIPLIER = 1.5
RANGE_CONTRACTION_MULTIPLIER = 0.5

FilterSpec = tuple[str, str, str, Callable[[pd.DataFrame], pd.Series]]


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


def compute_bar_features(observations: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["prior_close"] = by_session["bar_close"].shift(1)
    out["prior_bar_range"] = by_session["bar_range"].shift(1)
    out["bar_range_2"] = by_session["bar_range"].shift(2)

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
    out["atr20_1"] = by_session["atr20"].shift(1)
    out["atr20_5"] = by_session["atr20"].shift(5)
    out["atr20_10"] = by_session["atr20"].shift(10)
    out["atr50_ma"] = by_session["atr20"].transform(
        lambda s: s.rolling(ATR_MA_WINDOW, min_periods=ATR_MA_WINDOW).mean()
    )
    out["atr50_ma_1"] = by_session["atr50_ma"].shift(1)
    out["rolling_atr20_high"] = by_session["atr20"].cummax()
    out["vol_of_vol"] = by_session["atr20"].transform(
        lambda s: s.rolling(VOL_OF_VOL_WINDOW, min_periods=VOL_OF_VOL_WINDOW).std()
    )

    out["prior_avg_range_5"] = by_session["bar_range"].transform(
        lambda s: s.shift(1).rolling(RANGE_LOOKBACK, min_periods=RANGE_LOOKBACK).mean()
    )
    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )

    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])
    out["is_atr_increasing_5"] = out["atr20_5"].gt(0) & out["atr20"].gt(out["atr20_5"])
    out["is_atr_decreasing_5"] = out["atr20_5"].gt(0) & out["atr20"].lt(out["atr20_5"])
    out["is_atr_up_20pct_10"] = out["atr20_10"].gt(0) & out["atr20"].gt(1.2 * out["atr20_10"])
    out["is_atr_down_20pct_10"] = out["atr20_10"].gt(0) & out["atr20"].lt(0.8 * out["atr20_10"])
    out["is_atr20_session_high"] = out["atr20"].notna() & out["atr20"].eq(out["rolling_atr20_high"])

    out["is_expansion_bar"] = out["prior_avg_range_5"].gt(0) & out["bar_range"].gt(
        RANGE_EXPANSION_MULTIPLIER * out["prior_avg_range_5"]
    )
    out["is_contraction_bar"] = out["prior_avg_range_5"].gt(0) & out["bar_range"].lt(
        RANGE_CONTRACTION_MULTIPLIER * out["prior_avg_range_5"]
    )
    out["is_three_expanding_ranges"] = (
        out["bar_range_2"].notna()
        & out["prior_bar_range"].gt(out["bar_range_2"])
        & out["bar_range"].gt(out["prior_bar_range"])
    )
    out["is_three_contracting_ranges"] = (
        out["bar_range_2"].notna()
        & out["prior_bar_range"].lt(out["bar_range_2"])
        & out["bar_range"].lt(out["prior_bar_range"])
    )
    prior_is_contraction = out.groupby("session_date", sort=False)["is_contraction_bar"].shift(1)
    out["prior_is_contraction_bar"] = prior_is_contraction.eq(True)
    out["is_contraction_to_expansion"] = out["prior_is_contraction_bar"] & out["is_expansion_bar"]

    out["atr_crossed_above_ma50"] = (
        out["atr20"].gt(out["atr50_ma"])
        & out["atr20_1"].notna()
        & out["atr50_ma_1"].notna()
        & out["atr20_1"].le(out["atr50_ma_1"])
    )
    out["atr_crossed_below_ma50"] = (
        out["atr20"].lt(out["atr50_ma"])
        & out["atr20_1"].notna()
        & out["atr50_ma_1"].notna()
        & out["atr20_1"].ge(out["atr50_ma_1"])
    )
    out["is_extreme_atr"] = out["atr50_ma"].gt(0) & out["atr20"].gt(2.0 * out["atr50_ma"])
    out["is_calm_atr"] = out["atr50_ma"].gt(0) & out["atr20"].lt(0.5 * out["atr50_ma"])
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
    out["is_cvd_divergence"] = out["is_bullish_cvd_divergence"] | out["is_bearish_cvd_divergence"]
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
    return sample.reset_index(drop=True)


def compute_thresholds(df: pd.DataFrame) -> dict[str, float]:
    vol_of_vol = df["vol_of_vol"].dropna()
    return {
        "vol_of_vol_q25": float(vol_of_vol.quantile(0.25)) if not vol_of_vol.empty else float("nan"),
        "vol_of_vol_q75": float(vol_of_vol.quantile(0.75)) if not vol_of_vol.empty else float("nan"),
    }


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


def build_filter_specs(thresholds: dict[str, float]) -> list[FilterSpec]:
    stable_threshold = thresholds["vol_of_vol_q25"]
    unstable_threshold = thresholds["vol_of_vol_q75"]

    return [
        (
            "01",
            "A",
            "ATR20 increasing vs 5 bars ago + 60m + 15m",
            lambda df: df["is_atr_increasing_5"] & df["has_core_60m_15m_gate"],
        ),
        (
            "02",
            "A",
            "ATR20 decreasing vs 5 bars ago + 60m + 15m",
            lambda df: df["is_atr_decreasing_5"] & df["has_core_60m_15m_gate"],
        ),
        (
            "03",
            "A",
            "ATR20 increased >20% vs 10 bars ago + 60m + 15m",
            lambda df: df["is_atr_up_20pct_10"] & df["has_core_60m_15m_gate"],
        ),
        (
            "04",
            "A",
            "ATR20 decreased >20% vs 10 bars ago + 60m + 15m",
            lambda df: df["is_atr_down_20pct_10"] & df["has_core_60m_15m_gate"],
        ),
        (
            "05",
            "A",
            "ATR20 at session high so far today + 60m + 15m",
            lambda df: df["is_atr20_session_high"] & df["has_core_60m_15m_gate"],
        ),
        (
            "06",
            "B",
            "Vol-of-vol > 75th percentile + 60m + 15m",
            lambda df: df["vol_of_vol"].gt(unstable_threshold) & df["has_core_60m_15m_gate"],
        ),
        (
            "07",
            "B",
            "Vol-of-vol < 25th percentile + 60m + 15m",
            lambda df: df["vol_of_vol"].lt(stable_threshold) & df["has_core_60m_15m_gate"],
        ),
        (
            "08",
            "B",
            "Stable vol + 60m + 15m + first_hour",
            lambda df: df["vol_of_vol"].lt(stable_threshold) & df["has_core_60m_15m_gate"] & df["is_first_hour"],
        ),
        (
            "09",
            "B",
            "Unstable vol + 60m + 15m + NOT lunch",
            lambda df: df["vol_of_vol"].gt(unstable_threshold) & df["has_core_60m_15m_gate"] & df["is_not_lunch"],
        ),
        (
            "10",
            "C",
            "Current range > 1.5x avg of prior 5 ranges + 60m + 15m",
            lambda df: df["is_expansion_bar"] & df["has_core_60m_15m_gate"],
        ),
        (
            "11",
            "C",
            "Current range < 0.5x avg of prior 5 ranges + 60m + 15m",
            lambda df: df["is_contraction_bar"] & df["has_core_60m_15m_gate"],
        ),
        (
            "12",
            "C",
            "3 bars of expanding ranges + 60m + 15m",
            lambda df: df["is_three_expanding_ranges"] & df["has_core_60m_15m_gate"],
        ),
        (
            "13",
            "C",
            "3 bars of contracting ranges + 60m + 15m",
            lambda df: df["is_three_contracting_ranges"] & df["has_core_60m_15m_gate"],
        ),
        (
            "14",
            "C",
            "Contraction -> expansion + 60m + 15m",
            lambda df: df["is_contraction_to_expansion"] & df["has_core_60m_15m_gate"],
        ),
        (
            "15",
            "D",
            "ATR20 crossed above ATR50_MA + 60m + 15m",
            lambda df: df["atr_crossed_above_ma50"] & df["has_core_60m_15m_gate"],
        ),
        (
            "16",
            "D",
            "ATR20 crossed below ATR50_MA + 60m + 15m",
            lambda df: df["atr_crossed_below_ma50"] & df["has_core_60m_15m_gate"],
        ),
        (
            "17",
            "D",
            "ATR20 > 2x ATR50_MA + 60m + 15m",
            lambda df: df["is_extreme_atr"] & df["has_core_60m_15m_gate"],
        ),
        (
            "18",
            "D",
            "ATR20 < 0.5x ATR50_MA + 60m + 15m",
            lambda df: df["is_calm_atr"] & df["has_core_60m_15m_gate"],
        ),
        (
            "19",
            "E",
            "Stable vol + contraction bar + 60m + 15m + NOT killers",
            lambda df: df["vol_of_vol"].lt(stable_threshold)
            & df["is_contraction_bar"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
        ),
        (
            "20",
            "E",
            "Vol expansion + CVD divergence + 60m + 15m + NOT killers",
            lambda df: df["is_atr_increasing_5"]
            & df["is_cvd_divergence"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
        ),
    ]


def run_filters(sample: pd.DataFrame, thresholds: dict[str, float]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for code, group, label, predicate in build_filter_specs(thresholds):
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
    timeframe_context = build_timeframe_context(bars_1m)
    observations = attach_timeframe_context(observations, timeframe_context)
    observations = compute_bar_features(observations)
    observations = compute_cvd_features(observations)
    observations = add_time_flags(observations)

    sample = build_trade_sample(observations, observations["direction_sign"])
    thresholds = compute_thresholds(sample)
    results = run_filters(sample, thresholds)

    base_all = summarize_filter("00", "BASE", "All non-zero-delta signal bars", sample)
    base_core = summarize_filter(
        "00A",
        "BASE",
        "60m + 15m core gate",
        sample.loc[sample["has_core_60m_15m_gate"]].copy(),
    )
    base_core_not_killers = summarize_filter(
        "00B",
        "BASE",
        "60m + 15m + NOT killers",
        sample.loc[sample["has_core_60m_15m_gate"] & sample["passes_not_all_killers"]].copy(),
    )
    base_cvd = summarize_filter(
        "00C",
        "BASE",
        "CVD divergence + 60m + 15m",
        sample.loc[sample["is_cvd_divergence"] & sample["has_core_60m_15m_gate"]].copy(),
    )

    lines = [
        "DEEP6 round17 volatility-of-volatility analysis",
        "===============================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index.",
        "Trade direction for P&L: sign(bar_delta). Zero-delta bars are skipped.",
        "All ATR, vol-of-vol, and range-sequence features are built from deduped signal-event bars within each session, not full 1m bars.",
        "60m gate = bullish bar_low in bottom 20% of active 60m range / bearish bar_high in top 20% of active 60m range.",
        "15m gate = trade direction matches 15m open-close trend sign.",
        "ATR20 = rolling 20-bar mean of true range; ATR50_MA = rolling 50-bar mean of ATR20; vol-of-vol = rolling 10-bar std of ATR20.",
        "Range expansion/contraction compares current bar range to the average of the PRIOR 5 signal-bar ranges within the session.",
        "CVD divergence follows round8: price makes a new session high/low but session CVD fails to confirm.",
        "KILLER_1 = trade-direction anchor sits in the middle 40-60% of the active 60m range. KILLER_2 = bar_volume > 3x prior 20-bar EMA volume.",
        "NOT killers = NOT killer_1 AND NOT killer_2.",
        "Stable / unstable vol thresholds use the 25th / 75th percentile of vol-of-vol across the full non-zero-delta sample.",
        "N uses rows with complete 5b/10b/30b forward closes so every WR window and persistence label uses the same sample.",
        "Persistence: GROWING if WR_30b > WR_5b; STABLE if WR_30b is within 3 percentage points of WR_5b without growth; DECAYING otherwise.",
        "Filter 20 uses the round17 vol-expansion definition ATR20 > ATR20 from 5 bars ago.",
        "",
        f"Raw event rows loaded:              {len(events):,}",
        f"Grouped signal bars:                {len(observations):,}",
        f"Non-zero-delta trade sample:        {len(sample):,}",
        f"15m bars built:                     {len(timeframe_context[15]):,}",
        f"60m bars built:                     {len(timeframe_context[60]):,}",
        f"Core 60m + 15m bars:                {int(sample['has_core_60m_15m_gate'].sum()):,}",
        f"CVD divergence bars:                {int(sample['is_cvd_divergence'].sum()):,}",
        f"Stable vol bars (<25th pct):        {int(sample['vol_of_vol'].lt(thresholds['vol_of_vol_q25']).sum()):,}",
        f"Unstable vol bars (>75th pct):      {int(sample['vol_of_vol'].gt(thresholds['vol_of_vol_q75']).sum()):,}",
        f"KILLER_1 hits:                      {int(sample['is_killer_1'].sum()):,}",
        f"KILLER_2 hits:                      {int(sample['is_killer_2'].sum()):,}",
        f"Vol-of-vol 25th percentile:         {fmt_float(thresholds['vol_of_vol_q25'])}",
        f"Vol-of-vol 75th percentile:         {fmt_float(thresholds['vol_of_vol_q75'])}",
        "",
        "Baselines",
        "---------",
        f"All non-zero-delta bars:    {render_summary_line(base_all)}",
        f"60m + 15m core gate:       {render_summary_line(base_core)}",
        f"60m + 15m + NOT killers:   {render_summary_line(base_core_not_killers)}",
        f"CVD divergence + core gate:{render_summary_line(base_cvd)}",
        "",
        "20 volatility-change / vol-of-vol filters ranked by 30b win rate",
        "--------------------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
