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
OUT_PATH = OUT_DIR / "round30_absorption_clustering_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
FIRST_HOUR_MINUTES = 60

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


def distance_to_grid(series: pd.Series, spacing: float, offset: float = 0.0) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    distance = np.full(len(values), np.nan, dtype=float)
    valid = ~np.isnan(values)
    remainder = np.mod(values[valid] - offset, spacing)
    distance[valid] = np.minimum(remainder, spacing - remainder)
    return pd.Series(distance, index=series.index)


def price_distance_ticks(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a - b).abs() / TICK_SIZE


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
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_volume",
        "fwd_close_5b",
        "fwd_close_10b",
        "fwd_close_30b",
    ]
    df = pd.read_csv(EVENTS_CSV, usecols=cols, dtype=dtypes, low_memory=False)
    numeric_cols = [
        "score_final",
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
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
    df["category"] = df["category"].astype("string").str.lower()
    df["signal_id"] = df["signal_id"].astype("string").str.upper()
    return df.sort_values(["session_date", "bar_ts", "global_index", "signal_id"], kind="stable").reset_index(drop=True)


def build_directional_observations(events: pd.DataFrame) -> pd.DataFrame:
    working = events.copy()
    working["is_absorption"] = working["category"].eq("absorption")
    working["is_trap_family"] = working["category"].eq("trap")
    working["is_exhaustion_family"] = working["category"].eq("exhaustion")
    working["is_IMB_03"] = working["signal_id"].eq("IMB_03")
    working["is_DELT_04"] = working["signal_id"].eq("DELT_04")
    working["is_AUCT_03"] = working["signal_id"].eq("AUCT_03")

    observations = (
        working.groupby(["global_index", "direction_sign"], as_index=False, sort=False)
        .agg(
            session_date=("session_date", "first"),
            bar_ts=("bar_ts", "first"),
            bar_index=("bar_index", "first"),
            bar_open=("bar_open", "first"),
            bar_high=("bar_high", "first"),
            bar_low=("bar_low", "first"),
            bar_close=("bar_close", "first"),
            bar_volume=("bar_volume", "first"),
            fwd_close_5b=("fwd_close_5b", "first"),
            fwd_close_10b=("fwd_close_10b", "first"),
            fwd_close_30b=("fwd_close_30b", "first"),
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
            other_category_count=("category", lambda s: s[s != "absorption"].nunique()),
            max_score_final=("score_final", "max"),
            has_absorption=("is_absorption", "max"),
            has_trap_family=("is_trap_family", "max"),
            has_exhaustion_family=("is_exhaustion_family", "max"),
            has_IMB_03=("is_IMB_03", "max"),
            has_DELT_04=("is_DELT_04", "max"),
            has_AUCT_03=("is_AUCT_03", "max"),
        )
        .sort_values(["session_date", "bar_ts", "global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    return observations


def build_absorption_observations(events: pd.DataFrame) -> pd.DataFrame:
    abs_ev = events[events["category"].eq("absorption")].copy()
    observations = (
        abs_ev.groupby(["global_index", "direction_sign"], as_index=False, sort=False)
        .agg(
            session_date=("session_date", "first"),
            bar_ts=("bar_ts", "first"),
            bar_index=("bar_index", "first"),
            bar_open=("bar_open", "first"),
            bar_high=("bar_high", "first"),
            bar_low=("bar_low", "first"),
            bar_close=("bar_close", "first"),
            bar_volume=("bar_volume", "first"),
            fwd_close_5b=("fwd_close_5b", "first"),
            fwd_close_10b=("fwd_close_10b", "first"),
            fwd_close_30b=("fwd_close_30b", "first"),
            absorption_signal_ids=("signal_id", lambda s: ",".join(sorted(set(s)))),
            absorption_variants=("signal_id", "nunique"),
            absorption_score_final=("score_final", "max"),
        )
        .sort_values(["session_date", "bar_ts", "global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    observations["direction"] = np.where(observations["direction_sign"] > 0, "BULLISH", "BEARISH")
    for window in FORWARD_WINDOWS:
        observations[f"ret_{window}b_ticks"] = observations["direction_sign"] * (
            (observations[f"fwd_close_{window}b"] - observations["bar_close"]) / TICK_SIZE
        )
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

    for col in ["bar_open", "bar_high", "bar_low", "bar_close", "bar_volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.reset_index(drop=True)


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

    bars["session_high"] = by_session["high"].cummax()
    bars["session_low"] = by_session["low"].cummin()
    bars["cum_pv"] = ((bars["close"] * bars["volume"]).groupby(bars["session_date"], sort=False).cumsum())
    bars["cum_vol"] = by_session["volume"].cumsum()
    bars["session_vwap"] = np.where(bars["cum_vol"] > 0, bars["cum_pv"] / bars["cum_vol"], np.nan)
    bars["rolling_20_ema_vol"] = by_session["volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    bars["is_volume_spike_3x"] = bars["rolling_20_ema_vol"].gt(0) & bars["volume"].gt(3.0 * bars["rolling_20_ema_vol"])
    bars["is_first_hour"] = bars["minutes_since_930"].ge(0) & bars["minutes_since_930"].lt(FIRST_HOUR_MINUTES)

    daily = (
        bars.groupby("session_date", as_index=False, sort=False)
        .agg(prior_day_close_source=("close", "last"))
        .sort_values("session_date", kind="stable")
        .reset_index(drop=True)
    )
    daily["prior_day_close"] = daily["prior_day_close_source"].shift(1)
    bars = bars.merge(daily[["session_date", "prior_day_close"]], on="session_date", how="left", validate="many_to_one")

    return bars[
        [
            "ts_event",
            "session_date",
            "bar_index",
            "minutes_since_930",
            "is_first_hour",
            "session_high",
            "session_low",
            "session_vwap",
            "prior_day_close",
            "rolling_20_ema_vol",
            "is_volume_spike_3x",
        ]
    ].copy()


def merge_rth_context(observations: pd.DataFrame, rth_context: pd.DataFrame) -> pd.DataFrame:
    renamed = rth_context.rename(
        columns={
            "session_date": "rth_session_date",
            "bar_index": "rth_bar_index",
        }
    )
    out = observations.merge(
        renamed,
        left_on="bar_ts",
        right_on="ts_event",
        how="left",
        validate="many_to_one",
    ).drop(columns=["ts_event"])
    for col in ["is_first_hour", "is_volume_spike_3x"]:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def add_context_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["is_15m_trend_aligned"] = out["direction_sign"].eq(out["trend_sign_15m"])

    rng_60m = out["range_60m"].replace(0, np.nan)
    out["signal_price"] = np.where(out["direction_sign"] > 0, out["bar_low"], out["bar_high"])
    out["pos_60m"] = (out["signal_price"] - out["low_60m"]) / rng_60m
    out["is_60m_extreme"] = (
        ((out["direction_sign"] > 0) & out["pos_60m"].le(0.20))
        | ((out["direction_sign"] < 0) & out["pos_60m"].ge(0.80))
    )
    out["is_killer_1"] = out["pos_60m"].between(0.40, 0.60, inclusive="both")
    out["is_killer_2"] = out["is_volume_spike_3x"]
    out["passes_not_all_killers"] = (~out["is_killer_1"]) & (~out["is_killer_2"])
    out["has_core_60m_15m_gate"] = out["is_60m_extreme"] & out["is_15m_trend_aligned"]

    bool_cols = [
        "is_15m_trend_aligned",
        "is_60m_extreme",
        "is_first_hour",
        "is_killer_1",
        "is_killer_2",
        "passes_not_all_killers",
        "has_core_60m_15m_gate",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out.reset_index(drop=True)


def add_price_level_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["dist_vwap_ticks"] = price_distance_ticks(out["signal_price"], out["session_vwap"])
    out["dist_prior_close_ticks"] = price_distance_ticks(out["signal_price"], out["prior_day_close"])
    out["major_round_dist_ticks"] = distance_to_grid(out["signal_price"], 100.0) / TICK_SIZE
    out["dist_session_high_ticks"] = price_distance_ticks(out["signal_price"], out["session_high"])
    out["dist_session_low_ticks"] = price_distance_ticks(out["signal_price"], out["session_low"])
    return out


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

    out["abs_ordinal_session"] = out.groupby("session_date", sort=False).cumcount() + 1
    out["abs_ordinal_session_direction"] = out.groupby(["session_date", "direction_sign"], sort=False).cumcount() + 1
    out["is_first_absorption_session"] = out["abs_ordinal_session"].eq(1)
    out["is_first_absorption_session_direction"] = out["abs_ordinal_session_direction"].eq(1)

    prev_bar_index = out.groupby(["session_date", "direction_sign"], sort=False)["bar_index"].shift(1)
    out["prev_abs_gap_bars"] = out["bar_index"] - prev_bar_index
    out["has_prior_abs_gap_3plus"] = out["prev_abs_gap_bars"].ge(4)
    out["has_prior_abs_consecutive"] = out["prev_abs_gap_bars"].eq(1)

    trap_reference = directional.loc[directional["has_trap_family"]].copy()
    exhaustion_reference = directional.loc[directional["has_exhaustion_family"]].copy()
    out["has_future_trap_within_3"] = nearby_reference_flag(out, trap_reference, max_gap=3, direction="future")
    out["has_future_exhaustion_within_3"] = nearby_reference_flag(
        out,
        exhaustion_reference,
        max_gap=3,
        direction="future",
    )
    out["has_prior_trap_within_3"] = nearby_reference_flag(out, trap_reference, max_gap=3, direction="past")

    bool_cols = [
        "is_first_absorption_session",
        "is_first_absorption_session_direction",
        "has_prior_abs_gap_3plus",
        "has_prior_abs_consecutive",
        "has_future_trap_within_3",
        "has_future_exhaustion_within_3",
        "has_prior_trap_within_3",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out.reset_index(drop=True)


def build_filter_specs() -> list[FilterSpec]:
    def base(df: pd.DataFrame) -> pd.Series:
        return df["has_core_60m_15m_gate"]

    def base_not_killers(df: pd.DataFrame) -> pd.Series:
        return df["has_core_60m_15m_gate"] & df["passes_not_all_killers"]

    return [
        (
            "01",
            "A",
            "1 absorption in last 5 bars + 60m + 15m (single baseline)",
            lambda df: base(df) & df["abs_count_last_5"].eq(1),
        ),
        (
            "02",
            "A",
            "2+ absorptions in last 5 bars (same direction) + 60m + 15m (cluster)",
            lambda df: base(df) & df["abs_count_last_5"].ge(2),
        ),
        (
            "03",
            "A",
            "3+ absorptions in last 10 bars (same direction) + 60m + 15m (heavy cluster)",
            lambda df: base(df) & df["abs_count_last_10"].ge(3),
        ),
        (
            "04",
            "A",
            "2+ absorptions in last 3 bars + 60m + 15m (rapid-fire cluster)",
            lambda df: base(df) & df["abs_count_last_3"].ge(2),
        ),
        (
            "05",
            "A",
            "First absorption of session + 60m + 15m (fresh signal)",
            lambda df: base(df) & df["is_first_absorption_session"],
        ),
        (
            "06",
            "B",
            "Absorption -> gap of 3+ bars -> absorption again + 60m + 15m",
            lambda df: base(df) & df["has_prior_abs_gap_3plus"],
        ),
        (
            "07",
            "B",
            "Absorption on consecutive bars + 60m + 15m",
            lambda df: base(df) & df["has_prior_abs_consecutive"],
        ),
        (
            "08",
            "B",
            "Absorption -> TRAP within 3 bars + 60m + 15m",
            lambda df: base(df) & df["has_future_trap_within_3"],
        ),
        (
            "09",
            "B",
            "Absorption -> exhaustion within 3 bars + 60m + 15m",
            lambda df: base(df) & df["has_future_exhaustion_within_3"],
        ),
        (
            "10",
            "B",
            "TRAP -> absorption within 3 bars + 60m + 15m",
            lambda df: base(df) & df["has_prior_trap_within_3"],
        ),
        (
            "11",
            "C",
            "Absorption within 10 ticks of session VWAP + 60m + 15m",
            lambda df: base(df) & df["dist_vwap_ticks"].le(10),
        ),
        (
            "12",
            "C",
            "Absorption within 15 ticks of prior day close + 60m + 15m",
            lambda df: base(df) & df["dist_prior_close_ticks"].le(15),
        ),
        (
            "13",
            "C",
            "Absorption at round number (within 10 ticks of xx00) + 60m + 15m",
            lambda df: base(df) & df["major_round_dist_ticks"].le(10),
        ),
        (
            "14",
            "C",
            "Absorption within 10 ticks of session high + 60m + 15m",
            lambda df: base(df) & df["direction_sign"].lt(0) & df["dist_session_high_ticks"].le(10),
        ),
        (
            "15",
            "C",
            "Absorption within 10 ticks of session low + 60m + 15m",
            lambda df: base(df) & df["direction_sign"].gt(0) & df["dist_session_low_ticks"].le(10),
        ),
        (
            "16",
            "D",
            "Absorption + IMB_03 same bar + 60m + 15m + NOT killers",
            lambda df: base_not_killers(df) & df["has_IMB_03"],
        ),
        (
            "17",
            "D",
            "Absorption + DELT_04 same bar + 60m + 15m + NOT killers",
            lambda df: base_not_killers(df) & df["has_DELT_04"],
        ),
        (
            "18",
            "D",
            "Absorption + AUCT_03 same bar + 60m + 15m + NOT killers",
            lambda df: base_not_killers(df) & df["has_AUCT_03"],
        ),
        (
            "19",
            "D",
            "Absorption + 3+ other categories same bar + 60m + 15m + NOT killers",
            lambda df: base_not_killers(df) & df["other_category_count"].ge(3),
        ),
        (
            "20",
            "D",
            "Absorption + score >= 70 + 60m + 15m + NOT killers + first_hour",
            lambda df: base_not_killers(df) & df["is_first_hour"] & df["max_score_final"].ge(70),
        ),
    ]


def summarize_filter(code: str, group: str, label: str, df: pd.DataFrame) -> dict[str, object]:
    required_cols = [f"ret_{window}b_ticks" for window in FORWARD_WINDOWS]
    sample = df.dropna(subset=required_cols).copy()
    n = int(len(sample))
    win_rates: dict[int, float] = {window: np.nan for window in FORWARD_WINDOWS}

    for window in FORWARD_WINDOWS:
        returns = sample[f"ret_{window}b_ticks"]
        wins = int((returns > 0).sum())
        win_rates[window] = (wins / n) if n else np.nan

    returns_5b = sample["ret_5b_ticks"]
    wins_5b = int((returns_5b > 0).sum())
    ci_low, ci_high, win_rate_5b = wilson_ci(n, wins_5b)

    return {
        "code": code,
        "group": group,
        "label": label,
        "n": n,
        "wr_5b": win_rate_5b if n else np.nan,
        "wr_10b": win_rates[10],
        "wr_30b": win_rates[30],
        "pf_5b": profit_factor(returns_5b) if n else np.nan,
        "avg_ticks_5b": float(returns_5b.mean()) if n else np.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "persistence": classify_persistence(win_rate_5b if n else np.nan, win_rates[30]),
    }


def run_filters(df: pd.DataFrame) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for code, group, label, predicate in build_filter_specs():
        mask = predicate(df)
        results.append(summarize_filter(code, group, label, df.loc[mask].copy()))

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


def render_summary_line(row: dict[str, object]) -> str:
    return (
        f"N={int(row['n']):,} | WR5={fmt_pct(float(row['wr_5b']))} | WR10={fmt_pct(float(row['wr_10b']))} | "
        f"WR30={fmt_pct(float(row['wr_30b']))} | PF5={fmt_float(float(row['pf_5b']))} | "
        f"Avg5={fmt_float(float(row['avg_ticks_5b']))}t | CI5={fmt_ci(float(row['ci_low']), float(row['ci_high']))} | "
        f"Persistence={row['persistence']}"
    )


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
                f"{row['code']}[{row['group']}]. {row['label']}",
                f"{row['n']:,}",
                fmt_pct(float(row["wr_5b"])) if not pd.isna(row["wr_5b"]) else "nan",
                fmt_pct(float(row["wr_10b"])) if not pd.isna(row["wr_10b"]) else "nan",
                fmt_pct(float(row["wr_30b"])) if not pd.isna(row["wr_30b"]) else "nan",
                fmt_float(float(row["pf_5b"])) if not pd.isna(row["pf_5b"]) else "nan",
                fmt_float(float(row["avg_ticks_5b"])) if not pd.isna(row["avg_ticks_5b"]) else "nan",
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

    directional = build_directional_observations(events)
    absorption = build_absorption_observations(events)
    context = build_timeframe_context(bars_1m)
    rth_context = build_rth_context(bars_1m)

    absorption = absorption.merge(
        directional[
            [
                "global_index",
                "direction_sign",
                "signal_count",
                "category_count",
                "other_category_count",
                "max_score_final",
                "has_IMB_03",
                "has_DELT_04",
                "has_AUCT_03",
            ]
        ],
        on=["global_index", "direction_sign"],
        how="left",
        validate="one_to_one",
    )
    for col in ["has_IMB_03", "has_DELT_04", "has_AUCT_03"]:
        absorption[col] = absorption[col].fillna(False).astype(bool)

    absorption = attach_context(absorption, context)
    absorption = merge_rth_context(absorption, rth_context)
    absorption = add_context_flags(absorption)
    absorption = add_price_level_flags(absorption)
    absorption = add_absorption_sequence_flags(absorption, directional)

    baseline_all = summarize_filter("00", "BASE", "All absorption observations", absorption)
    baseline_core = summarize_filter(
        "00A",
        "BASE",
        "All absorption observations + 60m + 15m",
        absorption.loc[absorption["has_core_60m_15m_gate"]].copy(),
    )
    baseline_single = summarize_filter(
        "00B",
        "BASE",
        "Single absorption baseline (1 in last 5 bars) + 60m + 15m",
        absorption.loc[absorption["has_core_60m_15m_gate"] & absorption["abs_count_last_5"].eq(1)].copy(),
    )
    baseline_core_not_killers = summarize_filter(
        "00C",
        "BASE",
        "All absorption observations + 60m + 15m + NOT killers",
        absorption.loc[absorption["has_core_60m_15m_gate"] & absorption["passes_not_all_killers"]].copy(),
    )
    results = run_filters(absorption)

    lines = [
        "DEEP6 round30 absorption clustering analysis",
        "===========================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique absorption bar grouped by (global_index, direction_sign).",
        "Same-bar score / signal_count / category_count / co-fire flags are merged from all same-bar, same-direction signals.",
        "Rolling absorption density and spacing rules are tracked per session_date + direction_sign using event bar_index.",
        "Group B future-confirmation filters (08, 09) anchor on the absorption bar, then look ahead up to 3 bars for trap / exhaustion family confirmation.",
        "60m_extreme = bullish bar_low in bottom 20% of 60m range / bearish bar_high in top 20%. 15m_trend_aligned = signal direction matches 15m open-close sign.",
        "Session VWAP / session high / session low / prior day close / first_hour / volume spike come from RTH 1m context (09:30-16:00 ET).",
        "NOT killers = NOT killer_1 (60m position between 40%-60%) AND NOT killer_2 (bar_volume > 3x prior 20-bar EMA volume).",
        "Round number filter uses xx00 major handles only. Distance thresholds use true NQ ticks at 0.25 points.",
        "N uses rows with complete 5b/10b/30b forward closes so all WR windows compare the same sample.",
        "PF and Avg Ticks are based on 5b returns. Persistence compares WR_30b versus WR_5b. Sorted by 30b WR descending.",
        "",
        f"Raw event rows loaded:                         {len(events):,}",
        f"Grouped directional observations:              {len(directional):,}",
        f"Absorption observations:                       {len(absorption):,}",
        f"15m bars built:                                {len(context[15]):,}",
        f"60m bars built:                                {len(context[60]):,}",
        f"RTH bars in session context:                   {len(rth_context):,}",
        f"Absorption observations with 60m + 15m gate:   {int(absorption['has_core_60m_15m_gate'].sum()):,}",
        f"Absorption observations passing NOT killers:   {int(absorption['passes_not_all_killers'].sum()):,}",
        f"Absorption observations in first_hour:         {int(absorption['is_first_hour'].sum()):,}",
        f"Absorption observations with IMB_03 same bar:  {int(absorption['has_IMB_03'].sum()):,}",
        f"Absorption observations with DELT_04 same bar: {int(absorption['has_DELT_04'].sum()):,}",
        f"Absorption observations with AUCT_03 same bar: {int(absorption['has_AUCT_03'].sum()):,}",
        "",
        f"Baseline all absorption:                 {render_summary_line(baseline_all)}",
        f"Baseline 60m + 15m:                      {render_summary_line(baseline_core)}",
        f"Baseline single (1 in last 5) + 60m+15m: {render_summary_line(baseline_single)}",
        f"Baseline 60m + 15m + NOT killers:        {render_summary_line(baseline_core_not_killers)}",
        "",
        "20 requested absorption-clustering / spacing / level / co-fire filters ranked by 30b WR",
        "-------------------------------------------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
