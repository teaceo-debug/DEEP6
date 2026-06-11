#!/usr/bin/env python3
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data/backtests/signal_events.csv"
OHLCV_CSV = ROOT / "data/backtests/nq_1yr_1m.csv"
OUT_DIR = ROOT / "data/backtests/analysis"
OUT_PATH = OUT_DIR / "round31_entry_optimization_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
ENTRY_OFFSETS = (0, 1, 2)
FORWARD_WINDOW = 5
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
FIRST_HOUR_MINUTES = 60
LUNCH_START_MINUTES = 150
LUNCH_END_MINUTES = 270

Predicate = Callable[[pd.DataFrame], pd.Series]
DirectionFn = Callable[[pd.DataFrame], int | pd.Series]


@dataclass(frozen=True)
class SetupSpec:
    code: str
    label: str
    dataset_key: str
    observation_unit: str
    direction_label: str
    predicate: Predicate
    direction_fn: DirectionFn


@dataclass(frozen=True)
class TimingSpec:
    code: str
    description: str


TIMING_SPECS = (
    TimingSpec("T+0", "Enter on the signal bar close."),
    TimingSpec("T+1", "Enter on the next bar close."),
    TimingSpec("T+2", "Enter two bars after the signal."),
    TimingSpec("T+Best", "Use the best close from T+0/T+1/T+2 (lowest for longs, highest for shorts); ties go to the earliest bar."),
)


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


def fmt_ticks(value: float) -> str:
    if pd.isna(value):
        return "nan"
    if np.isinf(value):
        return "inf"
    return f"{value:+,.2f}t"


def fmt_ci(low: float, high: float) -> str:
    return f"[{low * 100:.1f}%, {high * 100:.1f}%]"


def profit_factor(returns: pd.Series) -> float:
    wins = returns[returns > 0].sum()
    losses = -returns[returns <= 0].sum()
    if losses <= 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / losses)


def sharpe_ratio(returns: pd.Series) -> float:
    if len(returns) <= 1:
        return 0.0
    std = float(returns.std(ddof=1))
    return float(returns.mean() / std) if std > 0 else 0.0


def wilson_ci(n: int, k: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return 0.0, 0.0, 0.0
    p_hat = k / n
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, center - margin), min(1.0, center + margin), p_hat


def render_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    lines = [
        " | ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers)),
        "-+-".join("-" * width for width in widths),
    ]
    for row in rows:
        lines.append(" | ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(row)))
    return lines


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
    ]
    events = pd.read_csv(EVENTS_CSV, usecols=cols, dtype=dtypes, low_memory=False)

    numeric_cols = [
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_delta",
        "bar_volume",
    ]
    for col in numeric_cols:
        events[col] = pd.to_numeric(events[col], errors="coerce")

    events["bar_ts"] = pd.to_datetime(events["bar_ts"], utc=True, errors="coerce").dt.tz_convert(EASTERN)
    events["event_direction_sign"] = direction_to_sign(events["direction"])
    return events.sort_values(["session_date", "bar_ts", "global_index", "signal_id"], kind="stable").reset_index(drop=True)


def load_ohlcv() -> pd.DataFrame:
    bars = pd.read_csv(
        OHLCV_CSV,
        usecols=["ts_event", "open", "high", "low", "close", "volume"],
        parse_dates=["ts_event"],
        low_memory=False,
    )
    bars["ts_event"] = pd.to_datetime(bars["ts_event"], utc=True).dt.tz_convert(EASTERN)
    return bars.sort_values("ts_event").reset_index(drop=True)


