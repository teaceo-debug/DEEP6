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
OUT_PATH = OUT_DIR / "round29_absorption_micro_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
ABS_SIGNAL_IDS = ("ABS_01", "ABS_02", "ABS_03", "ABS_04")
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
VOL_OF_VOL_WINDOW = 10
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
FIRST_HOUR_MINUTES = 60
SMALL_OVERNIGHT_MOVE_TICKS = 20

FilterSpec = tuple[str, str, str, Callable[[pd.DataFrame], pd.Series]]


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
    df["direction_sign"] = direction_to_sign(df["direction"])
    df = df[df["direction_sign"] != 0].copy()
    return df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)


def build_absorption_observations(events: pd.DataFrame) -> pd.DataFrame:
    absorption_events = events[events["category"].eq("absorption")].copy()
    observations = (
        absorption_events.groupby(["global_index", "direction_sign"], as_index=False, sort=False)
        .agg(
            session_date=("session_date", "first"),
            bar_ts=("bar_ts", "first"),
            bar_index=("bar_index", "first"),
            signal_id_list=("signal_id", lambda s: sorted(set(s))),
            absorption_strength=("strength", "max"),
            score_final=("score_final", "max"),
            score_tier=("score_tier", "first"),
            bar_open=("bar_open", "first"),
            bar_high=("bar_high", "first"),
            bar_low=("bar_low", "first"),
            bar_close=("bar_close", "first"),
            bar_delta=("bar_delta", "first"),
            bar_volume=("bar_volume", "first"),
            fwd_close_5b=("fwd_close_5b", "first"),
            fwd_close_10b=("fwd_close_10b", "first"),
            fwd_close_30b=("fwd_close_30b", "first"),
        )
        .sort_values(["session_date", "bar_ts", "global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )

    observations["signal_ids"] = observations["signal_id_list"].apply(lambda ids: ",".join(ids))
    observations["absorption_variants"] = observations["signal_id_list"].apply(len).astype("int8")
    for signal_id in ABS_SIGNAL_IDS:
        observations[f"has_{signal_id}"] = observations["signal_id_list"].apply(
            lambda ids, target=signal_id: target in ids
        )

    observations["is_abs_01_only"] = observations["has_ABS_01"] & observations["absorption_variants"].eq(1)
    observations["is_abs_02_only"] = observations["has_ABS_02"] & observations["absorption_variants"].eq(1)
    observations["is_abs_03_only"] = observations["has_ABS_03"] & observations["absorption_variants"].eq(1)
    observations["is_abs_04_only"] = observations["has_ABS_04"] & observations["absorption_variants"].eq(1)
    observations["has_abs_03_abs_04"] = observations["has_ABS_03"] & observations["has_ABS_04"]
    observations["direction"] = np.where(observations["direction_sign"] > 0, "BULLISH", "BEARISH")

    for window in FORWARD_WINDOWS:
        observations[f"ret_{window}b_ticks"] = observations["direction_sign"] * (
            (observations[f"fwd_close_{window}b"] - observations["bar_close"]) / TICK_SIZE
        )

    observations = observations.drop(columns=["signal_id_list"])
    return observations


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
            ],
        ]
        .copy()
        .reset_index(drop=True)
    )


def compute_bar_features(bars: pd.DataFrame) -> pd.DataFrame:
    out = bars.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["body_ratio"] = np.where(out["bar_range"] > 0, out["body"] / out["bar_range"], np.nan)
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
    out["vol_of_vol"] = by_session["atr20"].transform(
        lambda s: s.rolling(VOL_OF_VOL_WINDOW, min_periods=VOL_OF_VOL_WINDOW).std()
    )

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

    out["is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.10 * out["bar_range"])
    out["is_narrow_range"] = out["bar_range"].lt(out["range_q25"])
    out["is_very_narrow_range"] = out["bar_range"].lt(out["range_q10"])
    out["is_range_shrinking"] = out["prior_bar_range"].notna() & out["bar_range"].lt(out["prior_bar_range"])
    out["is_three_narrowing_ranges"] = (
        out["bar_range_2"].notna()
        & out["prior_bar_range"].lt(out["bar_range_2"])
        & out["bar_range"].lt(out["prior_bar_range"])
    )
    out["is_high_volume"] = out["bar_volume"].gt(out["volume_q75"])
    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])
    return out


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


