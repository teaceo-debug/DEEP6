#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data/backtests/signal_events.csv"
OHLCV_CSV = ROOT / "data/backtests/nq_1yr_1m.csv"
OUT_DIR = ROOT / "data/backtests/analysis"
OUT_PATH = OUT_DIR / "round41_edge_decay_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
REPORT_WINDOWS = (1, 2, 3, 5, 10, 15, 20, 25, 30)
RECON_WINDOWS = (3, 20, 25)
ROLLING_LOOKBACK = 20
FIRST_HOUR_MINUTES = 60
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
TICK_SIZE = 0.25

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


def normalize_direction(direction: int | pd.Series, df: pd.DataFrame) -> pd.Series:
    if isinstance(direction, pd.Series):
        series = direction.reindex(df.index)
    else:
        series = pd.Series(direction, index=df.index)
    series = pd.to_numeric(series, errors="coerce").fillna(0.0)
    return pd.Series(np.sign(series), index=df.index).astype(int)


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
        "score_final",
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_delta",
        "bar_volume",
        "fwd_close_1b",
        "fwd_close_2b",
        "fwd_close_5b",
        "fwd_close_10b",
        "fwd_close_15b",
        "fwd_close_30b",
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
        "fwd_close_1b",
        "fwd_close_2b",
        "fwd_close_5b",
        "fwd_close_10b",
        "fwd_close_15b",
        "fwd_close_30b",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["bar_ts"] = pd.to_datetime(df["bar_ts"], utc=True, errors="coerce").dt.tz_convert(EASTERN)
    df["direction_sign"] = direction_to_sign(df["direction"])
    df = df[df["bar_ts"].notna()].copy()
    return df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)


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
    bars = bars.loc[(minute_of_day >= RTH_START_MINUTE) & (minute_of_day < RTH_END_MINUTE)].copy()
    bars["session_date"] = bars["ts_event"].dt.strftime("%Y-%m-%d")
    bars["bar_index"] = bars.groupby("session_date", sort=False).cumcount().astype("int32")
    bars["session_size"] = bars.groupby("session_date", sort=False)["ts_event"].transform("size")

    by_session = bars.groupby("session_date", sort=False)
    for window in RECON_WINDOWS:
        bars[f"fwd_close_{window}b"] = by_session["close"].shift(-window)

    return bars.reset_index(drop=True)


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


def attach_timeframe_context(df: pd.DataFrame, context: dict[int, pd.DataFrame]) -> pd.DataFrame:
    out = df.copy()
    for tf, ctx in context.items():
        bucket_col = f"bucket_{tf}m"
        out[bucket_col] = out["bar_ts"].dt.floor(f"{tf}min")
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
        out = out.merge(renamed, on=bucket_col, how="left", validate="many_to_one")

    for col in ["bar_open", "bar_high", "bar_low", "bar_close", "bar_delta", "bar_volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.reset_index(drop=True)


def attach_reconstructed_forwards(df: pd.DataFrame, rth_bars: pd.DataFrame) -> pd.DataFrame:
    lookup = rth_bars[
        ["ts_event", "session_size"] + [f"fwd_close_{window}b" for window in RECON_WINDOWS]
    ].rename(columns={"ts_event": "bar_ts"})
    out = df.merge(lookup, on="bar_ts", how="left", validate="many_to_one")
    return out.reset_index(drop=True)


def add_time_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] * 60 + out["minute"]) - RTH_START_MINUTE
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(FIRST_HOUR_MINUTES)
    out["is_first_hour"] = out["is_first_hour"].fillna(False).astype(bool)
    return out


def build_bar_frame(events: pd.DataFrame) -> pd.DataFrame:
    bars = (
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
                "fwd_close_1b",
                "fwd_close_2b",
                "fwd_close_5b",
                "fwd_close_10b",
                "fwd_close_15b",
                "fwd_close_30b",
            ],
        ]
        .copy()
        .reset_index(drop=True)
    )
    bars["direction_sign"] = np.sign(bars["bar_delta"].fillna(0.0)).astype(int)
    return bars


