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
OUT_PATH = OUT_DIR / "round43_position_sizing_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
PATH_WINDOW = 30
TICK_SIZE = 0.25
TICK_VALUE = 5.0
ROLLING_LOOKBACK = 20
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
FIRST_HOUR_MINUTES = 60
LUNCH_START_MINUTES = 150
LUNCH_END_MINUTES = 270

ACCOUNT_SIZE = 100_000.0
NQ_MARGIN = 16_500.0
BETA_PRIOR_ALPHA = 10.0
BETA_PRIOR_BETA = 10.0

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


def fmt_money(value: float) -> str:
    if pd.isna(value):
        return "nan"
    if np.isinf(value):
        return "inf"
    return f"${value:,.2f}"


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
    ]
    events = pd.read_csv(EVENTS_CSV, usecols=cols, dtype=dtypes, low_memory=False)

    numeric_cols = [
        "score_final",
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
    events = events[events["bar_ts"].notna()].copy()
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
    bars["session_size"] = bars.groupby("session_date", sort=False)["ts_event"].transform("size")
    bars[f"fwd_close_{PATH_WINDOW}b"] = bars.groupby("session_date", sort=False)["close"].shift(-PATH_WINDOW)
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


def build_bar_observations(events: pd.DataFrame) -> pd.DataFrame:
    observations = (
        events.groupby("global_index", as_index=False, sort=False)
        .agg(
            session_date=("session_date", "first"),
            bar_ts=("bar_ts", "first"),
            bar_index=("bar_index", "first"),
            global_index=("global_index", "first"),
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
            global_index=("global_index", "first"),
            bar_open=("bar_open", "first"),
            bar_high=("bar_high", "first"),
            bar_low=("bar_low", "first"),
            bar_close=("bar_close", "first"),
            bar_delta=("bar_delta", "first"),
            bar_volume=("bar_volume", "first"),
            absorption_signal_count=("signal_id", "nunique"),
        )
        .rename(columns={"event_direction_sign": "direction_sign"})
        .sort_values(["session_date", "bar_ts", "global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    return observations


def build_score_observations(events: pd.DataFrame) -> pd.DataFrame:
    scored = events.loc[events["event_direction_sign"].ne(0)].copy()
    observations = (
        scored.groupby(["global_index", "event_direction_sign"], as_index=False, sort=False)
        .agg(
            session_date=("session_date", "first"),
            bar_ts=("bar_ts", "first"),
            bar_index=("bar_index", "first"),
            global_index=("global_index", "first"),
            bar_open=("bar_open", "first"),
            bar_high=("bar_high", "first"),
            bar_low=("bar_low", "first"),
            bar_close=("bar_close", "first"),
            bar_delta=("bar_delta", "first"),
            bar_volume=("bar_volume", "first"),
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
            max_score_final=("score_final", "max"),
        )
        .rename(columns={"event_direction_sign": "direction_sign"})
        .sort_values(["session_date", "bar_ts", "global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    return observations


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


def attach_rth_context(observations: pd.DataFrame, rth_bars: pd.DataFrame) -> pd.DataFrame:
    merge_cols = ["ts_event", "session_size", f"fwd_close_{PATH_WINDOW}b"]
    context = rth_bars[merge_cols].rename(columns={"ts_event": "bar_ts"})
    return observations.merge(context, on="bar_ts", how="left", validate="many_to_one").reset_index(drop=True)


def add_time_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] * 60 + out["minute"]) - RTH_START_MINUTE
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(FIRST_HOUR_MINUTES)
    out["is_not_lunch"] = ~(
        out["minutes_since_930"].ge(LUNCH_START_MINUTES) & out["minutes_since_930"].lt(LUNCH_END_MINUTES)
    )
    out["is_first_hour"] = out["is_first_hour"].fillna(False).astype(bool)
    out["is_not_lunch"] = out["is_not_lunch"].fillna(False).astype(bool)
    return out


def compute_bar_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["body_high"] = out[["bar_open", "bar_close"]].max(axis=1)
    out["body_low"] = out[["bar_open", "bar_close"]].min(axis=1)
    out["body_mid"] = (out["bar_open"] + out["bar_close"]) / 2.0
    out["price_change"] = out["bar_close"] - out["bar_open"]
    out["price_color_sign"] = np.sign(out["price_change"].fillna(0.0)).astype(int)

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

    out["price_color_sign_1"] = by_session["price_color_sign"].shift(1)
    out["price_color_sign_2"] = by_session["price_color_sign"].shift(2)
    out["body_mid_2"] = by_session["body_mid"].shift(2)
    out["is_doji_1"] = by_session["is_doji"].shift(1).fillna(False).astype(bool)
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

    out["cvd"] = by_session["bar_delta"].cumsum()
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

    bool_cols = [
        "is_first_hour",
        "is_not_lunch",
        "is_doji",
        "is_three_narrowing_ranges",
        "is_volume_spike_3x",
        "is_engulfing",
        "is_bullish_engulf",
        "is_bearish_engulf",
        "is_morning_star",
        "is_evening_star",
        "is_bearish_cvd_divergence",
        "is_bullish_cvd_divergence",
        "is_cvd_divergence",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def build_shared_bar_context(bar_frame: pd.DataFrame) -> pd.DataFrame:
    return bar_frame[["bar_ts", "is_first_hour", "is_not_lunch", "is_volume_spike_3x"]].copy()


def merge_shared_bar_context(df: pd.DataFrame, shared_bar_context: pd.DataFrame) -> pd.DataFrame:
    out = df.merge(shared_bar_context, on="bar_ts", how="left", validate="many_to_one")
    for col in ["is_first_hour", "is_not_lunch", "is_volume_spike_3x"]:
        out[col] = out[col].fillna(False).astype(bool)
    return out.reset_index(drop=True)


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
            code="2",
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
            code="3",
            label="CVD divergence + 60m + 15m",
            dataset_key="bar",
            observation_unit="global_index (unique signal bar)",
            direction_label="trade direction = divergence_sign",
            predicate=lambda df: df["is_cvd_divergence"] & has_core_60m_15m_gate_for(df, df["divergence_sign"]),
            direction_fn=lambda df: df["divergence_sign"],
        ),
        SetupSpec(
            code="4",
            label="absorption + 60m + 15m + NOT lunch",
            dataset_key="absorption",
            observation_unit="global_index + direction (unique absorption observation)",
            direction_label="trade direction = signal direction",
            predicate=lambda df: df["direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & df["is_not_lunch"],
            direction_fn=lambda df: df["direction_sign"],
        ),
        SetupSpec(
            code="5",
            label="score >= 60 + 60m + 15m + first_hour + NOT killers",
            dataset_key="score",
            observation_unit="global_index + direction (unique scored observation)",
            direction_label="trade direction = signal direction",
            predicate=lambda df: df["direction_sign"].ne(0)
            & df["max_score_final"].ge(60)
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & passes_not_all_killers_for(df, df["direction_sign"])
            & df["is_first_hour"],
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


def build_analysis_frames() -> dict[str, pd.DataFrame]:
    events = load_events()
    bars_1m = load_ohlcv()
    rth_bars = prepare_rth_bars(bars_1m)
    context = build_timeframe_context(bars_1m)

    bar_frame = build_bar_observations(events)
    bar_frame = attach_timeframe_context(bar_frame, context)
    bar_frame = attach_rth_context(bar_frame, rth_bars)
    bar_frame = add_time_flags(bar_frame)
    bar_frame = compute_bar_features(bar_frame)

    shared_bar_context = build_shared_bar_context(bar_frame)

    absorption_frame = build_absorption_observations(events)
    absorption_frame = attach_timeframe_context(absorption_frame, context)
    absorption_frame = attach_rth_context(absorption_frame, rth_bars)
    absorption_frame = merge_shared_bar_context(absorption_frame, shared_bar_context)

    score_frame = build_score_observations(events)
    score_frame = attach_timeframe_context(score_frame, context)
    score_frame = attach_rth_context(score_frame, rth_bars)
    score_frame = merge_shared_bar_context(score_frame, shared_bar_context)

    return {
        "bar": bar_frame,
        "absorption": absorption_frame,
        "score": score_frame,
    }


def kelly_fraction(win_rate: float, reward_risk: float) -> float:
    if pd.isna(win_rate) or pd.isna(reward_risk) or reward_risk <= 0:
        return np.nan
    if np.isinf(reward_risk):
        return float(win_rate)
    return float((win_rate * reward_risk - (1.0 - win_rate)) / reward_risk)


def clip_fraction(fraction: float) -> float:
    if pd.isna(fraction):
        return np.nan
    return float(min(max(fraction, 0.0), 1.0))


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


def build_setup_sample(source_df: pd.DataFrame, spec: SetupSpec) -> pd.DataFrame:
    mask = spec.predicate(source_df).fillna(False)
    sample = source_df.loc[mask].copy()
    sample["trade_sign"] = normalize_direction(spec.direction_fn(source_df), sample)
    sample = sample.loc[sample["trade_sign"].ne(0)].copy()
    sample = sample.loc[sample[f"fwd_close_{PATH_WINDOW}b"].notna()].copy()
    sample["ret_ticks"] = sample["trade_sign"] * ((sample[f"fwd_close_{PATH_WINDOW}b"] - sample["bar_close"]) / TICK_SIZE)
    return sample.reset_index(drop=True)


def build_sizing_row(name: str, fraction: float, ev_per_contract_dollars: float) -> dict[str, float | int | str]:
    clipped = clip_fraction(fraction)
    if pd.isna(clipped):
        return {
            "name": name,
            "fraction": fraction,
            "clipped_fraction": clipped,
            "continuous_contracts": np.nan,
            "whole_contracts": 0,
            "expected_trade_dollars": np.nan,
        }

    continuous_contracts = (ACCOUNT_SIZE * clipped) / NQ_MARGIN
    whole_contracts = int(np.floor(continuous_contracts + 1e-12))
    return {
        "name": name,
        "fraction": fraction,
        "clipped_fraction": clipped,
        "continuous_contracts": float(continuous_contracts),
        "whole_contracts": whole_contracts,
        "expected_trade_dollars": float(ev_per_contract_dollars * continuous_contracts),
    }


def summarize_setup(spec: SetupSpec, frames: dict[str, pd.DataFrame]) -> dict[str, object]:
    sample = build_setup_sample(frames[spec.dataset_key], spec)
    returns = sample["ret_ticks"].dropna()
    n = int(len(returns))
    wins = int((returns > 0).sum())
    non_wins = int((returns <= 0).sum())
    win_rate = float(wins / n) if n else np.nan
    bayes_wr = float((wins + BETA_PRIOR_ALPHA) / (n + BETA_PRIOR_ALPHA + BETA_PRIOR_BETA)) if n else 0.5

    win_returns = returns.loc[returns > 0]
    non_win_returns = returns.loc[returns <= 0]
    avg_win_ticks = float(win_returns.mean()) if not win_returns.empty else np.nan
    avg_loss_ticks = float(abs(non_win_returns.mean())) if not non_win_returns.empty else 0.0
    reward_risk = float(avg_win_ticks / avg_loss_ticks) if avg_loss_ticks > 0 and not pd.isna(avg_win_ticks) else float("inf") if not pd.isna(avg_win_ticks) else np.nan

    full_kelly = kelly_fraction(win_rate, reward_risk)
    half_kelly = full_kelly / 2.0 if not pd.isna(full_kelly) else np.nan
    quarter_kelly = full_kelly / 4.0 if not pd.isna(full_kelly) else np.nan
    bayes_kelly = kelly_fraction(bayes_wr, reward_risk)

    ev_ticks = float(returns.mean()) if n else np.nan
    ev_dollars = ev_ticks * TICK_VALUE if not pd.isna(ev_ticks) else np.nan
    bayes_ev_ticks = (bayes_wr * avg_win_ticks) - ((1.0 - bayes_wr) * avg_loss_ticks) if not pd.isna(avg_win_ticks) else np.nan
    bayes_ev_dollars = bayes_ev_ticks * TICK_VALUE if not pd.isna(bayes_ev_ticks) else np.nan

    sizing_rows = [
        build_sizing_row("Full Kelly", full_kelly, ev_dollars),
        build_sizing_row("Half Kelly", half_kelly, ev_dollars),
        build_sizing_row("Quarter Kelly", quarter_kelly, ev_dollars),
        build_sizing_row("Bayes Kelly", bayes_kelly, bayes_ev_dollars),
    ]

    return {
        "setup": spec,
        "n": n,
        "wins": wins,
        "non_wins": non_wins,
        "win_rate": win_rate,
        "bayes_wr": bayes_wr,
        "avg_win_ticks": avg_win_ticks,
        "avg_loss_ticks": avg_loss_ticks,
        "reward_risk": reward_risk,
        "full_kelly": full_kelly,
        "half_kelly": half_kelly,
        "quarter_kelly": quarter_kelly,
        "bayes_kelly": bayes_kelly,
        "ev_ticks": ev_ticks,
        "ev_dollars": ev_dollars,
        "bayes_ev_ticks": bayes_ev_ticks,
        "bayes_ev_dollars": bayes_ev_dollars,
        "sizing_rows": sizing_rows,
    }


def render_summary_table(results: list[dict[str, object]]) -> list[str]:
    headers = [
        "Setup",
        "WR",
        "Avg Win",
        "Avg Loss",
        "R:R",
        "Full Kelly",
        "Half Kelly",
        "Quarter Kelly",
        "Bayes Kelly",
        "Max Contracts/$100K",
    ]
    rows: list[list[str]] = []

    for row in results:
        sizing_rows = {entry["name"]: entry for entry in row["sizing_rows"]}
        max_contracts = "/".join(
            str(sizing_rows[name]["whole_contracts"])
            for name in ["Full Kelly", "Half Kelly", "Quarter Kelly", "Bayes Kelly"]
        )
        rows.append(
            [
                f"{row['setup'].code}. {row['setup'].label}",
                fmt_pct(float(row["win_rate"])),
                fmt_ticks(float(row["avg_win_ticks"])),
                fmt_ticks(-float(row["avg_loss_ticks"])) if not pd.isna(row["avg_loss_ticks"]) else "nan",
                fmt_float(float(row["reward_risk"])),
                fmt_pct(float(row["full_kelly"])),
                fmt_pct(float(row["half_kelly"])),
                fmt_pct(float(row["quarter_kelly"])),
                fmt_pct(float(row["bayes_kelly"])),
                max_contracts,
            ]
        )

    return render_table(headers, rows)


def render_sizing_table(sizing_rows: list[dict[str, float | int | str]]) -> list[str]:
    headers = ["Fraction", "Raw Kelly", "Kelly Used", "Exp $/Trade", "Cont. Contracts", "Max Whole Contracts"]
    rows: list[list[str]] = []
    for row in sizing_rows:
        rows.append(
            [
                str(row["name"]),
                fmt_pct(float(row["fraction"])),
                fmt_pct(float(row["clipped_fraction"])),
                fmt_money(float(row["expected_trade_dollars"])),
                fmt_float(float(row["continuous_contracts"])),
                str(int(row["whole_contracts"])),
            ]
        )
    return render_table(headers, rows)


def render_setup_section(result: dict[str, object]) -> list[str]:
    spec = result["setup"]
    lines = [
        f"SETUP {spec.code}: {spec.label}",
        "-" * (len(spec.label) + len(spec.code) + 8),
        f"Observation unit: {spec.observation_unit}",
        f"Trade direction: {spec.direction_label}",
        f"Complete {PATH_WINDOW}b sample: {int(result['n']):,} trades",
        f"Observed WR: {fmt_pct(float(result['win_rate']))} ({int(result['wins']):,} wins / {int(result['non_wins']):,} non-wins)",
        f"Posterior WR (Beta(10,10)): {fmt_pct(float(result['bayes_wr']))}",
        f"Avg win: {fmt_ticks(float(result['avg_win_ticks']))}",
        f"Avg loss (non-wins): {fmt_ticks(-float(result['avg_loss_ticks'])) if not pd.isna(result['avg_loss_ticks']) else 'nan'}",
        f"Reward:risk: {fmt_float(float(result['reward_risk']))}",
        f"Observed EV/contract: {fmt_ticks(float(result['ev_ticks']))} = {fmt_money(float(result['ev_dollars']))}",
        f"Bayes EV/contract: {fmt_ticks(float(result['bayes_ev_ticks']))} = {fmt_money(float(result['bayes_ev_dollars']))}",
        "",
        *render_sizing_table(result["sizing_rows"]),
    ]
    return lines


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    frames = build_analysis_frames()
    results = [summarize_setup(spec, frames) for spec in build_setup_specs()]

    lines = [
        "DEEP6 round43 Kelly position sizing report",
        "========================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        f"Trade exit assumption: fixed {PATH_WINDOW}-bar time exit using same-session RTH forward closes.",
        "Kelly formula: f = (WR * R - (1 - WR)) / R, where R = avg_win / avg_loss.",
        f"Bayesian WR prior: Beta({int(BETA_PRIOR_ALPHA)}, {int(BETA_PRIOR_BETA)}).",
        f"NQ tick value: {fmt_money(TICK_VALUE)} per tick. Margin assumption: {fmt_money(NQ_MARGIN)} per contract on a {fmt_money(ACCOUNT_SIZE)} account.",
        "Contracts column is Full/Half/Quarter/Bayes whole-contract caps; Kelly fractions are clipped to [0%, 100%] for sizing.",
        "",
        *render_summary_table(results),
    ]

    for result in results:
        lines.extend(["", *render_setup_section(result)])

    report = "\n".join(lines) + "\n"
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