def attach_session_context(
    observations: pd.DataFrame,
    session_summary: pd.DataFrame,
    session_thresholds: dict[str, float],
    overnight_context: pd.DataFrame,
) -> pd.DataFrame:
    session_cols = ["session_date", "prior_session_range"]
    out = observations.merge(session_summary[session_cols], on="session_date", how="left", validate="many_to_one")
    out["prior_session_is_wide_range"] = out["prior_session_range"].ge(session_thresholds["range_q75"])
    out["prior_session_is_wide_range"] = out["prior_session_is_wide_range"].fillna(False).astype(bool)
    out = out.merge(overnight_context, on="session_date", how="left", validate="many_to_one")
    out["overnight_move_sign"] = pd.to_numeric(out["overnight_move_sign"], errors="coerce").fillna(0).astype(int)
    return out


def compute_thresholds(bars: pd.DataFrame) -> dict[str, float]:
    vol_of_vol = bars["vol_of_vol"].dropna()
    return {
        "vol_of_vol_q25": float(vol_of_vol.quantile(0.25)) if not vol_of_vol.empty else float("nan"),
    }


def annotate_observations(observations: pd.DataFrame, thresholds: dict[str, float]) -> pd.DataFrame:
    out = observations.copy()
    out["trade_sign"] = out["direction_sign"]

    rng_60m = out["range_60m"].replace(0, np.nan)
    anchor = np.where(out["trade_sign"] > 0, out["bar_low"], np.where(out["trade_sign"] < 0, out["bar_high"], np.nan))
    out["pos_in_60m"] = (anchor - out["low_60m"]) / rng_60m
    out["is_60m_extreme"] = (
        ((out["trade_sign"] > 0) & out["pos_in_60m"].le(0.20))
        | ((out["trade_sign"] < 0) & out["pos_in_60m"].ge(0.80))
    )
    out["is_15m_trend_aligned"] = out["trade_sign"].eq(out["trend_sign_15m"])
    out["has_core_60m_15m_gate"] = out["is_60m_extreme"] & out["is_15m_trend_aligned"]

    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] * 60 + out["minute"]) - RTH_START_MINUTE
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(FIRST_HOUR_MINUTES)
    lunch_mask = out["minutes_since_930"].ge(150) & out["minutes_since_930"].lt(270)
    out["is_not_lunch"] = ~lunch_mask

    out["is_killer_1"] = out["pos_in_60m"].between(0.40, 0.60, inclusive="both")
    out["is_killer_2"] = out["is_volume_spike_3x"]
    out["passes_not_all_killers"] = (~out["is_killer_1"]) & (~out["is_killer_2"])

    out["is_stable_vol"] = out["vol_of_vol"].lt(thresholds["vol_of_vol_q25"])
    out["is_small_overnight"] = out["abs_overnight_move_ticks"].lt(SMALL_OVERNIGHT_MOVE_TICKS)
    out["has_matching_cvd_divergence"] = out["is_cvd_divergence"] & out["divergence_sign"].eq(out["trade_sign"])

    bool_cols = [
        "has_ABS_01",
        "has_ABS_02",
        "has_ABS_03",
        "has_ABS_04",
        "is_abs_01_only",
        "is_abs_02_only",
        "is_abs_03_only",
        "is_abs_04_only",
        "has_abs_03_abs_04",
        "is_doji",
        "is_narrow_range",
        "is_very_narrow_range",
        "is_range_shrinking",
        "is_three_narrowing_ranges",
        "is_high_volume",
        "is_volume_spike_3x",
        "is_cvd_divergence",
        "prior_session_is_wide_range",
        "is_60m_extreme",
        "is_15m_trend_aligned",
        "has_core_60m_15m_gate",
        "is_first_hour",
        "is_not_lunch",
        "is_killer_1",
        "is_killer_2",
        "passes_not_all_killers",
        "is_stable_vol",
        "is_small_overnight",
        "has_matching_cvd_divergence",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
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
            "ABS_01 only + 60m + 15m + NOT killers",
            lambda df: df["is_abs_01_only"] & df["has_core_60m_15m_gate"] & df["passes_not_all_killers"],
        ),
        (
            "02",
            "A",
            "ABS_02 only + 60m + 15m + NOT killers",
            lambda df: df["is_abs_02_only"] & df["has_core_60m_15m_gate"] & df["passes_not_all_killers"],
        ),
        (
            "03",
            "A",
            "ABS_03 only + 60m + 15m + NOT killers",
            lambda df: df["is_abs_03_only"] & df["has_core_60m_15m_gate"] & df["passes_not_all_killers"],
        ),
        (
            "04",
            "A",
            "ABS_04 only + 60m + 15m + NOT killers",
            lambda df: df["is_abs_04_only"] & df["has_core_60m_15m_gate"] & df["passes_not_all_killers"],
        ),
        (
            "05",
            "A",
            "ABS_03 + ABS_04 same bar + 60m + 15m + NOT killers",
            lambda df: df["has_abs_03_abs_04"] & df["has_core_60m_15m_gate"] & df["passes_not_all_killers"],
        ),
        (
            "06",
            "B",
            "absorption strength >= 0.3 + 60m + 15m",
            lambda df: df["absorption_strength"].ge(0.30) & df["has_core_60m_15m_gate"],
        ),
        (
            "07",
            "B",
            "absorption strength >= 0.5 + 60m + 15m",
            lambda df: df["absorption_strength"].ge(0.50) & df["has_core_60m_15m_gate"],
        ),
        (
            "08",
            "B",
            "absorption strength >= 0.7 + 60m + 15m",
            lambda df: df["absorption_strength"].ge(0.70) & df["has_core_60m_15m_gate"],
        ),
        (
            "09",
            "B",
            "absorption strength >= 0.9 + 60m + 15m",
            lambda df: df["absorption_strength"].ge(0.90) & df["has_core_60m_15m_gate"],
        ),
        (
            "10",
            "B",
            "absorption strength >= 0.5 + 60m + 15m + first_hour + NOT killers",
            lambda df: df["absorption_strength"].ge(0.50)
            & df["has_core_60m_15m_gate"]
            & df["is_first_hour"]
            & df["passes_not_all_killers"],
        ),
        (
            "11",
            "C",
            "absorption + |delta|/vol < 0.05 + 60m + 15m",
            lambda df: df["delta_ratio"].lt(0.05) & df["has_core_60m_15m_gate"],
        ),
        (
            "12",
            "C",
            "absorption + |delta|/vol < 0.10 + 60m + 15m",
            lambda df: df["delta_ratio"].lt(0.10) & df["has_core_60m_15m_gate"],
        ),
        (
            "13",
            "C",
            "absorption + |delta|/vol > 0.30 + 60m + 15m",
            lambda df: df["delta_ratio"].gt(0.30) & df["has_core_60m_15m_gate"],
        ),
        (
            "14",
            "C",
            "absorption + |delta|/vol < 0.05 + 60m + 15m + NOT killers + first_hour",
            lambda df: df["delta_ratio"].lt(0.05)
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
        (
            "15",
            "C",
            "absorption + doji (body<10%) + |delta|/vol < 0.10 + 60m + 15m",
            lambda df: df["is_doji"] & df["delta_ratio"].lt(0.10) & df["has_core_60m_15m_gate"],
        ),
        (
            "16",
            "D",
            "absorption + narrow range (<25th percentile of prior 20 bars) + 60m + 15m",
            lambda df: df["is_narrow_range"] & df["has_core_60m_15m_gate"],
        ),
        (
            "17",
            "D",
            "absorption + very narrow range (<10th percentile of prior 20 bars) + 60m + 15m",
            lambda df: df["is_very_narrow_range"] & df["has_core_60m_15m_gate"],
        ),
        (
            "18",
            "D",
            "absorption + range shrinking vs prior bar + 60m + 15m",
            lambda df: df["is_range_shrinking"] & df["has_core_60m_15m_gate"],
        ),
        (
            "19",
            "D",
            "absorption + narrow range + high volume (>75th percentile of prior 20 bars) + 60m + 15m",
            lambda df: df["is_narrow_range"] & df["is_high_volume"] & df["has_core_60m_15m_gate"],
        ),
        (
            "20",
            "D",
            "absorption + narrow + low delta/vol + 60m + 15m + NOT killers + first_hour",
            lambda df: df["is_narrow_range"]
            & df["delta_ratio"].lt(0.10)
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        ),
        (
            "21",
            "E",
            "absorption + 60m + 15m + NOT lunch + small overnight + NOT killers",
            lambda df: df["has_core_60m_15m_gate"]
            & df["is_not_lunch"]
            & df["is_small_overnight"]
            & df["passes_not_all_killers"],
        ),
        (
            "22",
            "E",
            "absorption + 60m + 15m + NOT lunch + stable vol + NOT killers",
            lambda df: df["has_core_60m_15m_gate"]
            & df["is_not_lunch"]
            & df["is_stable_vol"]
            & df["passes_not_all_killers"],
        ),
        (
            "23",
            "E",
            "absorption + 60m + 15m + prior wide-range day + NOT killers",
            lambda df: df["has_core_60m_15m_gate"]
            & df["prior_session_is_wide_range"]
            & df["passes_not_all_killers"],
        ),
        (
            "24",
            "E",
            "absorption + CVD divergence + 60m + 15m + NOT killers",
            lambda df: df["has_matching_cvd_divergence"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
        ),
        (
            "25",
            "E",
            "absorption + 60m + 15m + 3 narrowing ranges + NOT killers",
            lambda df: df["is_three_narrowing_ranges"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
        ),
    ]


def run_filters(df: pd.DataFrame) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for code, group, label, predicate in build_filter_specs():
        mask = predicate(df)
        results.append(summarize_filter(code, group, label, df.loc[mask].copy()))
    return results


def sorted_results(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    def score(value: object) -> float:
        if value is None or pd.isna(value):
            return -1.0
        return float(value)

    return sorted(
        rows,
        key=lambda row: (
            pd.isna(row["wr_30b"]),
            -score(row["wr_30b"]),
            -score(row["wr_10b"]),
            -score(row["wr_5b"]),
            -int(row["n"]),
            str(row["code"]),
        ),
    )


def render_table(rows: list[dict[str, object]]) -> list[str]:
    headers = [
        "Rank",
        "Code",
        "Group",
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

    for rank, row in enumerate(sorted_results(rows), start=1):
        data_rows.append(
            [
                str(rank),
                str(row["code"]),
                str(row["group"]),
                str(row["label"]),
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
    absorption_observations = build_absorption_observations(events)
    all_bars = build_bar_frame(events)
    bar_features = compute_bar_features(all_bars)
    session_summary, session_thresholds = build_session_summary(all_bars)
    overnight_context = build_overnight_context(filter_rth_bars(bars_1m))
    context = build_timeframe_context(bars_1m)
    thresholds = compute_thresholds(bar_features)

    bar_feature_cols = [
        "global_index",
        "bar_range",
        "body",
        "body_ratio",
        "abs_delta",
        "delta_ratio",
        "prior_bar_range",
        "bar_range_2",
        "range_q25",
        "range_q10",
        "volume_q75",
        "rolling_20_ema_vol",
        "atr20",
        "vol_of_vol",
        "divergence_sign",
        "is_cvd_divergence",
        "is_doji",
        "is_narrow_range",
        "is_very_narrow_range",
        "is_range_shrinking",
        "is_three_narrowing_ranges",
        "is_high_volume",
        "is_volume_spike_3x",
    ]
    observations = absorption_observations.merge(
        bar_features[bar_feature_cols],
        on="global_index",
        how="left",
        validate="many_to_one",
    )
    observations = attach_timeframe_context(observations, context)
    observations = attach_session_context(observations, session_summary, session_thresholds, overnight_context)
    observations = annotate_observations(observations, thresholds)

    baseline_all = summarize_filter("00", "BASE", "All absorption observations", observations)
    baseline_core = summarize_filter(
        "00A",
        "BASE",
        "absorption + 60m + 15m",
        observations.loc[observations["has_core_60m_15m_gate"]].copy(),
    )
    baseline_core_not_killers = summarize_filter(
        "00B",
        "BASE",
        "absorption + 60m + 15m + NOT killers",
        observations.loc[observations["has_core_60m_15m_gate"] & observations["passes_not_all_killers"]].copy(),
    )
    results = run_filters(observations)

    lines = [
        "DEEP6 round29 absorption microstructure analysis",
        "============================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique absorption observation grouped by global_index + direction_sign using only category == 'absorption'.",
        "Direction uses signal_events.direction_sign, not bar_delta, so bullish/bearish absorption keeps its explicit signal direction.",
        "60m/15m context comes from nq_1yr_1m.csv. Delta/volume, bar-range, vol-of-vol, and CVD features come from all unique signal bars merged back by global_index.",
        "Delta/vol follows round12: abs(bar_delta) / bar_volume. Narrow/high-volume thresholds use the prior 20 bars within each session. Stable vol = vol_of_vol below the 25th percentile, where vol_of_vol is the 10-bar std of ATR20.",
        "Small overnight follows round14: current 09:30 RTH open minus prior RTH close, in ticks, with the requested <20 tick cutoff.",
        "CVD divergence follows round8 and must match the absorption direction for filter 24.",
        "Requested filters are ranked by 30b WR; the Code column preserves the original request order.",
        "N / PF / Avg Ticks / Wilson CI use the 5-bar sample. WR10 and WR30 use the same fully-available sample per row.",
        "Persistence: GROWING if WR30 > WR5; STABLE if WR30 is within 3 percentage points of WR5 without growth; DECAYING otherwise.",
        "",
        f"Raw event rows loaded:                    {len(events):,}",
        f"Raw absorption event rows:                {int(events['category'].eq('absorption').sum()):,}",
        f"Unique all-signal bars:                   {len(all_bars):,}",
        f"Absorption observations:                  {len(observations):,}",
        f"15m bars built from nq_1yr_1m:           {len(context[15]):,}",
        f"60m bars built from nq_1yr_1m:           {len(context[60]):,}",
        f"Core 60m + 15m observations:             {int(observations['has_core_60m_15m_gate'].sum()):,}",
        f"Core 60m + 15m + NOT killers:            {int((observations['has_core_60m_15m_gate'] & observations['passes_not_all_killers']).sum()):,}",
        f"Stable-vol observations:                  {int(observations['is_stable_vol'].sum()):,}",
        f"Small-overnight observations:             {int(observations['is_small_overnight'].sum()):,}",
        f"Prior wide-range-day observations:        {int(observations['prior_session_is_wide_range'].sum()):,}",
        f"Matching CVD divergence observations:     {int(observations['has_matching_cvd_divergence'].sum()):,}",
        f"ABS_01 only observations:                 {int(observations['is_abs_01_only'].sum()):,}",
        f"ABS_02 only observations:                 {int(observations['is_abs_02_only'].sum()):,}",
        f"ABS_03 only observations:                 {int(observations['is_abs_03_only'].sum()):,}",
        f"ABS_04 only observations:                 {int(observations['is_abs_04_only'].sum()):,}",
        f"ABS_03 + ABS_04 same-observation count:   {int(observations['has_abs_03_abs_04'].sum()):,}",
        f"Stable-vol threshold (vol_of_vol q25):    {fmt_float(thresholds['vol_of_vol_q25'])}",
        f"Prior wide-range threshold (range q75):   {fmt_float(session_thresholds['range_q75'])}",
        "",
        "Baselines",
        "---------",
        f"All absorption observations:          {render_summary_line(baseline_all)}",
        f"absorption + 60m + 15m:              {render_summary_line(baseline_core)}",
        f"absorption + 60m + 15m + NOT killers:{render_summary_line(baseline_core_not_killers)}",
        "",
        "25 requested absorption micro filters ranked by 30b WR",
        "-----------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