def prepare_rth_bars(bars_1m: pd.DataFrame) -> pd.DataFrame:
    bars = bars_1m.copy()
    minute_of_day = bars["ts_event"].dt.hour * 60 + bars["ts_event"].dt.minute
    bars = bars[(minute_of_day >= RTH_START_MINUTE) & (minute_of_day < RTH_END_MINUTE)].copy()

    bars["session_date"] = bars["ts_event"].dt.strftime("%Y-%m-%d")
    bars["bar_index"] = bars.groupby("session_date", sort=False).cumcount().astype("int32")

    by_session = bars.groupby("session_date", sort=False)
    for offset in ENTRY_OFFSETS:
        if offset == 0:
            bars[f"entry_close_t{offset}"] = bars["close"]
        else:
            bars[f"entry_close_t{offset}"] = by_session["close"].shift(-offset)
        bars[f"exit_close_t{offset}"] = by_session["close"].shift(-(offset + FORWARD_WINDOW))

    return bars.reset_index(drop=True)


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
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
        )
        .sort_values(["session_date", "bar_ts", "global_index"], kind="stable")
        .reset_index(drop=True)
    )
    observations["direction_sign"] = np.sign(observations["bar_delta"].fillna(0.0)).astype(int)
    return observations


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
            signal_count=("signal_id", "nunique"),
        )
        .rename(columns={"event_direction_sign": "direction_sign"})
        .sort_values(["session_date", "bar_ts", "global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
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


def attach_entry_context(observations: pd.DataFrame, rth_bars: pd.DataFrame) -> pd.DataFrame:
    merge_cols = ["ts_event", "session_date", "bar_index"]
    merge_cols.extend([f"entry_close_t{offset}" for offset in ENTRY_OFFSETS])
    merge_cols.extend([f"exit_close_t{offset}" for offset in ENTRY_OFFSETS])

    context = rth_bars[merge_cols].rename(
        columns={
            "ts_event": "bar_ts",
            "session_date": "rth_session_date",
            "bar_index": "rth_bar_index",
        }
    )
    return observations.merge(context, on="bar_ts", how="left", validate="many_to_one")


def add_time_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] * 60 + out["minute"]) - RTH_START_MINUTE
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(FIRST_HOUR_MINUTES)
    lunch_mask = out["minutes_since_930"].ge(LUNCH_START_MINUTES) & out["minutes_since_930"].lt(LUNCH_END_MINUTES)
    out["is_not_lunch"] = out["minutes_since_930"].notna() & (~lunch_mask)
    out["is_first_hour"] = out["is_first_hour"].fillna(False).astype(bool)
    out["is_not_lunch"] = out["is_not_lunch"].fillna(False).astype(bool)
    return out


