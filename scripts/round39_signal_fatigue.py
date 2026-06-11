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
OUT_PATH = OUT_DIR / "round39_signal_fatigue_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
FIRST_HOUR_MINUTES = 60

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
    df["category"] = df["category"].astype("string").str.lower()
    df["signal_id"] = df["signal_id"].astype("string").str.upper()
    return df.sort_values(["session_date", "bar_ts", "global_index", "signal_id"], kind="stable").reset_index(drop=True)


def build_observations(events: pd.DataFrame) -> pd.DataFrame:
    working = events.copy()
    working["is_absorption"] = working["category"].eq("absorption")

    observations = (
        working.groupby("global_index", as_index=False, sort=False)
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
            has_absorption=("is_absorption", "max"),
        )
        .sort_values(["session_date", "bar_ts", "global_index"], kind="stable")
        .reset_index(drop=True)
    )

    observations["direction_sign"] = np.sign(observations["bar_delta"].fillna(0.0)).astype(int)
    observations = observations.loc[observations["direction_sign"] != 0].copy()
    observations["direction"] = np.where(observations["direction_sign"] > 0, "BULLISH", "BEARISH")
    for window in FORWARD_WINDOWS:
        observations[f"ret_{window}b_ticks"] = observations["direction_sign"] * (
            (observations[f"fwd_close_{window}b"] - observations["bar_close"]) / TICK_SIZE
        )
    observations["has_absorption"] = observations["has_absorption"].fillna(False).astype(bool)
    return observations.reset_index(drop=True)


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

    return df.reset_index(drop=True)


def filter_rth_bars(bars_1m: pd.DataFrame) -> pd.DataFrame:
    bars = bars_1m.copy()
    minute_of_day = bars["ts_event"].dt.hour * 60 + bars["ts_event"].dt.minute
    bars = bars.loc[(minute_of_day >= RTH_START_MINUTE) & (minute_of_day < RTH_END_MINUTE)].copy()
    bars["session_date"] = bars["ts_event"].dt.strftime("%Y-%m-%d")
    bars["minutes_since_930"] = minute_of_day.loc[bars.index] - RTH_START_MINUTE
    return bars.reset_index(drop=True)