def build_signal_observations(events: pd.DataFrame) -> pd.DataFrame:
    working = events[events["direction_sign"].ne(0)].copy()
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
            bar_delta=("bar_delta", "first"),
            bar_volume=("bar_volume", "first"),
            fwd_close_1b=("fwd_close_1b", "first"),
            fwd_close_2b=("fwd_close_2b", "first"),
            fwd_close_5b=("fwd_close_5b", "first"),
            fwd_close_10b=("fwd_close_10b", "first"),
            fwd_close_15b=("fwd_close_15b", "first"),
            fwd_close_30b=("fwd_close_30b", "first"),
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
            max_score_final=("score_final", "max"),
        )
        .sort_values(["global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    return observations


def build_absorption_observations(events: pd.DataFrame) -> pd.DataFrame:
    working = events[events["category"].eq("absorption") & events["direction_sign"].ne(0)].copy()
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
            bar_delta=("bar_delta", "first"),
            bar_volume=("bar_volume", "first"),
            fwd_close_1b=("fwd_close_1b", "first"),
            fwd_close_2b=("fwd_close_2b", "first"),
            fwd_close_5b=("fwd_close_5b", "first"),
            fwd_close_10b=("fwd_close_10b", "first"),
            fwd_close_15b=("fwd_close_15b", "first"),
            fwd_close_30b=("fwd_close_30b", "first"),
            absorption_signal_count=("signal_id", "nunique"),
        )
        .sort_values(["global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    return observations


def compute_bar_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["body_high"] = out[["bar_open", "bar_close"]].max(axis=1)
    out["body_low"] = out[["bar_open", "bar_close"]].min(axis=1)

    out["is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.10 * out["bar_range"])

    out["prior_bar_range"] = by_session["bar_range"].shift(1)
    out["bar_range_2"] = by_session["bar_range"].shift(2)
    out["is_three_narrowing_ranges"] = (
        out["bar_range_2"].notna()
        & out["prior_bar_range"].lt(out["bar_range_2"])
        & out["bar_range"].lt(out["prior_bar_range"])
    )

    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])

    out["prior_body_high"] = by_session["body_high"].shift(1)
    out["prior_body_low"] = by_session["body_low"].shift(1)
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

    bool_cols = [
        "is_first_hour",
        "is_doji",
        "is_three_narrowing_ranges",
        "is_volume_spike_3x",
        "is_engulfing",
        "is_bullish_engulf",
        "is_bearish_engulf",
        "is_bearish_cvd_divergence",
        "is_bullish_cvd_divergence",
        "is_cvd_divergence",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def build_shared_bar_context(bar_frame: pd.DataFrame) -> pd.DataFrame:
    return bar_frame[
        ["bar_ts", "session_size", "fwd_close_3b", "fwd_close_20b", "fwd_close_25b", "is_first_hour", "is_volume_spike_3x"]
    ].copy()


def merge_shared_bar_context(df: pd.DataFrame, shared_bar_context: pd.DataFrame) -> pd.DataFrame:
    out = df.merge(shared_bar_context, on="bar_ts", how="left", validate="many_to_one")
    for col in ["is_first_hour", "is_volume_spike_3x"]:
        out[col] = out[col].fillna(False).astype(bool)
    return out.reset_index(drop=True)


def anchor_pos_60m(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    rng_60m = df["range_60m"].replace(0, np.nan)
    anchor = np.where(direction_sign > 0, df["bar_low"], np.where(direction_sign < 0, df["bar_high"], np.nan))
    return pd.Series((anchor - df["low_60m"]) / rng_60m, index=df.index)


def has_core_60m_15m_gate_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    pos_60m = anchor_pos_60m(df, direction_sign)
    is_60m_extreme = ((direction_sign > 0) & pos_60m.le(0.20)) | ((direction_sign < 0) & pos_60m.ge(0.80))
    is_15m_trend_aligned = direction_sign.ne(0) & direction_sign.eq(df["trend_sign_15m"])
    return is_60m_extreme & is_15m_trend_aligned


def passes_not_all_killers_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    pos_60m = anchor_pos_60m(df, direction_sign)
    not_middle_60m = ~pos_60m.between(0.40, 0.60, inclusive="both")
    return direction_sign.ne(0) & not_middle_60m & (~df["is_volume_spike_3x"])


def build_setup_specs() -> list[SetupSpec]:
    return [
        SetupSpec(
            code="1",
            label="60m + 15m (base)",
            dataset_key="signal",
            observation_unit="global_index + direction (unique signal observation)",
            direction_label="trade direction = signal direction",
            predicate=lambda df: has_core_60m_15m_gate_for(df, df["direction_sign"]),
            direction_fn=lambda df: df["direction_sign"],
        ),
        SetupSpec(
            code="2",
            label="60m + 15m + NOT killers + first_hour",
            dataset_key="signal",
            observation_unit="global_index + direction (unique signal observation)",
            direction_label="trade direction = signal direction",
            predicate=lambda df: has_core_60m_15m_gate_for(df, df["direction_sign"])
            & passes_not_all_killers_for(df, df["direction_sign"])
            & df["is_first_hour"],
            direction_fn=lambda df: df["direction_sign"],
        ),
        SetupSpec(
            code="3",
            label="Doji + 60m + 15m",
            dataset_key="bar",
            observation_unit="global_index (unique signal bar)",
            direction_label="trade direction = sign(bar_delta)",
            predicate=lambda df: df["is_doji"]
            & df["direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            direction_fn=lambda df: df["direction_sign"],
        ),
        SetupSpec(
            code="4",
            label="CVD divergence + 60m + 15m",
            dataset_key="bar",
            observation_unit="global_index (unique signal bar)",
            direction_label="trade direction = divergence_sign",
            predicate=lambda df: df["is_cvd_divergence"] & has_core_60m_15m_gate_for(df, df["divergence_sign"]),
            direction_fn=lambda df: df["divergence_sign"],
        ),
        SetupSpec(
            code="5",
            label="absorption + 60m + 15m",
            dataset_key="absorption",
            observation_unit="global_index + direction (unique absorption observation)",
            direction_label="trade direction = signal direction",
            predicate=lambda df: has_core_60m_15m_gate_for(df, df["direction_sign"]),
            direction_fn=lambda df: df["direction_sign"],
        ),
        SetupSpec(
            code="6",
            label="3 narrowing ranges + 60m + 15m",
            dataset_key="bar",
            observation_unit="global_index (unique signal bar)",
            direction_label="trade direction = sign(bar_delta)",
            predicate=lambda df: df["is_three_narrowing_ranges"]
            & df["direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            direction_fn=lambda df: df["direction_sign"],
        ),
        SetupSpec(
            code="7",
            label="Engulfing + 60m + 15m",
            dataset_key="bar",
            observation_unit="global_index (unique signal bar)",
            direction_label="trade direction = engulf_direction_sign",
            predicate=lambda df: df["engulf_direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["engulf_direction_sign"]),
            direction_fn=lambda df: df["engulf_direction_sign"],
        ),
        SetupSpec(
            code="8",
            label="score >= 60 + 60m + 15m + first_hour",
            dataset_key="signal",
            observation_unit="global_index + direction (unique signal observation)",
            direction_label="trade direction = signal direction",
            predicate=lambda df: df["max_score_final"].ge(60)
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & df["is_first_hour"],
            direction_fn=lambda df: df["direction_sign"],
        ),
    ]


def build_analysis_frames() -> dict[str, pd.DataFrame]:
    events = load_events()
    bars_1m = load_ohlcv()
    rth_bars = prepare_rth_bars(bars_1m)
    context = build_timeframe_context(bars_1m)

    bar_frame = build_bar_frame(events)
    bar_frame = attach_timeframe_context(bar_frame, context)
    bar_frame = attach_reconstructed_forwards(bar_frame, rth_bars)
    bar_frame = add_time_flags(bar_frame)
    bar_frame = compute_bar_features(bar_frame)

    shared_bar_context = build_shared_bar_context(bar_frame)

    signal_frame = build_signal_observations(events)
    signal_frame = attach_timeframe_context(signal_frame, context)
    signal_frame = merge_shared_bar_context(signal_frame, shared_bar_context)

    absorption_frame = build_absorption_observations(events)
    absorption_frame = attach_timeframe_context(absorption_frame, context)
    absorption_frame = merge_shared_bar_context(absorption_frame, shared_bar_context)

    return {
        "bar": bar_frame,
        "signal": signal_frame,
        "absorption": absorption_frame,
    }


def build_setup_sample(source_df: pd.DataFrame, spec: SetupSpec) -> pd.DataFrame:
    mask = spec.predicate(source_df).fillna(False)
    sample = source_df.loc[mask].copy()

    direction = spec.direction_fn(source_df)
    sample["trade_sign"] = normalize_direction(direction, sample)
    sample = sample.loc[sample["trade_sign"].ne(0)].copy()
    return sample.reset_index(drop=True)


def compute_window_metrics(sample: pd.DataFrame, window: int) -> dict[str, float | int]:
    trade_sign = pd.to_numeric(sample["trade_sign"], errors="coerce")
    bar_close = pd.to_numeric(sample["bar_close"], errors="coerce")
    fwd_close = pd.to_numeric(sample[f"fwd_close_{window}b"], errors="coerce")
    bar_index = pd.to_numeric(sample["bar_index"], errors="coerce")
    session_size = pd.to_numeric(sample["session_size"], errors="coerce")

    valid = (
        trade_sign.notna()
        & trade_sign.ne(0)
        & bar_close.notna()
        & fwd_close.notna()
        & bar_index.notna()
        & session_size.notna()
        & bar_index.add(window).lt(session_size)
    )

    returns = trade_sign[valid] * ((fwd_close[valid] - bar_close[valid]) / TICK_SIZE)
    n = int(len(returns))
    return {
        "window": window,
        "n": n,
        "win_rate": float((returns > 0).mean()) if n else np.nan,
        "profit_factor": profit_factor(returns) if n else np.nan,
        "avg_ticks": float(returns.mean()) if n else np.nan,
        "sharpe": sharpe_ratio(returns) if n else np.nan,
    }


def choose_peak_window(metrics: dict[int, dict[str, float | int]]) -> tuple[int | None, float]:
    candidates = [row for row in metrics.values() if int(row["n"]) > 0 and not pd.isna(row["win_rate"])]
    if not candidates:
        return None, float("nan")
    best = max(
        candidates,
        key=lambda row: (
            float(row["win_rate"]),
            float(row["avg_ticks"]),
            float(row["profit_factor"]),
            -int(row["window"]),
        ),
    )
    return int(best["window"]), float(best["win_rate"])


def find_decay_window(metrics: dict[int, dict[str, float | int]], peak_window: int | None, peak_wr: float) -> int | None:
    if peak_window is None or pd.isna(peak_wr):
        return None
    if peak_wr < 0.55:
        return peak_window
    for window in REPORT_WINDOWS:
        if window <= peak_window:
            continue
        row = metrics[window]
        if int(row["n"]) > 0 and not pd.isna(row["win_rate"]) and float(row["win_rate"]) < 0.55:
            return window
    return None


def find_half_life_window(metrics: dict[int, dict[str, float | int]], peak_window: int | None, peak_wr: float) -> tuple[int | None, float]:
    if peak_window is None or pd.isna(peak_wr):
        return None, float("nan")
    edge_over_random = peak_wr - 0.50
    if edge_over_random <= 0:
        return None, float("nan")
    threshold = 0.50 + (edge_over_random / 2.0)
    for window in REPORT_WINDOWS:
        if window <= peak_window:
            continue
        row = metrics[window]
        if int(row["n"]) > 0 and not pd.isna(row["win_rate"]) and float(row["win_rate"]) <= threshold:
            return window, threshold
    return None, threshold


def summarize_setup(spec: SetupSpec, frames: dict[str, pd.DataFrame]) -> dict[str, object]:
    sample = build_setup_sample(frames[spec.dataset_key], spec)
    metrics = {window: compute_window_metrics(sample, window) for window in REPORT_WINDOWS}
    peak_window, peak_wr = choose_peak_window(metrics)
    decay_window = find_decay_window(metrics, peak_window, peak_wr)
    half_life_window, half_life_threshold = find_half_life_window(metrics, peak_window, peak_wr)

    return {
        "setup": spec,
        "sample_n": int(len(sample)),
        "metrics": metrics,
        "peak_window": peak_window,
        "peak_wr": peak_wr,
        "decay_window": decay_window,
        "half_life_window": half_life_window,
        "half_life_threshold": half_life_threshold,
    }


def run_analysis(frames: dict[str, pd.DataFrame]) -> list[dict[str, object]]:
    return [summarize_setup(spec, frames) for spec in build_setup_specs()]


def metric_triplet_cell(metrics: dict[str, float | int]) -> str:
    if int(metrics["n"]) == 0:
        return "n/a"
    return f"{fmt_pct(float(metrics['win_rate']))}/{fmt_float(float(metrics['profit_factor']))}/{fmt_ticks(float(metrics['avg_ticks']))}"


def peak_text(row: dict[str, object]) -> str:
    peak_window = row["peak_window"]
    peak_wr = float(row["peak_wr"])
    if peak_window is None or pd.isna(peak_wr):
        return "n/a"
    return f"{int(peak_window)}b@{fmt_pct(peak_wr)}"


def decay_text(row: dict[str, object]) -> str:
    if row["peak_window"] is None:
        return "n/a"
    if row["decay_window"] is None:
        return ">30b"
    return f"{int(row['decay_window'])}b"


def half_life_text(row: dict[str, object]) -> str:
    if row["peak_window"] is None:
        return "n/a"
    threshold = float(row["half_life_threshold"])
    if pd.isna(threshold):
        return "n/a"
    if row["half_life_window"] is None:
        return ">30b"
    return f"{int(row['half_life_window'])}b"


def render_overview_table(results: list[dict[str, object]]) -> list[str]:
    headers = ["Setup", "1b", "2b", "3b", "5b", "10b", "15b", "20b", "25b", "30b", "Peak", "Decay", "Half-life"]
    rows: list[list[str]] = []

    for row in results:
        metrics = row["metrics"]
        rows.append(
            [
                row["setup"].label,
                metric_triplet_cell(metrics[1]),
                metric_triplet_cell(metrics[2]),
                metric_triplet_cell(metrics[3]),
                metric_triplet_cell(metrics[5]),
                metric_triplet_cell(metrics[10]),
                metric_triplet_cell(metrics[15]),
                metric_triplet_cell(metrics[20]),
                metric_triplet_cell(metrics[25]),
                metric_triplet_cell(metrics[30]),
                peak_text(row),
                decay_text(row),
                half_life_text(row),
            ]
        )
    return render_table(headers, rows)


def render_detail_table(row: dict[str, object]) -> list[str]:
    headers = ["Window", "N", "WR", "PF", "Avg Ticks", "Sharpe"]
    table_rows: list[list[str]] = []
    for window in REPORT_WINDOWS:
        metrics = row["metrics"][window]
        table_rows.append(
            [
                f"{window}b",
                f"{int(metrics['n']):,}",
                fmt_pct(float(metrics["win_rate"])),
                fmt_float(float(metrics["profit_factor"])),
                fmt_ticks(float(metrics["avg_ticks"])),
                fmt_float(float(metrics["sharpe"])),
            ]
        )
    return render_table(headers, table_rows)


def build_report(frames: dict[str, pd.DataFrame], results: list[dict[str, object]]) -> str:
    lines = [
        "ROUND 41 EDGE DECAY ANALYSIS",
        "============================",
        "",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "",
        "Methodology:",
        "- Base and score setups use signal observations grouped by global_index + direction.",
        "- Doji, CVD divergence, 3 narrowing ranges, and engulfing use unique signal bars grouped by global_index.",
        "- Absorption uses absorption-only observations grouped by global_index + direction.",
        "- 15m/60m context comes from nq_1yr_1m.csv resamples.",
        "- Existing 1/2/5/10/15/30-bar closes come from signal_events.csv.",
        "- 3/20/25-bar closes are reconstructed from same-session RTH 1m closes via bar_ts merge.",
        "- NOT killers = direction-aware 60m anchor not in the 40%-60% middle band AND bar_volume not > 3x prior 20-bar EMA.",
        "- Peak = highest win-rate window; ties break by higher Avg ticks, then higher PF, then earlier window.",
        "- Decay = first post-peak tested window with WR < 55%.",
        "- Half-life = first post-peak tested window with WR <= 50% + (peak_WR - 50%) / 2.",
        "",
        f"Unique signal bars loaded:      {len(frames['bar']):,}",
        f"Signal observations loaded:     {len(frames['signal']):,}",
        f"Absorption observations loaded: {len(frames['absorption']):,}",
        f"Doji bars:                      {int(frames['bar']['is_doji'].sum()):,}",
        f"CVD divergence bars:            {int(frames['bar']['is_cvd_divergence'].sum()):,}",
        f"3 narrowing-range bars:         {int(frames['bar']['is_three_narrowing_ranges'].sum()):,}",
        f"Engulfing bars:                 {int(frames['bar']['engulf_direction_sign'].ne(0).sum()):,}",
        "",
        "OVERVIEW",
        "--------",
        "Window cell format: WR/PF/AvgTicks",
        "",
    ]
    lines.extend(render_overview_table(results))
    lines.extend(["", "DETAILED METRICS", "----------------"])

    for row in results:
        spec = row["setup"]
        peak_window = row["peak_window"]
        peak_wr = float(row["peak_wr"])
        decay_window = row["decay_window"]
        half_life_window = row["half_life_window"]
        half_life_threshold = float(row["half_life_threshold"])

        if peak_window is None or pd.isna(peak_wr):
            peak_line = "Peak window: n/a"
        else:
            peak_metrics = row["metrics"][peak_window]
            peak_line = (
                f"Peak window: {int(peak_window)}b at {fmt_pct(peak_wr)} "
                f"(PF {fmt_float(float(peak_metrics['profit_factor']))}, Avg {fmt_ticks(float(peak_metrics['avg_ticks']))}, Sharpe {fmt_float(float(peak_metrics['sharpe']))})"
            )

        if decay_window is None:
            decay_line = "Decay point: >30b (WR stayed >= 55% after the peak window)"
        else:
            decay_metrics = row["metrics"][decay_window]
            decay_line = f"Decay point: {int(decay_window)}b at {fmt_pct(float(decay_metrics['win_rate']))}"

        if pd.isna(half_life_threshold):
            half_life_line = "Half-life: n/a (peak WR did not exceed 50%)"
        elif half_life_window is None:
            half_life_line = f"Half-life: >30b (threshold {fmt_pct(half_life_threshold)})"
        else:
            half_life_metrics = row["metrics"][half_life_window]
            half_life_line = (
                f"Half-life: {int(half_life_window)}b at {fmt_pct(float(half_life_metrics['win_rate']))} "
                f"(threshold {fmt_pct(half_life_threshold)})"
            )

        lines.extend(
            [
                "",
                f"SETUP {spec.code}: {spec.label}",
                "-" * (9 + len(spec.code) + len(spec.label)),
                f"Observation unit: {spec.observation_unit}",
                f"Trade direction: {spec.direction_label}",
                f"Raw sample size before window-specific drops: {int(row['sample_n']):,}",
                peak_line,
                decay_line,
                half_life_line,
                "",
            ]
        )
        lines.extend(render_detail_table(row))

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    frames = build_analysis_frames()
    results = run_analysis(frames)
    report = build_report(frames, results)

    OUT_PATH.write_text(report, encoding="utf-8")
    print(report, end="")
    print(f"Saved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