def compute_bar_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.10 * out["bar_range"])
    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])

    out["delta_ratio"] = np.where(out["bar_volume"] > 0, out["bar_delta"].abs() / out["bar_volume"], np.nan)
    out["price_color_sign"] = np.sign(out["bar_close"] - out["bar_open"]).astype(int)
    out["body_mid"] = (out["bar_open"] + out["bar_close"]) / 2.0

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

    bool_cols = [
        "is_doji",
        "is_volume_spike_3x",
        "is_morning_star",
        "is_evening_star",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def compute_cvd_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
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

    bool_cols = ["is_bullish_cvd_divergence", "is_bearish_cvd_divergence", "is_cvd_divergence"]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def normalize_direction(direction: int | pd.Series, df: pd.DataFrame) -> pd.Series:
    if isinstance(direction, pd.Series):
        series = direction.reindex(df.index)
    else:
        series = pd.Series(direction, index=df.index)
    series = pd.to_numeric(series, errors="coerce").fillna(0.0)
    return pd.Series(np.sign(series), index=df.index).astype(int)


def anchor_pos_60m(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    rng_60m = df["range_60m"].replace(0, np.nan)
    anchor = np.where(direction_sign > 0, df["bar_low"], np.where(direction_sign < 0, df["bar_high"], np.nan))
    return pd.Series((anchor - df["low_60m"]) / rng_60m, index=df.index)


def is_15m_trend_aligned_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    return direction_sign.ne(0) & direction_sign.eq(df["trend_sign_15m"])


def has_core_60m_15m_gate_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    pos_60m = anchor_pos_60m(df, direction_sign)
    is_60m_extreme = ((direction_sign > 0) & pos_60m.le(0.20)) | ((direction_sign < 0) & pos_60m.ge(0.80))
    return is_60m_extreme & is_15m_trend_aligned_for(df, direction_sign)


def passes_not_all_killers_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    pos_60m = anchor_pos_60m(df, direction_sign)
    not_middle_60m = ~pos_60m.between(0.40, 0.60, inclusive="both")
    return direction_sign.ne(0) & not_middle_60m & (~df["is_volume_spike_3x"])


def build_setup_specs() -> list[SetupSpec]:
    return [
        SetupSpec(
            code="A",
            label="60m + 15m + NOT killers + first_hour",
            dataset_key="bar",
            observation_unit="global_index (unique signal bar)",
            direction_label="trade direction = sign(bar_delta)",
            predicate=lambda df: df["direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & passes_not_all_killers_for(df, df["direction_sign"])
            & df["is_first_hour"],
            direction_fn=lambda df: df["direction_sign"],
        ),
        SetupSpec(
            code="B",
            label="Doji + 60m + 15m + NOT killers",
            dataset_key="bar",
            observation_unit="global_index (unique signal bar)",
            direction_label="trade direction = sign(bar_delta)",
            predicate=lambda df: df["is_doji"]
            & df["direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & passes_not_all_killers_for(df, df["direction_sign"]),
            direction_fn=lambda df: df["direction_sign"],
        ),
        SetupSpec(
            code="C",
            label="CVD divergence + 60m + 15m",
            dataset_key="bar",
            observation_unit="global_index (unique signal bar)",
            direction_label="trade direction = divergence_sign",
            predicate=lambda df: df["is_cvd_divergence"] & has_core_60m_15m_gate_for(df, df["divergence_sign"]),
            direction_fn=lambda df: df["divergence_sign"],
        ),
        SetupSpec(
            code="D",
            label="absorption + 60m + 15m + NOT lunch",
            dataset_key="absorption",
            observation_unit="global_index + direction (unique absorption signal direction)",
            direction_label="trade direction = signal direction",
            predicate=lambda df: df["direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & df["is_not_lunch"],
            direction_fn=lambda df: df["direction_sign"],
        ),
        SetupSpec(
            code="E",
            label="Morning/evening star + 60m + 15m + NOT killers",
            dataset_key="bar",
            observation_unit="global_index (unique signal bar)",
            direction_label="trade direction = star_direction_sign",
            predicate=lambda df: df["star_direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["star_direction_sign"])
            & passes_not_all_killers_for(df, df["star_direction_sign"]),
            direction_fn=lambda df: df["star_direction_sign"],
        ),
    ]


def build_setup_sample(source_df: pd.DataFrame, spec: SetupSpec) -> pd.DataFrame:
    mask = spec.predicate(source_df).fillna(False)
    filtered = source_df.loc[mask].copy()

    direction = spec.direction_fn(source_df)
    if isinstance(direction, pd.Series):
        direction = direction.loc[mask]

    filtered["trade_sign"] = normalize_direction(direction, filtered)
    filtered = filtered.loc[filtered["trade_sign"].ne(0)].copy()
    return filtered.reset_index(drop=True)


def build_timing_sample(sample: pd.DataFrame, timing: TimingSpec) -> pd.DataFrame:
    if timing.code != "T+Best":
        offset = int(timing.code.replace("T+", ""))
        entry_col = f"entry_close_t{offset}"
        exit_col = f"exit_close_t{offset}"
        clean = sample.dropna(subset=[entry_col, exit_col]).copy()
        clean["selected_entry_offset"] = offset
        clean["entry_close"] = clean[entry_col]
        clean["exit_close_5b"] = clean[exit_col]
        clean["ret_5b_ticks"] = clean["trade_sign"] * ((clean["exit_close_5b"] - clean["entry_close"]) / TICK_SIZE)
        return clean.reset_index(drop=True)

    required_cols = [f"entry_close_t{offset}" for offset in ENTRY_OFFSETS]
    required_cols.extend(f"exit_close_t{offset}" for offset in ENTRY_OFFSETS)
    clean = sample.dropna(subset=required_cols).copy()
    if clean.empty:
        return clean

    entry_matrix = clean[[f"entry_close_t{offset}" for offset in ENTRY_OFFSETS]].to_numpy(dtype=float)
    exit_matrix = clean[[f"exit_close_t{offset}" for offset in ENTRY_OFFSETS]].to_numpy(dtype=float)
    trade_sign = clean["trade_sign"].to_numpy(dtype=int)
    selected_offsets = np.zeros(len(clean), dtype=int)

    long_mask = trade_sign > 0
    short_mask = trade_sign < 0
    if long_mask.any():
        selected_offsets[long_mask] = np.argmin(entry_matrix[long_mask], axis=1)
    if short_mask.any():
        selected_offsets[short_mask] = np.argmax(entry_matrix[short_mask], axis=1)

    row_index = np.arange(len(clean))
    clean["selected_entry_offset"] = selected_offsets
    clean["entry_close"] = entry_matrix[row_index, selected_offsets]
    clean["exit_close_5b"] = exit_matrix[row_index, selected_offsets]
    clean["ret_5b_ticks"] = clean["trade_sign"] * ((clean["exit_close_5b"] - clean["entry_close"]) / TICK_SIZE)
    return clean.reset_index(drop=True)


def summarize_timing(sample: pd.DataFrame, timing: TimingSpec) -> dict[str, object]:
    timing_sample = build_timing_sample(sample, timing)
    returns = timing_sample["ret_5b_ticks"].dropna()
    n = int(len(returns))
    wins = int((returns > 0).sum())
    ci_low, ci_high, win_rate = wilson_ci(n, wins)

    selection_counts: dict[int, int] | None = None
    if timing.code == "T+Best" and not timing_sample.empty:
        selection_counts = {
            offset: int(count)
            for offset, count in timing_sample["selected_entry_offset"].value_counts().reindex(list(ENTRY_OFFSETS), fill_value=0).items()
        }

    return {
        "timing": timing.code,
        "description": timing.description,
        "n": n,
        "win_rate": win_rate if n else np.nan,
        "profit_factor": profit_factor(returns) if n else np.nan,
        "avg_ticks": float(returns.mean()) if n else np.nan,
        "sharpe": sharpe_ratio(returns) if n else np.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "selection_counts": selection_counts,
    }


def pick_best_timing(rows: list[dict[str, object]], key: str) -> dict[str, object] | None:
    valid = [row for row in rows if not pd.isna(row[key])]
    if not valid:
        return None
    return max(
        valid,
        key=lambda row: (
            float(row[key]),
            float(row["profit_factor"]),
            float(row["avg_ticks"]),
            -int(row["n"]),
        ),
    )


def evaluate_setup(spec: SetupSpec, datasets: dict[str, pd.DataFrame]) -> dict[str, object]:
    sample = build_setup_sample(datasets[spec.dataset_key], spec)
    timing_rows = [summarize_timing(sample, timing) for timing in TIMING_SPECS]
    return {
        "sample_n": int(len(sample)),
        "timing_rows": timing_rows,
        "sharpe_leader": pick_best_timing(timing_rows, "sharpe"),
        "avg_leader": pick_best_timing(timing_rows, "avg_ticks"),
    }


def build_analysis_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    events = load_events()
    bars_1m = load_ohlcv()
    rth_bars = prepare_rth_bars(bars_1m)
    context = build_timeframe_context(bars_1m)

    bar_frame = build_bar_observations(events)
    bar_frame = attach_context(bar_frame, context)
    bar_frame = attach_entry_context(bar_frame, rth_bars)
    bar_frame = add_time_flags(bar_frame)
    bar_frame = compute_bar_features(bar_frame)
    bar_frame = compute_cvd_features(bar_frame)

    absorption_frame = build_absorption_observations(events)
    absorption_frame = attach_context(absorption_frame, context)
    absorption_frame = attach_entry_context(absorption_frame, rth_bars)
    absorption_frame = add_time_flags(absorption_frame)

    return bar_frame, absorption_frame, rth_bars


def render_overview_table(results: list[tuple[SetupSpec, dict[str, object]]]) -> list[str]:
    headers = ["Setup", "Entry", "N", "WR", "PF", "Avg", "Sharpe", "Wilson 95% CI"]
    rows: list[list[str]] = []

    for spec, result in results:
        for row in result["timing_rows"]:
            rows.append(
                [
                    f"{spec.code}. {spec.label}",
                    str(row["timing"]),
                    f"{int(row['n']):,}",
                    fmt_pct(float(row["win_rate"])),
                    fmt_float(float(row["profit_factor"])),
                    fmt_ticks(float(row["avg_ticks"])),
                    fmt_float(float(row["sharpe"])),
                    fmt_ci(float(row["ci_low"]), float(row["ci_high"])),
                ]
            )

    return render_table(headers, rows)


def render_setup_table(rows: list[dict[str, object]]) -> list[str]:
    headers = ["Entry", "N", "WR", "PF", "Avg", "Sharpe", "Wilson 95% CI"]
    table_rows = [
        [
            str(row["timing"]),
            f"{int(row['n']):,}",
            fmt_pct(float(row["win_rate"])),
            fmt_float(float(row["profit_factor"])),
            fmt_ticks(float(row["avg_ticks"])),
            fmt_float(float(row["sharpe"])),
            fmt_ci(float(row["ci_low"]), float(row["ci_high"])),
        ]
        for row in rows
    ]
    return render_table(headers, table_rows)


def render_leader_line(result: dict[str, object]) -> str:
    sharpe_leader = result["sharpe_leader"]
    avg_leader = result["avg_leader"]

    sharpe_text = (
        f"{sharpe_leader['timing']} (Sharpe {fmt_float(float(sharpe_leader['sharpe']))}, Avg {fmt_ticks(float(sharpe_leader['avg_ticks']))})"
        if sharpe_leader is not None
        else "n/a"
    )
    avg_text = (
        f"{avg_leader['timing']} (Avg {fmt_ticks(float(avg_leader['avg_ticks']))}, PF {fmt_float(float(avg_leader['profit_factor']))})"
        if avg_leader is not None
        else "n/a"
    )
    return f"- Sharpe leader: {sharpe_text}; Avg leader: {avg_text}."


def build_report(bar_frame: pd.DataFrame, absorption_frame: pd.DataFrame, rth_bars: pd.DataFrame, results: list[tuple[SetupSpec, dict[str, object]]]) -> str:
    lines = [
        "ROUND 31 ENTRY OPTIMIZATION",
        "===========================",
        "",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "",
        "Methodology:",
        "- Observation unit is global_index for bar setups and global_index + direction for the absorption setup.",
        "- 15m/60m context comes from nq_1yr_1m.csv resamples.",
        "- Entry and 5-bar exit prices are rebuilt from same-session RTH 1m closes only; no overnight carry is allowed.",
        "- T+0 enters on the signal-bar close; T+1/T+2 wait 1 or 2 bars; T+Best picks the best close in the first 3 bars (lowest for longs, highest for shorts).",
        "- T+Best is still scored from the chosen entry bar to the close 5 bars later, and equal best prices resolve to the earliest bar.",
        "- NOT killers = direction-aware 60m anchor not in the 40%-60% middle band AND bar_volume not > 3x prior 20-bar EMA.",
        "- NOT lunch excludes 12:00-13:59 ET.",
        "- Doji = body < 10% of full bar range.",
        "- Morning/evening star follows the round23 / round26 3-candle definition.",
        "- CVD divergence follows the round26 / round27 session-extreme versus prior-CVD-extreme definition.",
        "",
        f"Bar observations loaded:        {len(bar_frame):,}",
        f"Absorption observations loaded: {len(absorption_frame):,}",
        f"RTH 1m bars loaded:            {len(rth_bars):,}",
        f"Doji bars:                     {int(bar_frame['is_doji'].sum()):,}",
        f"CVD divergence bars:           {int(bar_frame['is_cvd_divergence'].sum()):,}",
        f"Morning/evening stars:         {int(bar_frame['star_direction_sign'].ne(0).sum()):,}",
        "",
        "All 20 setup x timing results (sorted by setup, then entry timing):",
    ]
    lines.extend(render_overview_table(results))
    lines.extend(["", "Per-setup leaders:"])

    for spec, result in results:
        lines.append(f"- {spec.code}. {spec.label}: {render_leader_line(result)[2:]}")

    for spec, result in results:
        lines.extend(
            [
                "",
                f"SETUP {spec.code}: {spec.label}",
                "-" * (9 + len(spec.code) + len(spec.label)),
                f"Observation unit: {spec.observation_unit}",
                f"Trade direction: {spec.direction_label}",
                f"Raw sample size before timing-specific drops: {int(result['sample_n']):,}",
                "",
            ]
        )
        lines.extend(render_setup_table(result["timing_rows"]))

        best_row = next((row for row in result["timing_rows"] if row["timing"] == "T+Best"), None)
        if best_row is not None and best_row["selection_counts"] is not None:
            counts = best_row["selection_counts"]
            lines.extend(
                [
                    "",
                    "T+Best entry-offset mix:",
                    f"- T+0 picks: {int(counts[0]):,} | T+1 picks: {int(counts[1]):,} | T+2 picks: {int(counts[2]):,}",
                ]
            )

        lines.extend(["", "Leader summary:", render_leader_line(result), ""])

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    bar_frame, absorption_frame, rth_bars = build_analysis_frames()
    datasets = {
        "bar": bar_frame,
        "absorption": absorption_frame,
    }

    results: list[tuple[SetupSpec, dict[str, object]]] = []
    for spec in build_setup_specs():
        results.append((spec, evaluate_setup(spec, datasets)))

    report = build_report(bar_frame, absorption_frame, rth_bars, results)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report, end="")
    print(f"Saved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