def build_rth_context(bars_1m: pd.DataFrame) -> pd.DataFrame:
    bars = filter_rth_bars(bars_1m)
    by_session = bars.groupby("session_date", sort=False)

    bars["rolling_20_ema_vol"] = by_session["volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    bars["is_volume_spike_3x"] = bars["rolling_20_ema_vol"].gt(0) & bars["volume"].gt(3.0 * bars["rolling_20_ema_vol"])
    bars["is_first_hour"] = bars["minutes_since_930"].ge(0) & bars["minutes_since_930"].lt(FIRST_HOUR_MINUTES)

    return bars[
        [
            "ts_event",
            "minutes_since_930",
            "rolling_20_ema_vol",
            "is_volume_spike_3x",
            "is_first_hour",
        ]
    ].copy()


def merge_rth_context(observations: pd.DataFrame, rth_context: pd.DataFrame) -> pd.DataFrame:
    out = observations.merge(
        rth_context,
        left_on="bar_ts",
        right_on="ts_event",
        how="left",
        validate="many_to_one",
    ).drop(columns=["ts_event"])

    for col in ["is_volume_spike_3x", "is_first_hour"]:
        out[col] = out[col].fillna(False).astype(bool)
    return out.reset_index(drop=True)


def compute_bar_features(observations: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.10 * out["bar_range"])
    out["is_doji"] = out["is_doji"].fillna(False).astype(bool)
    return out


def add_context_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["is_15m_trend_aligned"] = out["direction_sign"].eq(out["trend_sign_15m"])

    rng_60m = out["range_60m"].replace(0, np.nan)
    anchor = np.where(out["direction_sign"] > 0, out["bar_low"], out["bar_high"])
    out["pos_60m"] = (anchor - out["low_60m"]) / rng_60m
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
        "is_killer_1",
        "is_killer_2",
        "passes_not_all_killers",
        "has_core_60m_15m_gate",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out.reset_index(drop=True)


def merge_subset_sequence_features(df: pd.DataFrame, subset_mask: pd.Series, prefix: str) -> pd.DataFrame:
    subset = df.loc[subset_mask].sort_values(["session_date", "bar_index", "global_index"], kind="stable").copy()

    subset[f"{prefix}_ordinal_session"] = (subset.groupby("session_date", sort=False).cumcount() + 1).astype("Int32")
    subset[f"{prefix}_bars_since_prev"] = subset.groupby("session_date", sort=False)["bar_index"].diff()
    subset[f"{prefix}_bars_until_next"] = subset.groupby("session_date", sort=False)["bar_index"].shift(-1) - subset["bar_index"]
    subset[f"{prefix}_is_last_session"] = subset.groupby("session_date", sort=False)["bar_index"].transform("max").eq(
        subset["bar_index"]
    )

    feature_cols = [
        f"{prefix}_ordinal_session",
        f"{prefix}_bars_since_prev",
        f"{prefix}_bars_until_next",
        f"{prefix}_is_last_session",
    ]
    out = df.merge(subset[["global_index", *feature_cols]], on="global_index", how="left", validate="one_to_one")
    out[f"{prefix}_is_last_session"] = out[f"{prefix}_is_last_session"].fillna(False).astype(bool)
    return out.reset_index(drop=True)


def add_prior_nonqualifying_streak(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values(["session_date", "bar_index", "global_index"], kind="stable").copy()
    values = pd.Series(0, index=out.index, dtype="int32")

    for _, group in out.groupby("session_date", sort=False):
        qualifying = group["has_core_60m_15m_gate"].to_numpy(dtype=bool)
        streak_before = np.zeros(len(group), dtype=np.int32)
        streak = 0

        for idx, is_qualifying in enumerate(qualifying):
            if is_qualifying:
                streak_before[idx] = streak
                streak = 0
            else:
                streak += 1

        values.loc[group.index] = streak_before

    out["prior_nonqualifying_observation_streak"] = values.astype("int32")
    return out.reset_index(drop=True)


def add_fatigue_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values(["session_date", "bar_index", "global_index"], kind="stable").reset_index(drop=True).copy()
    out = merge_subset_sequence_features(out, out["has_core_60m_15m_gate"], "qualifying")
    out = merge_subset_sequence_features(out, out["has_core_60m_15m_gate"] & out["is_doji"], "doji_core")
    out = merge_subset_sequence_features(out, out["has_core_60m_15m_gate"] & out["has_absorption"], "absorption_core")
    out = add_prior_nonqualifying_streak(out)
    return out.reset_index(drop=True)


def build_filter_specs() -> list[FilterSpec]:
    def core(df: pd.DataFrame) -> pd.Series:
        return df["has_core_60m_15m_gate"]

    def core_best(df: pd.DataFrame) -> pd.Series:
        return df["has_core_60m_15m_gate"] & df["is_first_hour"] & df["passes_not_all_killers"]

    return [
        (
            "01",
            "A",
            "1st doji of session + 60m + 15m (fresh)",
            lambda df: core(df) & df["is_doji"] & df["doji_core_ordinal_session"].eq(1),
        ),
        (
            "02",
            "A",
            "2nd doji of session + 60m + 15m",
            lambda df: core(df) & df["is_doji"] & df["doji_core_ordinal_session"].eq(2),
        ),
        (
            "03",
            "A",
            "3rd+ doji of session + 60m + 15m",
            lambda df: core(df) & df["is_doji"] & df["doji_core_ordinal_session"].ge(3),
        ),
        (
            "04",
            "A",
            "1st doji of session + 60m + 15m + first_hour + NOT killers",
            lambda df: core_best(df) & df["is_doji"] & df["doji_core_ordinal_session"].eq(1),
        ),
        (
            "05",
            "A",
            "3rd+ doji of session + 60m + 15m + first_hour + NOT killers",
            lambda df: core_best(df) & df["is_doji"] & df["doji_core_ordinal_session"].ge(3),
        ),
        (
            "06",
            "B",
            "1st qualifying bar of session + 60m + 15m (virgin signal)",
            lambda df: core(df) & df["qualifying_ordinal_session"].eq(1),
        ),
        (
            "07",
            "B",
            "2nd qualifying bar of session + 60m + 15m",
            lambda df: core(df) & df["qualifying_ordinal_session"].eq(2),
        ),
        (
            "08",
            "B",
            "3rd qualifying bar of session + 60m + 15m",
            lambda df: core(df) & df["qualifying_ordinal_session"].eq(3),
        ),
        (
            "09",
            "B",
            "5th+ qualifying bar of session + 60m + 15m",
            lambda df: core(df) & df["qualifying_ordinal_session"].ge(5),
        ),
        (
            "10",
            "B",
            "10th+ qualifying bar of session + 60m + 15m",
            lambda df: core(df) & df["qualifying_ordinal_session"].ge(10),
        ),
        (
            "11",
            "C",
            "1st absorption of session + 60m + 15m",
            lambda df: core(df) & df["has_absorption"] & df["absorption_core_ordinal_session"].eq(1),
        ),
        (
            "12",
            "C",
            "2nd absorption of session + 60m + 15m",
            lambda df: core(df) & df["has_absorption"] & df["absorption_core_ordinal_session"].eq(2),
        ),
        (
            "13",
            "C",
            "3rd+ absorption of session + 60m + 15m",
            lambda df: core(df) & df["has_absorption"] & df["absorption_core_ordinal_session"].ge(3),
        ),
        (
            "14",
            "D",
            ">30 bars since last qualifying bar + 60m + 15m",
            lambda df: core(df) & df["qualifying_bars_since_prev"].gt(30),
        ),
        (
            "15",
            "D",
            "5-15 bars since last qualifying bar + 60m + 15m",
            lambda df: core(df) & df["qualifying_bars_since_prev"].between(5, 15, inclusive="both"),
        ),
        (
            "16",
            "D",
            "<5 bars since last qualifying bar + 60m + 15m",
            lambda df: core(df) & df["qualifying_bars_since_prev"].lt(5),
        ),
        (
            "17",
            "D",
            ">30 bars gap + 60m + 15m + NOT killers + first_hour",
            lambda df: core_best(df) & df["qualifying_bars_since_prev"].gt(30),
        ),
        (
            "18",
            "E",
            "Qualifying bar after 60+ bar gap in qualifying signals + 60m + 15m",
            lambda df: core(df) & df["qualifying_bars_since_prev"].ge(60),
        ),
        (
            "19",
            "E",
            "Qualifying bar after 3+ consecutive non-qualifying observation bars + 60m + 15m",
            lambda df: core(df) & df["prior_nonqualifying_observation_streak"].ge(3),
        ),
        (
            "20",
            "E",
            "Last qualifying bar of session + 60m + 15m (terminal, hindsight-only)",
            lambda df: core(df) & df["qualifying_is_last_session"],
        ),
    ]


def summarize_filter(code: str, group: str, label: str, sample: pd.DataFrame) -> dict[str, object]:
    required_cols = [f"ret_{window}b_ticks" for window in FORWARD_WINDOWS]
    clean = sample.dropna(subset=required_cols).copy()
    n = int(len(clean))
    win_rates: dict[int, float] = {window: np.nan for window in FORWARD_WINDOWS}

    for window in FORWARD_WINDOWS:
        returns = clean[f"ret_{window}b_ticks"]
        win_rates[window] = float((returns > 0).mean()) if n else np.nan

    returns_5b = clean["ret_5b_ticks"]
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
        mask = predicate(df).fillna(False)
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

    observations = build_observations(events)
    context = build_timeframe_context(bars_1m)
    rth_context = build_rth_context(bars_1m)

    observations = attach_timeframe_context(observations, context)
    observations = merge_rth_context(observations, rth_context)
    observations = compute_bar_features(observations)
    observations = add_context_flags(observations)
    observations = add_fatigue_features(observations)

    core = observations.loc[observations["has_core_60m_15m_gate"]].copy()
    doji_core = observations.loc[observations["has_core_60m_15m_gate"] & observations["is_doji"]].copy()
    absorption_core = observations.loc[observations["has_core_60m_15m_gate"] & observations["has_absorption"]].copy()
    core_first_hour_not_killers = observations.loc[
        observations["has_core_60m_15m_gate"] & observations["is_first_hour"] & observations["passes_not_all_killers"]
    ].copy()

    baseline_all = summarize_filter("00", "BASE", "All directional observations", observations)
    baseline_core = summarize_filter("00A", "BASE", "All qualifying observations + 60m + 15m", core)
    baseline_doji_core = summarize_filter("00B", "BASE", "Doji + 60m + 15m", doji_core)
    baseline_absorption_core = summarize_filter("00C", "BASE", "Absorption + 60m + 15m", absorption_core)
    baseline_best = summarize_filter(
        "00D",
        "BASE",
        "Qualifying observations + 60m + 15m + first_hour + NOT killers",
        core_first_hour_not_killers,
    )
    results = run_filters(observations)

    lines = [
        "DEEP6 round39 signal fatigue analysis",
        "====================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal-event bar grouped by global_index only, then traded in the direction of sign(bar_delta).",
        "Rows with bar_delta == 0 are excluded because the bar has no implied trade direction under this round's rules.",
        "60m_extreme = bullish bar_low in bottom 20% of 60m range / bearish bar_high in top 20%. 15m_trend_aligned = sign(bar_delta) matches the 15m open-close sign.",
        "NOT killers = NOT killer_1 (60m position between 40%-60%) AND NOT killer_2 (bar_volume > 3x prior 20-bar EMA volume on RTH 1m bars).",
        "Doji fatigue ordinals are counted only across doji bars that already pass the 60m + 15m gate. Absorption fatigue ordinals are counted only across absorption bars that already pass the same gate.",
        "Qualifying bar spacing uses session bar_index distance between consecutive 60m+15m qualifying bars. Filter 19 uses consecutive non-qualifying observation bars from the deduped signal-events stream, not all 1m bars.",
        "Filter 20 is hindsight-only and non-tradable: it identifies the terminal qualifying signal of the session after the fact.",
        "N uses rows with complete 5b/10b/30b forward closes so all WR windows compare the same sample.",
        "PF and Avg Ticks are based on 5b returns. Persistence compares WR_30b versus WR_5b. Rows are sorted by 30b WR.",
        "",
        f"Raw event rows loaded:                              {len(events):,}",
        f"Directional observations (global_index dedup):      {len(observations):,}",
        f"15m bars built:                                     {len(context[15]):,}",
        f"60m bars built:                                     {len(context[60]):,}",
        f"RTH bars in volume-spike context:                   {len(rth_context):,}",
        f"Qualifying observations with 60m + 15m gate:        {len(core):,}",
        f"Doji + 60m + 15m observations:                      {len(doji_core):,}",
        f"Absorption + 60m + 15m observations:                {len(absorption_core):,}",
        f"Qualifying observations + first_hour + NOT killers: {len(core_first_hour_not_killers):,}",
        f"Terminal qualifying observations (diagnostic):      {int(observations['qualifying_is_last_session'].sum()):,}",
        "",
        f"Baseline all directional observations:        {render_summary_line(baseline_all)}",
        f"Baseline qualifying 60m + 15m:               {render_summary_line(baseline_core)}",
        f"Baseline doji + 60m + 15m:                   {render_summary_line(baseline_doji_core)}",
        f"Baseline absorption + 60m + 15m:             {render_summary_line(baseline_absorption_core)}",
        f"Baseline qualifying + first_hour + NOT killers: {render_summary_line(baseline_best)}",
        "",
        "20 requested signal-fatigue filters ranked by 30b WR",
        "--------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
